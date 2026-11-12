"""CLI against an in-memory league: no network access needed."""

import json
from datetime import date

import freezegun
import pytest
from click.testing import CliRunner

from snooker_score_bot.cli import State, cli
from tests.test_league import find, make_league


@pytest.fixture(autouse=True)
def frozen_today():
    with freezegun.freeze_time("2026-11-12 18:00:00"):
        yield


@pytest.fixture
def league():
    lg = make_league()
    lg.generate_fixtures(round=2)
    wrong = find(lg, "Neuvonen Mikko", "Nevala Jyrki")
    lg.record_result(wrong.match_id, 2, 0, log="Jani - Mikko 2-0", date=date(2026, 11, 12))
    return lg


@pytest.fixture
def run(league):
    def run(*args, expect_exit=0):
        result = CliRunner().invoke(cli, list(args), obj=State(league=league, league_name="test"))
        assert result.exit_code == expect_exit, result.output + str(result.exception)
        return result

    return run


def run_json(run, *args, **kwargs):
    return json.loads(run("--json", *args, **kwargs).stdout)


def test_round_show(run):
    data = run_json(run, "round", "show")
    assert data["current_round"] == 2
    assert [r["number"] for r in data["rounds"]] == [1, 2, 3]
    assert "Current round: 2" in run("round", "show").output


def test_players_list(run):
    assert len(run_json(run, "players", "list")) == 5
    assert {p["name"] for p in run_json(run, "players", "list", "--group", "L3")} == {"Lundgren Mikko", "Nurmi Jani"}


def test_matches_list_filters(run):
    assert len(run_json(run, "matches", "list")) == 4
    completed = run_json(run, "matches", "list", "--status", "completed")
    assert [(m["winner"], m["outcome"]["player1_score"]) for m in completed] == [("Neuvonen Mikko", 2)]
    assert run_json(run, "matches", "list", "--round", "1") == []
    assert len(run_json(run, "matches", "list", "--group", "L7")) == 3
    assert "Neuvonen Mikko" in run("matches", "list").output


def test_matches_show_by_id_prefix(run, league):
    m = find(league, "Neuvonen Mikko", "Nevala Jyrki")
    data = run_json(run, "matches", "show", m.match_id[:8])
    assert data["id"] == m.match_id and data["winner"] == "Neuvonen Mikko" and data["breaks"] == []
    assert "result 2-0, winner Neuvonen Mikko" in run("matches", "show", m.match_id).output


def test_matches_show_not_found(run):
    result = run("--json", "matches", "show", "deadbeef", expect_exit=3)
    assert json.loads(result.stderr)["error"] == "MatchNotFound"
    assert "No match with id" in run("matches", "show", "deadbeef", expect_exit=3).stderr


def test_breaks_list(run, league):
    league.backend.append_rows("_breaks", [["t", "admin", "", "Nurmi Jani", "33", "46338", "2"]])
    (b,) = run_json(run, "breaks", "list")
    assert (b["player"], b["points"], b["date"]) == ("Nurmi Jani", 33, "2026-11-12")
    assert run_json(run, "breaks", "list", "--player", "Neuvonen Mikko") == []


def test_league_option_and_help():
    result = CliRunner().invoke(cli, ["--league", "nope", "round", "show"])
    assert result.exit_code == 2
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0 and "matches" in result.output and "breaks" in result.output


# ---------------------------------------------------------------------- writes


def test_correct_a_result(run, league):
    """The "Jani - Mikko 2-0" correction, done with the CLI."""
    wrong = find(league, "Neuvonen Mikko", "Nevala Jyrki")
    right = find(league, "Hauta-aho Jani", "Neuvonen Mikko")
    score = "2-0" if right.player1.name == "Hauta-aho Jani" else "0-2"

    preview = run_json(run, "results", "clear", wrong.match_id[:8], "--dry-run")
    assert preview["dry_run"] and preview["changes"][0]["before"]["winner"] == "Neuvonen Mikko"
    assert league.match(wrong.match_id).completed

    cleared = run_json(run, "results", "clear", wrong.match_id[:8])
    assert cleared["match"]["state"] == "unplayed" and cleared["changes"][0]["applied"]

    out = run("results", "record", right.match_id[:8], "-s", score, "-w", "Jani", "--log", "Jani - Mikko 2-0")
    assert "winner Hauta-aho Jani" in out.output and "winner: '' -> 'Hauta-aho Jani'" in out.output
    assert league.match(right.match_id).winner.name == "Hauta-aho Jani"


def test_record_refuses_wrong_winner_and_bad_scores(run, league):
    m = find(league, "Hauta-aho Jani", "Neuvonen Mikko")
    wrong_winner = "Neuvonen" if m.player1.name == "Hauta-aho Jani" else "Hauta-aho"
    assert "makes" in run("results", "record", m.match_id, "-s", "2-0", "-w", wrong_winner, expect_exit=2).output
    run("results", "record", m.match_id, "-s", "3-0", expect_exit=2)
    run("results", "record", m.match_id, "-s", "two-nil", expect_exit=2)
    run("results", "record", m.match_id, "-s", "2-0", "-b", "Jyrki:40", expect_exit=2)
    assert not league.match(m.match_id).completed


def test_record_refuses_completed_unless_overwrite(run, league):
    wrong = find(league, "Neuvonen Mikko", "Nevala Jyrki")
    run("results", "record", wrong.match_id, "-s", "0-2", expect_exit=4)
    data = run_json(run, "results", "record", wrong.match_id, "-s", "0-2", "--overwrite")
    assert data["match"]["winner"] == "Nevala Jyrki"


def test_record_with_breaks_and_date(run, league):
    m = find(league, "Lundgren Mikko", "Nurmi Jani")
    args = ["-s", "2-1", "-b", "Nurmi:45", "-b", "Mikko:30", "--date", "2026-11-10"]
    data = run_json(run, "results", "record", m.match_id, *args)
    assert [c["tab"] for c in data["changes"]] == ["_matches", "_breaks", "_breaks"]
    shown = run_json(run, "matches", "show", m.match_id)
    assert shown["outcome"]["date"] == "2026-11-10"
    breaks = sorted((b["player"], b["points"]) for b in shown["breaks"])
    assert breaks == [("Lundgren Mikko", 30), ("Nurmi Jani", 45)]

    cleared = run_json(run, "results", "clear", m.match_id, "--with-breaks")
    assert [c["action"] for c in cleared["changes"]] == ["update", "delete", "delete"]
    assert run_json(run, "breaks", "list") == []


def test_breaks_add_and_remove(run):
    run("breaks", "add", "--player", "Nobody", "--points", "40", expect_exit=3)
    run("breaks", "add", "--player", "Nurmi Jani", "--points", "148", expect_exit=2)
    added = run_json(run, "breaks", "add", "--player", "Nurmi Jani", "--points", "40")
    assert added["changes"][0]["after"]["player"] == "Nurmi Jani"
    (b,) = run_json(run, "breaks", "list")
    run("breaks", "remove", str(b["row"]), "--player", "Nurmi Jani", "--points", "41", expect_exit=4)
    run("breaks", "remove", str(b["row"]), "--player", "Nurmi Jani", "--points", "40")
    assert run_json(run, "breaks", "list") == []


def test_fixtures_generate(run):
    assert "Would add 0 fixtures" in run("fixtures", "generate", "--round", "2", "--dry-run").output
    data = run_json(run, "fixtures", "generate", "--round", "3")
    assert len(data["fixtures"]) == 4 and not data["dry_run"]


def test_fixtures_reset_needs_yes_and_test_league(run):
    run("fixtures", "reset", "--round", "2", expect_exit=2)
    assert "not allowed" in run("fixtures", "reset", "--round", "2", "--yes", expect_exit=4).stderr


def test_sms_parse_is_a_dry_run(run, league, monkeypatch):
    from tests.test_sms import jani_beats_mikko, llm_reading

    monkeypatch.setattr("snooker_score_bot.cli.make_llm", lambda settings: jani_beats_mikko())
    out = run("sms", "parse", "Hauta-aho - Neuvonen 2-0").output
    assert "[dry run] update _matches" in out and "Hauta-aho Jani won Neuvonen Mikko" in out
    assert league.matches(status="completed")[0].player2.name == "Nevala Jyrki"  # only the pre-existing result

    janis_and_mikkos = llm_reading(["Nurmi Jani", "Hauta-aho Jani"], ["Lundgren Mikko", "Neuvonen Mikko"])
    monkeypatch.setattr("snooker_score_bot.cli.make_llm", lambda settings: janis_and_mikkos)
    error = run_json(run, "sms", "parse", "Jani - Mikko 2-0")["error"]
    assert error["type"] == "AmbiguousPlayersError" and "Lundgren Mikko (L3)" in error["detail"]
