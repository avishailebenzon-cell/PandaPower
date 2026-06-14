"""Conversation handler integrating ConversationEngine with Green API messaging."""

import logging
from typing import Any, Optional
from uuid import UUID

from pandapower.agents.pandi.conversation_engine import ConversationEngine
from pandapower.integrations.green_api import get_green_api_client
from pandapower.core.supabase import get_supabase_client

import structlog as _structlog
logger = _structlog.get_logger(__name__)


async def _alert_admin_delivery_problem(
    pandi_client_id: UUID,
    chat_id: str,
    reason: str,
    response_preview: str = "",
    engine_error: bool = False,
) -> None:
    """Push a critical admin alert when a client message could not be answered.

    Best-effort safety net: a client request must never sit unseen because a
    WhatsApp send failed or the engine errored. Never raises.
    """
    try:
        from pandapower.agents.pandi.notification_service import NotificationService
        from pandapower.agents.pandi.tool_handlers import _resolve_client_name

        supabase = await get_supabase_client()
        client_name = await _resolve_client_name(supabase, pandi_client_id)
        phone = (chat_id or "").split("@")[0] or "—"
        notifier = NotificationService()
        if engine_error:
            await notifier.notify_engine_error(
                client_name=client_name, phone=phone, reason=reason
            )
        else:
            await notifier.notify_delivery_failure(
                client_name=client_name,
                phone=phone,
                reason=reason,
                response_preview=response_preview,
            )
    except Exception as e:  # pragma: no cover - best effort
        logger.warning("admin_delivery_alert_failed", error=str(e))


async def handle_client_message(
    conversation_id: UUID,
    pandi_client_id: UUID,
    incoming_text: str,
    chat_id: str,
) -> dict[str, Any]:
    """Process client message through ConversationEngine and send response.

    Args:
        conversation_id: UUID of the conversation
        pandi_client_id: UUID of the Pandi client
        incoming_text: Text of the incoming message
        chat_id: WhatsApp chat ID for sending response

    Returns:
        Processing result with response delivery status
    """
    logger.info(
        "handle_client_message",
        conversation_id=str(conversation_id),
        pandi_client_id=str(pandi_client_id),
        text_preview=incoming_text[:100],
    )

    try:
        # Initialize conversation engine
        engine = ConversationEngine()

        # Process message through engine
        response = await engine.handle_message(
            conversation_id=conversation_id,
            pandi_client_id=pandi_client_id,
            incoming_text=incoming_text,
        )

        if not response:
            logger.error("ConversationEngine returned None")
            return {"status": "failed", "reason": "No response from engine"}

        response_text = response.get("text", "")
        is_blocked = response.get("blocked", False)

        if not response_text:
            logger.warning("ConversationEngine returned empty response")
            return {"status": "failed", "reason": "Empty response from engine"}

        # Send response via Green API
        green_api = await get_green_api_client("pandi")
        if not green_api:
            logger.error("Could not initialize Green API client")
            await _alert_admin_delivery_problem(
                pandi_client_id, chat_id, "Green API not available", response_text
            )
            return {"status": "failed", "reason": "Green API not available"}

        send_result = await green_api.send_message(
            chat_id=chat_id,
            message=response_text,
        )

        if not send_result.get("success"):
            logger.error(f"Failed to send message: {send_result.get('error')}")
            await _alert_admin_delivery_problem(
                pandi_client_id,
                chat_id,
                send_result.get("error", "Send failed"),
                response_text,
            )
            return {
                "status": "response_failed",
                "reason": send_result.get("error", "Send failed"),
                "engine_response_sent_to_db": True,
            }

        # Save outgoing message to DB (already done by engine)
        logger.info(
            "message_processed_and_sent",
            conversation_id=str(conversation_id),
            message_id=send_result.get("messageId"),
            blocked=is_blocked,
        )

        return {
            "status": "success",
            "message_id": send_result.get("messageId"),
            "blocked": is_blocked,
            "reason": response.get("reason"),
        }

    except Exception as e:
        logger.error(
            "conversation_handling_failed",
            error=str(e),
            exc_info=True,
        )
        await _alert_admin_delivery_problem(
            pandi_client_id, chat_id, str(e), engine_error=True
        )
        return {"status": "failed", "reason": str(e)}
