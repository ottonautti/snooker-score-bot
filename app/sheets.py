"""Google sheets API client for managing snooker scores."""

import os
from datetime import datetime
from itertools import combinations
from typing import List, Tuple

import google.auth
import gspread
import gspread.utils
import pytz

from .models import SnookerMatch, SnookerPlayer

CURDIR = os.path.dirname(os.path.abspath(__file__))
SHEETS_DATE_FORMAT = "%d.%m.%Y"


def get_helsinki_timestamp():
    return datetime.now(pytz.timezone("Europe/Helsinki")).strftime("%Y-%m-%d %H:%M:%S")


def try_parse_date(date_str: str):
    """Tries to parse date from the assumed format. Returns original string if parsing fails."""
    try:
        return datetime.strptime(date_str, SHEETS_DATE_FORMAT).date()
    except (TypeError, ValueError):
        return None


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
        assert self.matches_sheet
        assert self.breaks_sheet
        assert self.current_round
        assert len(self.current_players) > 0

    @property
    def matches_sheet(self) -> gspread.Worksheet:
        """Create if it doesn't exist and add headers."""
        return self.ss.worksheet("_matches")

    @property
    def breaks_sheet(self) -> gspread.Worksheet:
        return self.ss.worksheet("_breaks")

    @property
    def current_round(self) -> int:
        """Get the current round number."""
        rounds = self.ss.values_get("nr_rounds").get("values")
        today = datetime.now().date()
        for r in sorted(rounds, key=lambda x: int(x[0]), reverse=True):
            round = int(r[0])
            start_date = datetime.strptime(r[1], SHEETS_DATE_FORMAT).date()
            end_date = datetime.strptime(r[2], SHEETS_DATE_FORMAT).date()
            if today >= start_date:
                return round
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
        return "\n".join([plr.__llm_str__ for plr in self.current_players])

    def _unhide_all_columns(self, ws: gspread.Worksheet):
        """Unhide all columns in worksheet.

        This is necessary for data entry to work."""
        ws.unhide_columns(0, 20)

    def get_current_roundurl(self) -> str:
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
        self._unhide_all_columns(self.matches_sheet)
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
        self.matches_sheet.append_row(ordered_values)

        return True

    def record_break(self, break_: dict, passage: str = None, sender: str = None):
        """Record break to spreadsheet"""
        self._unhide_all_columns(self.matches_sheet)
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
