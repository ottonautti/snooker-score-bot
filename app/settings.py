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
    MAX_SCORE = 2  # Matches are best of 3
    LLM = "vertexai"
    SHEETID = "1R2E2bx-0bj33z7jurkFAQED-24mgDQzYYmnm68lk5bY"
    SHEET_SHORTLINK = "https://tinyurl.com/groovesnk"  # shortened URL to the Google Sheet
    API_SECRET = os.getenv("SNOOKER_API_SECRET")
    MAX_SCORE = 2  # Matches are best of 3
    FORMAT = MatchFormats.BEST_OF_THREE


class TestSettings(Settings):
    _env = "test"
    SHEETID = "1JUicaU5OHi8HR49j9O4ex_rv3veAvadkaoeuEOw6ucY"


def get_settings() -> Settings:
    env = os.getenv("NODE_ENV", "test")
    if env.upper() == "PROD":
        return Settings
    return TestSettings
