"""Spreadsheet storage backends.

The league lives in a Google Sheet. All access goes through `SheetBackend` so that the league logic can be tested
against `MemoryBackend` without network access.

Rows and columns are 1-based, as in the spreadsheet. Values are read as displayed (strings) and written raw: numbers
stay numbers (dates are written as serial numbers and shown in the column's own format) and text is never
reinterpreted, e.g. a log message "2-0" does not become a date.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

Value = Any
Row = list[str]


class SheetBackend(ABC):
    @abstractmethod
    def get_values(self, range_name: str) -> list[Row]:
        """All values of a worksheet (by title) or a named range, as strings."""

    @abstractmethod
    def get_row(self, tab: str, row: int) -> Row:
        """One row of a worksheet."""

    @abstractmethod
    def update_cells(self, tab: str, row: int, values: dict[int, Value]) -> None:
        """Write the given columns of one row in a single request. Other columns are left untouched."""

    @abstractmethod
    def append_rows(self, tab: str, rows: list[list[Value]]) -> None:
        """Append rows after the last row of the worksheet."""

    @abstractmethod
    def delete_rows(self, tab: str, rows: list[int]) -> None:
        """Delete the given rows."""

    @abstractmethod
    def tab_id(self, title: str) -> Optional[int]:
        """Worksheet id (gid) for links, or None if there is no such worksheet."""


def _column_letter(col: int) -> str:
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


class GspreadBackend(SheetBackend):
    def __init__(self, spreadsheet_id: str):
        import google.auth
        import gspread

        credentials, _ = google.auth.default(
            scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        self.spreadsheet_id = spreadsheet_id
        self.gsheet = gspread.authorize(credentials).open_by_key(spreadsheet_id)
        # gspread fetches the spreadsheet's metadata again for every worksheet(title) lookup; load them all once
        self._worksheets = {ws.title: ws for ws in self.gsheet.worksheets()}
        self._tab_ids: dict[str, int] = {title: ws.id for title, ws in self._worksheets.items()}

    def _ws(self, title: str):
        if title not in self._worksheets:
            self._worksheets[title] = self.gsheet.worksheet(title)
        return self._worksheets[title]

    def get_values(self, range_name: str) -> list[Row]:
        return self.gsheet.values_get(range_name).get("values", [])

    def get_row(self, tab: str, row: int) -> Row:
        return self._ws(tab).row_values(row)

    def update_cells(self, tab: str, row: int, values: dict[int, Value]) -> None:
        if not values:
            return
        data = [{"range": f"{_column_letter(col)}{row}", "values": [[value]]} for col, value in values.items()]
        self._ws(tab).batch_update(data, value_input_option="RAW")

    def append_rows(self, tab: str, rows: list[list[Value]]) -> None:
        if rows:
            self._ws(tab).append_rows(rows, value_input_option="RAW")

    def delete_rows(self, tab: str, rows: list[int]) -> None:
        """Remove rows by moving the rows below them up and clearing the leftover rows at the bottom.

        Sheet rows are never actually deleted: that would shift ranges in formulas that refer to this tab
        (and the API refuses to delete the last data row). Cells are read as raw values so that rewriting them
        keeps them as they were. Refuses to move formulas, which could change meaning when moved."""
        doomed = set(rows)
        if not doomed:
            return
        ws = self._ws(tab)
        values = ws.get_all_values(value_render_option="FORMULA")
        first = min(doomed)
        tail = [row for n, row in enumerate(values[first - 1 :], start=first) if n not in doomed]
        if any(isinstance(v, str) and v.startswith("=") for row in values[first - 1 :] for v in row):
            raise ValueError(f"Refusing to delete rows of {tab}: rows from {first} down contain formulas")
        width = max((len(r) for r in values), default=1)
        if tail:
            padded = [row + [""] * (width - len(row)) for row in tail]
            ws.update(padded, f"A{first}", value_input_option="RAW")
        cleared_from = first + len(tail)
        ws.batch_clear([f"A{cleared_from}:{_column_letter(width)}{len(values)}"])

    def tab_id(self, title: str) -> Optional[int]:
        """Worksheet ids never change, so found ids are cached. Missing tabs are looked up again next time."""
        import gspread

        if title not in self._tab_ids:
            try:
                self._tab_ids[title] = self.gsheet.worksheet(title).id
            except gspread.WorksheetNotFound:
                return None
        return self._tab_ids[title]


class MemoryBackend(SheetBackend):
    """In-memory spreadsheet for tests. Named ranges are plain entries in `tabs`."""

    def __init__(self, tabs: dict[str, list[list[Value]]]):
        self.tabs = {name: [[_display(v) for v in row] for row in rows] for name, rows in tabs.items()}

    def get_values(self, range_name: str) -> list[Row]:
        return [list(row) for row in self.tabs[range_name]]

    def get_row(self, tab: str, row: int) -> Row:
        rows = self.tabs[tab]
        return list(rows[row - 1]) if row <= len(rows) else []

    def update_cells(self, tab: str, row: int, values: dict[int, Value]) -> None:
        target = self.tabs[tab][row - 1]
        for col, value in values.items():
            while len(target) < col:
                target.append("")
            target[col - 1] = _display(value)

    def append_rows(self, tab: str, rows: list[list[Value]]) -> None:
        self.tabs[tab].extend([_display(v) for v in row] for row in rows)

    def delete_rows(self, tab: str, rows: list[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            del self.tabs[tab][row - 1]

    def tab_id(self, title: str) -> Optional[int]:
        return abs(hash(title)) % 10**9 if title in self.tabs else None


def _display(value: Value) -> str:
    return "" if value is None else str(value)
