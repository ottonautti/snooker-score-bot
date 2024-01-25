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
from .settings import messages, settings
from .sheets import SnookerSheet
from .twilio_client import Twilio, TwilioInboundMessage


def setup_logging():
    """Sets up logging for the app"""
    client = google.cloud.logging.Client()
    client.setup_logging()  # registers handler with built-in logging
    if settings.DEBUG:  # when running locally, output to stdout
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


async def get_twilio():
    return Twilio()


async def get_sheet():
    sheet_id = os.environ.get("GOOGLESHEETS_SHEETID")
    return SnookerSheet(sheet_id)


async def get_llm():
    return SnookerScoresLLM(llm=settings.LLM)


@app.post("/scores")
async def handle_score(
    twilio: Twilio = Depends(get_twilio),
    sheet: SnookerSheet = Depends(get_sheet),
    msg=Depends(parse_twilio_msg),
    llm=Depends(get_llm),
):
    """Handles inbound scores"""
    logging.info("Received message from %s: %s", msg.sender, msg.body)
    valid_players = sheet.get_current_players()
    try:
        output: dict = llm.infer(passage=msg.body, valid_players=sheet.players_txt)
        snooker_match = get_match_model(
            valid_players=valid_players, max_score=settings.MAX_SCORE, **output
        )
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


@app.get("/sheet")
async def handle_sheet(sheet: SnookerSheet = Depends(get_sheet)):
    """Redirects to the Google Sheet, tab corresponding to current round."""
    url = sheet.get_current_round_url()
    if not url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No current round")
    return RedirectResponse(url=url)


@app.exception_handler(Exception)
async def handle_exception(req: Request, exc: Exception):
    logging.exception(exc)
    if not isinstance(exc, HTTPException):
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


setup_logging()
