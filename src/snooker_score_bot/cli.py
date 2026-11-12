"""`snooker`: command line interface for league administration.

Commands are grouped by what they act on: `snooker <noun> <verb>`. Every command is non-interactive, prints a
table by default and JSON with `--json` (for scripts and agents), and exits with:

    0  success
    1  unexpected error
    2  invalid input (bad arguments, scoreline that does not fit the match format, ...)
    3  not found (match id, player)
    4  refused (match already played, ambiguous id or text, sheet changed meanwhile, not allowed for league)

Writes accept `--dry-run`, which shows the changes without making them.
"""

import json
import os
import sys
from datetime import date
from typing import Any, Callable, Optional

import click
from pydantic import ValidationError
from tabulate import tabulate

from .errors import (
    AmbiguousIdError,
    AmbiguousPlayersError,
    MatchAlreadyCompleted,
    MatchNotFound,
    NotAllowedError,
    StaleRowError,
    UnknownPlayersError,
)
from .league import BreakRecord, Change, League
from .models import SnookerBreak, SnookerMatch
from .settings import LEAGUES, get_settings

EXIT_ERROR, EXIT_INVALID, EXIT_NOT_FOUND, EXIT_REFUSED = 1, 2, 3, 4

ERROR_EXIT_CODES = [
    ((MatchNotFound, UnknownPlayersError, LookupError), EXIT_NOT_FOUND),
    (
        (MatchAlreadyCompleted, AmbiguousIdError, AmbiguousPlayersError, StaleRowError, NotAllowedError),
        EXIT_REFUSED,
    ),
    ((ValidationError, ValueError), EXIT_INVALID),
]


class Output:
    """Writes results as tables or JSON, depending on --json."""

    def __init__(self, as_json: bool):
        self.as_json = as_json

    def emit(self, data: Any, human: Callable[[], str]) -> None:
        if self.as_json:
            click.echo(json.dumps(data, default=_json_default, ensure_ascii=False, indent=2))
        else:
            click.echo(human())

    def error(self, err: Exception) -> None:
        detail = getattr(err, "detail", None) or getattr(err, "reply", None) or str(err)
        if isinstance(err, ValidationError):
            detail = "; ".join(e["msg"] for e in err.errors())
        if self.as_json:
            click.echo(json.dumps({"error": type(err).__name__, "detail": detail}, ensure_ascii=False), err=True)
        else:
            click.echo(f"Error: {detail}", err=True)


def _json_default(value):
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return str(value)


class SnookerGroup(click.Group):
    """Turns known errors into an error message and exit code instead of a traceback."""

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except click.exceptions.Exit:
            raise
        except click.ClickException:
            raise
        except Exception as err:
            for types, code in ERROR_EXIT_CODES:
                if isinstance(err, types):
                    break
            else:
                code = EXIT_ERROR
                if os.getenv("SNOOKER_DEBUG"):
                    raise
            out = ctx.obj["out"] if isinstance(ctx.obj, dict) and "out" in ctx.obj else Output(False)
            out.error(err)
            sys.exit(code)


class State(dict):
    """ctx.obj: the league (created on first use) and the output writer."""

    @property
    def league(self) -> League:
        if "league" not in self:
            self["league"] = League(get_settings(self["league_name"]))
        return self["league"]

    @property
    def out(self) -> Output:
        return self["out"]


pass_state = click.make_pass_decorator(State)


@click.group(cls=SnookerGroup)
@click.option(
    "--league",
    "-l",
    "league_name",
    type=click.Choice(sorted(LEAGUES)),
    default=lambda: os.getenv("SNOOKER_LEAGUE", "test"),
    show_default="test, or $SNOOKER_LEAGUE",
    help="Which league sheet to use.",
)
@click.option("--json", "as_json", is_flag=True, help="Print results as JSON.")
@click.pass_context
def cli(ctx: click.Context, league_name: str, as_json: bool):
    """Administer the snooker league sheets."""
    state = ctx.obj if isinstance(ctx.obj, State) else State()
    state.setdefault("league_name", league_name)
    state["out"] = Output(as_json)
    ctx.obj = state


# ---------------------------------------------------------------------- formatting helpers


def score_text(m: SnookerMatch) -> str:
    return f"{m.outcome.player1_score}-{m.outcome.player2_score}" if m.outcome else ""


def match_rows(matches: list[SnookerMatch]) -> str:
    rows = [
        [
            m.match_id[:8],
            m.round,
            m.group,
            m.player1.name,
            m.player2.name,
            score_text(m),
            m.winner.name if m.outcome else "",
            m.outcome.date.isoformat() if m.outcome and m.outcome.date else "",
        ]
        for m in matches
    ]
    return tabulate(rows, headers=["ID", "ROUND", "GROUP", "PLAYER1", "PLAYER2", "SCORE", "WINNER", "DATE"])


def match_detail(m: SnookerMatch) -> str:
    lines = [
        f"Match {m.match_id}",
        f"  round {m.round}, group {m.group}",
        f"  {m.player1.name} - {m.player2.name}",
    ]
    if m.outcome:
        played = f" on {m.outcome.date.isoformat()}" if m.outcome.date else ""
        lines.append(f"  result {score_text(m)}, winner {m.winner.name}{played}")
    else:
        lines.append("  unplayed")
    return "\n".join(lines)


def break_rows(breaks: list[BreakRecord]) -> str:
    rows = [[b.row, b.round, b.player, b.points, b.date.isoformat() if b.date else "", b.source] for b in breaks]
    return tabulate(rows, headers=["ROW", "ROUND", "PLAYER", "POINTS", "DATE", "FROM"])


def change_lines(changes: list[Change]) -> str:
    lines = []
    for c in changes:
        prefix = "" if c.applied else "[dry run] "
        where = f"{c.tab} row {c.row}" if c.row else c.tab
        if c.action == "update":
            diffs = [f"{k}: {c.before.get(k, '')!r} -> {v!r}" for k, v in c.after.items() if c.before.get(k, "") != v]
            lines.append(f"{prefix}update {where}: " + (", ".join(diffs) or "no change"))
        elif c.action == "append":
            lines.append(f"{prefix}append {where}: " + ", ".join(f"{k}={v}" for k, v in c.after.items() if v))
        else:
            lines.append(f"{prefix}delete {where}: " + ", ".join(f"{k}={v}" for k, v in c.before.items() if v))
    return "\n".join(lines)


def round_option(f):
    f = click.option("--all-rounds", is_flag=True, help="All rounds instead of one.")(f)
    return click.option("--round", "-r", "round_", type=int, help="Round number (default: current round).")(f)


# ---------------------------------------------------------------------- round


@cli.group("round")
def round_group():
    """League rounds."""


@round_group.command("show")
@pass_state
def round_show(state: State):
    """Current round, all rounds and the link to the current round's sheet."""
    league = state.league
    rounds = league.rounds()
    data = {
        "current_round": league.current_round,
        "rounds": [{"number": r.number, "start": r.start, "end": r.end} for r in rounds],
        "sheet_url": league.round_sheet_url(),
    }

    def human():
        table = tabulate([[r.number, r.start or "", r.end or ""] for r in rounds], headers=["ROUND", "START", "END"])
        return f"Current round: {league.current_round}\nSheet: {data['sheet_url']}\n\n{table}"

    state.out.emit(data, human)


# ---------------------------------------------------------------------- players


@cli.group("players")
def players_group():
    """Players of the league."""


@players_group.command("list")
@click.option("--group", "-g", help="Only players of this group.")
@pass_state
def players_list(state: State, group: Optional[str]):
    """Current players and their groups."""
    players = [p for p in state.league.players if not group or p.group == group]
    data = [{"name": p.name, "group": p.group} for p in players]
    state.out.emit(data, lambda: tabulate([[p.name, p.group] for p in players], headers=["PLAYER", "GROUP"]))


# ---------------------------------------------------------------------- matches


@cli.group("matches")
def matches_group():
    """Matches (fixtures and results)."""


@matches_group.command("list")
@round_option
@click.option("--group", "-g", help="Only matches of this group.")
@click.option("--status", type=click.Choice(["unplayed", "completed"]), help="Only unplayed or completed matches.")
@pass_state
def matches_list(state: State, round_: Optional[int], all_rounds: bool, group: Optional[str], status: Optional[str]):
    """List matches of the current round, or of the given round."""
    matches = state.league.matches(round=round_, all_rounds=all_rounds, group=group, status=status)
    state.out.emit([m.model_dump() for m in matches], lambda: match_rows(matches))


@matches_group.command("show")
@click.argument("match_id")
@pass_state
def matches_show(state: State, match_id: str):
    """One match, with the breaks recorded with its result. MATCH_ID may be a unique prefix (6+ characters)."""
    match = state.league.match(match_id)
    breaks = state.league.related_breaks(match)
    data = {**match.model_dump(), "breaks": [b.to_dict() for b in breaks]}

    def human():
        text = match_detail(match)
        if breaks:
            text += "\n\nBreaks recorded with the result:\n" + break_rows(breaks)
        return text

    state.out.emit(data, human)


# ---------------------------------------------------------------------- results


def dry_run_option(f):
    return click.option("--dry-run", is_flag=True, help="Show the changes without making them.")(f)


def parse_score(value: str) -> tuple[int, int]:
    parts = value.replace("–", "-").split("-")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        raise click.BadParameter(f"expected a score like 2-1, got {value!r}")
    return int(parts[0]), int(parts[1])


def _name_tokens(name: str) -> set[str]:
    """Ways to refer to a player: full name, each name, and each part of a hyphenated name."""
    lower = name.lower()
    return {lower, *lower.split(), *lower.replace("-", " ").split()}


def match_player(match: SnookerMatch, name: str) -> str:
    """Full name of the match player that NAME refers to: the full name or a part of it ("Jani", "Hauta-aho")."""
    players = [match.player1.name, match.player2.name]
    hits = [p for p in players if name.strip().lower() in _name_tokens(p)]
    if len(hits) != 1:
        raise click.BadParameter(f"{name!r} is not exactly one of the match players {players[0]}, {players[1]}")
    return hits[0]


def parse_break(match: SnookerMatch, value: str) -> tuple[str, int]:
    name, sep, points = value.rpartition(":")
    if not sep or not points.strip().isdigit():
        raise click.BadParameter(f"expected a break like 'Jani:45', got {value!r}")
    return match_player(match, name), int(points)


def write_result(state: State, match: SnookerMatch, changes: list[Change], dry_run: bool) -> None:
    data = {"match": match.model_dump(), "changes": [c.to_dict() for c in changes], "dry_run": dry_run}
    state.out.emit(data, lambda: match_detail(match) + "\n\n" + change_lines(changes))


@cli.group("results")
def results_group():
    """Match results."""


@results_group.command("record")
@click.argument("match_id")
@click.option("--score", "-s", required=True, help="Frames in the match's player order (player1-player2), e.g. 0-2.")
@click.option("--winner", "-w", help="Expected winner (name or part of it). Refuses if the score says otherwise.")
@click.option("--break", "-b", "breaks", multiple=True, help="Break as NAME:POINTS, e.g. 'Jani:45'. Repeatable.")
@click.option("--date", "-d", "played_on", type=click.DateTime(["%Y-%m-%d"]), help="Date played (default: today).")
@click.option("--log", default="", help="Text stored in the log column, e.g. the original SMS.")
@click.option("--overwrite", is_flag=True, help="Replace an existing result (its breaks are kept).")
@dry_run_option
@pass_state
def results_record(state: State, match_id, score, winner, breaks, played_on, log, overwrite, dry_run):
    """Record the result of a match. MATCH_ID may be a unique prefix (6+ characters)."""
    league = state.league
    match = league.match(match_id)
    player1_score, player2_score = parse_score(score)
    if winner:
        expected = match_player(match, winner)
        actual = match.player1.name if player1_score > player2_score else match.player2.name
        if expected != actual:
            raise click.BadParameter(
                f"score {score} makes {actual} the winner ({match.player1.name} - {match.player2.name}), "
                f"not {expected}",
                param_hint="--score/--winner",
            )
    match, changes = league.record_result(
        match.match_id,
        player1_score,
        player2_score,
        breaks=[parse_break(match, b) for b in breaks],
        date=played_on.date() if played_on else None,
        log=log,
        overwrite=overwrite,
        dry_run=dry_run,
    )
    write_result(state, match, changes, dry_run)


@results_group.command("clear")
@click.argument("match_id")
@click.option("--with-breaks", is_flag=True, help="Also remove the breaks recorded with the result.")
@dry_run_option
@pass_state
def results_clear(state: State, match_id, with_breaks, dry_run):
    """Return a match to unplayed. See `matches show` for the breaks recorded with the result."""
    match, changes = state.league.clear_result(match_id, remove_breaks=with_breaks, dry_run=dry_run)
    write_result(state, match, changes, dry_run)


# ---------------------------------------------------------------------- breaks


@cli.group("breaks")
def breaks_group():
    """Breaks."""


@breaks_group.command("list")
@round_option
@click.option("--player", "-p", help="Only breaks by this player (full name).")
@pass_state
def breaks_list(state: State, round_: Optional[int], all_rounds: bool, player: Optional[str]):
    """List breaks of the current round, or of the given round."""
    breaks = state.league.breaks(round=round_, all_rounds=all_rounds, player=player)
    state.out.emit([b.to_dict() for b in breaks], lambda: break_rows(breaks))


@breaks_group.command("add")
@click.option("--player", "-p", required=True, help="Player's full name.")
@click.option("--points", type=click.IntRange(1, 147), required=True)
@click.option("--date", "-d", "played_on", type=click.DateTime(["%Y-%m-%d"]), help="Date (default: today).")
@click.option("--round", "-r", "round_", type=int, help="Round number (default: current round).")
@dry_run_option
@pass_state
def breaks_add(state: State, player, points, played_on, round_, dry_run):
    """Add a break."""
    league = state.league
    brk = SnookerBreak(player=league.player(player), points=points)
    changes = league.add_breaks([brk], date=played_on.date() if played_on else None, round=round_, dry_run=dry_run)
    state.out.emit({"changes": [c.to_dict() for c in changes], "dry_run": dry_run}, lambda: change_lines(changes))


@breaks_group.command("remove")
@click.argument("row", type=int)
@click.option("--player", "-p", required=True, help="Player in that row (full name), as a safety check.")
@click.option("--points", type=int, required=True, help="Points in that row, as a safety check.")
@dry_run_option
@pass_state
def breaks_remove(state: State, row, player, points, dry_run):
    """Remove the break in ROW (see `breaks list`)."""
    change = state.league.remove_break(row, player, points, dry_run=dry_run)
    state.out.emit({"changes": [change.to_dict()], "dry_run": dry_run}, lambda: change_lines([change]))


# ---------------------------------------------------------------------- fixtures


@cli.group("fixtures")
def fixtures_group():
    """Fixtures: the matches of a round, generated in advance."""


@fixtures_group.command("generate")
@click.option("--round", "-r", "round_", type=int, required=True)
@dry_run_option
@pass_state
def fixtures_generate(state: State, round_, dry_run):
    """Add a match for every pair of players within each group. Pairs that already have a match are skipped."""
    new, changes = state.league.generate_fixtures(round_, dry_run=dry_run)
    verb = "Would add" if dry_run else "Added"

    def human():
        return f"{verb} {len(new)} fixtures for round {round_}" + (f"\n\n{match_rows(new)}" if new else "")

    state.out.emit({"fixtures": [m.model_dump() for m in new], "dry_run": dry_run}, human)


@fixtures_group.command("reset")
@click.option("--round", "-r", "round_", type=int, required=True)
@click.option("--yes", is_flag=True, help="Confirm deleting every match and result of the round.")
@dry_run_option
@pass_state
def fixtures_reset(state: State, round_, yes, dry_run):
    """Delete every match of a round, results included, and generate fresh fixtures. Test league only."""
    if not (yes or dry_run):
        raise click.UsageError("This deletes every match and result of the round; pass --yes to confirm.")
    changes = state.league.reset_round(round_, dry_run=dry_run)
    deleted = sum(c.action == "delete" for c in changes)
    added = sum(c.action == "append" for c in changes)
    verb = "Would delete" if dry_run else "Deleted"
    state.out.emit(
        {"deleted": deleted, "added": added, "changes": [c.to_dict() for c in changes], "dry_run": dry_run},
        lambda: f"{verb} {deleted} matches and added {added} fixtures for round {round_}",
    )


# ---------------------------------------------------------------------- sms


@cli.group("sms")
def sms_group():
    """Score messages, as the SMS bot handles them."""


def make_llm(settings):
    """The LLM client, imported only when needed: loading it takes a few seconds."""
    from .llm.inference import get_llm_client

    return get_llm_client(settings)


@sms_group.command("parse")
@click.argument("text")
@pass_state
def sms_parse(state: State, text: str):
    """Show what the bot would record and reply for TEXT. Never records anything or sends a message.

    Calls the LLM (Vertex AI), as the bot does."""
    from .sms import process_sms

    llm = make_llm(state.league.settings)
    result = process_sms(text, state.league, llm, dry_run=True)

    def human():
        lines = [f"Players: {' - '.join(p.name for p in result.players) if result.players else '-'}"]
        if result.inferred:
            i = result.inferred
            options = " | ".join(", ".join(m.options) or "?" for m in i.players)
            breaks = ", ".join(f"person {b.player}: {b.points}" for b in i.breaks) or "none"
            lines.append(f"LLM: {options}; score {i.player1_score}-{i.player2_score}; breaks {breaks}")
        if result.error:
            lines.append(f"Error: {type(result.error).__name__}: {getattr(result.error, 'detail', result.error)}")
        if result.changes:
            lines += ["", change_lines(result.changes)]
        if result.reply:
            lines += ["", "Reply:", result.reply]
        return "\n".join(lines)

    state.out.emit(result.to_dict(), human)


if __name__ == "__main__":
    cli()
