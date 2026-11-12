import logging
import os

from pydantic import BaseModel, ConfigDict, Field
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from snooker_score_bot.settings import Settings


class TwilioSms(BaseModel):
    """Form fields of Twilio's incoming-message webhook that the bot uses. Twilio sends more; they are ignored."""

    model_config = ConfigDict(populate_by_name=True)

    body: str = Field(alias="Body", min_length=1)
    sender: str = Field(alias="From", min_length=1)


class Twilio:
    skip_send = os.environ.get("TWILIO_NO_SEND", False)

    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        if not account_sid or not auth_token or not from_number:
            raise ValueError("Missing Twilio credentials")
        self.client = Client(account_sid, auth_token)
        self.validator = RequestValidator(auth_token)
        self.from_number = from_number
        if self.skip_send:
            self.client.messages.create = self._skip_send_message

    def _skip_send_message(self, *args, **kwargs):
        logging.warning("Twilio send is skipped.")
        return None

    def is_valid_request(self, url: str, params: dict, signature: str) -> bool:
        """Whether a webhook request really comes from Twilio: its X-Twilio-Signature header signs the URL and form
        fields with the account's auth token. https://www.twilio.com/docs/usage/webhooks/webhooks-security"""
        return self.validator.validate(url, params, signature)

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
