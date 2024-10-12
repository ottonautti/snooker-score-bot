"""FastAPI app for recording snooker match outcomes reported by users."""

import argparse
import json
import logging
import os
import sys
from typing import Optional

import google.cloud.logging
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
from tabulate import tabulate

from .llm.inference import SnookerScoresLLM
from .models import SnookerMatch, get_match_model
from .settings import get_settings, messages
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


async def handle_scores(msg: TwilioInboundMessage, settings):
    sheet = SnookerSheet(settings.SHEETID)
    llm = SnookerScoresLLM(llm=settings.LLM)
    """Handles inbound scores"""
    logging.info("Received message from %s: %s", msg.sender, msg.body)
    valid_players = sheet.current_players
    try:
        output: dict = llm.infer(passage=msg.body, valid_players_txt=sheet.players_txt)
        snooker_match = get_match_model(valid_players=valid_players, max_score=settings.MAX_SCORE, **output)
    except ValidationError as err:
        TWILIO.send_message(msg.sender, messages.INVALID)
        error_messages: list[str] = [err.get("msg") for err in err.errors()]
        detail = {"llm_output": output, "error_messages": error_messages}
        logging.error(json.dumps(detail))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail)
    sheet.record_match(values=snooker_match.model_dump(), passage=msg.body, sender=msg.sender)
    for break_ in snooker_match.breaks:
        sheet.record_break(break_.model_dump(), passage=msg.body, sender=msg.sender)
    reply = snooker_match.summary(snooker_match.passage_language)
    TWILIO.send_message(msg.sender, reply)
    reply_msg = "Match tested" if msg.is_test else "Match recorded"
    content = {"status": reply_msg, "match": jsonable_encoder(snooker_match)}
    logging.info(json.dumps(content))
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=content)


@app.exception_handler(Exception)
async def handle_exception(req: Request, exc: Exception):
    logging.exception(exc)
    if not isinstance(exc, HTTPException):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.post("/scores/sms")
async def post_scores(
    msg=Depends(parse_twilio_msg),
):
    """Handles inbound scores"""
    return await handle_scores(settings=SETTINGS, msg=msg)


@app.post("/scores/sms/sixred24")
async def post_scores_sixred24(
    msg=Depends(parse_twilio_msg),
):
    """Handles inbound scores for SixRed24 league."""
    return await handle_scores(settings=get_settings(sixred24=True), msg=msg)


@app.exception_handler(Exception)
async def handle_exception(req: Request, exc: Exception):
    logging.exception(exc)
    if not isinstance(exc, HTTPException):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


async def fetch_matches(settings, incomplete_only: bool = False, round_: Optional[str] = None) -> list[SnookerMatch]:
    """Fetch matches based on the provided parameters."""
    sheet = SnookerSheet(settings.SHEETID)
    matches: list[SnookerMatch] = sheet.get_matches(incomplete_only=incomplete_only, round_=round_)
    return matches


async def fetch_match_by_id(settings, match_id: str) -> SnookerMatch:
    """Fetch a single match by its ID."""
    sheet = SnookerSheet(settings.SHEETID)
    match = sheet.get_match_by_id(match_id)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    return match


@app.get("/fixtures")
async def get_fixtures(settings=Depends(SETTINGS)):
    """Returns scheduled matches for the current round."""
    sheet = SnookerSheet(settings.SHEETID)
    current_round = sheet.current_round
    fixtures = await fetch_matches(settings, incomplete_only=True, round_=current_round)
    fixtures_out = [fixture.model_dump(by_alias=True) for fixture in fixtures]
    return JSONResponse(content={"round": current_round, "fixtures": fixtures_out})


@app.get("/matches")
async def get_matches(settings=Depends(SETTINGS)):
    """Returns all matches."""
    matches = await fetch_matches(settings)
    matches_out = [match.model_dump(by_alias=True) for match in matches]
    return JSONResponse(content={"matches": matches_out})


@app.get("/fixtures/{id}")
async def get_fixture_by_id(id: str, settings=Depends(SETTINGS)):
    """Returns a specific fixture by ID."""
    match = await fetch_match_by_id(settings, id)
    if match.state == "scheduled":
        return JSONResponse(content=match.model_dump(by_alias=True))
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fixture not found")


@app.get("/matches/{id}")
async def get_match_by_id(id: str, settings=Depends(SETTINGS)):
    """Returns a specific match by ID."""
    match = await fetch_match_by_id(settings, id)
    return JSONResponse(content=match.model_dump(by_alias=True))


setup_logging()


def main():
    parser = argparse.ArgumentParser(description="Snooker Score Bot")
    parser.add_argument("--add-fixtures", action="store_true", help="Add fixtures for the current round")
    parser.add_argument("--sheet-id", "-s", type=str, help="Override the default sheet ID")
    args = parser.parse_args()

    # Prompt for sheet-id if not provided
    if not args.sheet_id:
        args.sheet_id = input("Please enter the sheet ID: ")

    sheet_id = args.sheet_id
    sheet = SnookerSheet(sheet_id)
    current_round = sheet.current_round
    players = sheet.current_players

    # Display current players and round
    player_table = [[player.name, player.group] for player in players]
    print(f"Current Round: {current_round}")
    print(tabulate(player_table, headers=["PLAYER", "GROUP"], tablefmt="grid"))

    if args.add_fixtures:
        confirmation = input(f"Are you sure you want to add fixtures to sheet {sheet_id}? (yes/no): ")
        if confirmation.lower() == "yes":
            sheet.add_fixtures(current_round)
            logging.info("Fixtures added for round %s", current_round)
        else:
            logging.info("Operation cancelled by user.")


if __name__ == "__main__":
    main()
    sys.exit(0)
