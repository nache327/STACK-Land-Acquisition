"""Thin Resend HTTP-API wrapper.

Only the digest worker uses this today. We hit Resend's REST endpoint
directly with httpx instead of pulling in the SDK — keeps deps lean and
the failure modes obvious. When ``RESEND_API_KEY`` is unset we log the
rendered email and short-circuit, so the worker is safe to deploy
before the secret lands in Railway.
"""
from __future__ import annotations

import logging
from typing import Sequence

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


async def send_email(
    *,
    to: str | Sequence[str],
    subject: str,
    text: str,
    html: str,
    from_address: str | None = None,
) -> str | None:
    """Send a single email via Resend. Returns the message id, or None
    when ``RESEND_API_KEY`` isn't configured (in which case the body is
    logged instead).
    """
    recipients = [to] if isinstance(to, str) else list(to)

    if not settings.resend_enabled:
        logger.info(
            "RESEND_API_KEY not set — would have sent to=%s subject=%r\n--- text ---\n%s",
            recipients, subject, text,
        )
        return None

    payload = {
        "from": from_address or settings.resend_from_address,
        "to": recipients,
        "subject": subject,
        "text": text,
        "html": html,
    }
    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(_RESEND_URL, json=payload, headers=headers)
    if resp.status_code >= 300:
        logger.error("Resend send failed: %s %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
    return resp.json().get("id")
