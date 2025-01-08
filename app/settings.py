import os
from typing import Union

from app.models import MatchFormats


class EngMessages:
    INVALID = "Sorry, I could not understand the message."


class FinMessages:
    INVALID = "En ymmärtänyt viestiä, pahoittelut."


def get_messages(lang: str) -> Union[FinMessages, EngMessages]:
    return {
        "eng": EngMessages,
        "fin": FinMessages,
    }.get(lang.lower(), FinMessages)


messages = get_messages("fin")


class Settings:
    MAX_SCORE = 2  # Matches are best of 3
    LLM = "vertexai"
    SHEET_SHORTLINK = "https://tinyurl.com/groovesnk"  # shortened URL to the Google Sheet
    API_SECRET = os.getenv("SNOOKER_API_SECRET")

class HouseLeagueSettings(Settings):
    MAX_SCORE = 2  # Matches are best of 3
    SHEETID = os.getenv("GOOGLESHEETS_SHEETID", "1R2E2bx-0bj33z7jurkFAQED-24mgDQzYYmnm68lk5bY")
    FORMAT = MatchFormats.BEST_OF_THREE


def get_settings(sixred24: bool = False):
    return HouseLeagueSettings
