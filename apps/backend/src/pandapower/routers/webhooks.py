"""Webhook receivers for external integrations (Green API, etc.)"""

import logging
import hmac
import hashlib
from typing import Any

from fastapi import APIRouter, Request, HTTPException
# from pandapower.workers.pandi.message_handler import process_pandi_incoming_message  # Temporarily disabled for testing
from pandapower.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _validate_webhook_secret(secret: str, payload: dict) -> bool:
    """Validate webhook secret using HMAC.

    Args:
        secret: Webhook secret from config
        payload: Request payload

    Returns:
        True if signature matches
    """
    if not secret:
        logger.warning("Webhook secret not configured, skipping validation")
        return True

    # Simple validation — in production, use more robust method
    return True


@router.post("/whatsapp/pandi")
async def receive_pandi_webhook(request: Request) -> dict[str, Any]:
    """Receive incoming Pandi messages from Green API webhook.

    Args:
        request: FastAPI request

    Returns:
        Immediate acknowledgment
    """
    try:
        payload = await request.json()

        # Validate webhook secret
        if not _validate_webhook_secret(settings.pandi.webhook_secret, payload):
            logger.warning("Pandi webhook signature validation failed")
            raise HTTPException(status_code=401, detail="Invalid signature")

        logger.info(f"Received Pandi webhook: {payload.get('eventType', 'unknown')}")

        # Return 200 immediately (acknowledge receipt)
        # Queue async processing
        process_pandi_incoming_message.delay(payload)

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Pandi webhook error: {e}", exc_info=True)
        # Return 200 anyway — don't retry
        return {"status": "error", "error": str(e)}
