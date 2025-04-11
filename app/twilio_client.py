import logging
import os
from collections import namedtuple

from twilio.rest import Client


class Twilio:
    skip_send = os.environ.get("TWILIO_NO_SEND", False)

    def __init__(self, account_sid: str = None, auth_token: str = None, from_number: str = None):
        if not account_sid:
            account_sid = os.environ.get("TWILIO_ACCOUNTSID")
        if not auth_token:
            auth_token = os.environ.get("TWILIO_AUTHTOKEN")
        if not from_number:
            from_number = os.environ.get("TWILIO_FROM")
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


TwilioInboundMessage = namedtuple("TwilioInboundMessage", ["body", "sender", "is_test"])
