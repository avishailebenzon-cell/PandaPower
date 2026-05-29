"""Handler for incoming Pandi messages from Green API webhook."""

import logging
import asyncio
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from pandapower.workers.celery_app import app
from pandapower.core.supabase import get_supabase_client
from .identification import auto_identify_by_phone
from .onboarding import continue_intake_flow
from .conversation_handler import handle_client_message

logger = logging.getLogger(__name__)


async def _process_pandi_incoming_message_async(payload: dict) -> dict[str, Any]:
    """Process incoming message from Green API webhook.

    Args:
        payload: Green API webhook payload with message details

    Returns:
        Processing result summary
    """
    try:
        supabase = await get_supabase_client()

        # Extract message details from Green API payload
        # Green API format: messages[0] contains the message details
        messages = payload.get("messages", [])
        if not messages:
            logger.warning("Webhook payload has no messages")
            return {"status": "skipped", "reason": "No messages in payload"}

        message = messages[0]
        green_api_message_id = message.get("id")
        phone = message.get("from", "").replace("@c.us", "")
        message_text = message.get("text", "")
        timestamp = message.get("timestamp", int(datetime.utcnow().timestamp()))

        if not phone:
            logger.warning("Message has no sender phone")
            return {"status": "failed", "reason": "No sender phone"}

        # Check for duplicate message (idempotency)
        existing = supabase.table("pandi_messages").select("id").eq(
            "green_api_message_id", green_api_message_id
        ).execute()

        if existing.data:
            logger.info(f"Message {green_api_message_id} already processed")
            return {"status": "skipped", "reason": "Duplicate message"}

        # Look up pandi_client by phone
        client_result = supabase.table("pandi_clients").select("*").eq(
            "phone", phone
        ).execute()

        if client_result.data:
            # Client exists
            client = client_result.data[0]
            client_id = client["id"]
            logger.info(f"Incoming message from existing client {client_id}")

            # Update last_message_at
            supabase.table("pandi_clients").update({
                "last_message_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", client_id).execute()

            # Get active conversation for this client
            conv_result = supabase.table("pandi_conversations").select("*").eq(
                "pandi_client_id", client_id
            ).eq("status", "open").execute()

            conversation_id = conv_result.data[0]["id"] if conv_result.data else None

            # Create conversation if needed
            if not conversation_id:
                conv_create = supabase.table("pandi_conversations").insert({
                    "pandi_client_id": client_id,
                    "status": "open",
                    "started_at": datetime.utcnow().isoformat(),
                    "last_activity_at": datetime.utcnow().isoformat()
                }).execute()
                conversation_id = conv_create.data[0]["id"] if conv_create.data else None

            # Save incoming message
            supabase.table("pandi_messages").insert({
                "conversation_id": conversation_id,
                "pandi_client_id": client_id,
                "direction": "inbound",
                "message_type": "text",
                "green_api_message_id": green_api_message_id,
                "text": message_text,
                "sent_at": datetime.fromtimestamp(timestamp).isoformat()
            }).execute()

            # Check if client is in intake flow
            if client.get("intake_status") == "in_progress":
                # Continue intake
                logger.info(f"Continuing intake for client {client_id}")
                await continue_intake_flow(client_id, message_text, supabase)
            else:
                # Route to conversation handler (Session 28)
                logger.info(f"Routing to conversation handler for client {client_id}")
                if conversation_id:
                    conv_handler_result = await handle_client_message(
                        conversation_id=UUID(str(conversation_id)),
                        pandi_client_id=UUID(str(client_id)),
                        incoming_text=message_text,
                        chat_id=client.get("whatsapp_chat_id"),
                    )
                    logger.info(f"Conversation handler result: {conv_handler_result}")

            return {
                "status": "processed",
                "client_id": client_id,
                "is_new_client": False,
                "intake_in_progress": client.get("intake_status") == "in_progress"
            }

        else:
            # New client — try auto-identify or start intake
            logger.info(f"Incoming message from unknown phone: {phone}")

            # Try auto-identify
            auto_id_result = await auto_identify_by_phone(phone, supabase)

            if auto_id_result["success"]:
                client_id = auto_id_result["client_id"]
                contact_name = auto_id_result.get("contact_name")
                logger.info(f"Auto-identified as client {client_id}")

                # Create conversation
                conv_create = supabase.table("pandi_conversations").insert({
                    "pandi_client_id": client_id,
                    "status": "open",
                    "started_at": datetime.utcnow().isoformat(),
                    "last_activity_at": datetime.utcnow().isoformat()
                }).execute()
                conversation_id = conv_create.data[0]["id"] if conv_create.data else None

                # Save message
                supabase.table("pandi_messages").insert({
                    "conversation_id": conversation_id,
                    "pandi_client_id": client_id,
                    "direction": "inbound",
                    "message_type": "text",
                    "green_api_message_id": green_api_message_id,
                    "text": message_text,
                    "sent_at": datetime.fromtimestamp(timestamp).isoformat()
                }).execute()

                # Auto-identified clients already completed intake, route to conversation handler
                if conversation_id:
                    logger.info(f"Auto-identified client {client_id}, routing to conversation handler")
                    conv_handler_result = await handle_client_message(
                        conversation_id=UUID(str(conversation_id)),
                        pandi_client_id=UUID(str(client_id)),
                        incoming_text=message_text,
                        chat_id=f"{phone.replace('+', '')}@c.us",
                    )
                    logger.info(f"Conversation handler result: {conv_handler_result}")

                return {
                    "status": "processed",
                    "client_id": client_id,
                    "is_new_client": True,
                    "auto_identified": True
                }
            else:
                # No match — start intake flow
                logger.info(f"Starting intake for unknown phone: {phone}")

                # Create pandi_client with intake_status=in_progress
                client_create = supabase.table("pandi_clients").insert({
                    "phone": phone,
                    "whatsapp_chat_id": f"{phone.replace('+', '')}@c.us",
                    "intake_status": "in_progress",
                    "identification_method": "manual_intake_via_bot",
                    "first_message_at": datetime.utcnow().isoformat()
                }).execute()

                if not client_create.data:
                    logger.error(f"Failed to create pandi_client for {phone}")
                    return {"status": "failed", "reason": "Could not create client"}

                client_id = client_create.data[0]["id"]

                # Create conversation
                conv_create = supabase.table("pandi_conversations").insert({
                    "pandi_client_id": client_id,
                    "status": "open",
                    "started_at": datetime.utcnow().isoformat(),
                    "last_activity_at": datetime.utcnow().isoformat()
                }).execute()
                conversation_id = conv_create.data[0]["id"] if conv_create.data else None

                # Save message
                supabase.table("pandi_messages").insert({
                    "conversation_id": conversation_id,
                    "pandi_client_id": client_id,
                    "direction": "inbound",
                    "message_type": "text",
                    "green_api_message_id": green_api_message_id,
                    "text": message_text,
                    "sent_at": datetime.fromtimestamp(timestamp).isoformat()
                }).execute()

                # Route to conversation handler for Pandi to handle client identification
                # (Session 34: Pandi handles new client intake via tools)
                logger.info(f"New client {client_id}, routing to conversation handler for Pandi to identify")
                if conversation_id:
                    conv_handler_result = await handle_client_message(
                        conversation_id=UUID(str(conversation_id)),
                        pandi_client_id=UUID(str(client_id)),
                        incoming_text=message_text,
                        chat_id=f"{phone.replace('+', '')}@c.us",
                    )
                    logger.info(f"Conversation handler result: {conv_handler_result}")

                return {
                    "status": "processed",
                    "client_id": client_id,
                    "is_new_client": True,
                    "intake_started": False
                }

    except Exception as e:
        logger.error(f"Failed to process Pandi message: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True)
def process_pandi_incoming_message(self, payload: dict) -> dict[str, Any]:
    """Celery task to process incoming Pandi webhook message.

    Args:
        payload: Green API webhook payload

    Returns:
        Processing result
    """
    logger.info("Processing incoming Pandi message")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_process_pandi_incoming_message_async(payload))
            logger.info(f"Pandi message processed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Pandi message processing task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
