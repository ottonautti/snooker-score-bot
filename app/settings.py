from .messages import get_messages
import os

class Settings:
    MAX_SCORE = 2  # Matches are best of 3
    APP_LANG = "fin"
    LLM = "vertexai"

    DEBUG = bool(os.environ.get("SNOOKER_DEBUG", False))

settings = Settings()
messages = get_messages(settings.APP_LANG)
