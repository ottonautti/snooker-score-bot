"""FastAPI app for recording snooker match outcomes reported by users."""

import json
import logging
import os
import sys

import google.cloud.logging
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError

from .llm.inference import SnookerScoresLLM
from .models import get_match_model
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


twilio = Twilio()


@app.post("/scores")
async def post_scores(
    msg=Depends(parse_twilio_msg),
):
    """Handles inbound scores"""
    return await handle_scores(settings=SETTINGS, msg=msg)


@app.post("/scores/sixred24")
async def post_scores_sixred24(
    msg=Depends(parse_twilio_msg),
):
    """Handles inbound scores for SixRed24 league."""
    return await handle_scores(settings=get_settings(sixred24=True), msg=msg)


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
        twilio.send_message(msg.sender, messages.INVALID)
        error_messages: list[str] = [err.get("msg") for err in err.errors()]
        detail = {"llm_output": output, "error_messages": error_messages}
        logging.error(json.dumps(detail))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail)
    sheet.record_match(values=snooker_match.model_dump(), passage=msg.body, sender=msg.sender)
    for break_ in snooker_match.breaks:
        sheet.record_break(break_.model_dump(), passage=msg.body, sender=msg.sender)
    reply = snooker_match.summary(snooker_match.passage_language)
    twilio.send_message(msg.sender, reply)
    reply_msg = "Match tested" if msg.is_test else "Match recorded"
    content = {"status": reply_msg, "match": jsonable_encoder(snooker_match)}
    logging.info(json.dumps(content))
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=content)


@app.exception_handler(Exception)
async def handle_exception(req: Request, exc: Exception):
    logging.exception(exc)
    if not isinstance(exc, HTTPException):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


setup_logging()
