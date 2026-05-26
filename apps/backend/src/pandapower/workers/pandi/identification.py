"""Auto-identification of Pandi clients by phone number."""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


async def auto_identify_by_phone(phone: str, supabase: Any) -> dict[str, Any]:
    """Try to auto-identify unknown phone as existing contact.

    Args:
        phone: Phone number in E.164 format
        supabase: Supabase client

    Returns:
        {success: bool, client_id: str|None, contact_id: str|None, reason: str}
    """
    try:
        # Look up contact by phone
        contact_result = supabase.table("contacts").select("*").eq(
            "phone", phone
        ).execute()

        if not contact_result.data:
            logger.info(f"Phone {phone} not found in contacts")
            return {"success": False, "reason": "Phone not in contacts"}

        contact = contact_result.data[0]
        contact_id = contact["id"]

        # Create pandi_client linked to this contact
        client_data = {
            "contact_id": contact_id,
            "phone": phone,
            "whatsapp_chat_id": f"{phone.replace('+', '')}@c.us",
            "identified_at": datetime.utcnow().isoformat(),
            "identification_method": "auto_phone_match",
            "intake_status": "completed",
            "first_message_at": datetime.utcnow().isoformat()
        }

        client_result = supabase.table("pandi_clients").insert(client_data).execute()

        if not client_result.data:
            logger.error(f"Failed to create pandi_client for contact {contact_id}")
            return {"success": False, "reason": "Client creation failed"}

        client_id = client_result.data[0]["id"]

        # Initialize quota for current month
        from .quota_manager import initialize_quota
        await initialize_quota(client_id, supabase)

        logger.info(f"Auto-identified phone {phone} as contact {contact_id}, client {client_id}")

        return {
            "success": True,
            "client_id": client_id,
            "contact_id": contact_id,
            "contact_name": contact.get("full_name")
        }

    except Exception as e:
        logger.error(f"Auto-identification failed: {e}", exc_info=True)
        return {"success": False, "reason": str(e)}
