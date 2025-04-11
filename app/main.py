"""FastAPI app for recording snooker match outcomes reported by users."""

import logging
import os
import sys
from typing import List, Literal, Optional

import google.cloud.logging
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field, ValidationError

from .errors import (
    InvalidContentType,
    InvalidMatchError,
    MatchAlreadyCompleted,
    MatchFixtureMismatchError,
    MatchNotFound,
)
from .llm.inference import SnookerScoresLLM
from .models import (
    InferredMatch,
    MatchOutcome,
    SnookerBreak,
    SnookerMatch,
    SnookerMatchList,
    SnookerPlayer,
)
from .settings import get_messages, get_settings
from .sheets import SnookerSheet
from .twilio_client import Twilio, TwilioInboundMessage

DEBUG = bool(os.environ.get("SNOOKER_DEBUG", False))
SETTINGS = get_settings()
TWILIO = Twilio()
SHEET = SnookerSheet(SETTINGS.SHEETID)
LLM = SnookerScoresLLM()


def setup_logging():
    """Sets up logging for the app"""
    client = google.cloud.logging.Client()
    client.setup_logging()  # registers handler with built-in logging
    if DEBUG:  # when running locally, output to stdout
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
        logging.getLogger().setLevel(logging.INFO)


app = FastAPI(
    version="1.0.0",
    title="Snooker Scores API",
    description="API for recording Groove Snooker League match outcomes",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def authorize_v1(authorization: str = Header(None)):
    if authorization != SETTINGS.API_SECRET:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthorized")


security = HTTPBasic()


def basic_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if credentials.password != SETTINGS.API_SECRET:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthorized")


# Targeted by Twilio webhooks
twilio_router = APIRouter(prefix="/sms")

# API Routers
v1_api = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize_v1)], deprecated=True)
v2_api = APIRouter(prefix="/api/v2", dependencies=[Depends(basic_auth)])


# Utility Functions
async def parse_twilio_msg(req: Request) -> TwilioInboundMessage:
    """Returns inbound Twilio message details from request form data"""
    # expect application/x-www-form-urlencoded
    if req.headers["Content-Type"] != "application/x-www-form-urlencoded":
        raise InvalidContentType()
    form_data = await req.form()
    body = form_data.get("Body")
    sender = form_data.get("From")
    # set is_test to True if the message contains TEST
    is_test = bool(body and "TEST" in body)
    if not body or not sender:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Twilio message")
    return TwilioInboundMessage(body=body, sender=sender, is_test=is_test)


def ok_created(content) -> ORJSONResponse:
    """Returns a successful response"""
    return ORJSONResponse(jsonable_encoder(content), status_code=status.HTTP_201_CREATED)


async def get_match_by_id(match_id: str) -> SnookerMatch:
    """Returns a specific match by ID."""
    try:
        return SHEET.get_match_by_id(match_id)
    except LookupError:
        raise MatchNotFound()


# Models
class BreakRequest(BaseModel):
    player: Literal["player1", "player2"]
    points: int


class ScoreRequest(BaseModel):
    breaks: Optional[list[BreakRequest]]
    player1_score: int
    player2_score: int


# Twilio SMS Endpoint
@twilio_router.post("/scores", include_in_schema=False)
async def post_scores_sms(msg=Depends(parse_twilio_msg)):
    """Handles inbound scores via SMS"""
    logging.info("Received SMS from %s: %s", msg.sender, msg.body)
    inferred: InferredMatch = LLM.infer(passage=msg.body, known_players=SHEET.current_players)
    fixture: SnookerMatch = SHEET.lookup_match_by_player_names((inferred.player1, inferred.player2))
    if not fixture:
        raise MatchNotFound()
    if fixture.completed:
        raise MatchAlreadyCompleted()
    if inferred.player2 == fixture.player1.name and inferred.player1 == fixture.player2.name:
        inferred.player1, inferred.player2 = inferred.player2, inferred.player1
        inferred.player1_score, inferred.player2_score = (inferred.player2_score, inferred.player1_score)
    # if players still not matching, raise
    if inferred.player1 != fixture.player1.name or inferred.player2 != fixture.player2.name:
        raise MatchFixtureMismatchError("Players do not match those in fixture")
    try:
        reply: str = ""
        breaks = [SnookerBreak.from_dict(b) for b in inferred.breaks]
        outcome = MatchOutcome(
            player1_score=inferred.player1_score, player2_score=inferred.player2_score, breaks=breaks
        )
        match: SnookerMatch = fixture.model_copy(update={"outcome": outcome})
        reply = match.summary(link=SETTINGS.SHEET_SHORTLINK)
        SHEET.record_match(match, log=msg.body)
    except ValidationError as err:
        reply = get_messages().INVALID
        error_messages: list[str] = [err.get("msg") for err in err.errors()]
        raise InvalidMatchError(error_messages)
    finally:
        TWILIO.send_message(msg.sender, reply)

    return ok_created(dict(message=reply, match=match.model_dump()))


# V2 API Endpoints
@v2_api.post("/scores/{match_id}", response_model=SnookerMatch, summary="Report result for a match")
async def post_scores(body: ScoreRequest, match_id: str):
    """Handles inbound scores via API with Basic Auth"""
    logging.info("Received API scores: %s", body)
    match: SnookerMatch = await get_match_by_id(match_id)
    if match.completed:
        raise MatchAlreadyCompleted()
    breaks = []
    for brk in body.breaks:
        break_by: Literal["player1", "player2"] = brk.player
        breaks.append(SnookerBreak(player=getattr(match, break_by), points=brk.points))
    match.outcome = MatchOutcome(
        player1_score=body.player1_score,
        player2_score=body.player2_score,
        breaks=breaks,
    )
    SHEET.record_match(match)
    return ok_created(match.model_dump())


@v2_api.get("/matches", response_model=SnookerMatchList)
async def get_matches(
    unplayed: bool = False,
    completed: bool = False,
    round: int = None,
    group: str = None,
):
    """Returns matches, optionally filtered by query parameters with Basic Auth."""
    matches = SHEET.get_matches(round=round, group=group, unplayed_only=unplayed, completed_only=completed)
    matches_list = SnookerMatchList(round=SHEET.current_round, matches=matches)
    return ORJSONResponse(content=matches_list.model_dump(by_alias=True))


@v2_api.get("/matches/{match_id}", response_model=SnookerMatch)
async def get_match(match_id: str):
    """Returns a specific match by ID with Basic Auth."""
    match = await get_match_by_id(match_id)
    return ORJSONResponse(content=match.model_dump(by_alias=True))


# V1 API Endpoints (Legacy)
@v1_api.post("/scores/{match_id}", response_model=SnookerMatch, summary="Report result for a match")
async def post_scores_v1(body: ScoreRequest, match_id: str):
    """Handles inbound scores via API (legacy)"""
    return await post_scores(body, match_id)


@v1_api.get("/matches", response_model=SnookerMatchList)
async def get_matches_v1(
    unplayed: bool = False,
    completed: bool = False,
    round: int = None,
    group: str = None,
):
    """Returns matches, optionally filtered by query parameters (legacy)."""
    return await get_matches(unplayed, completed, round, group)


@v1_api.get("/matches/{match_id}", response_model=SnookerMatch)
async def get_match_v1(match_id: str):
    """Returns a specific match by ID (legacy)."""
    return await get_match(match_id)


@v1_api.get("/fixtures", deprecated=True, response_model=SnookerMatchList)
async def get_fixtures():
    """Returns unplayed matches.

    Deprecated, replace by calling /matches with unplayed=True"""
    fixtures = SHEET.get_fixtures()
    fixtures_list = SnookerMatchList(round=SHEET.current_round, matches=fixtures)
    return ORJSONResponse(content=fixtures_list.model_dump(by_alias=True))


# Exception Handlers
@app.exception_handler(ValidationError)
async def handle_validation_error(req: Request, exc: ValidationError):
    error_messages: list[str] = [err.get("msg") for err in exc.errors()]
    raise InvalidMatchError(error_messages)


@app.exception_handler(Exception)
async def handle_exception(req: Request, exc: Exception):
    logging.exception(exc)
    if isinstance(exc, HTTPException):
        return ORJSONResponse({"detail": exc.detail}, exc.status_code)
    else:
        return ORJSONResponse({"detail": "Internal server error"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


# Include the routers in the FastAPI app
app.include_router(twilio_router)
app.include_router(v2_api)
app.include_router(v1_api)

setup_logging()
