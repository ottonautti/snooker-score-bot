from fastapi import HTTPException, status


class MatchNotFound(HTTPException):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Match not found (from fixtures)"

    def __init__(self, detail=None):
        super().__init__(status_code=self.status_code, detail=detail or self.detail)


class MatchAlreadyCompleted(HTTPException):
    status_code = status.HTTP_409_CONFLICT
    detail = "Match already completed"

    def __init__(self):
        super().__init__(status_code=self.status_code, detail=self.detail)


class StaleRowError(HTTPException):
    """A sheet row changed between reading and writing it."""

    status_code = status.HTTP_409_CONFLICT

    def __init__(self, detail):
        super().__init__(status_code=self.status_code, detail=detail)


class NotAllowedError(HTTPException):
    """The operation is not allowed for this league."""

    status_code = status.HTTP_403_FORBIDDEN

    def __init__(self, detail):
        super().__init__(status_code=self.status_code, detail=detail)


class SmsReplyError(HTTPException):
    """Error that carries a reply to send back to the SMS sender."""

    status_code = status.HTTP_400_BAD_REQUEST
    reply = "Sorry, I could not understand the message."

    def __init__(self, detail=None):
        super().__init__(status_code=self.status_code, detail=detail or self.reply)


class UnknownPlayersError(SmsReplyError):
    reply = "Sorry, I could not recognise both players. Please use names as they appear in the league table."


class AmbiguousPlayersError(SmsReplyError):
    def __init__(self, candidates, scoreline=None):
        """candidates: player pairs in the order they are mentioned; scoreline: frames in the same order, used only in
        the example of how to resend."""
        score = f" {scoreline[0]}-{scoreline[1]}" if scoreline else ""
        options = "\n".join(f"{a} - {b} ({a.group})" for a, b in candidates)
        a, b = candidates[0]
        self.reply = (
            f"Nothing was recorded. Your message fits more than one match:\n\n{options}\n\n"
            f"Please send the result again with full names, e.g. \"{a.name} - {b.name}{score or ' 2-0'}\"."
        )
        super().__init__(detail=self.reply)


class InferenceMismatchError(SmsReplyError):
    """The LLM's interpretation disagrees with the message. Details are logged, the sender gets a generic reply."""

    def __init__(self, detail):
        super().__init__(detail=detail)


class AmbiguousIdError(HTTPException):
    """A match id prefix fits more than one match."""

    status_code = status.HTTP_409_CONFLICT

    def __init__(self, detail):
        super().__init__(status_code=self.status_code, detail=detail)
