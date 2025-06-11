import os
from typing import Union
from langchain_google_vertexai import VertexAI

from app.models import MatchFormats


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
    LLM = VertexAI
    SHEETID = "1R2E2bx-0bj33z7jurkFAQED-24mgDQzYYmnm68lk5bY"
    SHEET_SHORTLINK = "https://tinyurl.com/groovesnk"  # shortened URL to the Google Sheet
    API_SECRET = os.getenv("SNOOKER_API_SECRET")
    MATCH_FORMAT = MatchFormats.LEAGUE.value


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
