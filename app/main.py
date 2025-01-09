"""FastAPI app for recording snooker match outcomes reported by users."""

import logging
import os
import sys
from typing import List, Literal, Optional

import google.cloud.logging
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from .errors import (
    InvalidContentType,
    InvalidMatchError,
    MatchAlreadyCompleted,
    MatchNotFound,
)
from .llm.inference import SnookerScoresLLM
from .models import (
    MatchFixture,
    MatchOutcome,
    SnookerBreak,
    SnookerMatch,
    SnookerMatchList,
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


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def authorize(authorization: str = Header(None)):
    if authorization != SETTINGS.API_SECRET:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unauthorized")


# Targeted by Twilio webhooks
twilio_router = APIRouter(prefix="/sms")

# Targeted by scorer app
v1_api = APIRouter(prefix="/api/v1", dependencies=[Depends(authorize)])


async def parse_twilio_msg(req: Request) -> TwilioInboundMessage:
    """Returns inbound Twilio message details from request form data"""
    # expect application/x-www-form-urlencoded
    if req.headers["Content-Type"] != "application/x-www-form-urlencoded":
        raise InvalidContentType("application/x-www-form-urlencoded")
    form_data = await req.form()
    body = form_data.get("Body")
    sender = form_data.get("From")
    # set is_test to True if the message contains TEST
    is_test = bool(body and "TEST" in body)
    if not body or not sender:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Twilio message")
    return TwilioInboundMessage(body=body, sender=sender, is_test=is_test)


def ok_created(**kwargs):
    """Returns a successful response"""
    return JSONResponse(jsonable_encoder(kwargs), status.HTTP_201_CREATED)


@twilio_router.post("/scores", include_in_schema=False)
async def post_scores_sms(msg=Depends(parse_twilio_msg)):
    """Handles inbound scores via SMS"""
    logging.info("Received SMS from %s: %s", msg.sender, msg.body)
    inference: dict = LLM.infer(passage=msg.body, known_players=SHEET.current_players)
    inferred_fixture = SHEET.lookup_match_by_player_names((inference["player1"], inference["player2"]))
    if not inferred_fixture:
        raise MatchNotFound()
    if inferred_fixture.completed:
        raise MatchAlreadyCompleted()
    match_data = inferred_fixture.model_dump()
    reply: str = ""
    breaks = [SnookerBreak.from_dict(b) for b in inference.get("breaks", [])]
    try:
        match = SnookerMatch(**match_data).validate_against_fixture(inferred_fixture)
        match.outcome = MatchOutcome(
            player1_score=inference["player1_score"], player2_score=inference["player2_score"], breaks=breaks
        )
        reply = match.summary("eng")
    except ValidationError as err:
        reply = get_messages("eng").INVALID
        error_messages: list[str] = [err.get("msg") for err in err.errors()]
        raise InvalidMatchError(error_messages)
    finally:
        TWILIO.send_message(msg.sender, reply)

    SHEET.record_match(match)
    return ok_created(message=reply, match=match.model_dump())


class BreakRequest(BaseModel):
    player: Literal["player1", "player2"]
    points: int


class ScoreRequest(BaseModel):
    breaks: list[BreakRequest]
    player1_score: int
    player2_score: int


@v1_api.post("/scores/{match_id}", response_model=SnookerMatch, summary="Report result for a match")
async def post_scores(body: ScoreRequest, match_id: str):
    """Handles inbound scores via API"""
    logging.info("Received API scores: %s", body)
    match: SnookerMatch = await get_match_by_id(match_id)
    if match.completed:
        raise MatchAlreadyCompleted()
    breaks = []
    for brk in body.breaks:
        break_by: Literal["player1", "player2"] = brk.player
        breaks.append(SnookerBreak(player=getattr(match, break_by), points=brk.points))
    match.outcome = MatchOutcome(player1_score=body.player1_score, player2_score=body.player2_score, breaks=breaks)
    SHEET.record_match(match)
    return ok_created(match=match.model_dump())


@app.exception_handler(ValidationError)
async def handle_validation_error(req: Request, exc: ValidationError):
    error_messages: list[str] = [err.get("msg") for err in exc.errors()]
    raise InvalidMatchError(error_messages)


@app.exception_handler(Exception)
async def handle_exception(req: Request, exc: Exception):
    logging.exception(exc)
    if isinstance(exc, HTTPException):
        return JSONResponse({"detail": exc.detail}, exc.status_code)
    else:
        return JSONResponse({"detail": "Internal server error"}, status.HTTP_500_INTERNAL_SERVER_ERROR)


@v1_api.get("/fixtures", response_model=SnookerMatchList)
async def get_fixtures():
    """Returns scheduled matches for the current round."""
    fixtures_list = SnookerMatchList(round=SHEET.current_round, matches=SHEET.get_fixtures())
    return JSONResponse(content=fixtures_list.model_dump(by_alias=True))


async def get_match_by_id(match_id: str) -> SnookerMatch:
    """Returns a specific match by ID."""
    try:
        return SHEET.get_match_by_id(match_id)
    except LookupError:
        raise MatchNotFound()


@v1_api.get("/matches/{match_id}", response_model=SnookerMatch)
async def get_match(match_id: str):
    """Returns a specific match by ID."""
    match = await get_match_by_id(match_id)
    return JSONResponse(content=match.model_dump(by_alias=True))


# Include the routers in the FastAPI app
app.include_router(twilio_router)
app.include_router(v1_api)

setup_logging()
