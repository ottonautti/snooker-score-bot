import os
from unittest.mock import patch


import pytest
from fastapi.testclient import TestClient

from .llm.fewshots_mock import MockFewShotData
from .models import SnookerMatch, SnookerPlayer
from .twilio_client import TwilioInboundMessage

os.environ["TWILIO_NO_SEND"] = "True"


# mock classes for unit testing
# can be initialized with no env. variables
class MockTwilio:
    def __init__(self):
        self.mock_twilio = None


class MockSheet:
    def __init__(self, *args, **kwargs):
        pass

    def get_current_players(self) -> list[SnookerPlayer]:
        return MockFewShotData.players

    def record_match(self, *args, **kwargs):
        pass


class MockLLM:
    def __init__(self, *args, **kwargs):
        pass


@pytest.fixture(scope="module")
def client():
    with (
        patch("app.twilio_client.Twilio", MockTwilio),
        patch("app.sheets.SnookerSheet", MockSheet),
        patch("app.llm.inference.SnookerScoresLLM", MockLLM),
    ):
        from app import main

        yield TestClient(main.app)


def test_successful_request(client):
    # arrange
    mock_match = SnookerMatch(
        group="1",
        player1="Huhtala Katja",
        player2="Andersson Leila",
        player1_score=2,
        player2_score=1,
        winner="Huhtala Katja",
        highest_break=45,
        break_owner="Huhtala Katja",
    )
    msg = TwilioInboundMessage(body="Huhtala - Andersson 2-1. Breikki 45, Huhtala.", sender="+358123456789")

    # act
    with patch("app.LLM.infer_match") as mock_llm:
        mock_llm.return_value = mock_match
        response = client.post("/scores", data=msg.dict())

    # assert
    assert response.status_code == 200
    assert response.json() == {
        "status": "Match recorded",
        "match": {
            "group": "1",
            "player1": "Huhtala Katja",
            "player2": "Andersson Leila",
            "player1_score": 2,
            "player2_score": 1,
            "winner": "Huhtala Katja",
            "highest_break": 45,
            "break_owner": "Huhtala Katja",
        },
    }

    mock_llm.assert_called_once_with(msg.body)
