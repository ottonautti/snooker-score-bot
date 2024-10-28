import os

from typing import Union


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


class SixRed24Settings(Settings):
    MAX_SCORE = 3  # Matches are best of 5
    SHEETID = "1NUEP1Mrl7-FPbr98rVNjULVdzQutCVi5PwlQEl6dez4"
    SHEET_SHORTLINK = "https://bit.ly/g147-6R24"  # shortened URL to the Google Sheet


class HouseLeagueSettings(Settings):
    MAX_SCORE = 2  # Matches are best of 3
    SHEETID = "1R2E2bx-0bj33z7jurkFAQED-24mgDQzYYmnm68lk5bY"


def get_settings(sixred24: bool = False):
    if sixred24:
        return SixRed24Settings
    return HouseLeagueSettings
