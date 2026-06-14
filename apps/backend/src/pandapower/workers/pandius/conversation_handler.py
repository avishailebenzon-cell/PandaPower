"""Run Pandius's engine on an inbound message and deliver his reply."""

import logging
from uuid import UUID

from pandapower.agents.pandius import PandiusConversationEngine
from pandapower.integrations.green_api import get_green_api_client
from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)


async def _alert_admin_delivery_problem(
    pandius_client_id: UUID,
    phone: str,
    reason: str,
    response_preview: str = "",
    engine_error: bool = False,
) -> None:
    """Push a critical admin alert when a candidate could not be answered.

    Best-effort safety net so a candidate request never sits unseen because a
    WhatsApp send failed or the engine errored. Never raises.
    """
    try:
        from pandapower.agents.pandi.notification_service import NotificationService
        from pandapower.agents.pandius.tool_handlers import (
            _resolve_pandius_client_name,
        )

        supabase = await get_supabase_client()
        client_name = await _resolve_pandius_client_name(supabase, pandius_client_id)
        notifier = NotificationService()
        if engine_error:
            await notifier.notify_engine_error(
                client_name=client_name, phone=phone or "—", reason=reason
            )
        else:
            await notifier.notify_delivery_failure(
                client_name=client_name,
                phone=phone or "—",
                reason=reason,
                response_preview=response_preview,
            )
    except Exception as e:  # pragma: no cover - best effort
        logger.warning(f"Pandius admin delivery alert failed: {e}")


async def handle_candidate_message(
    conversation_id: UUID,
    pandius_client_id: UUID,
    incoming_text: str,
    chat_id: str,
    phone: str = "",
) -> dict:
    """Generate Pandius's reply and send it to the candidate via WhatsApp."""
    engine = PandiusConversationEngine()
    result = await engine.handle_message(
        conversation_id=conversation_id,
        pandius_client_id=pandius_client_id,
        incoming_text=incoming_text,
        phone=phone,
    )

    response_text = (result or {}).get("text", "") if isinstance(result, dict) else ""
    delivered = False
    send_error = "no_green_api_client"
    if response_text and chat_id:
        try:
            client = await get_green_api_client("pandius")
            if client:
                send_result = await client.send_message(chat_id, response_text)
                delivered = bool(send_result.get("success"))
                if not delivered:
                    send_error = str(send_result.get("error", "send_failed"))
                await client.close()
        except Exception as e:
            send_error = str(e)
            logger.warning(f"Pandius WhatsApp send failed (message saved): {e}")

    # If Pandius produced a reply but it never reached the candidate, alert the
    # admin so the lead is not lost silently.
    if response_text and chat_id and not delivered:
        await _alert_admin_delivery_problem(
            pandius_client_id, phone, send_error, response_text
        )

    return {
        "status": "sent" if delivered else "saved",
        "response_text": response_text,
    }
