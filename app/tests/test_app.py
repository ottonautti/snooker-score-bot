import json
import logging
import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_sheet, get_twilio
from app.models import SnookerPlayer
from app.sheets import SnookerSheet

from ..llm.fewshots_mock import MockFewShotData
from ..llm.inference import SnookerScoresLLM

os.environ["TWILIO_NO_SEND"] = "True"

# TODO: test writing to Google sheet, but not on production file
GOOGLESHEETS_SHEETID_PROD = os.environ["GOOGLESHEETS_SHEETID"]
GOOGLESHEETS_SHEETID_TEST = "12zoI6AQRvqB_t4rrmhgwsRT4RAlbJnKv3ovZgI_NtOY"

PRODUCTION_SHEET = SnookerSheet(spreadsheet_id=GOOGLESHEETS_SHEETID_PROD)
LLM_GOOGLE = SnookerScoresLLM(llm="vertexai")
LLM_OPENAI = SnookerScoresLLM(llm="openai")


class MockTwilio:
    def send_message(self, *args, **kwargs):
        logging.info("MockTwilio would send : %s", kwargs)
        return None


class MockSheet(SnookerSheet):
    def __init__(self):
        super().__init__(spreadsheet_id=GOOGLESHEETS_SHEETID_TEST)

    def get_current_players(self) -> list[SnookerPlayer]:
        return MockFewShotData.players


app.dependency_overrides = {
    get_twilio: MockTwilio,
    get_sheet: MockSheet,
}


@pytest.fixture
def client_with_mocks():
    with TestClient(app) as test_client:
        yield test_client


def test_app_dryrun(client_with_mocks):
    """Dryrun tests:

    * App can start up
    * App can get players from production sheet
    * App can call LLM.
    """
    # Arrange

    from app.main import app

    # otherwise mock sheet is used
    overrides = app.dependency_overrides.copy()
    del app.dependency_overrides[get_sheet]

    # Act
    try:
        response = client_with_mocks.post(
            "/scores",
            data={
                "Body": "Huhtala - Andersson 2-1. Breikki 45, Huhtala.",
                "From": "+358123456789",
            },
        )
    finally:
        # revert dependency overrides
        app.dependency_overrides = overrides

    assert response


def test_e2e(client_with_mocks: TestClient):
    """Tests that a successful request is handled correctly.

    LLM is mocked to return a mock match."""

    # Arrange
    today = datetime.today()
    sheet = SnookerSheet(spreadsheet_id=GOOGLESHEETS_SHEETID_TEST)
    # count number of matches before test
    num_matches_before = len(sheet.matches_sheet.get_all_values())

    # Act

    # make the LLM return the mock match
    response = client_with_mocks.post(
        "/scores",
        data={
            "Body": "Huhtala - Andersson 2-1. Breikki 45, Huhtala.",
            "From": "+358123456789",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    # Assert
    assert response.status_code == 201
    assert response.json() == {
        "status": "Match recorded",
        "match": {
            "date": today.strftime("%Y-%m-%d"),
            "group": "L1",
            "player1": "Huhtala Katja",
            "player2": "Andersson Leila",
            "player1_score": 2,
            "player2_score": 1,
            "winner": "Huhtala Katja",
            "highest_break": 45,
            "highest_break_player": "Huhtala Katja",
            "breaks": [{"player": "Huhtala Katja", "points": 45}],
        },
    }

    # check that the match was recorded to the sheet
    num_matches_after = len(sheet.matches_sheet.get_all_values())
    assert num_matches_after == num_matches_before + 1



def read_passages():
    with open("/home/otto/dev/otto/snooker-scores/local-only/test_passages.txt") as f:
        yield from f.readlines()

@pytest.mark.parametrize("passage", read_passages())
def test_identical_inference_openai_vs_goole(passage: str):
    production_players = PRODUCTION_SHEET.players_blob
    assert LLM_OPENAI.infer(passage, production_players) == LLM_GOOGLE.infer(passage, production_players)