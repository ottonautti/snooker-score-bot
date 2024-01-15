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
