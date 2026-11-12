from fastapi import status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def ok_created(content) -> JSONResponse:
    """Returns a successful response"""
    return JSONResponse(jsonable_encoder(content), status_code=status.HTTP_201_CREATED)
