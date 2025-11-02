"""Google sheets API client for managing snooker scores."""

import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from functools import cached_property
from itertools import combinations
from typing import Any, List, Optional, Tuple

import google.auth
import gspread
import pytz

from snooker_score_bot.errors import (
    MatchAlreadyCompleted,
    MatchFixtureMismatchError,
    MatchNotFound,
)
from snooker_score_bot.settings import Settings, SixRedSettings

from .models import MatchFixture, MatchOutcome, SnookerBreak, SnookerMatch, SnookerPlayer

CURDIR = os.path.dirname(os.path.abspath(__file__))
SHEETS_DATE_FORMAT = "%d.%m.%Y"


def get_helsinki_timestamp():
    return datetime.now(pytz.timezone("Europe/Helsinki")).strftime("%Y-%m-%d %H:%M:%S")


def try_parse_date(value: Any) -> Optional[datetime.date]:
    """Safely parse a value from a spreadsheet cell into a date object."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, int):
        # Convert from Excel date serial number
        try:
            return (datetime(1899, 12, 30) + timedelta(days=value)).date()
        except (OverflowError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.strptime(value, SHEETS_DATE_FORMAT).date()
        except (TypeError, ValueError):
            return None
    return None


class SnookerSheetBase(ABC):
    def __init__(self, spreadsheet_id: str):
        credentials, project_id = google.auth.default(
            scopes=[
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
        )

        self.spreadsheet_id = spreadsheet_id
        self.client = gspread.authorize(credentials)
        self.gsheet = self.client.open_by_key(spreadsheet_id)

        # assert that well-known assets exist
        assert self.matches_sheet
        assert self.breaks_sheet
        assert len(self.current_players) > 0

    @cached_property
    def matches_sheet(self) -> gspread.Worksheet:
        """Create if it doesn't exist and add headers."""
        return self.gsheet.worksheet("_matches")

    @cached_property
    def breaks_sheet(self) -> gspread.Worksheet:
        return self.gsheet.worksheet("_breaks")

    @cached_property
    def current_players(self) -> List[SnookerPlayer]:
        """Get list of current players from spreadsheet.

        Assumes column order 'group', 'name' in the 'nr_currentPlayers' sheet."""
        players_rows = self.gsheet.values_get("nr_currentPlayers").get("values")
        if not players_rows:
            raise RuntimeError("No players found in spreadsheet")
        return [
            SnookerPlayer(name=row[0], group=row[1])
            for row in players_rows
            if len(row) >= 2
        ]

    @property
    def current_round(self) -> int:
        return None

    def get_current_round_sheet_id(self) -> str:
        """Get the sheet ID for the current round sheet."""
        try:
            round_sheet = self.gsheet.worksheet(f"ROUND {self.current_round}")
            pass
        except gspread.WorksheetNotFound:
            return None
        return round_sheet.id

    def _unhide_all_columns(self, ws: gspread.Worksheet):
        """Unhide all columns in worksheet.

        This is necessary for data entry to work."""
        ws.unhide_columns(0, 20)

    def delete_matches(self, force=False):
        """Delete everything from _matches, apart from headers.

        Att.! This should only ever be used for testing purposes."""

        # prompt user for confirmation when doing this for the first time
        sheet = self.matches_sheet
        if not force:
            print(
                f"Are you sure you want to clear all results from {self.spreadsheet_id}?"
            )
            if input("Type 'yes' to confirm: ") != "yes":
                return False
        self._unhide_all_columns(sheet)
        row_count = sheet.row_count
        sheet.batch_clear([f"A2:Z{row_count}"])

    @staticmethod
    def days_since_1900(timestamp=None) -> str:
        """Generate Excel date value from timestamp"""
        if not timestamp:
            timestamp = datetime.now()
        return (timestamp - datetime(1899, 12, 30).date()).days

    def record_breaks(self, breaks: list[SnookerBreak], date=None):
        """Record break to spreadsheet"""
        self._unhide_all_columns(self.matches_sheet)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # excel fields are: timestamp	from	passage	player	break	date    round

        def record_break(b):
            column_values = [
                timestamp,
                "admin",  # source
                "",
                b.player.name,
                b.points,
                self.days_since_1900(date) if date else "",
                self.current_round,
            ]
            self.breaks_sheet.append_row(column_values)

        for b in breaks:
            record_break(b)

        return True

    def get_matches(
        self,
        round: int = None,
        group: str = None,
        unplayed_only=False,
        completed_only=False,
    ) -> List[SnookerMatch]:
        if not round:
            round = self.current_round
        rows = self.matches_sheet.get_all_records(default_blank=None)
        if round:
            rows = [f for f in rows if f["round"] == round]
        if group:
            rows = [f for f in rows if f["group"] == group]
        matches = []
        for fixture in rows:
            outcome = None
            if fixture.get("winner"):
                outcome = MatchOutcome(
                    date=try_parse_date(fixture.get("date")),
                    player1_score=fixture.get("player1_score"),
                    player2_score=fixture.get("player2_score"),
                    winner=fixture.get("winner"),
                )
            else:
                outcome = None
            match = SnookerMatch.from_storage(
                match_id=fixture.get("id"),
                round=fixture.get("round"),
                group=fixture.get("group"),
                player1=SnookerPlayer(
                    name=fixture.get("player1"), group=fixture.get("group")
                ),
                player2=SnookerPlayer(
                    name=fixture.get("player2"), group=fixture.get("group")
                ),
                outcome=outcome,
            )
            matches.append(match)
        if unplayed_only:
            return [m for m in matches if not m.completed]
        elif completed_only:
            return [m for m in matches if m.completed]

        return matches

    def _get_match_data_by_id(self, match_id: str) -> Tuple[dict, int]:
        """Lookup match by ID. Return row data and row number."""
        # find the row where the fixture is located (in_column=1 means column A)
        match = self.matches_sheet.find(match_id, in_column=1)
        if not match:
            raise LookupError(f"Match with ID {match_id} not found")
        # get the row data
        values = self.matches_sheet.row_values(match.row)
        data = dict(zip(self.matches_sheet.row_values(1), values))
        nth_row = match.row
        return data, nth_row

    def get_match_by_id(self, match_id: str) -> SnookerMatch:
        data, _ = self._get_match_data_by_id(match_id)
        match = SnookerMatch.from_storage(
            match_id=match_id,
            date=try_parse_date(data.pop("date", None)),
            player1=SnookerPlayer(name=data.pop("player1"), group=data.get("group")),
            player2=SnookerPlayer(name=data.pop("player2"), group=data.get("group")),
            round=data.pop("round"),
            group=data.pop("group"),
        )
        if data.get("winner"):
            match.outcome = MatchOutcome(
                date=try_parse_date(data.get("date")),
                player1_score=data.get("player1_score"),
                player2_score=data.get("player2_score"),
                winner=data.get("winner"),
            )
        return match

    @abstractmethod
    def record_match(self, *arg, **kwargs):
        """This method must be implemented in subclasses"""
        pass

    def lookup_match_by_player_names(
        self, players=tuple[str, str], round: int = None
    ) -> SnookerMatch:
        """Lookup match by player names and round number."""
        if round is None:
            round = self.current_round
        assert len(players) == 2, "Provide exactly two player names"
        assert players[0] != players[1], "Players must be different"
        matches = self.get_matches(round=round)
        for match in matches:
            if match.player1.name in players and match.player2.name in players:
                return match
        return None

    def assert_match_not_completed(self, match: SnookerMatch):
        """Assert that match is not found in the sheet."""
        if match := self.lookup_match_by_player_names(
            (match.player1.name, match.player2.name)
        ):
            if match.completed:
                raise MatchAlreadyCompleted()


class InsertMatchSnookerSheet(SnookerSheetBase):
    """Snooker sheet that does not require fixtures to be prepared in advance.

    Enables players to join the league at any time and play matches without
    waiting for fixtures to be created.
    """

    current_round = 1

    def record_match(self, match: SnookerMatch, log: str = None):
        """Inserts match outcome into the sheet without fixtures."""
        self.assert_match_not_completed(match)
        if match.outcome.breaks:
            self.record_breaks(match.outcome.breaks, date=match.outcome.date)
        headers = self.matches_sheet.row_values(1)
        row = {
            "id": match.match_id,
            "group": match.player1.group,
            "player1": match.player1.name,
            "player2": match.player2.name,
            "player1_score": match.outcome.player1_score,
            "player2_score": match.outcome.player2_score,
            "winner": match.winner.name,
            "date": self.days_since_1900(match.outcome.date),
            "round": match.round,
            "log": log or "",
        }
        values = [row.get(header, "") for header in headers]
        self.matches_sheet.append_row(values)
        return match


class PreparedFixturesSnookerSheet(SnookerSheetBase):
    """Snooker sheet that uses match fixtures prepared in advance.

    Players are known in advance and fixtures are created for each round."""

    @cached_property
    def current_round(self) -> int:
        """Get the current round number."""
        rounds = self.gsheet.values_get("nr_rounds").get("values")
        today = datetime.now().date()
        for r in sorted(rounds, key=lambda x: int(x[0]), reverse=True):
            round = int(r[0])
            start_date = datetime.strptime(r[1], SHEETS_DATE_FORMAT).date()
            end_date = datetime.strptime(r[2], SHEETS_DATE_FORMAT).date()
            if today >= start_date:
                return round
        return None

    def get_fixtures(self) -> List[MatchFixture]:
        return self.get_matches(unplayed_only=True)

    def make_fixtures(self, round: int):
        """Append sheet with fixtures for the current round."""
        players = self.current_players
        # unique groups
        groups = {p.group for p in players}

        # get fixtures for each group
        fixtures = []
        for group in sorted(groups):
            group_players = [p for p in players if p.group == group]
            for p1, p2 in combinations(group_players, 2):
                fixture = MatchFixture(
                    round=round,
                    group=group,
                    player1=SnookerPlayer(name=p1.name, group=group),
                    player2=SnookerPlayer(name=p2.name, group=group),
                )
                fixtures.append(fixture)

        # get sheet headers
        headers = self.matches_sheet.row_values(1)
        #  ['id', 'round', 'group', 'player1', 'player2', 'date', 'player1_score', 'player2_score', 'winner', 'log']

        # fmt: off
        def fixture_row(f):
            return [
                f"{f.match_id}" if header == 'id' else
                int(round) if header == 'round' else
                f"{f.group}" if header == 'group' else
                f"{f.player1}" if header == 'player1' else
                f"{f.player2}" if header == 'player2' else
                ""  # for any other header
                for header in headers
            ]
        # fmt: on
        values = list(fixture_row(f) for f in fixtures)
        self.matches_sheet.append_rows(values)

    def reset_fixtures(self, round: int = None):
        """Clear all fixtures for the current round."""
        if not round:
            round = self.current_round
        self.delete_matches(force=True)
        self.make_fixtures(round)

    def update_match_by_id(self, m_id: str, updates: dict):
        """Update match fields by ID with the provided updates dictionary."""
        # get the fixture data and row number per sheets
        fixture_data, nth_row = self._get_match_data_by_id(m_id)

        for field, value in updates.items():
            col = self.matches_sheet.find(field, in_row=1).col
            self.matches_sheet.update_cell(nth_row, col, value)

    def record_match(self, match: SnookerMatch, log: str = None):
        """Persist the pre-validated match outcome to the spreadsheet.

        Assert that the fixture has not been recorded before. (no winner)

        Assert that player names according to sheet match the fixture.
        """
        self.assert_match_not_completed(match)
        fixture: SnookerMatch = self.lookup_match_by_player_names(
            (match.player1, match.player2)
        )
        if not fixture:
            raise MatchNotFound()
        # if player order is reverse of fixture, swap them in the match
        if (
            match.player2 == fixture.player1.name
            and match.player1 == fixture.player2.name
        ):
            match.reverse_players()
        # if players still not matching, raise
        if (
            match.player1 != fixture.player1.name
            or match.player2 != fixture.player2.name
        ):
            raise MatchFixtureMismatchError("Players do not match those in fixture")

        m_id = fixture.match_id
        sheets_match = self.get_match_by_id(m_id)
        if sheets_match.winner:
            raise ValueError(f"Match {m_id} (round {match.round}) already has a winner")
        if sheets_match.player1 != match.player1:
            raise ValueError(
                f"Player1 mismatch: expected {sheets_match['player1']}, got {match.player1}"
            )
        if sheets_match.player2 != match.player2:
            raise ValueError(
                f"Player2 mismatch: expected {sheets_match['player2']}, got {match.player2}"
            )

        self.record_breaks(match.outcome.breaks, date=match.outcome.date)

        updates = {
            "date": self.days_since_1900(match.outcome.date),
            "player1_score": match.outcome.player1_score,
            "player2_score": match.outcome.player2_score,
            "winner": match.winner.name,
            "log": log or "",
        }
        self.update_match_by_id(m_id, updates)

        return match


def get_sheet_client(settings: Settings) -> SnookerSheetBase:
    """Get a Google Sheets client with default credentials."""
    sheet_id = settings.SHEETID
    if isinstance(settings, SixRedSettings):
        sheet_type = InsertMatchSnookerSheet
    else:
        sheet_type = PreparedFixturesSnookerSheet
    if not sheet_id:
        raise ValueError("Google Sheets ID is not set in settings")
    return sheet_type(spreadsheet_id=sheet_id)
