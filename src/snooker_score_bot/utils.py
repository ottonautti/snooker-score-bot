from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import ORJSONResponse


def ok_created(content) -> ORJSONResponse:
    """Returns a successful response"""
    return ORJSONResponse(jsonable_encoder(content), status_code=status.HTTP_201_CREATED)
