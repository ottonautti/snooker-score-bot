from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pytest import raises

from app.errors import InvalidMatchError, MatchAlreadyCompleted, MatchNotFound
from app.main import SETTINGS, app
from app.sheets import SnookerSheet

# Mock settings for testing
SETTINGS.SHEETID = "1JUicaU5OHi8HR49j9O4ex_rv3veAvadkaoeuEOw6ucY"
TEST_ROUND = 3


@pytest.fixture(autouse=True)
def no_requests(monkeypatch):
    """The tests here should not make any external requests."""
    monkeypatch.delattr("langchain.chains.base.Chain.invoke")


@pytest.fixture(scope="session")
def test_client():
    return TestClient(
        app=app,
        headers={"Authorization": SETTINGS.API_SECRET},
        raise_server_exceptions=True,
    )


@pytest.fixture(scope="class")
def prepared_sheet():
    sheet = SnookerSheet(SETTINGS.SHEETID)
    # double check that we are targeting the test sheet
    sheet.reset_fixtures(round=TEST_ROUND)
    yield sheet
    # Any cleanup tasks after each test
    pass


class TestSmsRoutes:
    """Tests for POST /sms/scores.

    This path involves inference by LLM about the match result from the SMS message.
    """

    TEST_SMS = {
        "Body": "Aatos voitti Joonaksen 2-1",
        "From": "+1234567890",
    }

    def test_sms_score_valid_inference(self, test_client, monkeypatch, prepared_sheet):
        """Test for valid inference by LLM"""
        mock_llm_response = {
            "player1": "Virtanen Aatos",
            "player2": "Mäkinen Joonas",
            "player1_score": 2,
            "player2_score": 1,
        }
        with patch("app.llm.inference.SnookerScoresLLM.infer", return_value=mock_llm_response) as mock_llm:
            response = test_client.post("/sms/scores", data=self.TEST_SMS)
            assert response.status_code == 201
            assert "message" in response.json()
            assert "match" in response.json()

            # attempting to post score for the same match a second time should raise a 409 Conflict
            response = test_client.post("/sms/scores", data=self.TEST_SMS)
            assert response.status_code == MatchAlreadyCompleted.status_code
            detail = response.json().get("detail")
            assert detail == MatchAlreadyCompleted.detail

    def test_sms_score_valid_inference_reversed_player_order(self, prepared_sheet, test_client):
        """Test for when the player order is reversed in the LLM inference"""
        with patch("app.main.SnookerScoresLLM.infer") as mock_llm:
            mock_llm.return_value = {
                "player1": "Mäkinen Joonas",
                "player2": "Virtanen Aatos",
                "player1_score": 1,
                "player2_score": 2,
            }
            response = test_client.post(
                "/sms/scores",
                data=self.TEST_SMS,
            )

    def test_sms_score_llm_infers_nonexisting_match(self, prepared_sheet, test_client):
        """InvalidMatchError should be raised as players are from different groups"""
        with patch("app.main.SnookerScoresLLM.infer") as mock_llm:
            mock_llm.return_value = {
                "player1": "Virtanen Aatos",
                "player2": "Rantanen Lauri",
                "player1_score": 2,
                "player2_score": 1,
            }
            response = test_client.post(
                "/sms/scores",
                data=self.TEST_SMS,
            )
            assert response.status_code == MatchNotFound.status_code
            detail = response.json().get("detail")
            assert detail == MatchNotFound.detail

    def test_sms_score_llm_hallucinates_players(self, prepared_sheet, test_client):
        """MatchNotFound should be raised as players are not found in the fixtures"""
        with patch("app.main.SnookerScoresLLM.infer") as mock_llm:
            mock_llm.return_value = {
                "player1": "Biden Joe",
                "player2": "Trump Donald",
                "player1_score": 2,
                "player2_score": 1,
            }
            response = test_client.post("/sms/scores", data=self.TEST_SMS)
            assert response.status_code == MatchNotFound.status_code
            detail = response.json().get("detail")
            assert detail == MatchNotFound.detail


class TestApiRoutes:
    """Tests for POST /api/v1/scores/{match_id}

    Tests for posting scores to a match twice:
    1. First time should succeed as match has no scores yet
    2. Second time should fail with 409 Conflict as match already has scores
    """

    path = "/api/v1"
    fixtures = None

    @classmethod
    def test_get_fixtures(cls, prepared_sheet, test_client):
        response = test_client.get(f"{cls.path}/fixtures")
        assert response.status_code == 200
        data = response.json()
        assert "round" in data
        assert "matches" in data
        # let's cache the fixtures for later tests, fetching them is expensive
        cls.fixtures = data["matches"]

    def test_post_scores(self, prepared_sheet, test_client):
        """Test for posting scores to a match"""
        if self.fixtures is None:
            self.test_get_fixtures(prepared_sheet, test_client)
        target_fixture = self.fixtures[0]
        match_id = target_fixture["id"]
        response = test_client.post(
            f"{self.path}/scores/{match_id}", json={"player1_score": 2, "player2_score": 1, "breaks": []}
        )
        data = response.json()
        assert response.status_code == 201
        assert "match" in data
        assert target_fixture["player1"] == data["match"]["player1"]
        assert target_fixture["player2"] == data["match"]["player2"]

        # attempting to post score for the same match a second time should raise a 409 Conflict
        response = test_client.post(
            f"{self.path}/scores/{match_id}", json={"player1_score": 2, "player2_score": 1, "breaks": []}
        )
        assert response.status_code == 409
        assert "detail" in response.json()
        assert response.json()["detail"] == "Match already completed"

    def test_post_scores_with_valid_breaks(self, prepared_sheet, test_client):
        """Test for posting scores to a match with breaks"""
        if self.fixtures is None:
            self.test_get_fixtures(prepared_sheet, test_client)
        target_fixture = self.fixtures[1]
        match_id = target_fixture["id"]
        response = test_client.post(
            f"{self.path}/scores/{match_id}",
            json={
                "player1_score": 2,
                "player2_score": 1,
                "breaks": [
                    {"player": "player1", "points": 50},
                    {"player": "player2", "points": 30},
                ],
            },
        )
        data = response.json()
        assert response.status_code == 201
        assert "match" in data
        assert target_fixture["player1"] == data["match"]["player1"]
        assert target_fixture["player2"] == data["match"]["player2"]
        assert data["match"]["highest_break"] == 50
        assert data["match"]["highest_break_player"] == target_fixture["player1"]

    def test_post_scores_with_invalid_breaks(self, prepared_sheet, test_client):
        """Test for posting scores to a match with invalid breaks"""
        if self.fixtures is None:
            self.test_get_fixtures(prepared_sheet, test_client)
        target_fixture = self.fixtures[2]
        match_id = target_fixture["id"]

        # wrong player
        response = test_client.post(
            f"{self.path}/scores/{match_id}",
            json={
                "player1_score": 2,
                "player2_score": 1,
                "breaks": [
                    {"player": "Trump Donald", "points": 100},
                ],
            },
        )
        assert response.status_code == 422
        assert "detail" in response.json()

        # too many points
        player1_name = target_fixture["player1"]
        response = test_client.post(
            f"{self.path}/scores/{match_id}",
            json={
                "player1_score": 2,
                "player2_score": 1,
                "breaks": [
                    {"player": player1_name, "score": 167},
                ],
            },
        )
        assert response.status_code == 422
        assert "detail" in response.json()
