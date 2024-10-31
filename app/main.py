"""FastAPI app for recording snooker match outcomes reported by users."""

import json
import logging
import os
import sys
from typing import Optional

import google.cloud.logging
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .llm.inference import SnookerScoresLLM
from .models import (
    MatchFixture,
    MatchOutcome,
    SnookerMatch,
    SnookerMatchList,
    get_match_model,
)
from .settings import get_messages, get_settings
from .sheets import SnookerSheet
from .twilio_client import Twilio, TwilioInboundMessage

DEBUG = bool(os.environ.get("SNOOKER_DEBUG", False))
SETTINGS = get_settings()


def setup_logging():
    """Sets up logging for the app"""
    client = google.cloud.logging.Client()
    client.setup_logging()  # registers handler with built-in logging
    if DEBUG:  # when running locally, output to stdout
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
        logging.getLogger().setLevel(logging.INFO)


app = FastAPI()
TWILIO = Twilio()
SHEET = SnookerSheet(SETTINGS.SHEETID)
LLM = SnookerScoresLLM(llm=SETTINGS.LLM)


async def parse_twilio_msg(req: Request) -> TwilioInboundMessage:
    """Returns inbound Twilio message details from request form data"""
    # expect application/x-www-form-urlencoded
    if req.headers["Content-Type"] != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Content-Type")
    form_data = await req.form()
    body = form_data.get("Body")
    sender = form_data.get("From")
    # set is_test to True if the message contains TEST
    is_test = bool(body and "TEST" in body)
    if not body or not sender:
        raise HTTPException(status_code=400, detail="Invalid Twilio message")
    return TwilioInboundMessage(body=body, sender=sender, is_test=is_test)


def process_match_outcome(payload: dict, match_id: Optional[str] = None) -> SnookerMatch:
    """Processes the match outcome and records it to the Google Sheet."""
    valid_players = SHEET.current_players
    try:
        match = get_match_model(valid_players=valid_players, max_score=SETTINGS.MAX_SCORE, **payload)
    except ValidationError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=err.errors())
    if match_id:
        SHEET.record_match_outcome(id_=match_id, **match.model_dump())
    for brk in match.breaks:
        SHEET.record_break(brk.model_dump(), passage=payload["passage"], sender=payload["sender"])
    return match


async def handle_scores_passage(passage: TwilioInboundMessage, settings):
    """Handles inbound scores"""
    output: dict = LLM.infer(passage=passage.body, valid_players_txt=SHEET.players_txt)
    return process_match_outcome(output)


@app.exception_handler(Exception)
async def handle_exception(req: Request, exc: Exception):
    logging.exception(exc)
    if not isinstance(exc, HTTPException):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def ok_response(**kwargs):
    """Returns a successful response"""
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=jsonable_encoder(kwargs))


@app.post("/scores/sms", include_in_schema=False)
async def post_scores_sms(
    msg=Depends(parse_twilio_msg),
):
    """Handles inbound scores via SMS"""
    logging.info("Received SMS from %s: %s", msg.sender, msg.body)
    try:
        match = await handle_scores_passage(msg, SETTINGS)
    except ValidationError as err:
        reply = get_messages("eng").INVALID
        error_messages: list[str] = [err.get("msg") for err in err.errors()]
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error_messages)
    reply = match.summary(match.passage_language)
    TWILIO.send_message(msg.sender, reply)
    return ok_response(message=reply, match=match.model_dump())


@app.post(
    "/scores/{id}",
    response_model=SnookerMatch,
    summary="Record match outcome",
    response_description="Recorded match details",
)
async def post_scores(
    id: str,
    payload: MatchOutcome,
):
    """Handles inbound scores via API"""
    logging.info("Received API scores: %s", payload)
    try:
        match = process_match_outcome(payload)
    except ValidationError as err:
        error_messages: list[str] = [err.get("msg") for err in err.errors()]
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=error_messages)
    return ok_response(match=match.model_dump())


@app.exception_handler(Exception)
async def handle_exception(req: Request, exc: Exception):
    logging.exception(exc)
    if not isinstance(exc, HTTPException):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


async def fetch_matches(settings, unplayed_only: bool = False, round: Optional[str] = None) -> list[SnookerMatch]:
    """Fetch matches based on the provided parameters."""
    sheet = SnookerSheet(settings.SHEETID)
    matches: list[SnookerMatch] = sheet.get_matches(unplayed_only=unplayed_only, round=round)
    return matches


async def fetch_match_by_id(settings, match_id: str) -> SnookerMatch:
    """Fetch a single match by its ID."""
    sheet = SnookerSheet(settings.SHEETID)
    match = sheet.get_match_by_id(match_id)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    return match


@app.get("/fixtures")
async def get_fixtures(settings=Depends(SETTINGS)) -> list[MatchFixture]:
    """Returns scheduled matches for the current round."""
    sheet = SnookerSheet(settings.SHEETID)
    current_round = sheet.current_round
    fixtures = await fetch_matches(settings, unplayed_only=True, round=current_round)
    fixtures_out = [fixture.model_dump(by_alias=True) for fixture in fixtures]
    return JSONResponse(content={"round": current_round, "fixtures": fixtures_out})


@app.get("/matches", response_model=SnookerMatchList, response_model_exclude_unset=True)
async def get_matches(unplayed: bool = False, completed: bool = False, round: int = None, settings=Depends(SETTINGS)):
    """Returns all matches or only unplayed matches if 'unplayed' is True."""
    current_round = None
    if unplayed or round is None:
        sheet = SnookerSheet(settings.SHEETID)
        current_round = sheet.current_round
    matches = await fetch_matches(settings, unplayed_only=unplayed, round=round or current_round)
    matches_dump = [
        m.model_dump(
            exclude_none=True,
            exclude_unset=True,
            exclude="breaks",  # TODO: fetch breaks to the response
        )
        for m in matches
    ]
    matches_list = SnookerMatchList(matches=matches_dump, round=current_round)
    if unplayed:
        content = matches_list.model_dump(by_alias=True, include={"round", "unplayed"})
    elif completed:
        content = matches_list.model_dump(by_alias=True, include={"round", "completed"})
    else:
        content = matches_list.model_dump(by_alias=True, include={"round", "matches"})
    return JSONResponse(content=content)


@app.get("/matches/{id}", response_model=SnookerMatch)
async def get_match_by_id(id: str, settings=Depends(SETTINGS)):
    """Returns a specific match by ID."""
    match = await fetch_match_by_id(settings, id)
    return JSONResponse(content=match.model_dump(by_alias=True))


setup_logging()
