"""Common test assets."""

# pylint: disable=redefined-outer-name
import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.models import SnookerPlayer
from app.sheets import SnookerSheet

from ..llm.fewshots_mock import MockFewShotData

# If we ever want to test writing to a real sheet, we can safely use this sheet ID
GOOGLESHEETS_SHEETID_TEST = "169U2owGfzOZP47UIUwauf8MVtUkjGotif5MzsxWfvLQ"


class MockTwilio:
    def __init__(self):
        self.mock_twilio = None

    def send_message(self, *args, **kwargs):
        logging.info("MockTwilio would send : %s", kwargs)
        return None


@pytest.fixture
def mock_twilio():
    return MockTwilio()


class MockSheet(SnookerSheet):
    def __init__(self, *args, **kwargs):
        super().__init__(spreadsheet_id=GOOGLESHEETS_SHEETID_TEST, *args, **kwargs)

    def get_current_players(self) -> list[SnookerPlayer]:
        return MockFewShotData.players

    def record_match(self, *args, **kwargs):
        pass


@pytest.fixture
def mock_sheet():
    return MockSheet()


class MockLLM:
    def __init__(self, *args, **kwargs):
        pass

    def run(self, *args, **kwargs):
        raise NotImplementedError("Patch this method with `return_value`.")


@pytest.fixture
def mock_llm():
    return MockLLM()


@pytest.fixture
def test_client_with_mocks(mock_twilio, mock_sheet, mock_llm):
    with (
        patch("app.twilio_client.Twilio", return_value=mock_twilio),
        patch("app.sheets.SnookerSheet", return_value=mock_sheet),
        patch("app.llm.inference.SnookerScoresLLM", return_value=mock_llm),
    ):
        from app import main

        yield TestClient(main.app)


@pytest.fixture
def real_llm_with_mock_players(mock_players):
    from app.llm.inference import SnookerScoresLLM

    return SnookerScoresLLM(players=MockFewShotData.players)
