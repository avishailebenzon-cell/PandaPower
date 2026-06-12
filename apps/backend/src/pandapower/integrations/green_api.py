"""Green API client for WhatsApp messaging integration.

Supports multiple instances (Tal, Elad, Pandi) with instance-specific
credentials. Factory function routes to correct instance based on agent code.
"""

import aiohttp
import logging
from typing import Literal, Optional
from pydantic import BaseModel

from pandapower.core import phone as phone_utils

logger = logging.getLogger(__name__)


def normalize_chat_id(chat_id: str) -> Optional[str]:
    """Coerce any caller-supplied recipient into a valid Green API chatId.

    Accepts the three shapes that flow through this client:
      * a bare phone in any format ("058-666-5248", "+972…", "0586665248")
        -> canonical "<intl>@c.us"
      * an already-built individual chatId ("9725…@c.us") -> re-validated
      * a group / lid chatId ("…@g.us" / "…@lid") -> passed through as-is

    Returns ``None`` when an individual recipient's number is not a valid
    WhatsApp number, so the caller can fail loudly instead of POSTing junk."""
    cid = (chat_id or "").strip()
    if not cid:
        return None
    if cid.endswith("@g.us") or cid.endswith("@lid"):
        return cid
    # Individual chatId or bare phone — validate/normalize the number part.
    raw = phone_utils.chat_id_to_phone(cid) if "@" in cid else cid
    return phone_utils.to_chat_id(raw)


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
        normalized = normalize_chat_id(chat_id)
        if not normalized:
            logger.error(f"Green API send aborted: invalid recipient '{chat_id}'")
            return {"success": False, "error": f"invalid phone/chatId: {chat_id}"}
        chat_id = normalized

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

    async def send_buttons(
        self, chat_id: str, body: str, buttons: list[dict], footer: str = ""
    ) -> dict:
        """Send an interactive button message via WhatsApp (Green API sendButtons).

        ``buttons`` is a list of {"buttonId": str, "buttonText": str}. Not every
        WhatsApp/Green-API account supports interactive buttons; callers must
        treat a falsy ``success`` as "buttons unavailable" and fall back to a
        plain numbered-text prompt so the flow never stalls.
        """
        normalized = normalize_chat_id(chat_id)
        if not normalized:
            logger.error(f"Green API send_buttons aborted: invalid recipient '{chat_id}'")
            return {"success": False, "error": f"invalid phone/chatId: {chat_id}"}
        chat_id = normalized

        session = await self._get_session()
        url = f"{self.base_url}/sendButtons/{self.token}"
        payload = {"chatId": chat_id, "message": body, "buttons": buttons}
        if footer:
            payload["footer"] = footer

        try:
            async with session.post(url, json=payload) as response:
                data = await response.json()
                if response.status == 200 and data.get("idMessage"):
                    return {"success": True, "messageId": data.get("idMessage")}
                logger.warning(f"Green API send_buttons failed ({response.status}): {data}")
                return {"success": False, "error": data.get("message", "buttons_unavailable")}
        except Exception as e:
            logger.error(f"Green API send_buttons request failed: {e}")
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
        normalized = normalize_chat_id(chat_id)
        if not normalized:
            logger.error(f"Green API file send aborted: invalid recipient '{chat_id}'")
            return {"success": False, "error": f"invalid phone/chatId: {chat_id}"}
        chat_id = normalized

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

    async def set_profile_picture(
        self, image_bytes: bytes, filename: str = "profile.jpg"
    ) -> dict:
        """Set the instance's WhatsApp profile picture.

        Green API's ``setProfilePicture`` takes a multipart/form-data upload
        with a single ``file`` field (a square JPEG/PNG). On success it echoes
        back the new ``urlAvatar``; a non-200 (or a ``reason``) means WhatsApp
        rejected the image (too small, wrong format, rate-limited, …).

        Args:
            image_bytes: Raw image bytes (square, JPEG/PNG, ideally >=192px).
            filename: Filename hint sent with the upload.

        Returns:
            ``{"success": True, "urlAvatar": ...}`` or ``{"success": False, "error": ...}``.
        """
        session = await self._get_session()
        url = f"{self.base_url}/setProfilePicture/{self.token}"

        form = aiohttp.FormData()
        form.add_field(
            "file", image_bytes, filename=filename, content_type="image/jpeg"
        )

        try:
            async with session.post(url, data=form) as response:
                data = await response.json(content_type=None)
                if response.status == 200 and not data.get("reason"):
                    return {"success": True, "urlAvatar": data.get("urlAvatar")}
                logger.error(f"Green API setProfilePicture failed ({response.status}): {data}")
                return {
                    "success": False,
                    "error": data.get("reason") or data.get("message", "Unknown error"),
                }
        except Exception as e:
            logger.error(f"Green API setProfilePicture request failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_avatar(self, chat_id: str) -> dict:
        """Fetch the current WhatsApp avatar URL for a chat/number.

        Green API ``getAvatar`` returns ``urlAvatar`` (empty when none is set)
        and ``available`` (whether the number is on WhatsApp).
        """
        normalized = normalize_chat_id(chat_id)
        if not normalized:
            return {"success": False, "error": f"invalid phone/chatId: {chat_id}"}

        session = await self._get_session()
        url = f"{self.base_url}/getAvatar/{self.token}"
        try:
            async with session.post(url, json={"chatId": normalized}) as response:
                data = await response.json(content_type=None)
                if response.status == 200:
                    return {
                        "success": True,
                        "url_avatar": data.get("urlAvatar") or None,
                        "available": data.get("available", False),
                    }
                logger.error(f"Green API getAvatar failed ({response.status}): {data}")
                return {"success": False, "error": data.get("message", "Unknown error")}
        except Exception as e:
            logger.error(f"Green API getAvatar request failed: {e}")
            return {"success": False, "error": str(e)}

    async def get_my_avatar(self) -> dict:
        """Fetch THIS instance's own current WhatsApp profile picture URL.

        Uses Green API ``getWaSettings``, which returns the authorized
        account's own ``avatar`` URL (and ``phone``) directly — so the UI can
        show what the account actually presents right now, bypassing any
        WhatsApp client-side cache. (``getMe`` is unreliable on these
        instances and can return an HTML error page.)
        """
        session = await self._get_session()
        url = f"{self.base_url}/getWaSettings/{self.token}"
        try:
            async with session.get(url) as response:
                data = await response.json(content_type=None)
                if response.status == 200:
                    return {
                        "success": True,
                        "url_avatar": data.get("avatar") or None,
                        "phone": data.get("phone"),
                        "available": True,
                    }
                logger.error(f"Green API getWaSettings failed ({response.status}): {data}")
                return {"success": False, "error": data.get("message", "Unknown error")}
        except Exception as e:
            logger.error(f"Green API getWaSettings request failed: {e}")
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
    agent_code: Literal["tal", "elad", "pandi", "pandius"]
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

        settings_response = await supabase.table("system_settings").select(
            "setting_key, setting_value"
        ).in_("setting_key", settings_keys).execute()

        settings_dict = {}
        for row in settings_response.data or []:
            settings_dict[row["setting_key"]] = row["setting_value"]

        instance_id = settings_dict.get(f"{agent_code}.instance_id", "").strip()
        token = settings_dict.get(f"{agent_code}.token", "").strip()

        if not instance_id or not token:
            logger.warning(f"Green API credentials for {agent_code} not configured")
            return None

        return GreenAPIClient(instance_id=instance_id, token=token)

    except Exception as e:
        logger.error(f"Failed to get Green API client for {agent_code}: {e}")
        return None
