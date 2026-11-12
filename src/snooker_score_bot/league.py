"""League operations on top of the spreadsheet.

This is the single place that reads and writes league data. The SMS handler, the HTTP API and the CLI all go through
`League`, so every change gets the same checks.

Sheet layout:
* `_matches`: one row per match. Columns are looked up by header; result columns are date, player1_score,
  player2_score, winner and log.
* `_breaks`: one row per break: timestamp, from, passage, player, break, date, round. Breaks are not linked to a
  match id; they are associated with a match by player, round and date.
* `nr_currentPlayers`: named range of players and their groups (column order per settings).
* `nr_rounds`: named range of rounds: number, start date, end date.

Every write returns `Change` records with the values before and after, and can be run as a dry run.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from functools import cached_property
from itertools import combinations
from typing import Iterable, Literal, Optional, Union

import pytz
from pydantic import ValidationError

from .errors import AmbiguousIdError, MatchAlreadyCompleted, MatchNotFound, NotAllowedError, StaleRowError
from .models import MatchFormat, MatchOutcome, SnookerBreak, SnookerMatch, SnookerPlayer
from .settings import Settings
from .storage import GspreadBackend, SheetBackend

MATCHES = "_matches"
BREAKS = "_breaks"
PLAYERS_RANGE = "nr_currentPlayers"
ROUNDS_RANGE = "nr_rounds"
MIN_ID_PREFIX = 6
RESULT_FIELDS = ("date", "player1_score", "player2_score", "winner", "log")
SHEETS_DATE_FORMAT = "%d.%m.%Y"
EXCEL_EPOCH = date(1899, 12, 30)
TIMEZONE = pytz.timezone("Europe/Helsinki")

Status = Literal["unplayed", "completed"]
BreakInput = Union[SnookerBreak, tuple[str, int]]


def today() -> date:
    return datetime.now(TIMEZONE).date()


def to_serial(d: date) -> int:
    """Spreadsheet date serial number, as stored in the sheet."""
    return (d - EXCEL_EPOCH).days


def parse_date(value) -> Optional[date]:
    """Parse a date cell: a serial number ("46338") or a formatted date ("12.11.2026")."""
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if text.isdigit():
        return EXCEL_EPOCH + timedelta(days=int(text))
    try:
        return datetime.strptime(text, SHEETS_DATE_FORMAT).date()
    except ValueError:
        return None


def parse_int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


@dataclass
class Round:
    number: int
    start: Optional[date] = None
    end: Optional[date] = None


@dataclass
class Change:
    """One row written (or to be written, on a dry run)."""

    action: Literal["update", "append", "delete"]
    tab: str
    row: Optional[int]
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    applied: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BreakRecord:
    row: int
    player: str
    points: int
    date: Optional[date]
    round: Optional[int]
    source: str = ""
    passage: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat() if self.date else None
        return d


@dataclass
class PairLookup:
    """Result of League.lookup_pair: the round's match rows between two players."""

    names: frozenset
    round: Optional[int]
    table: "_Table"
    existing: list[tuple[int, dict]]


@dataclass
class _Table:
    headers: list[str]
    rows: list[tuple[int, dict]]  # (sheet row number, {header: value})

    def col(self, header: str) -> int:
        return self.headers.index(header) + 1


class League:
    def __init__(self, settings: Settings, backend: SheetBackend = None):
        self.settings = settings
        self.backend = backend or GspreadBackend(settings.SHEETID)
        self.format = MatchFormat(**settings.MATCH_FORMAT)
        self._header_cache: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ reading

    def _headers(self, tab: str) -> list[str]:
        """Header row of a tab. Headers never change while the app runs, so they are read once."""
        if tab not in self._header_cache:
            self._header_cache[tab] = self.backend.get_row(tab, 1)
        return self._header_cache[tab]

    def _table(self, tab: str) -> _Table:
        values = self.backend.get_values(tab)
        if not values:
            return _Table(headers=[], rows=[])
        headers = values[0]
        self._header_cache[tab] = headers
        rows = []
        for i, raw in enumerate(values[1:], start=2):
            if not any(str(v).strip() for v in raw):
                continue
            padded = list(raw) + [""] * (len(headers) - len(raw))
            rows.append((i, dict(zip(headers, padded))))
        return _Table(headers=headers, rows=rows)

    @cached_property
    def players(self) -> list[SnookerPlayer]:
        rows = self.backend.get_values(PLAYERS_RANGE)
        name_col = self.settings.PLAYERS_COLUMNS.index("name")
        group_col = self.settings.PLAYERS_COLUMNS.index("group")
        players = [
            SnookerPlayer(name=row[name_col].strip(), group=row[group_col].strip())
            for row in rows
            if len(row) >= 2 and row[name_col].strip() and row[group_col].strip()
        ]
        if not players:
            raise RuntimeError("No players found in spreadsheet")
        return players

    def player(self, name: str) -> SnookerPlayer:
        for p in self.players:
            if p.name == name:
                return p
        raise LookupError(f"Unknown player: {name}")

    def rounds(self) -> list[Round]:
        if self.settings.FIXED_ROUND is not None:
            return [Round(number=self.settings.FIXED_ROUND)]
        rounds = []
        for row in self.backend.get_values(ROUNDS_RANGE):
            number = parse_int(row[0]) if row else None
            if number is not None:
                rounds.append(
                    Round(
                        number=number,
                        start=parse_date(row[1]) if len(row) > 1 else None,
                        end=parse_date(row[2]) if len(row) > 2 else None,
                    )
                )
        return sorted(rounds, key=lambda r: r.number)

    @cached_property
    def current_round(self) -> Optional[int]:
        """The latest round that has started."""
        if self.settings.FIXED_ROUND is not None:
            return self.settings.FIXED_ROUND
        started = [r for r in self.rounds() if r.start and r.start <= today()]
        return started[-1].number if started else None

    def round_sheet_url(self, round: int = None) -> str:
        round = round or self.current_round
        gid = self.backend.tab_id(f"ROUND {round}") if round else None
        return f"{self.settings.SHEET_URL}?gid={gid}" if gid is not None else self.settings.SHEET_URL

    def _to_match(self, record: dict) -> SnookerMatch:
        outcome = None
        if record.get("winner"):
            outcome = MatchOutcome(
                date=parse_date(record.get("date")),
                player1_score=parse_int(record.get("player1_score")),
                player2_score=parse_int(record.get("player2_score")),
            )
        data = dict(
            round=parse_int(record.get("round")),
            group=record["group"],
            player1=SnookerPlayer(name=record["player1"], group=record["group"]),
            player2=SnookerPlayer(name=record["player2"], group=record["group"]),
            outcome=outcome,
            format=self.format,
        )
        try:
            return SnookerMatch.from_storage(match_id=record["id"], **data)
        except ValidationError as err:
            # Rows edited by hand (e.g. walkovers) may not pass validation; still list them as they are.
            logging.warning("Match %s does not validate: %s", record.get("id"), err)
            return SnookerMatch.model_construct(_match_id=record["id"], **data)

    def _match_rows(self) -> tuple[_Table, list[tuple[int, dict]]]:
        table = self._table(MATCHES)
        return table, [(n, r) for n, r in table.rows if r.get("id")]

    def matches(
        self,
        round: Optional[int] = None,
        all_rounds: bool = False,
        group: Optional[str] = None,
        status: Optional[Status] = None,
    ) -> list[SnookerMatch]:
        """Matches of the current round (or the given round, or all rounds)."""
        if round is None and not all_rounds:
            round = self.current_round
        _, rows = self._match_rows()
        matches = []
        for _, record in rows:
            if round is not None and parse_int(record.get("round")) != round:
                continue
            if group and record.get("group") != group:
                continue
            match = self._to_match(record)
            if status and match.state != status:
                continue
            matches.append(match)
        return matches

    def _find_row(self, match_id: str) -> tuple[_Table, int, dict]:
        """Find a match row by id, or by a unique id prefix of at least 6 characters (e.g. "2b53d651")."""
        table, rows = self._match_rows()
        exact = [(n, r) for n, r in rows if r["id"] == match_id]
        if not exact and len(match_id) >= MIN_ID_PREFIX:
            exact = [(n, r) for n, r in rows if r["id"].startswith(match_id)]
        if len(exact) > 1:
            raise AmbiguousIdError(f"Match id prefix {match_id} fits {len(exact)} matches; use more characters")
        if not exact:
            raise MatchNotFound(f"No match with id {match_id}")
        n, record = exact[0]
        return table, n, record

    def match(self, match_id: str) -> SnookerMatch:
        _, _, record = self._find_row(match_id)
        return self._to_match(record)

    def _new_match(self, a: SnookerPlayer, b: SnookerPlayer, round: Optional[int]) -> SnookerMatch:
        return SnookerMatch.create(player1=a.name, player2=b.name, group=a.group, round=round, format=self.format)

    # ------------------------------------------------------------------ writing

    def _breaks(self, match: SnookerMatch, breaks: Iterable[BreakInput]) -> list[SnookerBreak]:
        result = []
        for b in breaks:
            if not isinstance(b, SnookerBreak):
                name, points = b
                b = SnookerBreak(player=SnookerPlayer(name=name, group=match.group), points=points)
            result.append(b)
        return result

    def record_result(
        self,
        match_id: str,
        player1_score: int,
        player2_score: int,
        breaks: Iterable[BreakInput] = (),
        date: Optional[date] = None,
        log: str = "",
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> tuple[SnookerMatch, list[Change]]:
        """Record the result of a match. Scores are in the order of the match's player1 and player2.

        Refuses to replace an existing result unless overwrite is set. Breaks of a replaced result are kept;
        remove them with clear_result first if they are wrong."""
        table, row, record = self._find_row(match_id)
        scores = (player1_score, player2_score)
        return self._record_row(table, row, record, *scores, breaks, date, log, overwrite, dry_run)

    def _record_row(
        self, table, row, record, player1_score, player2_score, breaks, date, log, overwrite, dry_run
    ) -> tuple[SnookerMatch, list[Change]]:
        """Write a result into a _matches row.

        The row is not re-read before writing: _matches rows never move, except in reset_round on the test league.
        """
        if record.get("winner") and not overwrite:
            raise MatchAlreadyCompleted()
        match = self._to_match(record)
        played_on = date or today()
        outcome = MatchOutcome(
            date=played_on,
            player1_score=player1_score,
            player2_score=player2_score,
            breaks=self._breaks(match, breaks),
        )
        # validates the scoreline against the match format and that breaks are by the match players
        match = SnookerMatch.from_storage(
            match_id=match.match_id,
            round=match.round,
            group=match.group,
            player1=match.player1,
            player2=match.player2,
            outcome=outcome,
            format=self.format,
        )
        after = {
            "date": to_serial(played_on),
            "player1_score": player1_score,
            "player2_score": player2_score,
            "winner": match.winner.name,
            "log": log,
        }
        change = Change(
            action="update",
            tab=MATCHES,
            row=row,
            before={k: record.get(k, "") for k in RESULT_FIELDS},
            after={k: str(v) for k, v in after.items()},
        )
        def write_result():
            if not dry_run:
                self.backend.update_cells(MATCHES, row, {table.col(k): v for k, v in after.items()})
                change.applied = True

        # The result and its breaks go to different tabs, so they are written at the same time
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(write_result)
            try:
                break_changes = self.add_breaks(
                    outcome.breaks, date=played_on, round=match.round, passage=log, dry_run=dry_run
                )
            finally:
                try:
                    pending.result()
                except Exception:
                    if outcome.breaks and not dry_run:
                        logging.error("Writing result of %s failed; its breaks may have been added", record["id"])
                    raise
        return match, [change, *break_changes]

    def read_matches(self) -> tuple["_Table", list[tuple[int, dict]]]:
        """All match rows (one read of _matches), for lookup_pair. Can run while the LLM reads a message."""
        return self._match_rows()

    def round_pairs(self, matches: Optional[tuple] = None) -> Optional[set[frozenset[str]]]:
        """Name pairs that have a match in the current round, or None when any same-group pair may play."""
        if not self.settings.PREPARED_FIXTURES:
            return None
        _, rows = matches or self._match_rows()
        round = self.current_round
        return {frozenset((r["player1"], r["player2"])) for _, r in rows if parse_int(r.get("round")) == round}

    def lookup_pair(self, name_a: str, name_b: str, matches: Optional[tuple] = None) -> "PairLookup":
        """Find the current round's match between two players, in matches from read_matches (read if not given)."""
        round = self.current_round
        table, rows = matches or self._match_rows()
        existing = [
            (n, r)
            for n, r in rows
            if parse_int(r.get("round")) == round and {r["player1"], r["player2"]} == {name_a, name_b}
        ]
        return PairLookup(names=frozenset((name_a, name_b)), round=round, table=table, existing=existing)

    def report_result(
        self,
        scores: dict[str, int],
        breaks: Iterable[BreakInput] = (),
        date: Optional[date] = None,
        log: str = "",
        dry_run: bool = False,
        lookup: Optional["PairLookup"] = None,
    ) -> tuple[SnookerMatch, list[Change]]:
        """Record a result by player names, e.g. from an SMS: {"Hauta-aho Jani": 2, "Neuvonen Mikko": 0}.

        With prepared fixtures the match must exist in the current round. Otherwise a new match is added,
        unless the players have already played this round. Pass a lookup_pair result to skip reading _matches."""
        (name_a, score_a), (name_b, score_b) = scores.items()
        a, b = self.player(name_a), self.player(name_b)
        if lookup is None or lookup.names != {a.name, b.name}:
            lookup = self.lookup_pair(a.name, b.name)
        if lookup.existing:
            row, record = lookup.existing[0]
            p1, p2 = scores[record["player1"]], scores[record["player2"]]
            return self._record_row(lookup.table, row, record, p1, p2, breaks, date, log, False, dry_run)
        if self.settings.PREPARED_FIXTURES:
            raise MatchNotFound()
        return self._insert_match(a, b, score_a, score_b, breaks, date, log, lookup.round, dry_run)

    def _insert_match(self, a, b, score_a, score_b, breaks, date, log, round, dry_run):
        played_on = date or today()
        match = self._new_match(a, b, round)
        match.outcome = MatchOutcome(
            date=played_on, player1_score=score_a, player2_score=score_b, breaks=self._breaks(match, breaks)
        )
        headers = self._headers(MATCHES)
        values = {
            "id": match.match_id,
            "round": round,
            "group": a.group,
            "player1": a.name,
            "player2": b.name,
            "date": to_serial(played_on),
            "player1_score": score_a,
            "player2_score": score_b,
            "winner": match.winner.name,
            "log": log,
        }
        change = Change(action="append", tab=MATCHES, row=None, after={k: str(v) for k, v in values.items()})
        if not dry_run:
            self.backend.append_rows(MATCHES, [[values.get(h, "") for h in headers]])
            change.applied = True
        changes = [change] + self.add_breaks(
            match.outcome.breaks, date=played_on, round=round, passage=log, dry_run=dry_run
        )
        return match, changes

    def related_breaks(self, match: SnookerMatch) -> list[BreakRecord]:
        """Breaks that were most likely recorded with the match's result: same round, players and date."""
        if not match.outcome:
            return []
        return [
            b
            for b in self.breaks(round=match.round)
            if b.player in (match.player1.name, match.player2.name) and b.date == match.outcome.date
        ]

    def clear_result(
        self, match_id: str, remove_breaks: bool = False, dry_run: bool = False
    ) -> tuple[SnookerMatch, list[Change]]:
        """Return a match to unplayed. Optionally also remove the breaks recorded with it (see related_breaks)."""
        table, row, record = self._find_row(match_id)
        match = self._to_match(record)
        change = Change(
            action="update",
            tab=MATCHES,
            row=row,
            before={k: record.get(k, "") for k in RESULT_FIELDS},
            after={k: "" for k in RESULT_FIELDS},
        )
        changes = [change]
        if remove_breaks:
            for b in sorted(self.related_breaks(match), key=lambda b: b.row, reverse=True):
                changes.append(self.remove_break(b.row, b.player, b.points, dry_run=dry_run))
        if not dry_run:
            self.backend.update_cells(MATCHES, row, {table.col(k): "" for k in RESULT_FIELDS})
            change.applied = True
        return (self.match(record["id"]) if not dry_run else match), changes

    # ------------------------------------------------------------------ breaks

    def breaks(
        self, round: Optional[int] = None, all_rounds: bool = False, player: Optional[str] = None
    ) -> list[BreakRecord]:
        if round is None and not all_rounds:
            round = self.current_round
        records = []
        for row, r in self._table(BREAKS).rows:
            record = BreakRecord(
                row=row,
                player=r.get("player", ""),
                points=parse_int(r.get("break")) or 0,
                date=parse_date(r.get("date")),
                round=parse_int(r.get("round")),
                source=r.get("from", ""),
                passage=r.get("passage", ""),
                timestamp=r.get("timestamp", ""),
            )
            if round is not None and record.round != round:
                continue
            if player and record.player != player:
                continue
            records.append(record)
        return records

    def add_breaks(
        self,
        breaks: Iterable[SnookerBreak],
        date: Optional[date] = None,
        round: Optional[int] = None,
        source: str = "admin",
        passage: str = "",
        dry_run: bool = False,
    ) -> list[Change]:
        breaks = list(breaks)
        if not breaks:
            return []
        headers = self._headers(BREAKS)
        timestamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        rows, changes = [], []
        for b in breaks:
            values = {
                "timestamp": timestamp,
                "from": source,
                "passage": passage,
                "player": b.player.name,
                "break": b.points,
                "date": to_serial(date or today()),
                "round": round if round is not None else self.current_round,
            }
            rows.append([values.get(h, "") for h in headers])
            changes.append(Change(action="append", tab=BREAKS, row=None, after={k: str(v) for k, v in values.items()}))
        if not dry_run:
            self.backend.append_rows(BREAKS, rows)
            for c in changes:
                c.applied = True
        return changes

    def remove_break(self, row: int, player: str, points: int, dry_run: bool = False) -> Change:
        """Delete a break row.

        Player and points must match what is in the row, as a guard against stale row numbers."""
        table = self._table(BREAKS)
        record = dict(table.rows).get(row)
        if not record or record.get("player") != player or parse_int(record.get("break")) != points:
            raise StaleRowError(f"Row {row} of {BREAKS} is not a break of {points} by {player}")
        change = Change(action="delete", tab=BREAKS, row=row, before=dict(record))
        if not dry_run:
            self.backend.delete_rows(BREAKS, [row])
            change.applied = True
        return change

    # ------------------------------------------------------------------ fixtures

    def generate_fixtures(self, round: int, dry_run: bool = False) -> tuple[list[SnookerMatch], list[Change]]:
        """Add a match for every pair of players within each group, skipping pairs that already have one."""
        existing = {frozenset((m.player1.name, m.player2.name)) for m in self.matches(round=round)}
        return self._add_fixtures(round, existing, dry_run)

    def _add_fixtures(self, round: int, existing: set, dry_run: bool) -> tuple[list[SnookerMatch], list[Change]]:
        if not self.settings.PREPARED_FIXTURES:
            raise NotAllowedError(f"League {self.settings.LEAGUE} does not use prepared fixtures")
        new = []
        for group in sorted({p.group for p in self.players}):
            group_players = [p for p in self.players if p.group == group]
            for a, b in combinations(group_players, 2):
                if frozenset((a.name, b.name)) not in existing:
                    new.append(self._new_match(a, b, round))
        headers = self._headers(MATCHES)
        rows, changes = [], []
        for m in new:
            values = {
                "id": m.match_id,
                "round": round,
                "group": m.group,
                "player1": m.player1.name,
                "player2": m.player2.name,
            }
            rows.append([values.get(h, "") for h in headers])
            after = {k: str(v) for k, v in values.items()}
            changes.append(Change(action="append", tab=MATCHES, row=None, after=after))
        if not dry_run:
            self.backend.append_rows(MATCHES, rows)
            for c in changes:
                c.applied = True
        return new, changes

    def reset_round(self, round: int, dry_run: bool = False) -> list[Change]:
        """Delete every match of a round, results included, and generate fresh fixtures. Test sheets only."""
        if not self.settings.ALLOW_RESET:
            raise NotAllowedError(f"Resetting rounds is not allowed for league {self.settings.LEAGUE}")
        _, rows = self._match_rows()
        doomed = [(n, r) for n, r in rows if parse_int(r.get("round")) == round]
        changes = [Change(action="delete", tab=MATCHES, row=n, before=dict(r)) for n, r in doomed]
        if not dry_run:
            self.backend.delete_rows(MATCHES, [n for n, _ in doomed])
            for c in changes:
                c.applied = True
        _, added = self._add_fixtures(round, existing=set(), dry_run=dry_run)
        return changes + added
