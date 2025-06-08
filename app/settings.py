import os
from typing import Union

from app.models import MatchFormats


class EngMessages:
    INVALID = "Sorry, I could not understand the message."


class FinMessages:
    INVALID = "En ymmärtänyt viestiä, pahoittelut."


def get_messages(lang: str = "eng") -> Union[FinMessages, EngMessages]:
    return {
        "eng": EngMessages,
        "fin": FinMessages,
    }.get(lang.lower(), FinMessages)


messages = get_messages("fin")


class Settings:
    _env = "prod"
    LLM = "vertexai"
    SHEETID = "1R2E2bx-0bj33z7jurkFAQED-24mgDQzYYmnm68lk5bY"
    SHEET_SHORTLINK = "https://tinyurl.com/groovesnk"  # shortened URL to the Google Sheet
    API_SECRET = os.getenv("SNOOKER_API_SECRET")
    FORMAT = MatchFormats.LEAGUE


class SixRedSettings(Settings):
    SHEETID = "xxx"
    SHEET_SHORTLINK = "https://tinyurl.com/groovesnk/sixred"  # shortened URL to the Google Sheet
    FORMAT = MatchFormats.SIXRED

class TestSettings(Settings):
    _env = "test"
    SHEETID = "1JUicaU5OHi8HR49j9O4ex_rv3veAvadkaoeuEOw6ucY"


def get_settings() -> Settings:
    # if env var "SIXRED" == 1
    if os.getenv("SIXRED") == "1":
        return Settings
    env = os.getenv("NODE_ENV", "test")
    if env.upper() == "PROD":
        return Settings
    return TestSettings
