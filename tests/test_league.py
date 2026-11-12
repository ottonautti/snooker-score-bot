"""League logic against an in-memory sheet: no network access needed."""

from datetime import date

import freezegun
import pytest

from snooker_score_bot.errors import MatchAlreadyCompleted, MatchNotFound, NotAllowedError
from snooker_score_bot.league import BREAKS, MATCHES, League, parse_date, to_serial
from snooker_score_bot.settings import Settings, SixRedSettings, TestSettings
from snooker_score_bot.storage import MemoryBackend

MATCH_HEADERS = ["id", "round", "group", "player1", "player2", "date", "player1_score", "player2_score", "winner",
                 "log", "walkover?"]  # fmt: skip
BREAK_HEADERS = ["timestamp", "from", "passage", "player", "break", "date", "round"]
PLAYERS = [
    ["Lundgren Mikko", "L3"],
    ["Nurmi Jani", "L3"],
    ["Neuvonen Mikko", "L7"],
    ["Nevala Jyrki", "L7"],
    ["Hauta-aho Jani", "L7"],
]
ROUNDS = [["1", "1.9.2026", "11.10.2026"], ["2", "14.10.2026", "22.11.2026"], ["3", "25.11.2026", "10.1.2027"]]

pytestmark = pytest.mark.usefixtures("frozen_today")


@pytest.fixture
def frozen_today():
    with freezegun.freeze_time("2026-11-12 18:00:00"):
        yield


def make_league(settings=Settings, matches=(), breaks=(), players=PLAYERS, rounds=ROUNDS, match_headers=None):
    tabs = {
        MATCHES: [match_headers or MATCH_HEADERS, *matches],
        BREAKS: [BREAK_HEADERS, *breaks],
        "nr_currentPlayers": players,
        "nr_rounds": rounds,
        "ROUND 2": [],
    }
    return League(settings(), backend=MemoryBackend(tabs))


@pytest.fixture
def league():
    """Round 2 fixtures; Neuvonen - Nevala wrongly recorded as in the "Jani - Mikko 2-0" incident."""
    lg = make_league()
    lg.generate_fixtures(round=2)
    wrong = find(lg, "Neuvonen Mikko", "Nevala Jyrki")
    lg.record_result(wrong.match_id, 2, 0, log="Jani - Mikko 2-0", date=date(2026, 11, 12))
    del lg.players  # reset caches as a fresh instance would have
    return lg


def find(league, a, b, round=2):
    return next(m for m in league.matches(round=round) if {m.player1.name, m.player2.name} == {a, b})


def rows(league, tab):
    return league.backend.tabs[tab]


def test_parse_date():
    assert parse_date("46338") == date(2026, 11, 12)
    assert parse_date("12.11.2026") == date(2026, 11, 12)
    assert parse_date("") is None
    assert to_serial(date(2026, 11, 12)) == 46338


def test_current_round_and_link(league):
    assert league.current_round == 2
    assert [r.number for r in league.rounds()] == [1, 2, 3]
    assert league.round_sheet_url().startswith(Settings.SHEET_URL + "?gid=")
    assert league.round_sheet_url(3) == Settings.SHEET_URL


def test_players_column_order_per_league():
    sixred = make_league(SixRedSettings, players=[["A", "Lundgren Mikko"], ["A", "Nurmi Jani"]], rounds=[])
    assert [(p.name, p.group) for p in sixred.players] == [("Lundgren Mikko", "A"), ("Nurmi Jani", "A")]
    assert sixred.current_round == 1


def test_generate_fixtures_is_idempotent(league):
    assert len(league.matches()) == 1 + 3  # L3: one pair, L7: three pairs
    new, changes = league.generate_fixtures(round=2)
    assert new == [] and changes == []


def test_record_result_dry_run(league):
    m = find(league, "Hauta-aho Jani", "Neuvonen Mikko")
    before = [list(r) for r in rows(league, MATCHES)]
    match, changes = league.record_result(m.match_id, 2, 0, breaks=[("Hauta-aho Jani", 45)], dry_run=True)
    assert match.winner.name == m.player1.name
    assert [c.tab for c in changes] == [MATCHES, BREAKS] and not any(c.applied for c in changes)
    assert rows(league, MATCHES) == before and len(rows(league, BREAKS)) == 1


def test_report_result_by_names_orients_scores(league):
    match, _ = league.report_result({"Hauta-aho Jani": 2, "Neuvonen Mikko": 0}, log="sms")
    assert match.winner.name == "Hauta-aho Jani"
    with pytest.raises(MatchNotFound):
        league.report_result({"Hauta-aho Jani": 2, "Nurmi Jani": 0})


def test_report_result_inserts_match_without_prepared_fixtures():
    headers = ["id", "group", "player1", "player2", "player1_score", "player2_score", "winner", "date", "round", "log"]
    lg = make_league(SixRedSettings, players=[["A", "Lundgren Mikko"], ["A", "Nurmi Jani"]], match_headers=headers)
    match, changes = lg.report_result({"Nurmi Jani": 3, "Lundgren Mikko": 1}, log="Jani - Mikko 3-1")
    assert match.winner.name == "Nurmi Jani"
    (row,) = rows(lg, MATCHES)[1:]
    assert dict(zip(headers, row))["winner"] == "Nurmi Jani" and dict(zip(headers, row))["round"] == "1"
    with pytest.raises(MatchAlreadyCompleted):
        lg.report_result({"Nurmi Jani": 3, "Lundgren Mikko": 0})
    with pytest.raises(NotAllowedError):
        lg.generate_fixtures(round=1)


def test_reset_round_only_on_test_league(league):
    with pytest.raises(NotAllowedError):
        league.reset_round(2)
    lg = make_league(TestSettings)
    lg.generate_fixtures(round=1)
    lg.generate_fixtures(round=2)
    m = find(lg, "Nurmi Jani", "Lundgren Mikko")
    lg.record_result(m.match_id, 2, 0)
    changes = lg.reset_round(2)
    assert [c.action for c in changes].count("delete") == 4
    assert lg.matches(round=2, status="completed") == []
    assert len(lg.matches(round=2)) == 4 and len(lg.matches(round=1)) == 4


def test_unvalidated_rows_are_still_listed():
    bad = ["x1", "2", "L7", "Neuvonen Mikko", "Nevala Jyrki", "46338", "2", "2", "Neuvonen Mikko", "", ""]
    lg = make_league(matches=[bad])
    (m,) = lg.matches()
    assert m.match_id == "x1"


def test_failed_result_write_is_raised_even_when_breaks_succeed(league):
    m = find(league, "Hauta-aho Jani", "Neuvonen Mikko")

    def fail(*args, **kwargs):
        raise RuntimeError("sheets down")

    league.backend.update_cells = fail
    with pytest.raises(RuntimeError, match="sheets down"):
        league.record_result(m.match_id, 2, 0, breaks=[("Hauta-aho Jani", 45)])
