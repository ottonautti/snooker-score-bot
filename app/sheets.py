"""Google sheets API client for managing snooker scores."""

import os
import random
import string
from datetime import datetime
from itertools import combinations
from typing import List, Tuple

import google.auth
import gspread
import gspread.utils
import pytz
from pydantic.fields import Field

from .models import MatchOutcome, SnookerPlayer

CURDIR = os.path.dirname(os.path.abspath(__file__))
DATE_FORMAT = "%d.%m.%Y"


def get_helsinki_timestamp():
    return datetime.now(pytz.timezone("Europe/Helsinki")).strftime("%Y-%m-%d %H:%M:%S")


class MatchFixture(MatchOutcome):
    """Interface for match fixture data."""

    id_: str = Field(default_factory=lambda: MatchFixture.generate_id(), alias="id")

    @property
    def winner(self) -> str:
        if self.player1_score == self.player2_score:
            return None
        return self.player1 if self.player1_score > self.player2_score else self.player2

    @staticmethod
    def generate_id(length: int = 5) -> str:
        """Generate a random ID for the fixture."""
        return "".join(random.choices("abcdefghjkmnpqrstuvwxyz" + string.digits, k=length))


class SnookerSheet:

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
            start_date = datetime.strptime(r[1], DATE_FORMAT).date()
            end_date = datetime.strptime(r[2], DATE_FORMAT).date()
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

    def get_fixtures(self, round_: int) -> List[MatchFixture]:
        if not round_:
            round_ = self.current_round
        fixtures_data = self.fixtures_sheet.get_all_records()
        return [MatchFixture(**m) for m in fixtures_data if m["round"] == round_]

    def add_fixtures(self, round_: int):
        """Append _fixtures sheet with fixtures for the current round."""
        # get players groupwise
        players = self.current_players

        # get unique groups
        groups = sorted(set([p.group for p in players]))
        column_order = ["id", "round", "group", "player1", "player2"]

        # get fixtures for each group
        fixtures = []
        for group in groups:
            group_players = [p for p in players if p.group == group]
            for p1, p2 in combinations(group_players, 2):
                fixture = MatchFixture(
                    id=MatchFixture.generate_id(),
                    round=round_,
                    group=group,
                    player1=p1.name,
                    player2=p2.name,
                )
                fixtures.append(fixture)

        # append fixtures to sheet
        values = [fixture.dict(by_alias=True) for fixture in fixtures]
        self.fixtures_sheet.append_rows(values)

    def get_fixture(self, round_: int, player1: str, player2: str) -> MatchFixture:
        """Lookup fixture by round and players."""
        fixtures = self.get_fixtures(round_)
        for m in fixtures:
            if m.round == round_ and m.player1 == player1 and m.player2 == player2:
                return m
        return None

    def get_fixture_by_id(self, match_id: str) -> Tuple[MatchFixture, str]:
        """Lookup fixture by ID."""
        # find the row where the fixture is located (in_column=1 means column A)
        match = self.fixtures_sheet.find(match_id, in_column=1)
        sheet_row = match.row
        if not match:
            raise ValueError(f"MatchFixture with ID {match_id} not found")
        # get the row data
        values = self.fixtures_sheet.row_values(match.row)
        dict_ = dict(zip(self.fixtures_sheet.row_values(1), values))
        fixture = MatchFixture(**dict_)
        return fixture, sheet_row

    def record_match_outcome(self, id_: str, outcome: MatchOutcome):
        """Look up the fixture by ID and record the result.

        Assert that the fixture has not been recorded before. (no winner)

        Assert that player names according to sheet match the fixture.
        """
        # get the fixture data and row number per sheets
        fixture_data, nth_row = self.get_fixture_by_id(id_)
        if fixture_data["winner"]:
            raise ValueError(f"MatchFixture with ID {id_} already has a winner")
        assert fixture_data["player1"] == str(
            outcome.player1
        ), f"Player1 mismatch: expected {fixture_data['player1']}, got {outcome.player1}"
        assert fixture_data["player2"] == str(
            outcome.player2
        ), f"Player2 mismatch: expected {fixture_data['player2']}, got {outcome.player2}"

        # form a MatchFixture object from the fixture data and outcome
        outcome = MatchFixture(**fixture_data, **outcome.model_dump())
        for field in ["player1_score", "player2_score", "winner"]:
            col = self.fixtures_sheet.find(field, in_row=1).col
            self.fixtures_sheet.update_cell(
                nth_row,
                col,
                getattr(outcome, field),
            )


if __name__ == "__main__":
    sheet = SnookerSheet("1yp-LgqPKfcsTzD5kXmc7-dOQR6-KVC2iYiy5Om9Zdm0")
    sheet.get_fixture_by_id("btxuz")
