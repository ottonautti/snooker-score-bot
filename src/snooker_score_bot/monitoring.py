"""Pushover client for sending push notifications."""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


@dataclass
class PushoverNotification:
    """Data class for a Pushover notification."""

    message: str
    title: Optional[str] = None
    priority: int = 0
    url: Optional[str] = None
    url_title: Optional[str] = None


class PushoverClient:
    """Client for sending notifications via Pushover API."""

    BASE_URL = "https://api.pushover.net/1/messages.json"

    def __init__(self, user_key: str, api_token: str, enabled: bool = True):
        """
        Initialize Pushover client.

        Args:
            user_key: Your Pushover user key
            api_token: Your Pushover application API token
            enabled: Whether notifications are enabled
        """
        self.user_key = user_key
        self.api_token = api_token
        self.enabled = enabled

    async def send_notification(
        self,
        message: str,
        title: Optional[str] = None,
        priority: int = 0,
        url: Optional[str] = None,
        url_title: Optional[str] = None,
    ) -> bool:
        """
        Send a push notification via Pushover (async).

        Args:
            message: The message content (required)
            title: Optional title for the notification
            priority: Priority level (-2 to 2, default 0)
            url: Optional URL to include
            url_title: Optional title for the URL

        Returns:
            True if notification sent successfully, False otherwise
        """
        if not self.enabled:
            logging.info("Pushover notifications disabled, skipping notification")
            return False

        if not self.user_key or not self.api_token:
            logging.warning("Pushover credentials not configured, skipping notification")
            return False

        payload = {
            "token": self.api_token,
            "user": self.user_key,
            "message": message,
            "priority": priority,
        }

        if title:
            payload["title"] = title
        if url:
            payload["url"] = url
        if url_title:
            payload["url_title"] = url_title

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.BASE_URL, data=payload, timeout=10.0)
                response.raise_for_status()
            logging.info("Pushover notification sent successfully")
            return True
        except:
            logging.exception("Error sending Pushover notification: %s", e)
            return False


def get_pushover_client(settings) -> PushoverClient:
    """Factory function to create a Pushover client from settings."""
    return PushoverClient(
        user_key=settings.PUSHOVER_USER_KEY,
        api_token=settings.PUSHOVER_API_TOKEN,
        enabled=settings.PUSHOVER_ENABLED,
    )


def queue_notification(request, notification: PushoverNotification) -> None:
    """Queue a notification to be sent after the request completes."""
    if not hasattr(request.state, "pushover_notification"):
        request.state.pushover_notification = notification
