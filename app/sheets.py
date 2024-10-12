"""Google sheets API client for managing snooker scores."""

import os
from datetime import datetime
from itertools import combinations
from typing import List, Tuple

import google.auth
import gspread
import gspread.utils
import pytz

from .models import SnookerMatch, SnookerPlayer, MatchFixture

CURDIR = os.path.dirname(os.path.abspath(__file__))
SHEETS_DATE_FORMAT = "%d.%m.%Y"


def get_helsinki_timestamp():
    return datetime.now(pytz.timezone("Europe/Helsinki")).strftime("%Y-%m-%d %H:%M:%S")


def try_parse_date(date_str: str):
    """Tries to parse date from the assumed format. Returns original string if parsing fails."""
    try:
        return datetime.strptime(date_str, SHEETS_DATE_FORMAT).date()
    except ValueError:
        return date_str


class SnookerSheet:

    fixture_headers = [
        "id", "round", "group", "player1", "player2", "date", "player1_score", "player2_score", "winner", "log"  # fmt: skip
    ]

    def __init__(self, spreadsheet_id: str):
        credentials, project_id = google.auth.default(
            scopes=[
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
        )
        self.client = gspread.authorize(credentials)
        self.ss = self.client.open_by_key(spreadsheet_id)

        # assert that well-known assets exist
        assert self.fixtures_sheet
        assert self.breaks_sheet
        assert self.current_round
        assert len(self.current_players) > 0

    @property
    def fixtures_sheet(self) -> gspread.Worksheet:
        """Create if it doesn't exist and add headers."""
        if "_fixtures" not in [ws.title for ws in self.ss.worksheets()]:
            ws = self.ss.add_worksheet("_fixtures", rows=1, cols=10)
            ws.append_row(self.fixture_headers)
        return self.ss.worksheet("_fixtures")

    @property
    def breaks_sheet(self) -> gspread.Worksheet:
        return self.ss.worksheet("_breaks")

    @property
    def current_round(self) -> int:
        """Get the current round number."""
        rounds = self.ss.values_get("nr_rounds").get("values")
        today = datetime.now().date()
        for r in rounds:
            start_date = datetime.strptime(r[1], SHEETS_DATE_FORMAT).date()
            end_date = datetime.strptime(r[2], SHEETS_DATE_FORMAT).date()
            if start_date <= today <= end_date:
                return int(r[0])
        return None

    @property
    def current_players(self) -> List[SnookerPlayer]:
        """Get list of current players from spreadsheet."""
        players_rows = self.ss.values_get("nr_currentPlayers").get("values")
        if not players_rows:
            return RuntimeError("No players found in spreadsheet")
        header_order = ["name", "group"]
        return [
            SnookerPlayer(
                name=plr[header_order.index("name")],
                group=plr[header_order.index("group")],
            )
            for plr in players_rows
        ]

    @property
    def players_txt(self) -> str:
        """Newline-separated list of current players"""
        return "\n".join([plr.__llm_str__() for plr in self.current_players])

    def _unhide_all_columns(self, ws: gspread.Worksheet):
        """Unhide all columns in worksheet.

        This is necessary for data entry to work."""
        ws.unhide_columns(0, 20)

    def get_current_round_url(self) -> str:
        """Get URL of current round."""
        current_round = self.current_round
        if current_round is not None:
            sheet_name = f"ROUND {current_round}"
            try:
                url = self.ss.worksheet(sheet_name).url
                return url
            except gspread.WorksheetNotFound:
                return None
        else:
            # no current round, fall back on sheet URL
            return self.ss.url

    @staticmethod
    def days_since_1900(timestamp=None) -> str:
        """Generate Excel date value from timestamp"""
        if not timestamp:
            timestamp = datetime.now()
        return (timestamp - datetime(1899, 12, 30).date()).days

    def record_match(self, values: dict, passage: str, sender: str = None):
        """Record match to spreadsheet"""
        self._unhide_all_columns(self.fixtures_sheet)
        timestamp = get_helsinki_timestamp()
        log = r"\r".join([timestamp, str(sender), passage])
        ordered_values = [
            "FROM_TWILIO",
            self.current_round,
            values["group"],
            values["player1"],
            values["player2"],
            self.days_since_1900(values["date"]),
            values["player1_score"],
            values["player2_score"],
            values["winner"],
            log,
        ]
        self.fixtures_sheet.append_row(ordered_values)

        return True

    def record_break(self, break_: dict, passage: str = None, sender: str = None):
        """Record break to spreadsheet"""
        self._unhide_all_columns(self.fixtures_sheet)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # excel fields are: timestamp	from	passage	player	break	date    round
        ordered_values = [
            timestamp,
            sender,
            passage,
            break_["player"],
            break_["points"],
            self.days_since_1900(break_["date"]),
            self.current_round,
        ]
        self.breaks_sheet.append_row(ordered_values)

        return True

    def get_matches(self, round_: int = None, incomplete_only: bool = False) -> List[SnookerMatch]:
        if not round_:
            round_ = self.current_round
        fixtures_data = self.fixtures_sheet.get_all_records(default_blank=None)
        matches = []
        for fixture in fixtures_data:
            if fixture["round"] == round_:
                match = SnookerMatch(
                    date=try_parse_date(fixture.pop("date")),
                    player1=SnookerPlayer(name=fixture.pop("player1"), group=fixture.get("group")),
                    player2=SnookerPlayer(name=fixture.pop("player2"), group=fixture.get("group")),
                    **fixture,
                )
                if incomplete_only and match.winner:
                    continue
                matches.append(match)
        return matches

    def add_fixtures(self, round_: int):
        """Append sheet with fixtures for the current round."""
        # get players groupwise
        players = self.current_players

        # get unique groups
        groups = sorted(set([p.group for p in players]))

        # get fixtures for each group
        fixtures = []
        for group in groups:
            group_players = [p for p in players if p.group == group]
            for p1, p2 in combinations(group_players, 2):
                fixture = MatchFixture(
                    round=round_,
                    group=group,
                    player1=SnookerPlayer(name=p1.name, group=group),
                    player2=SnookerPlayer(name=p2.name, group=group),
                )
                fixtures.append(fixture)

        # append fixtures to sheet
        values = [fixture.dict(include=self.fixture_headers, by_alias=True) for fixture in fixtures]
        self.fixtures_sheet.append_rows(values)

    def get_match(self, round_: int, player1: str, player2: str) -> SnookerMatch:
        """Lookup fixture by round and players."""
        fixtures = self.get_matches(round_)
        for m in fixtures:
            if m.round == round_ and m.player1 == player1 and m.player2 == player2:
                return m
        return None

    def _get_match_data_by_id(self, match_id: str) -> Tuple[dict, int]:
        """Lookup match by ID. Return row data and row number."""
        # find the row where the fixture is located (in_column=1 means column A)
        match = self.fixtures_sheet.find(match_id, in_column=1)
        nth_row = match.row
        if not match:
            raise ValueError(f"Match with ID {match_id} not found")
        # get the row data
        values = self.fixtures_sheet.row_values(match.row)
        data = dict(zip(self.fixtures_sheet.row_values(1), values))
        return data, nth_row

    def get_match_by_id(self, match_id: str) -> SnookerMatch:
        match, _ = self._get_match_data_by_id(match_id)
        return SnookerMatch(
            date=try_parse_date(match.pop("date")),
            player1=SnookerPlayer(name=match.pop("player1"), group=match.get("group")),
            player2=SnookerPlayer(name=match.pop("player2"), group=match.get("group")),
            **match,
        )

    def record_match_outcome(self, id_: str, outcome: SnookerMatch):
        """Look up the fixture by ID and record outcome

        Assert that the fixture has not been recorded before. (no winner)

        Assert that player names according to sheet match the fixture.
        """
        # get the fixture data and row number per sheets
        fixture_data, nth_row = self._get_match_data_by_id(id_)
        if fixture_data["winner"]:
            raise ValueError(f"Match with ID {id_} already has a winner")
        assert fixture_data["player1"] == str(
            outcome.player1
        ), f"Player1 mismatch: expected {fixture_data['player1']}, got {outcome.player1}"
        assert fixture_data["player2"] == str(
            outcome.player2
        ), f"Player2 mismatch: expected {fixture_data['player2']}, got {outcome.player2}"

        outcome = SnookerMatch(**outcome.model_dump())
        for field in ["player1_score", "player2_score", "winner"]:
            col = self.fixtures_sheet.find(field, in_row=1).col
            self.fixtures_sheet.update_cell(
                nth_row,
                col,
                getattr(outcome, field),
            )

        return True
