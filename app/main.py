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
from .models import SnookerMatch, SnookerPlayer
from .settings import messages, settings
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


async def get_twilio():
    return Twilio()


async def get_sheet():
    sheet_id = os.environ.get("GOOGLESHEETS_SHEETID")
    return SnookerSheet(sheet_id)


async def get_players(sheet: SnookerSheet = Depends(get_sheet)) -> list[SnookerPlayer]:
    return sheet.get_current_players()


async def get_llm(players: list[SnookerPlayer] = Depends(get_players)) -> SnookerScoresLLM:
    return SnookerScoresLLM(players=players)


@app.post("/scores")
async def handle_message(
    twilio: Twilio = Depends(get_twilio),
    msg: TwilioInboundMessage = Depends(parse_twilio_msg),
    llm=Depends(get_llm),
    sheet=Depends(get_sheet),
    players=Depends(get_players),
):
    """Handles inbound scores"""
    assert msg.body
    logging.info("Received message from %s: %s", msg.sender, msg.body)
    model = SnookerMatch.get_model(valid_players=players, _max_score=settings.MAX_SCORE)
    try:
        output: dict = llm.run(msg.body)
        snooker_match = model(**output)
    except ValidationError as err:
        twilio.send_message(msg.sender, messages.REPLY_404)
        raise HTTPException(status_code=400, detail=err.errors()) from err
    sheet.record_match(values={**snooker_match.dict(), "passage": msg.body}, sender=msg.sender)
    reply = messages.REPLY_201.format(snooker_match.summary(settings.APP_LANG))
    twilio.send_message(msg.sender, reply)
    content = {"status": "Match recorded", "match": jsonable_encoder(snooker_match)}
    logging.info(json.dumps(content))
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=content)


setup_logging()
