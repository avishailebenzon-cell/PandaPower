"""Run Pandius's engine on an inbound message and deliver his reply."""

import logging
from uuid import UUID

from pandapower.agents.pandius import PandiusConversationEngine
from pandapower.integrations.green_api import get_green_api_client

logger = logging.getLogger(__name__)


async def handle_candidate_message(
    conversation_id: UUID,
    pandius_client_id: UUID,
    incoming_text: str,
    chat_id: str,
) -> dict:
    """Generate Pandius's reply and send it to the candidate via WhatsApp."""
    engine = PandiusConversationEngine()
    result = await engine.handle_message(
        conversation_id=conversation_id,
        pandius_client_id=pandius_client_id,
        incoming_text=incoming_text,
    )

    response_text = (result or {}).get("text", "") if isinstance(result, dict) else ""
    delivered = False
    if response_text and chat_id:
        try:
            client = await get_green_api_client("pandius")
            if client:
                send_result = await client.send_message(chat_id, response_text)
                delivered = bool(send_result.get("success"))
                await client.close()
        except Exception as e:
            logger.warning(f"Pandius WhatsApp send failed (message saved): {e}")

    return {
        "status": "sent" if delivered else "saved",
        "response_text": response_text,
    }
