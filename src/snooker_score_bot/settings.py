import os
from typing import Union

from langchain_google_vertexai import VertexAI

from snooker_score_bot.models import MatchFormats


class EngMessages:
    INVALID = "Sorry, I could not understand the message."
    ALREADY_COMPLETED = "Match {} has already been played."


class FinMessages:
    INVALID = "En ymmärtänyt viestiä, pahoittelut."
    ALREADY_COMPLETED = "Ottelu {} on jo pelattu."

def get_messages(lang: str = "eng") -> Union[FinMessages, EngMessages]:
    return {
        "eng": EngMessages,
        "fin": FinMessages,
    }.get(lang.lower(), FinMessages)


messages = get_messages("fin")


class Settings:
    _env = "prod"
    LLM_PROVIDER = VertexAI
    LLM_MODEL = "gemini-2.5-flash"
    # https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations#global-endpoint
    LLM_LOCATION = "global"
    SHEETID = "1R2E2bx-0bj33z7jurkFAQED-24mgDQzYYmnm68lk5bY"
    SHEET_URL = "https://snooker.groovescore.app/sheet"  # shortened URL to the Google Sheet
    API_SECRET = os.getenv("SNOOKER_API_SECRET")
    MATCH_FORMAT = MatchFormats.LEAGUE.value
    PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY", "")
    PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN", "")
    PUSHOVER_ENABLED = os.getenv("PUSHOVER_ENABLED", "1") == "1"


class SixRedSettings(Settings):
    SHEETID = "16MlIIRn1WSLHpdGeArKB2-NzyN68zg4qXaU0UWGVUYs"
    SHEET_SHORTLINK = "tinyurl.com/gjss25"  # shortened URL to the Google Sheet
    MATCH_FORMAT = MatchFormats.SIXRED.value

class TestSettings(Settings):
    _env = "test"
    SHEETID = "1JUicaU5OHi8HR49j9O4ex_rv3veAvadkaoeuEOw6ucY"


def get_settings() -> Settings:
    if os.getenv("SNOOKER_SIXRED") == "1":
        return SixRedSettings()
    env = os.getenv("NODE_ENV", "test")
    if env.upper() == "PROD":
        return Settings()
    return TestSettings()
