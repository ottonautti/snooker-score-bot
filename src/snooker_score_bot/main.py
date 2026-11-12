"""FastAPI app for recording snooker match outcomes reported by users."""

import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import ValidationError

from .errors import MatchAlreadyCompleted
from .league import League
from .llm.inference import SnookerScoresLLM, get_llm_client
from .models import (
    ScoreRequest,
    SnookerMatch,
    SnookerMatchList,
)
from .monitoring import PushoverClient, get_pushover_client
from .settings import Settings, get_settings
from .sms import process_sms
from .twilio_client import Twilio, TwilioSms, get_twilio_client
from .utils import ok_created

DEBUG = bool(os.environ.get("SNOOKER_DEBUG", False))


@dataclass
class Services:
    """The app's connections to the outside world, created once at startup."""

    settings: Settings
    league: League
    llm: SnookerScoresLLM
    twilio: Twilio
    pushover: PushoverClient


def create_services(settings: Optional[Settings] = None) -> Services:
    settings = settings or get_settings()
    return Services(
        settings=settings,
        league=League(settings),
        llm=get_llm_client(settings),
        twilio=get_twilio_client(settings),
        pushover=get_pushover_client(settings),
    )


def setup_logging():
    """Sets up logging for the app"""
    import google.cloud.logging

    client = google.cloud.logging.Client()
    client.setup_logging()  # registers handler with built-in logging
    if DEBUG:  # when running locally, output to stdout
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
        logging.getLogger().setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to Cloud Logging, the sheet, Gemini, Twilio and Pushover when the server starts."""
    setup_logging()
    app.state.services = create_services()
    yield


def get_services(request: Request) -> Services:
    """Dependency for the services; tests replace it through app.dependency_overrides."""
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]

app = FastAPI(
    version="1.0.0",
    title="Snooker Scores API",
    description="API for recording Groove Snooker League match outcomes",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _check_secret(given: Optional[str], services: Services) -> None:
    """Constant-time comparison with the API secret. Everything is refused if no secret is configured."""
    expected = services.settings.API_SECRET
    if not expected or not given or not secrets.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthorized")


def authorize_v1(services: ServicesDep, authorization: Annotated[Optional[str], Header()] = None):
    """Legacy API: the secret as the whole Authorization header."""
    _check_secret(authorization, services)


BasicCredentials = Annotated[HTTPBasicCredentials, Depends(HTTPBasic())]


def basic_auth(services: ServicesDep, credentials: BasicCredentials):
    """API v2: HTTP Basic auth with the secret as the password."""
    _check_secret(credentials.password, services)


async def notify_sms(pushover: PushoverClient, sms_body: str, error: Optional[str] = None) -> None:
    """Pushover notification about a handled SMS. Runs as a background task, after the response is sent."""
    if not pushover.enabled:
        return
    if error:
        await pushover.send_notification(message=f"SMS: {sms_body}\nError: {error}", title="❌ SMS Failed", priority=1)
    else:
        await pushover.send_notification(message=f"SMS: {sms_body}", title="✅ SMS Processed")


async def monitor_sms_request(request: Request, services: ServicesDep):
    """Dependency that reports unexpected crashes in SMS handling via Pushover.

    Messages the bot handles, accepted or rejected, are reported by the endpoint itself."""
    try:
        yield
    except Exception as exc:
        try:
            sms_body = (await request.form()).get("Body", "<no body>")
        except Exception:
            sms_body = "<parse error>"
        await notify_sms(services.pushover, sms_body, getattr(exc, "detail", None) or str(exc))
        raise


async def verify_twilio_signature(request: Request, services: ServicesDep):
    """Dependency that rejects SMS webhook requests not signed by Twilio, so nobody else can record results.

    Twilio signs the URL it called. Cloud Run's proxy terminates HTTPS, so the app sees http://; the original scheme
    is in X-Forwarded-Proto."""
    if not services.settings.VERIFY_TWILIO_SIGNATURE:
        return
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    url = str(request.url.replace(scheme=scheme))
    params = dict(await request.form())
    signature = request.headers.get("x-twilio-signature", "")
    if not services.twilio.is_valid_request(url, params, signature):
        logging.warning("Rejected SMS webhook with invalid Twilio signature (url %s, signature %r)", url, signature)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid Twilio signature")


# Targeted by Twilio webhooks
twilio_router = APIRouter(
    prefix="/sms", dependencies=[Depends(verify_twilio_signature), Depends(monitor_sms_request)]
)

# API Routers
v1_api = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize_v1)], deprecated=True)
v2_api = APIRouter(prefix="/api/v2", dependencies=[Depends(basic_auth)])


# Endpoints are plain functions: their work (Sheets, Gemini, Twilio) uses blocking clients, so FastAPI runs them in
# its thread pool and a slow SMS doesn't hold up other requests.

# Twilio SMS Endpoint
@twilio_router.post("/scores", include_in_schema=False, status_code=status.HTTP_201_CREATED)
def post_scores_sms(
    msg: Annotated[TwilioSms, Form()], services: ServicesDep, response: Response, background_tasks: BackgroundTasks
):
    """Handles inbound scores via SMS.

    A message the bot rejects, and has already replied to, is answered with 200 rather than an error status: on an
    error status Twilio calls the number's fallback URL, which would handle the message again and reply twice."""
    logging.info("Received SMS from %s: %s", msg.sender, msg.body)
    result = process_sms(msg.body, services.league, services.llm)
    with result.timed("send"):
        services.twilio.send_message(msg.sender, result.reply)
    logging.info("SMS handled in %.2f s: %s", sum(result.timings.values()), result.timings)

    err = result.error
    detail = None
    if isinstance(err, ValidationError):
        detail = "; ".join(e.get("msg") for e in err.errors())
    elif err:
        detail = str(getattr(err, "detail", None) or err)
    background_tasks.add_task(notify_sms, services.pushover, msg.body, detail)

    if err:
        response.status_code = status.HTTP_200_OK
        return {"message": result.reply, "error": {"type": type(err).__name__, "detail": detail}}
    return {"message": result.reply, "match": result.match.model_dump(mode="json")}


# V2 API Endpoints
@v2_api.post(
    "/scores/{match_id}",
    response_model=SnookerMatch,
    summary="Report result for a match",
)
def post_scores(services: ServicesDep, body: ScoreRequest, match_id: str):
    """Handles inbound scores via API with Basic Auth"""
    logging.info("Received API scores: %s", body)
    league = services.league
    fixture = league.match(match_id)
    if fixture.completed:
        raise MatchAlreadyCompleted()
    breaks = [(getattr(fixture, b.player).name, b.points) for b in body.breaks or []]
    match, _ = league.record_result(match_id, body.player1_score, body.player2_score, breaks=breaks)
    return ok_created(match.model_dump())


@v2_api.get("/matches", response_model=SnookerMatchList)
def get_matches(
    services: ServicesDep,
    unplayed: bool = False,
    completed: bool = False,
    round: int = None,
    group: str = None,
):
    """Returns matches, optionally filtered by query parameters with Basic Auth."""
    status = "unplayed" if unplayed else "completed" if completed else None
    matches = services.league.matches(round=round, group=group, status=status)
    matches_list = SnookerMatchList(round=services.league.current_round, matches=matches)
    return JSONResponse(content=matches_list.model_dump(mode="json", by_alias=True))


@v2_api.get("/matches/{match_id}", response_model=SnookerMatch)
def get_match(services: ServicesDep, match_id: str):
    """Returns a specific match by ID with Basic Auth."""
    match = services.league.match(match_id)
    return JSONResponse(content=match.model_dump(mode="json", by_alias=True))


# V1 API Endpoints (Legacy)
@v1_api.post(
    "/scores/{match_id}",
    response_model=SnookerMatch,
    summary="Report result for a match",
)
def post_scores_v1(services: ServicesDep, body: ScoreRequest, match_id: str):
    """Handles inbound scores via API (legacy)"""
    return post_scores(services, body, match_id)


@v1_api.get("/matches", response_model=SnookerMatchList)
def get_matches_v1(
    services: ServicesDep,
    unplayed: bool = False,
    completed: bool = False,
    round: int = None,
    group: str = None,
):
    """Returns matches, optionally filtered by query parameters (legacy)."""
    return get_matches(services, unplayed, completed, round, group)


@v1_api.get("/matches/{match_id}", response_model=SnookerMatch)
def get_match_v1(services: ServicesDep, match_id: str):
    """Returns a specific match by ID (legacy)."""
    return get_match(services, match_id)


@v1_api.get("/fixtures", deprecated=True, response_model=SnookerMatchList)
def get_fixtures(services: ServicesDep):
    """Returns unplayed matches.

    Deprecated, replace by calling /matches with unplayed=True"""
    fixtures = services.league.matches(status="unplayed")
    fixtures_list = SnookerMatchList(round=services.league.current_round, matches=fixtures)
    return JSONResponse(content=fixtures_list.model_dump(mode="json", by_alias=True))


# Exception Handlers
@app.exception_handler(ValidationError)
async def handle_validation_error(req: Request, exc: ValidationError):
    """Our own models rejecting input, e.g. a scoreline that doesn't fit the match format, is a 400."""
    return JSONResponse({"detail": [err["msg"] for err in exc.errors()]}, status.HTTP_400_BAD_REQUEST)


@app.exception_handler(Exception)
async def handle_exception(req: Request, exc: Exception):
    """Anything unexpected: logged with its traceback, answered with a generic 500.

    HTTPException never gets here; FastAPI's own handler answers those with their status and detail."""
    logging.exception(exc)
    return JSONResponse({"detail": "Internal server error"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


# Include the routers in the FastAPI app
app.include_router(twilio_router)
app.include_router(v2_api)
app.include_router(v1_api)
