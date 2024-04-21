"""Google sheets API client for managing snooker scores."""

import os
import pytz
from datetime import datetime

import google.auth
import gspread

from .models import SnookerPlayer


def get_helsinki_timestamp():
    return datetime.now(pytz.timezone("Europe/Helsinki")).strftime("%Y-%m-%d %H:%M:%S")


CURDIR = os.path.dirname(os.path.abspath(__file__))
DATE_FORMAT = "%d.%m.%Y"


class SnookerSheet(gspread.Spreadsheet):
    results_sheet_name = "_matches"
    breaks_sheet_name = "_breaks"
    named_ranges = {
        "players": "nr_currentPlayers",
        "rounds": "nr_rounds",
    }

    def __init__(self, spreadsheet_id: str):
        credentials, project_id = google.auth.default(
            scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        self.client = gspread.authorize(credentials)
        super().__init__(self.client.http_client, {"id": spreadsheet_id})

        # check that expected named ranges exist
        for name in self.named_ranges.values():
            if not name in [nr["name"] for nr in self.list_named_ranges()]:
                raise RuntimeError(f"Named range `{name}` not found in spreadsheet")

        # check that expected sheets exist
        self.matches_sheet = self.worksheet(self.results_sheet_name)
        self.breaks_sheet = self.worksheet(self.breaks_sheet_name)

    def _unhide_all_columns(self, ws: gspread.Worksheet):
        """Unhide all columns in worksheet.

        This is necessary for data entry to work."""
        ws.unhide_columns(0, 20)

    def get_current_players(self) -> list[SnookerPlayer]:
        """Get list of current players from spreadsheet."""
        players_rows = self.values_get(self.named_ranges["players"]).get("values")
        if not players_rows:
            return RuntimeError("No players found in spreadsheet")
        return [SnookerPlayer(name=plr[0], group=plr[1]) for plr in players_rows]

    @property
    def players_txt(self) -> str:
        """Newline-separated list of current players"""
        return "\n".join([plr._gn for plr in self.get_current_players()])

    def get_current_round_url(self) -> str:
        """Get URL of current round."""
        rounds = self.values_get(self.named_ranges["rounds"]).get("values")
        # [['1', '6.9.2023', '8.10.2023'], ['2', '10.10.2023', '12.11.2023'], ...
        today = datetime.now().date()
        for r in rounds:
            start_date = datetime.strptime(r[1], DATE_FORMAT).date()
            end_date = datetime.strptime(r[2], DATE_FORMAT).date()
            if start_date <= today <= end_date:
                sheet_name = f"ROUND {r[0]}"
                try:
                    url = self.worksheet(sheet_name).url
                    break
                except gspread.WorksheetNotFound:
                    return None
        else:
            # no current round, fall back on sheet URL
            url = self.url
        return url

    @staticmethod
    def days_since_1900(timestamp) -> str:
        """Generate Excel date value from timestamp"""
        return (timestamp - datetime(1899, 12, 30).date()).days

    def record_match(self, values: dict, passage: str, sender: str = None):
        """Record match to spreadsheet"""
        self._unhide_all_columns(self.matches_sheet)
        timestamp = get_helsinki_timestamp()
        ordered_values = [
            r"\r".join([timestamp, str(sender), passage]),
            values["group"],
            values["player1"],
            values["player2"],
            values["player1_score"],
            values["player2_score"],
            values["winner"],
            values.get("highest_break", ""),
            values.get("highest_break_player", ""),
            self.days_since_1900(values["date"]),
        ]
        self.matches_sheet.append_row(ordered_values)

        return True

    def record_break(self, break_: dict, passage: str = None, sender: str = None):
        """Record break to spreadsheet"""
        self._unhide_all_columns(self.matches_sheet)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # excel fields are: timestamp	from	passage	player	break	date
        ordered_values = [
            timestamp,
            sender,
            passage,
            break_["player"],
            break_["points"],
            self.days_since_1900(break_["date"]),
        ]
        self.breaks_sheet.append_row(ordered_values)

        return True


if __name__ == "__main__":
    sheet = SnookerSheet(os.environ["GOOGLESHEETS_SHEETID"])
    print([str(plr) for plr in sheet.get_current_players()])
