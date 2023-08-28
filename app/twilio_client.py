from collections import namedtuple

from twilio.rest import Client


class Twilio:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.client = Client(account_sid, auth_token)
        self.from_number = from_number

    def send_message(self, to: str, body: str):
        """Sends a message via Twilio"""
        self.client.messages.create(from_=self.from_number, to=to, body=body)

TwilioInboundMessage = namedtuple("TwilioInboundMessage", ["body", "sender"])
