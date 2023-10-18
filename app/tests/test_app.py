import logging
import os
from unittest.mock import patch

import freezegun
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import SnookerMatch, SnookerPlayer
from app.sheets import SnookerSheet

from ..llm.fewshots_mock import MockFewShotData

os.environ["TWILIO_NO_SEND"] = "True"

# TODO: test writing to Google sheet, but not on production file
GOOGLESHEETS_SHEETID_TEST = "12zoI6AQRvqB_t4rrmhgwsRT4RAlbJnKv3ovZgI_NtOY"


class MockTwilio:
    def send_message(self, *args, **kwargs):
        logging.info("MockTwilio would send : %s", kwargs)
        return None


class MockSheet(SnookerSheet):
    def __init__(self, *args, **kwargs):
        super().__init__(spreadsheet_id=GOOGLESHEETS_SHEETID_TEST, *args, **kwargs)

    def get_current_players(self) -> list[SnookerPlayer]:
        return MockFewShotData.players

    def record_match(self, *args, **kwargs):
        pass


class MockLLM:
    def __init__(self, *args, **kwargs):
        pass

    def run(self, *args, **kwargs):
        """Should be patched"""
        raise NotImplementedError("Patch this method to return a SnookerMatch object.")


app.dependency_overrides = {
    "get_twilio": MockTwilio,
    "get_sheet": MockSheet,
    "get_llm": MockLLM,
}


@pytest.fixture
def test_client_with_mocks():
    with TestClient(app) as test_client:
        yield test_client


# def test_app_dryrun(test_client_with_mocks):
#     """Dryrun tests:

#     * App can start up
#     * App can get players from production sheet
#     * App can call LLM.
#     """
#     # Arrange

#     from app.main import app

#     # otherwise mock sheet is used
#     overrides = app.dependency_overrides.copy()
#     del app.dependency_overrides["get_sheet"]

#     # Act
#     try:
#         response = test_client_with_mocks.post(
#             "/scores", data={"Body": "Huhtala - Andersson 2-1. Breikki 45, Huhtala.", "From": "+358123456789"}
#         )
#     # Validation error
#     except ValidationError as e:
#         # this is fine
#         pass
#     except:
#         # raise everything else
#         raise
#     finally:
#         # revert dependency overrides
#         app.dependency_overrides = overrides


# @freezegun.freeze_time("2023-09-11")
def test_successful_request(test_client_with_mocks):
    """Tests that a successful request is handled correctly.

    LLM is mocked to return a mock match."""

    # Arrange
    mock_match = SnookerMatch.construct(  # skips validation
        group="L1",
        player1="Huhtala Katja",
        player2="Andersson Leila",
        player1_score=2,
        player2_score=1,
        winner="Huhtala Katja",
        highest_break=45,
        break_owner="Huhtala Katja",
    )

    # Act

    # make the LLM return the mock match
    with patch.object(MockLLM, "run", return_value=mock_match):
        response = test_client_with_mocks.post(
            "/scores", data={"Body": "Huhtala - Andersson 2-1. Breikki 45, Huhtala.", "From": "+358123456789"}
        )

    # Assert
    assert response.status_code == 201
    assert response.json() == {
        "status": "Match recorded",
        "match": {
            "date": "2023-09-11",
            "group": "L1",
            "player1": "Huhtala Katja",
            "player2": "Andersson Leila",
            "player1_score": 2,
            "player2_score": 1,
            "winner": "Huhtala Katja",
            "highest_break": 45,
            "break_owner": "Huhtala Katja",
        },
    }
