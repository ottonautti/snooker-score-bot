from .messages import get_messages

class Settings:
    MAX_SCORE = 2  # Matches are best of 3
    APP_LANG = "fin"


settings = Settings()
messages = get_messages(settings.APP_LANG)
