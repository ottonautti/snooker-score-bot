from typing import Literal, Union

class EngMessages:
    REPLY_201 = "Thank you, match was recorded as:\n{}"
    REPLY_404 = "Sorry, I could not understand the message."
    REPLY_404_REPORTED = "Error has been reported."

class FinMessages:
    REPLY_201 = "Kiitos, ottelu kirjattiin:\n{}"
    REPLY_404 = "En ymmärtänyt viestiä, pahoittelut."
    REPLY_404_REPORTED = "Vikatilanne on raportoitu."

def get_messages(lang: Literal["fin", "eng"]) -> Union[FinMessages, EngMessages]:
    if lang.lower() == "fin":
        return FinMessages
    else:
        return EngMessages
