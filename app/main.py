"""FastAPI app for recording snooker match outcomes reported by users."""
import json
import logging
import os
import sys

import google.cloud.logging
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .llm.inference import SnookerScoresLLM
from .messages import get_messages
from .models import SnookerMatch
from .sheets import SnookerSheet
from .twilio_client import Twilio, TwilioInboundMessage


def setup_logging():
    """Sets up logging for the app"""
    client = google.cloud.logging.Client()
    client.setup_logging()  # registers handler with built-in logging
    # locally output to stdout
    if os.environ.get("DEBUG_APP"):
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
        logging.getLogger().setLevel(logging.INFO)


SHEET_ID = os.environ.get("GOOGLESHEETS_SHEETID")
TWILIO = Twilio()
SHEET = SnookerSheet(SHEET_ID)
LLM = SnookerScoresLLM(players=SHEET.get_current_players())

OPENAI_APIKEY = os.environ.get("OPENAI_APIKEY")
MESSAGE_LANG = "fin"
MESSAGES = get_messages(MESSAGE_LANG)

app = FastAPI()


async def parse_twilio_msg(req: Request) -> TwilioInboundMessage:
    """Returns inbound Twilio message details from request form data"""
    # expect application/x-www-form-urlencoded
    if req.headers["Content-Type"] != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=400, detail="Invalid Content-Type")
    form_data = await req.form()
    body = form_data.get("Body")
    sender = form_data.get("From")
    if not body or not sender:
        raise HTTPException(status_code=400, detail="Invalid Twilio message")
    return TwilioInboundMessage(body=body, sender=sender)


@app.post("/scores")
async def handle_message(msg: TwilioInboundMessage = Depends(parse_twilio_msg)):
    """Handles inbound scores"""
    assert msg.body
    logging.info("Received message from %s: %s", msg.sender, msg.body)
    try:
        match: SnookerMatch = LLM.infer_match(msg.body)
    except ValidationError as err:
        TWILIO.send_message(msg.sender, MESSAGES.REPLY_404)
        raise HTTPException(status_code=400, detail=err.errors()) from err
    SHEET.record_match(values={**match.dict(), "passage": msg.body}, sender=msg.sender)
    reply = MESSAGES.REPLY_201.format(match.summary(MESSAGE_LANG))
    TWILIO.send_message(msg.sender, reply)
    content = {"status": "Match recorded", "match": jsonable_encoder(match)}
    logging.info(json.dumps(content))
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=content)


setup_logging()
