"""Google sheets API client for managing snooker scores."""

import os
import random
import string
from datetime import datetime
from itertools import combinations

import google.auth
import gspread
import gspread.utils
import pytz
from pydantic import BaseModel
from pydantic.fields import Field

from .models import MatchOutcome, SnookerPlayer

CURDIR = os.path.dirname(os.path.abspath(__file__))
DATE_FORMAT = "%d.%m.%Y"


def get_helsinki_timestamp():
    return datetime.now(pytz.timezone("Europe/Helsinki")).strftime("%Y-%m-%d %H:%M:%S")


class Matchup(MatchOutcome):
    """Interface for Sheets matchup data."""

    id_: str = Field(default_factory=lambda: Matchup.generate_id(), alias="id")

    @property
    def winner(self) -> str:
        if self.player1_score == self.player2_score:
            return None
        return self.player1 if self.player1_score > self.player2_score else self.player2

    @staticmethod
    def generate_id(length: int = 6) -> str:
        """Generate a random ID for the matchup."""
        return "".join(
            random.choices("abcdefghjkmnpqrstuvwxyz" + string.digits, k=length)
        )


class SnookerSheet:
    matchups_sheet_name = "_matchups"
    breaks_sheet_name = "_breaks"
    named_ranges = {"players": "nr_currentPlayers", "rounds": "nr_rounds"}

    def __init__(self, spreadsheet_id: str):
        credentials, project_id = google.auth.default(
            scopes=[
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
        )
        self.client = gspread.authorize(credentials)
        self.ss = self.client.open_by_key(spreadsheet_id)

        # check that expected named ranges exist
        for name in self.named_ranges.values():
            if not name in [nr["name"] for nr in self.ss.list_named_ranges()]:
                raise RuntimeError(f"Named range `{name}` not found in spreadsheet")

        # check that expected sheets exist
        self.matchups_sheet = self.ss.worksheet(self.matchups_sheet_name)
        self.breaks_sheet = self.ss.worksheet(self.breaks_sheet_name)

    def _unhide_all_columns(self, ws: gspread.Worksheet):
        """Unhide all columns in worksheet.

        This is necessary for data entry to work."""
        ws.unhide_columns(0, 20)

    def get_current_players(self) -> list[SnookerPlayer]:
        """Get list of current players from spreadsheet."""
        players_rows = self.ss.values_get(self.named_ranges["players"]).get("values")
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
        return "\n".join([plr._gn for plr in self.get_current_players()])

    @property
    def current_round(self) -> int:
        """Get the current round number."""
        rounds = self.ss.values_get(self.named_ranges["rounds"]).get("values")
        today = datetime.now().date()
        for r in rounds:
            start_date = datetime.strptime(r[1], DATE_FORMAT).date()
            end_date = datetime.strptime(r[2], DATE_FORMAT).date()
            if start_date <= today <= end_date:
                return int(r[0])
        return None

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
        self._unhide_all_columns(self.matchups_sheet)
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
        self.matchups_sheet.append_row(ordered_values)

        return True

    def record_break(self, break_: dict, passage: str = None, sender: str = None):
        """Record break to spreadsheet"""
        self._unhide_all_columns(self.matchups_sheet)
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

    def get_matchups(self, round_: int) -> list[Matchup]:
        matchups_data = self.ss.worksheet(self.matchups_sheet_name).get_all_records()
        return [Matchup(**m) for m in matchups_data if m["round"] == round_]

    def add_matchups(self, round_: int):
        """Append _matchups sheet with matchups for the current round."""
        # get players groupwise
        players = self.get_current_players()

        # get unique groups
        groups = sorted(set([p.group for p in players]))
        column_order = ["id", "round", "group", "player1", "player2"]

        # get matchups for each group
        matchups = []
        for group in groups:
            group_players = [p for p in players if p.group == group]
            for p1, p2 in combinations(group_players, 2):
                matchup = Matchup(
                    id=Matchup.generate_id(),
                    round=round_,
                    group=group,
                    player1=p1.name,
                    player2=p2.name,
                )
                matchups.append(matchup)

        # append matchups to sheet
        values = [matchup.dict(by_alias=True) for matchup in matchups]
        self.ss.worksheet(self.matchups_sheet_name).append_rows(values)

    def get_matchup(self, round_: int, player1: str, player2: str) -> Matchup:
        """Lookup matchup by round and players."""
        matchups = self.get_matchups(round_)
        for m in matchups:
            if m.round == round_ and m.player1 == player1 and m.player2 == player2:
                return m
        return None

    def get_matchup_by_id(self, match_id: str) -> Matchup:
        """Lookup matchup by ID."""
        # find the row where the matchup is located (in_column=1 means column A)
        match = self.matchups_sheet.find(match_id, in_column=1)
        if not match:
            raise ValueError(f"Matchup with ID {match_id} not found")
        # get the row data
        values = self.matchups_sheet.row_values(match.row)
        dict_ = dict(zip(self.matchups_sheet.row_values(1), values))
        return Matchup(**dict_)

    def record_matchup_outcome(self, id_: str, outcome: MatchOutcome):
        """Look up the matchup by ID and record the result.

        Assert that the matchup has not been recorded before. (no winner)

        Assert that player names according to sheet match the matchup.
        """

        matchup = self.get_matchup_by_id(id_)
        # find the target row
        row = self.matchups_sheet.find(id_).row
        # get the row data
        values = self.matchups_sheet.row_values(row)
        # create a dict from the row data
        dict_ = dict(zip(self.matchups_sheet.row_values(1), values))
        # create a Matchup object from the dict
        matchup = Matchup(**dict_)
        # check that the matchup has not been recorded before
        if matchup.winner:
            raise ValueError(f"Matchup with ID {id_} already has a winner")
        if matchup.player1 != str(outcome.player1):
            raise ValueError(f"Player names do not match the matchup")
        if matchup.player2 != str(outcome.player2):
            raise ValueError(f"Player names do not match the matchup")
        # record the result
        for field in ["player1_score", "player2_score", "winner"]:
            col = self.matchups_sheet.find(field, in_row=1).col
            self.matchups_sheet.update_cell(
                row,
                col,
                getattr(outcome, field),
            )


if __name__ == "__main__":
    sheet = SnookerSheet("1yp-LgqPKfcsTzD5kXmc7-dOQR6-KVC2iYiy5Om9Zdm0")
    sheet.get_matchup_by_id("btxuz")
