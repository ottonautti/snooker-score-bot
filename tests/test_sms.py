"""SMS processing against an in-memory league and a fake LLM."""

from datetime import date

import freezegun
import pytest

from snooker_score_bot.errors import (
    AmbiguousPlayersError,
    InferenceMismatchError,
    MatchAlreadyCompleted,
)
from snooker_score_bot.models import InferredMatch
from snooker_score_bot.settings import get_messages
from snooker_score_bot.sms import process_sms
from tests.test_league import find, make_league


@pytest.fixture(autouse=True)
def frozen_today():
    with freezegun.freeze_time("2026-11-12 18:00:00"):
        yield


@pytest.fixture
def league():
    lg = make_league()
    lg.generate_fixtures(round=2)
    return lg


class FakeLLM:
    def __init__(self, answer: InferredMatch):
        self.answer = answer
        self.calls = []

    def infer(self, passage, known_players):
        self.calls.append((passage, [p.name for p in known_players]))
        return self.answer


def llm_reading(first, second, s1=2, s2=0, breaks=()):
    """A fake LLM that reads the given player options, scores and breaks from any message."""
    return FakeLLM(
        InferredMatch(
            players=[{"options": first}, {"options": second}],
            player1_score=s1,
            player2_score=s2,
            breaks=[{"player": p, "points": n} for p, n in breaks],
        )
    )


def jani_beats_mikko(**kwargs):
    return llm_reading(["Hauta-aho Jani"], ["Neuvonen Mikko"], **kwargs)


def test_records_result_and_replies(league):
    llm = jani_beats_mikko(breaks=[(1, 45)])
    result = process_sms("Hauta-aho - Neuvonen 2-0, breikki Jani 45", league, llm)
    assert result.error is None
    passage, known = llm.calls[0]
    assert passage == "Hauta-aho - Neuvonen 2-0, breikki Jani 45" and len(known) == 5  # the whole player list
    assert result.reply.startswith("Hauta-aho Jani won Neuvonen Mikko by 2 frames to 0. Breaks: Jani 45.")
    stored = league.match(find(league, "Hauta-aho Jani", "Neuvonen Mikko").match_id)
    assert stored.winner.name == "Hauta-aho Jani" and stored.outcome.date == date(2026, 11, 12)
    assert [(b.player, b.points) for b in league.breaks()] == [("Hauta-aho Jani", 45)]


def test_scores_follow_the_order_the_players_are_mentioned(league):
    result = process_sms(
        "Neuvonen hävisi Hauta-aholle 0-2", league, llm_reading(["Neuvonen Mikko"], ["Hauta-aho Jani"], 0, 2)
    )
    assert result.match.winner.name == "Hauta-aho Jani"


def test_dry_run_records_nothing(league):
    result = process_sms("Hauta-aho - Neuvonen 2-0", league, jani_beats_mikko(), dry_run=True)
    assert result.error is None and result.reply.startswith("Hauta-aho Jani won")
    assert not any(c.applied for c in result.changes)
    assert league.matches(status="completed") == []


def test_ambiguous_message_is_not_recorded(league):
    """Regression: "Jani - Mikko 2-0" was recorded as Neuvonen Mikko beating Nevala Jyrki."""
    llm = llm_reading(["Nurmi Jani", "Hauta-aho Jani"], ["Lundgren Mikko", "Neuvonen Mikko"])
    result = process_sms("Jani - Mikko 2-0", league, llm)
    assert isinstance(result.error, AmbiguousPlayersError)
    assert "Hauta-aho Jani - Neuvonen Mikko (L7)" in result.reply.splitlines()
    assert league.matches(status="completed") == []


def test_incoherent_answer_gets_the_generic_reply(league):
    result = process_sms("Hauta-aho - Neuvonen", league, jani_beats_mikko(s1=1, s2=1))
    assert isinstance(result.error, InferenceMismatchError)
    assert result.reply == get_messages().INVALID
    assert league.matches(status="completed") == []


def test_already_played(league):
    process_sms("Hauta-aho - Neuvonen 2-0", league, jani_beats_mikko())
    result = process_sms("Hauta-aho - Neuvonen 2-0", league, jani_beats_mikko())
    assert isinstance(result.error, MatchAlreadyCompleted)
    assert result.reply == get_messages().ALREADY_COMPLETED.format("Hauta-aho Jani vs Neuvonen Mikko")


def test_matches_are_read_once_while_llm_runs(league):
    reads = []
    original = league.backend.get_values
    league.backend.get_values = lambda tab: reads.append(tab) or original(tab)
    result = process_sms("Hauta-aho - Neuvonen 2-0", league, jani_beats_mikko())
    assert result.error is None and "lookup" in result.timings
    assert reads.count("_matches") == 1
