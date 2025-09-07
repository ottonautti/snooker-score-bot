from copy import deepcopy
from unittest.mock import patch

import freezegun
import pytest
from fastapi.testclient import TestClient
from requests.auth import HTTPBasicAuth

from app.errors import InvalidMatchError, MatchAlreadyCompleted, MatchNotFound
from app.main import SETTINGS, app
from app.models import InferredMatch
from app.sheets import PreparedFixturesSnookerSheet

# Mock settings for testing
SETTINGS.SHEETID = "1JUicaU5OHi8HR49j9O4ex_rv3veAvadkaoeuEOw6ucY"
TEST_ROUND = 3



@pytest.fixture(autouse=True)
def no_requests(monkeypatch):
    """The tests here should not make any external requests."""
    monkeypatch.delattr("langchain.chains.base.Chain.invoke")


@pytest.fixture(scope="class")
def test_client():
    test_client = TestClient(app, raise_server_exceptions=True)
    test_client.auth = HTTPBasicAuth(username="", password=SETTINGS.API_SECRET)
    return test_client


@pytest.fixture(scope="class")
def prepared_sheet():
    sheet = PreparedFixturesSnookerSheet(SETTINGS.SHEETID)
    # double check that we are targeting the test sheet
    sheet.reset_fixtures(round=TEST_ROUND)
    yield sheet
    # Any cleanup tasks after each test
    pass

@freezegun.freeze_time("2025-10-01")
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
        mock_inference = InferredMatch(
            player1="Virtanen Aatos",
            player2="Mäkinen Joonas",
            player1_score=2,
            player2_score=1,
            winner="Virtanen Aatos",
            group="L1",
        )
        with patch("app.main.SnookerScoresLLM.infer", return_value=mock_inference):
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
        mock_inference = InferredMatch(
            player1="Mäkinen Joonas",
            player2="Virtanen Aatos",
            player1_score=1,
            player2_score=2,
            winner="Virtanen Aatos",
            group="L1",
        )
        with patch("app.main.SnookerScoresLLM.infer", return_value=mock_inference):
            response = test_client.post(
                "/sms/scores",
                data=self.TEST_SMS,
            )

    def test_sms_score_llm_infers_nonexisting_match(self, prepared_sheet, test_client):
        """InvalidMatchError should be raised as players are from different groups"""
        mock_inference = InferredMatch(
            player1="Virtanen Aatos",
            player2="Rantanen Lauri",
            player1_score=2,
            player2_score=1,
            winner="Virtanen Aatos",
            group="L1",
        )
        with patch("app.main.SnookerScoresLLM.infer", return_value=mock_inference):
            response = test_client.post(
                "/sms/scores",
                data=self.TEST_SMS,
            )
            assert response.status_code == MatchNotFound.status_code
            detail = response.json().get("detail")
            assert detail == MatchNotFound.detail

    def test_sms_score_llm_hallucinates_players(self, prepared_sheet, test_client):
        """MatchNotFound should be raised as players are not found in the fixtures"""
        mock_inference = InferredMatch(
            player1="Biden Joe",
            player2="Trump Donald",
            player1_score=2,
            player2_score=1,
            winner="Biden Joe",
            group="L1",
        )
        with patch("app.main.SnookerScoresLLM.infer", return_value=mock_inference):
            response = test_client.post("/sms/scores", data=self.TEST_SMS)
            assert response.status_code == MatchNotFound.status_code
            detail = response.json().get("detail")
            assert detail == MatchNotFound.detail

@freezegun.freeze_time("2025-10-01")
class TestApiRoutes:
    """Tests for POST /api/v*/scores/{match_id}

    Tests for posting scores to a match twice:
    1. First time should succeed as match has no scores yet
    2. Second time should fail with 409 Conflict as match already has scores
    """

    API_VERSION = "v2"
    path = f"/api/{API_VERSION}"
    fixtures = None

    @classmethod
    def test_get_all_unplayed_matches(cls, prepared_sheet, test_client):
        response = test_client.get(f"{cls.path}/matches?unplayed=true")
        assert response.status_code == 200
        data = response.json()
        assert "round" in data
        assert "matches" in data
        # let's cache the fixtures for later tests, fetching them is expensive
        cls.fixtures = data["matches"]
        if not cls.fixtures:
            raise ValueError("No unplayed matches found in the test sheet")
        assert len(cls.fixtures) > 0
        assert all(fixture["state"] == "unplayed" for fixture in cls.fixtures)

    def test_get_unplayed_match(self, prepared_sheet, test_client):
        """Test for getting a single match, before it's outcome has been recorded."""
        if self.fixtures is None:
            self.test_get_all_unplayed_matches(prepared_sheet, test_client)
        fixture = self.fixtures[0]
        match_id = fixture["id"]
        response = test_client.get(f"{self.path}/matches/{match_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "unplayed"
        assert data["completed"] is False
        assert fixture["player1"] == data["player1"]
        assert fixture["player2"] == data["player2"]
        assert data["winner"] is None

    def test_post_scores_and_get(self, prepared_sheet, test_client):
        """Test for posting scores to a match"""
        if self.fixtures is None:
            self.test_get_all_unplayed_matches(prepared_sheet, test_client)
        fixture = self.fixtures[0]
        match_id = fixture["id"]
        response = test_client.post(
            f"{self.path}/scores/{match_id}", json={"player1_score": 2, "player2_score": 1, "breaks": []}
        )
        post_response = response.json()
        assert response.status_code == 201
        assert fixture["player1"] == post_response["player1"]
        assert fixture["player2"] == post_response["player2"]

        # attempting to post score for the same match a second time should raise a 409 Conflict
        response = test_client.post(
            f"{self.path}/scores/{match_id}", json={"player1_score": 2, "player2_score": 1, "breaks": []}
        )
        assert response.status_code == 409
        assert "detail" in response.json()
        assert response.json()["detail"] == "Match already completed"

        # get the match again to check that the outcome was
        response = test_client.get(f"{self.path}/matches/{match_id}")
        assert response.status_code == 200
        get_response = response.json()

        # apart from outcome.breaks and outcome.date, the responses should be identical
        post_outcome = post_response.pop("outcome")
        get_outcome = get_response.pop("outcome")
        assert post_response == get_response
        assert post_outcome["player1_score"] == get_outcome["player1_score"]
        assert post_outcome["player2_score"] == get_outcome["player2_score"]

    def test_post_scores_with_valid_breaks(self, prepared_sheet, test_client):
        """Test for posting scores to a match with breaks"""
        if self.fixtures is None:
            self.test_get_all_unplayed_matches(prepared_sheet, test_client)
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
        assert target_fixture["player1"] == data["player1"]
        assert target_fixture["player2"] == data["player2"]
        assert data["highest_break"] == 50
        assert data["highest_break_player"] == target_fixture["player1"]

    def test_post_scores_with_invalid_breaks_raises(self, prepared_sheet, test_client):
        """Test for posting scores to a match with invalid breaks"""
        if self.fixtures is None:
            self.test_get_all_unplayed_matches(prepared_sheet, test_client)
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


class TestApiRoutesUnauthenticated:
    path = TestApiRoutes.path

    def test_get_matches_no_auth(self, test_client):
        """Test for posting scores without authentication"""
        # get matches
        test_client.auth = None
        response = test_client.get(f"{self.path}/matches")
        assert response.status_code == 401

    def test_get_matches_wrong_auth(self, test_client):
        """Test for posting scores with wrong authentication"""
        test_client.auth = HTTPBasicAuth(username="", password="wrong")
        response = test_client.get(f"{self.path}/matches")
        assert response.status_code == 401
