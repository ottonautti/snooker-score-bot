from typing import Literal, Union


class EngMessages:
    OK = "Thank you, match was recorded as:\n{}"
    INVALID = "Sorry, I could not understand the message."

class FinMessages:
    OK = "Kiitos, ottelu kirjattiin:\n{}"
    INVALID = "En ymmärtänyt viestiä, pahoittelut."

def get_messages(lang: Literal["fin", "eng"]) -> Union[FinMessages, EngMessages]:
    if lang.lower() == "fin":
        return FinMessages
    else:
        return EngMessages
