"""FastAPI app for recording snooker match outcomes reported by users."""
import logging
import os

import google.cloud.logging
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .inference import SnookerScoresLLM
from .messages import get_messages
from .models import SnookerMatch
from .sheets import SnookerScoresSheet
from .twilio_client import Twilio, TwilioInboundMessage

client = google.cloud.logging.Client()
client.setup_logging()  # registers handler with built-in logging

SHEET_ID = os.environ["GOOGLESHEETS_SHEETID"]
TWILIO_ACCOUNTSID = os.environ.get("TWILIO_ACCOUNTSID")
TWILIO_AUTHTOKEN = os.environ.get("TWILIO_AUTHTOKEN")
TWILIO_FROM = os.environ.get("TWILIO_FROM")

TWILIO = Twilio(TWILIO_ACCOUNTSID, TWILIO_AUTHTOKEN, TWILIO_FROM)
SHEET = SnookerScoresSheet(SHEET_ID)
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
    logging.info("Sending reply to %s: %s", msg.sender, reply)
    TWILIO.send_message(msg.sender, reply)
    content = {"status": "Match recorded", "match": jsonable_encoder(match)}
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=content)
