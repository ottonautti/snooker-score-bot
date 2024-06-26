import logging
import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import SnookerPlayer
from app.settings import Settings
from app.sheets import SnookerSheet

from ..llm.fewshots_mock import MockFewShotData
from ..llm.inference import SnookerScoresLLM


class TestSettings(Settings):
    SHEETID = "12zoI6AQRvqB_t4rrmhgwsRT4RAlbJnKv3ovZgI_NtOY"


TEST_SETTINGS = TestSettings()

os.environ["TWILIO_NO_SEND"] = "True"

LLM_GOOGLE = SnookerScoresLLM(llm="vertexai")
LLM_OPENAI = SnookerScoresLLM(llm="openai")


class MockTwilio:
    def send_message(self, *args, **kwargs):
        logging.info("MockTwilio would send : %s", kwargs)
        return None


class MockSheet(SnookerSheet):
    def __init__(self):
        super().__init__(spreadsheet_id=TEST_SETTINGS.SHEETID)

    def get_current_players(self) -> list[SnookerPlayer]:
        return MockFewShotData.players


client = TestClient(app)
client.app.SETTINGS = TEST_SETTINGS

MOCK_TWILIO = MockTwilio()


def test_app_dryrun(monkeypatch):
    """Dryrun tests:

    * App can start up
    * App can get players from production sheet
    * App can call LLM.
    """
    # Act
    try:
        response = client.post(
            "/scores",
            data={
                "Body": "Huhtala - Andersson 2-1. Breikki 45, Huhtala.",
                "From": "+358123456789",
            },
        )
    except Exception as e:
        logging.error(e)

    assert response


def test_e2e(monkeypatch):
    """Tests that a successful request is handled correctly.

    LLM is mocked to return a mock match."""

    # Arrange
    monkeypatch.setattr("app.main.SnookerSheet", MockSheet)
    today = datetime.today()
    # count number of matches before test
    num_matches_before = len(MockSheet.matches_sheet.get_all_values())

    # Act

    # make the LLM return the mock match
    response = client.post(
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
            "passage_language": "fin",
            "date": today.strftime("%Y-%m-%d"),
            "group": "L1",
            "player1": "Huhtala Katja",
            "player2": "Andersson Leila",
            "player1_score": 2,
            "player2_score": 1,
            "winner": "Huhtala Katja",
            "highest_break": 45,
            "highest_break_player": "Huhtala Katja",
            "breaks": [{"date": today.strftime("%Y-%m-%d"), "player": "Huhtala Katja", "points": 45}],
        },
    }

    # check that the match was recorded to the sheet
    num_matches_after = len(MOCK_SHEET.matches_sheet.get_all_values())
    assert num_matches_after == num_matches_before + 1


# def read_passages():
#     with open("/home/otto/dev/otto/snooker-scores/local-only/test_passages.txt") as f:
#         yield from f.readlines()

# @pytest.mark.parametrize("passage", read_passages())
# def test_identical_inference_openai_vs_goole(passage: str):
#     production_players = PRODUCTION_SHEET.players_txt
#     assert LLM_OPENAI.infer(passage, production_players) == LLM_GOOGLE.infer(passage, production_players)


def adhoc_llm_tests(client: TestClient):

    response = client.post(
        "/scores",
        data={
            "Body": "Chiodo-jani hauta-aho 2-0",
            "From": "+358123456789",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # log response
    pytest.set_trace()
