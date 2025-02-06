from fastapi import HTTPException, status


class InvalidContentType(HTTPException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Content-Type")


class MatchNotFound(HTTPException):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Match not found"

    def __init__(self):
        super().__init__(status_code=self.status_code, detail=self.detail)


class MatchAlreadyCompleted(HTTPException):
    status_code = status.HTTP_409_CONFLICT
    detail = "Match already completed"

    def __init__(self):
        super().__init__(status_code=self.status_code, detail=self.detail)


class InvalidMatchError(HTTPException):
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail=None):
        self.detail = detail or "Invalid match"
        super().__init__(status_code=self.status_code, detail=self.detail)


class MatchFixtureMismatchError(ValueError):
    pass
