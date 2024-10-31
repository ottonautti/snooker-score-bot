from ..llm.fewshots_mock import MockFewShotData
from app.sheets import SnookerSheet
import pytest
import gspread
import os
from fastapi.testclient import TestClient
from app.main import app
# https://docs.google.com/spreadsheets/d/19mlmzBIdSQXA98pjEV8oeqetUxGSJJyzj_JtG-UaB2U
TEST_TEMPLATE_SHEET_ID = "19mlmzBIdSQXA98pjEV8oeqetUxGSJJyzj_JtG"

# create a new google sheets and copy the following sheets from test template sheet:
# - _matches
# - _matches_flatten
# - _breaks


cred_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
CLIENT = gspread.service_account(filename=cred_file)

@pytest.fixture
def test_sheet(scope="module"):
    sheet = CLIENT.copy(TEST_TEMPLATE_SHEET_ID)
    players_sheet = sheet.worksheet("_players")
    players_sheet.update("A4", [[p.name, p.group] for p in MockFewShotData.players])
    yield SnookerSheet(sheet.id)
    # CLIENT.del_spreadsheet(sheet.id)


@pytest.fixture(scope="module")
def test_client():
    client = TestClient(app)
    yield client


def test_make_fixtures(test_sheet, test_client):
    sheet = test_sheet
    sheet.make_fixtures()
    assert sheet.current_round == 1
    matches = test_client.get("/matches")
    # build dict of groups to players (MockFewShotData.players)
    groups = {}
    for p in MockFewShotData.players:
        groups.setdefault(p.group, []).append(p)

    # check that the number of matches is correct
    for group, players in groups.items():
        n = len(players)
        assert len([m for m in matches.json() if m["group"] == group]) == n * (n - 1) / 2

    assert matches.status_code == 200
    assert len(matches.json()) == 2





def test_update_match_outcome(test_sheet):


def test_update_breaks(test_sheet):
