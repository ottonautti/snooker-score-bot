"""The FastAPI app, with its services replaced by an in-memory league and fakes: no network access needed."""

from unittest.mock import AsyncMock, MagicMock

import freezegun
import pytest
from fastapi.testclient import TestClient
from requests.auth import HTTPBasicAuth

from snooker_score_bot.errors import MatchAlreadyCompleted
from snooker_score_bot.main import Services, app, get_services
from snooker_score_bot.monitoring import PushoverClient
from snooker_score_bot.settings import TestSettings
from tests.test_league import find, make_league
from tests.test_sms import jani_beats_mikko, llm_reading

API_SECRET = "test-secret"


@pytest.fixture(autouse=True)
def frozen_today():
    with freezegun.freeze_time("2026-11-12 18:00:00"):
        yield


@pytest.fixture
def services():
    settings = TestSettings()
    settings.API_SECRET = API_SECRET
    league = make_league()
    league.generate_fixtures(round=2)
    pushover = PushoverClient(user_key="u", api_token="t", enabled=True)
    pushover.send_notification = AsyncMock()
    return Services(settings=settings, league=league, llm=jani_beats_mikko(), twilio=MagicMock(), pushover=pushover)


@pytest.fixture
def client(services):
    app.dependency_overrides[get_services] = lambda: services
    # not used as a context manager, so the lifespan (which connects to the real services) doesn't run
    client = TestClient(app, raise_server_exceptions=True)
    client.auth = HTTPBasicAuth(username="", password=API_SECRET)
    yield client
    app.dependency_overrides.clear()


def sms(client, body):
    return client.post("/sms/scores", data={"Body": body, "From": "+1234567890"})


class TestSms:
    def test_recorded_then_already_played(self, client, services):
        response = sms(client, "Hauta-aho - Neuvonen 2-0")
        assert response.status_code == 201
        assert response.json()["match"]["winner"] == "Hauta-aho Jani"
        services.twilio.send_message.assert_called_once_with("+1234567890", response.json()["message"])
        assert services.pushover.send_notification.await_args.kwargs["title"] == "✅ SMS Processed"

        # a rejected message is answered with 200: an error status makes Twilio retry via the fallback URL
        response = sms(client, "Hauta-aho - Neuvonen 2-0")
        assert response.status_code == 200
        assert response.json()["error"] == {"type": "MatchAlreadyCompleted", "detail": MatchAlreadyCompleted.detail}
        assert "already been played" in response.json()["message"]

    def test_rejected_message_gets_one_reply_and_an_alert(self, client, services):
        services.llm = llm_reading([], [])  # nobody in the list
        response = sms(client, "Pekka - Matti 2-0")
        assert response.status_code == 200
        assert response.json()["error"]["type"] == "UnknownPlayersError"
        services.twilio.send_message.assert_called_once_with("+1234567890", response.json()["message"])
        services.pushover.send_notification.assert_awaited_once()
        assert services.pushover.send_notification.await_args.kwargs["title"] == "❌ SMS Failed"

    def test_crash_is_reported_and_returns_an_error(self, client, services):
        services.twilio.send_message.side_effect = RuntimeError("twilio down")
        client = TestClient(app, raise_server_exceptions=False)
        response = sms(client, "Hauta-aho - Neuvonen 2-0")
        assert response.status_code == 500 and response.json() == {"detail": "Internal server error"}
        assert "twilio down" in services.pushover.send_notification.await_args.kwargs["message"]


class TestApi:
    path = "/api/v2"

    def test_list_unplayed(self, client):
        data = client.get(f"{self.path}/matches?unplayed=true").json()
        assert data["round"] == 2 and len(data["matches"]) == 4
        assert all(m["state"] == "unplayed" for m in data["matches"])

    def test_post_scores_and_get(self, client, services):
        m = find(services.league, "Nurmi Jani", "Lundgren Mikko")
        body = {"player1_score": 2, "player2_score": 1, "breaks": [{"player": "player1", "points": 50}]}
        response = client.post(f"{self.path}/scores/{m.match_id}", json=body)
        assert response.status_code == 201
        posted = response.json()
        assert posted["winner"] == m.player1.name and posted["highest_break"] == 50

        response = client.post(f"{self.path}/scores/{m.match_id}", json=body)
        assert response.status_code == 409 and response.json()["detail"] == "Match already completed"

        got = client.get(f"{self.path}/matches/{m.match_id}").json()
        assert got["winner"] == posted["winner"] and got["outcome"]["player1_score"] == 2

    def test_invalid_breaks(self, client, services):
        m = find(services.league, "Nurmi Jani", "Lundgren Mikko")
        for brk in [{"player": "Trump Donald", "points": 100}, {"player": "player1", "score": 167}]:
            body = {"player1_score": 2, "player2_score": 1, "breaks": [brk]}
            assert client.post(f"{self.path}/scores/{m.match_id}", json=body).status_code == 422

    def test_scoreline_not_fitting_the_format_is_a_400(self, client, services):
        m = find(services.league, "Nurmi Jani", "Lundgren Mikko")
        client_no_raise = TestClient(app, raise_server_exceptions=False)
        client_no_raise.auth = client.auth
        body = {"player1_score": 3, "player2_score": 0, "breaks": []}
        response = client_no_raise.post(f"{self.path}/scores/{m.match_id}", json=body)
        assert response.status_code == 400
        assert "does not match the match format" in response.json()["detail"][0]

    def test_auth_required(self, client):
        client.auth = None
        assert client.get(f"{self.path}/matches").status_code == 401
        client.auth = HTTPBasicAuth(username="", password="wrong")
        assert client.get(f"{self.path}/matches").status_code == 401

    def test_legacy_v1_header_auth(self, client):
        client.auth = None
        assert client.get("/api/v1/matches", headers={"Authorization": API_SECRET}).status_code == 200
        assert client.get("/api/v1/matches", headers={"Authorization": "wrong"}).status_code == 401
        assert client.get("/api/v1/matches").status_code == 401

    def test_everything_refused_without_a_configured_secret(self, client, services):
        services.settings.API_SECRET = None
        client.auth = None
        assert client.get("/api/v1/matches").status_code == 401  # used to pass: None == None
        assert client.get(f"{self.path}/matches", auth=HTTPBasicAuth("", "")).status_code == 401


def test_sms_form_needs_body_and_sender(client):
    assert client.post("/sms/scores", data={"From": "+1234567890"}).status_code == 422
    assert client.post("/sms/scores", data={"Body": "", "From": "+1234567890"}).status_code == 422
    # Twilio's other form fields are ignored
    extra = {"Body": "Hauta-aho - Neuvonen 2-0", "From": "+1", "To": "+358000", "MessageSid": "SM1", "NumMedia": "0"}
    assert client.post("/sms/scores", data=extra).status_code == 201


class TestTwilioSignature:
    TOKEN = "twilio-auth-token"
    FORM = {"Body": "Hauta-aho - Neuvonen 2-0", "From": "+1234567890"}

    @pytest.fixture
    def signed_client(self, client, services):
        from twilio.request_validator import RequestValidator

        self.validator = RequestValidator(self.TOKEN)
        services.twilio.is_valid_request = self.validator.validate  # real check instead of the mock
        return client

    def post(self, client, signature, form=None, headers=None):
        headers = {"X-Twilio-Signature": signature, **(headers or {})}
        return client.post("/sms/scores", data=form or self.FORM, headers=headers)

    def test_signed_request_is_accepted(self, signed_client):
        signature = self.validator.compute_signature("http://testserver/sms/scores", self.FORM)
        assert self.post(signed_client, signature).status_code == 201

    def test_https_url_behind_cloud_run_proxy(self, signed_client):
        signature = self.validator.compute_signature("https://testserver/sms/scores", self.FORM)
        assert self.post(signed_client, signature, headers={"X-Forwarded-Proto": "https"}).status_code == 201

    def test_forged_or_tampered_requests_are_rejected(self, signed_client, services):
        assert self.post(signed_client, "").status_code == 403
        signature = self.validator.compute_signature("http://testserver/sms/scores", self.FORM)
        tampered = {**self.FORM, "Body": "Hauta-aho - Neuvonen 0-2"}
        assert self.post(signed_client, signature, form=tampered).status_code == 403
        assert services.league.matches(status="completed") == []
        services.twilio.send_message.assert_not_called()

    def test_check_can_be_turned_off(self, signed_client, services):
        services.settings.VERIFY_TWILIO_SIGNATURE = False
        assert self.post(signed_client, "").status_code == 201
