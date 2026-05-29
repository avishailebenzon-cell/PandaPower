"""Celery task: Send Elad outreach messages with rate limiting (Session 35)"""

import asyncio
import logging
import time
from datetime import datetime
from uuid import UUID

from pandapower.workers.celery_app import app
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.green_api import get_green_api_client

logger = logging.getLogger(__name__)


async def _process_elad_outreach_async(campaign_id: str) -> dict:
    """Process outreach campaign: send messages with rate limiting"""
    try:
        supabase = await get_supabase_client()

        # Get campaign
        campaign_result = await supabase.table("elad_outreach_campaigns").select("*").eq(
            "id", campaign_id
        ).execute()

        if not campaign_result.data:
            logger.error(f"Campaign {campaign_id} not found")
            return {"status": "failed", "reason": "Campaign not found"}

        campaign = campaign_result.data[0]
        logger.info(f"Processing outreach campaign {campaign_id}: {campaign.get('campaign_name')}")

        # Get Elad Green API client
        try:
            elad_client = await get_green_api_client("elad")
            if not elad_client:
                raise Exception("Elad WhatsApp not configured")
        except Exception as e:
            logger.error(f"Failed to get Green API client: {e}")
            return {"status": "failed", "reason": str(e)}

        # Get pending messages
        messages_result = await supabase.table("elad_outreach_messages").select("*").eq(
            "campaign_id", campaign_id
        ).eq("status", "pending").execute()

        messages = messages_result.data or []
        logger.info(f"Sending {len(messages)} messages for campaign {campaign_id}")

        sent_count = 0
        failed_count = 0

        # Send each message with 3-second rate limiting
        for i, msg in enumerate(messages):
            try:
                chat_id = msg.get("green_api_chat_id")
                message_text = msg.get("message_text")

                if not chat_id:
                    logger.warning(f"Message {msg.get('id')} missing chat_id")
                    await supabase.table("elad_outreach_messages").update({
                        "status": "failed",
                        "error_message": "No WhatsApp number found"
                    }).eq("id", msg.get("id")).execute()
                    failed_count += 1
                    continue

                # Send message via Green API
                logger.info(f"Sending message {i+1}/{len(messages)} to {chat_id}")
                result = await elad_client.send_message(chat_id, message_text)

                if result and result.get("success") or result.get("idMessage"):
                    # Mark as sent
                    await supabase.table("elad_outreach_messages").update({
                        "status": "sent",
                        "green_api_message_id": result.get("idMessage"),
                        "sent_at": datetime.utcnow().isoformat()
                    }).eq("id", msg.get("id")).execute()
                    sent_count += 1
                    logger.info(f"✅ Message sent to {chat_id}")
                else:
                    # Mark as failed
                    error_msg = result.get("error") or "Unknown error"
                    await supabase.table("elad_outreach_messages").update({
                        "status": "failed",
                        "error_message": error_msg
                    }).eq("id", msg.get("id")).execute()
                    failed_count += 1
                    logger.warning(f"❌ Message failed to {chat_id}: {error_msg}")

            except Exception as e:
                logger.error(f"Error sending message {msg.get('id')}: {e}", exc_info=True)
                failed_count += 1
                try:
                    await supabase.table("elad_outreach_messages").update({
                        "status": "failed",
                        "error_message": str(e)[:200]
                    }).eq("id", msg.get("id")).execute()
                except Exception as update_e:
                    logger.error(f"Failed to update message status: {update_e}")

            # Rate limiting: 3 seconds between sends
            if i < len(messages) - 1:
                logger.info(f"Rate limiting: sleeping 3 seconds before next message...")
                await asyncio.sleep(3)

        # Update campaign: set final status
        status = "completed" if failed_count == 0 else "completed_with_errors"
        await supabase.table("elad_outreach_campaigns").update({
            "status": status,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "completed_at": datetime.utcnow().isoformat()
        }).eq("id", campaign_id).execute()

        logger.info(f"Campaign {campaign_id} completed: {sent_count} sent, {failed_count} failed")

        return {
            "status": "completed",
            "campaign_id": campaign_id,
            "sent_count": sent_count,
            "failed_count": failed_count
        }

    except Exception as e:
        logger.error(f"Outreach processing failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}


@app.task(bind=True, default_retry_delay=60, max_retries=3)
def process_elad_outreach(self, campaign_id: str) -> dict:
    """Celery task to process Elad outreach campaign

    Rate limiting: messages are sent at 3-second intervals (no spam flagging)

    Args:
        campaign_id: UUID of the campaign to process

    Returns:
        Result dict with status, sent_count, failed_count
    """
    logger.info(f"Starting Elad outreach task for campaign {campaign_id}")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_process_elad_outreach_async(campaign_id))
            logger.info(f"Outreach task completed: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Outreach task failed: {e}", exc_info=True)
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=min(60 * (2 ** self.request.retries), 3600))
