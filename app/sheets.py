"""Google sheets API client for managing snooker scores."""

import os
from datetime import datetime

import google.auth
import gspread

from .models import SnookerPlayer

CURDIR = os.path.dirname(os.path.abspath(__file__))
DATE_FORMAT = "%d.%m.%Y"

class SnookerSheet(gspread.Spreadsheet):
    results_sheet_name = "_results"
    named_ranges = {
        "players": "nr_currentPlayers",
    }

    def __init__(self, spreadsheet_id: str):
        credentials, project_id = google.auth.default(
            scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        self.client = gspread.authorize(credentials)
        super().__init__(self.client, {"id": spreadsheet_id})

        # check that expected named ranges exist
        for name in self.named_ranges.values():
            if not name in [nr["name"] for nr in self.list_named_ranges()]:
                raise RuntimeError(f"Named range {name} not found in spreadsheet")

        # check that expected sheets exist
        self.results_sheet = self.worksheet(self.results_sheet_name)

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
    def players(self) -> list[SnookerPlayer]:
        return self.get_current_players()

    def record_match(self, values: dict, sender=None):
        """Record match to spreadsheet"""
        self._unhide_all_columns(self.results_sheet)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_days_since_1900 = (values.get("date") - datetime(1899, 12, 30).date()).days
        ordered_values = [
            r"\r".join([timestamp, str(sender), values["passage"]]),
            values["group"],
            values["player1"],
            values["player2"],
            values["player1_score"],
            values["player2_score"],
            values["winner"],
            values["highest_break"],
            values["break_owner"],
            date_days_since_1900,
        ]
        self.results_sheet.append_row(ordered_values)

        return True


if __name__ == "__main__":
    sheet = SnookerSheet(os.environ["GOOGLESHEETS_SHEETID"])
    print([str(plr) for plr in sheet.get_current_players()])
