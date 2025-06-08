from fastapi import APIRouter, Depends

from .twilio_client import parse_twilio_msg


sixred_router = APIRouter()


@sixred_router.post("/scores", include_in_schema=False, summary="Report result for a six-red snooker match")
async def sixred_post_scores_sms(msg=Depends(parse_twilio_msg)):
    """Handles inbound scores for a six-red snooker match."""
