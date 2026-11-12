"""Turning a score SMS into a recorded result and a reply.

Used by the Twilio webhook, and by `snooker sms parse` as a dry run, so both behave identically.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional

from .errors import AmbiguousPlayersError, MatchAlreadyCompleted, UnknownPlayersError
from .league import Change, League
from .models import InferredMatch, SnookerMatch, SnookerPlayer
from .settings import get_messages
from .verification import resolve_match


@dataclass
class SmsResult:
    reply: str = ""
    players: Optional[tuple[SnookerPlayer, SnookerPlayer]] = None
    inferred: Optional[InferredMatch] = None
    match: Optional[SnookerMatch] = None
    changes: list[Change] = field(default_factory=list)
    error: Optional[Exception] = None
    timings: dict[str, float] = field(default_factory=dict)  # seconds per stage

    @contextmanager
    def timed(self, stage: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.timings[stage] = round(time.perf_counter() - start, 3)

    def to_dict(self) -> dict:
        return {
            "reply": self.reply,
            "players": [p.name for p in self.players] if self.players else None,
            "inferred": self.inferred.model_dump() if self.inferred else None,
            "match": self.match.model_dump() if self.match else None,
            "changes": [c.to_dict() for c in self.changes],
            "error": {"type": type(self.error).__name__, "detail": _detail(self.error)} if self.error else None,
            "timings": self.timings,
        }


def _detail(err: Exception) -> str:
    return str(getattr(err, "detail", None) or err)


def process_sms(body: str, league: League, llm, dry_run: bool = False) -> SmsResult:
    """Record the result an SMS reports and work out the reply. Errors are captured in the result.

    The LLM reads who the two people mentioned could be (from the full player list) and the scores; resolve_match
    narrows that down to one match of this round before anything is recorded."""
    result = SmsResult()
    try:
        players = league.players

        def read_matches():
            with result.timed("lookup"):
                return league.read_matches()

        # Read the round's matches from the sheet while the LLM reads the message
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending_matches = pool.submit(read_matches)
            with result.timed("llm"):
                result.inferred = llm.infer(passage=body, known_players=players)
            matches = pending_matches.result()
        reading = result.inferred
        result.players = first, second = resolve_match(reading, players, league.round_pairs(matches))
        with result.timed("record"):
            result.match, result.changes = league.report_result(
                {first.name: reading.player1_score, second.name: reading.player2_score},
                breaks=[(result.players[b.player - 1].name, b.points) for b in reading.breaks],
                log=body,
                dry_run=dry_run,
                lookup=league.lookup_pair(first.name, second.name, matches),
            )
        with result.timed("link"):
            link = league.round_sheet_url()
        result.reply = result.match.summary(link=link)
    except MatchAlreadyCompleted as err:
        result.error = err
        result.reply = get_messages().ALREADY_COMPLETED.format(" vs ".join(str(p) for p in result.players))
    except (UnknownPlayersError, AmbiguousPlayersError) as err:
        result.error = err
        result.reply = err.reply
    except Exception as err:
        result.error = err
        result.reply = get_messages().INVALID
    logging.info("SMS processing times (s): %s", result.timings)
    return result
