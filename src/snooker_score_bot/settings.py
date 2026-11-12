import os
from typing import Union

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
    LEAGUE = "prod"
    GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "otto-snooker-bot")
    LLM_MODEL = "gemini-3.6-flash"
    # https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations#global-endpoint
    LLM_LOCATION = "global"
    LLM_THINKING_LEVEL = "minimal"  # reading a score needs no reasoning; more thinking only adds latency
    SHEETID = "1hu2_rqOObQ4UDGmPEmXKih67kJJZAD4FDLjQBotBbe0"
    SHEET_URL = "https://snooker.groovescore.app/sheet"  # shortened URL to the Google Sheet
    API_SECRET = os.getenv("SNOOKER_API_SECRET")
    MATCH_FORMAT = MatchFormats.LEAGUE.value
    # Sheet layout
    PREPARED_FIXTURES = True  # matches are generated per round in advance; results must match a fixture
    PLAYERS_COLUMNS = ("name", "group")  # column order of the nr_currentPlayers named range
    FIXED_ROUND = None  # round number to use when the sheet has no nr_rounds named range
    ALLOW_RESET = False  # whether all fixtures of a round may be deleted and regenerated
    # Reject SMS webhook requests without a valid Twilio signature. Turn off only for local testing with curl.
    VERIFY_TWILIO_SIGNATURE = os.getenv("TWILIO_VERIFY_SIGNATURE", "1") == "1"
    PUSHOVER_USER_KEY = os.getenv("PUSHOVER_USER_KEY", "")
    PUSHOVER_API_TOKEN = os.getenv("PUSHOVER_API_TOKEN", "")
    PUSHOVER_ENABLED = os.getenv("PUSHOVER_ENABLED", "1") == "1"


class SixRedSettings(Settings):
    LEAGUE = "sixred"
    SHEETID = "1Huic8_J3Zv7MK3KhpqUeVaekqbgemw-hmYPZTZ7tr84"
    SHEET_URL = "https://tinyurl.com/gjss26"  # shortened URL to the Six Red Google Sheet
    MATCH_FORMAT = MatchFormats.SIXRED.value
    PREPARED_FIXTURES = False
    PLAYERS_COLUMNS = ("group", "name")
    FIXED_ROUND = 1


class TestSettings(Settings):
    _env = "test"
    LEAGUE = "test"
    SHEETID = "1JUicaU5OHi8HR49j9O4ex_rv3veAvadkaoeuEOw6ucY"
    ALLOW_RESET = True


LEAGUES = {"prod": Settings, "test": TestSettings, "sixred": SixRedSettings}


def get_settings(league: str = None) -> Settings:
    """Settings for the named league, or the one selected by environment variables."""
    if league:
        return LEAGUES[league]()
    if os.getenv("SNOOKER_SIXRED") == "1":
        return SixRedSettings()
    env = os.getenv("NODE_ENV", "test")
    if env.upper() == "PROD":
        return Settings()
    return TestSettings()
