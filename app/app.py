"""FastAPI app for recording snooker match outcomes reported by users."""

import os
from collections import namedtuple

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import ValidationError
from twilio.rest import Client

from .inference import SnookerScoresLLM
from .sheets import SnookerScoresSheet

SHEET_ID = os.environ["GOOGLESHEETS_SHEETID"]
TWILIO_ACCOUNTSID = os.environ.get("TWILIO_ACCOUNTSID")
TWILIO_AUTHTOKEN = os.environ.get("TWILIO_AUTHTOKEN")
TWILIO_FROM = os.environ.get("TWILIO_FROM")


class Twilio:
    def __init__(self, account_sid: str, auth_token: str):
        self.client = Client(account_sid, auth_token)

    def send_message(self, to: str, body: str):
        """Sends a message via Twilio"""
        self.client.messages.create(from_=TWILIO_FROM, to=to, body=body)


TWILIO = Twilio(TWILIO_ACCOUNTSID, TWILIO_AUTHTOKEN)
SHEET = SnookerScoresSheet(SHEET_ID)
LLM = SnookerScoresLLM(players=SHEET.get_current_players())

OPENAI_APIKEY = os.environ.get("OPENAI_APIKEY")


app = FastAPI()

TwilioInboundMessage = namedtuple("TwilioInboundMessage", ["body", "sender"])


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
async def handle_inbound_scores(msg: TwilioInboundMessage = Depends(parse_twilio_msg)):
    """Handles inbound scores"""
    assert msg.body
    try:
        match = LLM.infer_match(msg.body)
    except ValidationError as e:
        TWILIO.send_message(msg.sender, "Sorry, I could not understand the message.")
        raise HTTPException(status_code=400)
    SHEET.record_match(match=match.dict(), sender=msg.sender)
    reply = "Thank you, match was recorded as:\n{}".format(match.summary)
    TWILIO.send_message(msg.sender, reply)
    return match.json()
