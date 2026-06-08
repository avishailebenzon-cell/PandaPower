"""Onboarding flow for new Pandi clients through intake questionnaire."""

import logging
from datetime import datetime
from typing import Optional, Any
from uuid import UUID

logger = logging.getLogger(__name__)


async def continue_intake_flow(
    client_id: str,
    user_response: Optional[str],
    supabase: Any,
    is_first: bool = False
) -> dict[str, Any]:
    """Continue intake questionnaire for new client.

    4-step intake:
    1. What's your name?
    2. Which company?
    3. What's your role?
    4. Who referred you?

    Args:
        client_id: Pandi client ID
        user_response: Client's response to previous question (None if first call)
        supabase: Supabase client
        is_first: True if first call (send greeting)

    Returns:
        Processing result with next question or completion status
    """
    try:
        # Get current client
        client_result = supabase.table("pandi_clients").select("*").eq(
            "id", client_id
        ).execute()

        if not client_result.data:
            logger.error(f"Client {client_id} not found")
            return {"status": "failed", "reason": "Client not found"}

        client = client_result.data[0]
        intake_data = client.get("intake_collected_data") or {}
        step = len([k for k in ["name", "company", "role", "referrer"] if k in intake_data])

        # Opening greeting Pandi sends to every first-time contact.
        # Tone and wording confirmed by product: keep singular and friendly,
        # no bot disclosure beyond "סוכנת גיוס בינה מלאכותית".
        greeting = (
            "היי, אני פנדי סוכנת גיוס בינה מלאכותית של פנדה-טק. "
            "אני כאן כדי לעזור לך למצוא מועמד מתאים לתפקיד."
        )

        # First message: send greeting
        if is_first:
            # TODO: Queue outbound message via Green API
            logger.info(f"Sending greeting to client {client_id}")
            return {
                "status": "intake_started",
                "client_id": client_id,
                "step": 1,
                "next_question": greeting
            }

        # Save response and advance
        if step == 0 and user_response:  # After greeting, expect name
            intake_data["name"] = user_response
            next_q = "נעים מאוד {name}. מאיזה חברה אתה?".format(name=user_response)
        elif step == 1 and user_response:  # After name, expect company
            intake_data["company"] = user_response
            next_q = "ומה תפקידך ב{company}?".format(company=user_response)
        elif step == 2 and user_response:  # After company, expect role
            intake_data["role"] = user_response
            next_q = "האם מישהו ספציפי מ-PandaTech המליץ לך להגיע אליי? אם כן, מה שמו?"
        elif step == 3 and user_response:  # After role, expect referrer
            intake_data["referrer"] = user_response
            # Intake complete
            return await complete_intake(client_id, intake_data, supabase)
        else:
            logger.warning(f"Intake step mismatch: step={step}, response={user_response}")
            return {"status": "failed", "reason": "Intake step mismatch"}

        # Update client with collected data
        supabase.table("pandi_clients").update({
            "intake_collected_data": intake_data,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", client_id).execute()

        # TODO: Queue next question via Green API
        logger.info(f"Intake step {step + 1} for client {client_id}")

        return {
            "status": "intake_in_progress",
            "client_id": client_id,
            "step": step + 1,
            "next_question": next_q
        }

    except Exception as e:
        logger.error(f"Intake flow failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


async def complete_intake(
    client_id: str,
    intake_data: dict,
    supabase: Any
) -> dict[str, Any]:
    """Complete intake and create contact/organization.

    Args:
        client_id: Pandi client ID
        intake_data: Collected {name, company, role, referrer}
        supabase: Supabase client

    Returns:
        Completion status
    """
    try:
        logger.info(f"Completing intake for client {client_id}")

        # Create Contact
        contact_data = {
            "full_name": intake_data.get("name", "Unknown"),
            "contact_status": "potential_client",  # לקוח פוטנציאלי (canonical)
            "created_at": datetime.utcnow().isoformat()
        }

        contact_result = supabase.table("contacts").insert(contact_data).execute()
        if not contact_result.data:
            logger.error(f"Failed to create contact for intake {client_id}")
            return {"status": "failed", "reason": "Contact creation failed"}

        contact_id = contact_result.data[0]["id"]

        # Create Organization if not exists
        org_name = intake_data.get("company", "Unknown")
        org_result = supabase.table("organizations").select("id").eq(
            "name", org_name
        ).execute()

        if org_result.data:
            org_id = org_result.data[0]["id"]
        else:
            org_create = supabase.table("organizations").insert({
                "name": org_name,
                "org_type": "prospect",
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            org_id = org_create.data[0]["id"] if org_create.data else None

        # Update contact with organization
        if org_id:
            supabase.table("contacts").update({
                "organization_id": org_id
            }).eq("id", contact_id).execute()

        # Update pandi_client
        supabase.table("pandi_clients").update({
            "contact_id": contact_id,
            "intake_status": "completed",
            "identified_at": datetime.utcnow().isoformat(),
            "identification_method": "manual_intake_via_bot",
            "intake_collected_data": intake_data,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", client_id).execute()

        # Initialize quota for current month
        from .quota_manager import initialize_quota
        await initialize_quota(client_id, supabase)

        # Create conversation for this client
        conv_create = supabase.table("pandi_conversations").insert({
            "pandi_client_id": client_id,
            "status": "open",
            "started_at": datetime.utcnow().isoformat(),
            "last_activity_at": datetime.utcnow().isoformat()
        }).execute()

        conversation_id = conv_create.data[0]["id"] if conv_create.data else None

        # Get client details for greeting
        client_result = supabase.table("pandi_clients").select(
            "phone, whatsapp_chat_id"
        ).eq("id", client_id).execute()

        # Send opening greeting message via Green API
        if client_result.data:
            client = client_result.data[0]
            from pandapower.integrations.green_api import get_green_api_client

            green_api = await get_green_api_client("pandi")
            if green_api:
                opening_msg = f"שלום {intake_data.get('name', 'חבר')}! 🐼 נחמד להכיר אותך. עכשיו אוכל לעזור לך למצוא candidates! בואו נשמע על המשרה שאתה מחפש?"
                send_result = await green_api.send_message(
                    chat_id=client.get("whatsapp_chat_id"),
                    message=opening_msg,
                )
                logger.info(f"Opening greeting sent to client {client_id}: {send_result}")

                # Save the greeting as outbound message
                if conversation_id and send_result.get("success"):
                    supabase.table("pandi_messages").insert({
                        "conversation_id": conversation_id,
                        "pandi_client_id": client_id,
                        "direction": "outbound",
                        "message_type": "text",
                        "text": opening_msg,
                        "sent_at": datetime.utcnow().isoformat()
                    }).execute()

        # TODO: Notify admin via Telegram
        # admin_msg = f"🆕 לקוח פוטנציאלי חדש: {intake_data['name']} מ-{org_name}, התפקיד: {intake_data['role']}. הופנה ע\"י {intake_data.get('referrer', 'לא צוין')}"

        logger.info(f"Intake completed for client {client_id}, contact {contact_id}")

        return {
            "status": "intake_completed",
            "client_id": client_id,
            "contact_id": contact_id,
            "organization_id": org_id,
            "conversation_id": conversation_id
        }

    except Exception as e:
        logger.error(f"Intake completion failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}
