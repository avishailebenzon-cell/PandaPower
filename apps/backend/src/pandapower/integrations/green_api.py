"""Green API client for WhatsApp messaging integration.

Supports multiple instances (Tal, Elad, Pandi) with instance-specific
credentials. Factory function routes to correct instance based on agent code.
"""

import aiohttp
import logging
from typing import Literal, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class GreenAPIMessage(BaseModel):
    """Green API message payload structure."""
    chatId: str
    message: str


class GreenAPIResponse(BaseModel):
    """Green API response wrapper."""
    apiStatus: str
    idMessage: Optional[str] = None


class GreenAPIClient:
    """Client for Green API WhatsApp integration."""

    def __init__(self, instance_id: str, token: str):
        """Initialize Green API client.

        Args:
            instance_id: Green API instance ID
            token: Green API authentication token
        """
        self.instance_id = instance_id
        self.token = token
        self.base_url = f"https://api.green-api.com/waInstance{instance_id}"
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def send_message(self, chat_id: str, message: str) -> dict:
        """Send a text message via WhatsApp.

        Args:
            chat_id: WhatsApp chat ID (typically phone@c.us format)
            message: Message text to send

        Returns:
            API response with message ID if successful
        """
        session = await self._get_session()
        url = f"{self.base_url}/sendMessage/{self.token}"
        payload = {
            "chatId": chat_id,
            "message": message
        }

        try:
            async with session.post(url, json=payload) as response:
                data = await response.json()
                if response.status == 200:
                    return {
                        "success": True,
                        "messageId": data.get("idMessage"),
                        "status": data.get("apiStatus")
                    }
                else:
                    logger.error(f"Green API send message failed: {data}")
                    return {
                        "success": False,
                        "error": data.get("message", "Unknown error")
                    }
        except Exception as e:
            logger.error(f"Green API request failed: {e}")
            return {"success": False, "error": str(e)}

    async def send_file(self, chat_id: str, url_file: str, filename: str = "") -> dict:
        """Send a file via WhatsApp.

        Args:
            chat_id: WhatsApp chat ID
            url_file: URL of the file to send
            filename: Optional filename for the file

        Returns:
            API response with message ID if successful
        """
        session = await self._get_session()
        url = f"{self.base_url}/sendFileByUrl/{self.token}"
        payload = {
            "chatId": chat_id,
            "urlFile": url_file,
            "fileName": filename or "file"
        }

        try:
            async with session.post(url, json=payload) as response:
                data = await response.json()
                if response.status == 200:
                    return {
                        "success": True,
                        "messageId": data.get("idMessage"),
                        "status": data.get("apiStatus")
                    }
                else:
                    logger.error(f"Green API send file failed: {data}")
                    return {
                        "success": False,
                        "error": data.get("message", "Unknown error")
                    }
        except Exception as e:
            logger.error(f"Green API request failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_me(self) -> dict:
        """Get account information including WhatsApp number.

        Returns:
            Account info with phone number
        """
        session = await self._get_session()
        url = f"{self.base_url}/getMe/{self.token}"

        try:
            async with session.get(url) as response:
                data = await response.json()
                if response.status == 200:
                    return {
                        "success": True,
                        "phone": data.get("wid", "").replace("@c.us", ""),
                        "status": data.get("status")
                    }
                else:
                    logger.error(f"Green API getMe failed: {data}")
                    return {"success": False, "error": data.get("message", "Unknown error")}
        except Exception as e:
            logger.error(f"Green API request failed: {e}")
            return {"success": False, "error": str(e)}

    async def close(self):
        """Close the session."""
        if self.session:
            await self.session.close()
            self.session = None


async def get_green_api_client(
    agent_code: Literal["tal", "elad", "pandi"]
) -> Optional[GreenAPIClient]:
    """Factory function to get Green API client for specific agent.

    Args:
        agent_code: Which agent to get credentials for

    Returns:
        Configured GreenAPIClient or None if credentials not available
    """
    from pandapower.core.supabase import get_supabase_client

    try:
        supabase = await get_supabase_client()

        # Fetch instance ID and token from system_settings
        settings_keys = [
            f"{agent_code}.instance_id",
            f"{agent_code}.token"
        ]

        settings_response = supabase.table("system_settings").select(
            "key, value"
        ).in_("key", settings_keys).execute()

        settings_dict = {}
        for row in settings_response.data or []:
            settings_dict[row["key"]] = row["value"]

        instance_id = settings_dict.get(f"{agent_code}.instance_id", "").strip()
        token = settings_dict.get(f"{agent_code}.token", "").strip()

        if not instance_id or not token:
            logger.warning(f"Green API credentials for {agent_code} not configured")
            return None

        return GreenAPIClient(instance_id=instance_id, token=token)

    except Exception as e:
        logger.error(f"Failed to get Green API client for {agent_code}: {e}")
        return None
