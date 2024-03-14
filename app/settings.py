import os

from .messages import get_messages


class Settings:
    MAX_SCORE = 2  # Matches are best of 3
    APP_LANG = "fin"
    LLM = "vertexai"

    DEBUG = bool(os.environ.get("SNOOKER_DEBUG", False))
    SHEET_ENDPOINT_SHORTENED = "https://bit.ly/g147"  # shortened URL to the Google Sheet

settings = Settings()
messages = get_messages(settings.APP_LANG)

