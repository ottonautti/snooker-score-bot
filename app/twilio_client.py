import logging
import os
from collections import namedtuple

from fastapi import HTTPException, Request, status
from twilio.rest import Client

from app.errors import InvalidContentType
from app.settings import Settings

TwilioInboundMessage = namedtuple("TwilioInboundMessage", ["body", "sender", "is_test"])


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


class Twilio:
    skip_send = os.environ.get("TWILIO_NO_SEND", False)

    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        if not account_sid or not auth_token or not from_number:
            raise ValueError("Missing Twilio credentials")
        self.client = Client(account_sid, auth_token)
        self.from_number = from_number
        if self.skip_send:
            self.client.messages.create = self._skip_send_message

    def _skip_send_message(self, *args, **kwargs):
        logging.warning("Twilio send is skipped.")
        return None

    def send_message(self, to: str, body: str):
        """Sends a message via Twilio"""
        logging.info('Sending message to %s: "%s"', to, body.replace("\n", " "))
        # "force delivery" attempts delivery even if to-number looks like a landline
        # https://www.twilio.com/docs/api/errors/21635
        return self.client.messages.create(from_=self.from_number, to=to, body=body, force_delivery=True)


def get_twilio_client(settings: Settings) -> Twilio:
    """Returns a Twilio client instance with credentials taken from settings or environment variables"""
    account_sid = os.environ.get("TWILIO_ACCOUNTSID")
    auth_token = os.environ.get("TWILIO_AUTHTOKEN")
    from_number = os.environ.get("TWILIO_FROM")
    if not (account_sid and auth_token and from_number):
        raise ValueError("Missing Twilio credentials")
    return Twilio(account_sid=account_sid, auth_token=auth_token, from_number=from_number)
