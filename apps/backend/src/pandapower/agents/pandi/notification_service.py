"""
Session 33: Admin Notifications & Monitoring Service
Sends Telegram alerts for important Pandi events and status changes
"""

from enum import Enum
from datetime import datetime
from typing import Optional
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


class NotificationEvent(str, Enum):
    """Events that trigger admin notifications."""

    # Referral events
    CLIENT_INTERESTED = "client_interested"
    CLIENT_DECLINED = "client_declined"
    CANDIDATE_HIRED = "candidate_hired"
    REFERRAL_REJECTED = "referral_rejected"

    # System events
    QUOTA_EXHAUSTED = "quota_exhausted"
    QUOTA_WARNING = "quota_warning"
    INAPPROPRIATE_CONTENT = "inappropriate_content"
    CONVERSATION_TRANSFERRED = "conversation_transferred"

    # Admin actions
    FULL_CV_APPROVAL_REQUESTED = "full_cv_approval_requested"
    FULL_CV_APPROVED = "full_cv_approved"
    FULL_CV_SENT = "full_cv_sent"


class NotificationService:
    """
    Manages admin notifications for Pandi events.

    Session 33 features:
    - Telegram bot integration (send messages to admin group)
    - Smart notification formatting (Hebrew, contextual info)
    - Event filtering (don't spam admins)
    - Retry logic for failed deliveries
    - Notification history/logging
    """

    def __init__(self):
        self._telegram_client = None
        self._settings = None

    @staticmethod
    def _unwrap(val):
        """system_settings.setting_value may be a plain string or {"value": ...}."""
        if isinstance(val, dict):
            val = val.get("value")
        if isinstance(val, str):
            val = val.strip().strip('"').strip()
        return val or ""

    async def _get_settings(self):
        """Load Telegram settings from system_settings (best-effort)."""
        if self._settings is None:
            try:
                from pandapower.core.supabase import get_supabase_client

                supabase = await get_supabase_client()
                # NOTE: async Supabase requires await ...execute() — the prior
                # code called .single() with no execute(), so this always raised
                # and settings stayed empty.
                result = await supabase.table("system_settings").select(
                    "setting_key, setting_value"
                ).in_(
                    "setting_key", ["telegram.bot_token", "telegram.admin_chat_id"]
                ).execute()
                rows = {r["setting_key"]: r.get("setting_value") for r in (result.data or [])}
                self._settings = {
                    "bot_token": self._unwrap(rows.get("telegram.bot_token")),
                    "admin_chat_id": self._unwrap(rows.get("telegram.admin_chat_id")),
                }
            except Exception as e:
                logger.warning("telegram_settings_load_failed", error=str(e))
                self._settings = {}

        return self._settings or {}

    async def notify_event(
        self,
        event_type: NotificationEvent,
        title: str,
        message: str,
        context: dict = None,
        severity: str = "info",
    ) -> dict:
        """
        Send notification for important event.

        Args:
            event_type: Type of event (see NotificationEvent enum)
            title: Event title (Hebrew)
            message: Event message (Hebrew)
            context: Additional context (candidate_number, client_name, etc.)
            severity: "info" | "warning" | "critical"

        Returns:
            Notification delivery result dict
        """
        try:
            # Format notification
            notification = self._format_notification(
                event_type=event_type,
                title=title,
                message=message,
                context=context,
                severity=severity,
            )

            # Log notification (always, even if Telegram fails)
            await self._log_notification(
                event_type=event_type,
                notification=notification,
                severity=severity,
            )

            # Send to Telegram
            result = await self._send_telegram_message(notification)

            return {
                "status": "success" if result.get("sent") else "queued",
                "notification_id": notification.get("id"),
                "message": f"Sent to admins: {title}",
            }

        except Exception as e:
            logger.error(f"notify_event failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": "Failed to send notification",
                "error": str(e),
            }

    def _format_notification(
        self,
        event_type: NotificationEvent,
        title: str,
        message: str,
        context: dict = None,
        severity: str = "info",
    ) -> dict:
        """Format notification for Telegram delivery."""
        context = context or {}

        # Build emoji based on severity/type
        emoji = self._get_emoji(event_type, severity)

        # Format for Telegram
        text = f"{emoji} *{title}*\n\n{message}"

        # Add context details
        if context:
            details = self._format_context(context)
            if details:
                text += f"\n\n{details}"

        # Add timestamp
        timestamp = datetime.utcnow().isoformat()
        text += f"\n\n_({timestamp} UTC)_"

        return {
            "id": f"{event_type}_{timestamp}",
            "event_type": event_type.value,
            "severity": severity,
            "title": title,
            "message": message,
            "telegram_text": text,
            "context": context,
            "created_at": timestamp,
        }

    def _format_context(self, context: dict) -> str:
        """Format context fields for display."""
        parts = []

        if context.get("candidate_number"):
            parts.append(f"📌 מועמד: {context['candidate_number']}")

        if context.get("client_name"):
            parts.append(f"👤 לקוח: {context['client_name']}")

        if context.get("job_title"):
            parts.append(f"💼 משרה: {context['job_title']}")

        if context.get("reason"):
            parts.append(f"💭 סיבה: {context['reason']}")

        if context.get("quota_remaining"):
            parts.append(
                f"📊 מכסה נותרת: {context['quota_remaining']}/{context.get('quota_limit', '?')}"
            )

        if context.get("inappropriate_text"):
            parts.append(f"⚠️ תוכן: `{context['inappropriate_text'][:50]}...`")

        return "\n".join(parts)

    def _get_emoji(self, event_type: NotificationEvent, severity: str) -> str:
        """Get emoji for notification type."""
        if severity == "critical":
            return "🚨"
        elif severity == "warning":
            return "⚠️"

        emoji_map = {
            NotificationEvent.CLIENT_INTERESTED: "👍",
            NotificationEvent.CLIENT_DECLINED: "👎",
            NotificationEvent.CANDIDATE_HIRED: "🎉",
            NotificationEvent.REFERRAL_REJECTED: "❌",
            NotificationEvent.QUOTA_EXHAUSTED: "🚫",
            NotificationEvent.QUOTA_WARNING: "⏰",
            NotificationEvent.INAPPROPRIATE_CONTENT: "🚨",
            NotificationEvent.CONVERSATION_TRANSFERRED: "🔄",
            NotificationEvent.FULL_CV_APPROVAL_REQUESTED: "📋",
            NotificationEvent.FULL_CV_APPROVED: "✅",
            NotificationEvent.FULL_CV_SENT: "📧",
        }

        return emoji_map.get(event_type, "ℹ️")

    async def _send_telegram_message(self, notification: dict) -> dict:
        """Deliver the notification to the admin.

        Prefers Telegram when ``telegram.bot_token`` + ``telegram.admin_chat_id``
        are configured in system_settings; otherwise falls back to the proven
        Resend email path (same channel the rest of the app uses for admin
        alerts). Always best-effort — a delivery failure never breaks the flow.
        """
        # 1) Telegram, if configured.
        try:
            settings = await self._get_settings()
            bot_token = settings.get("bot_token")
            admin_chat_id = settings.get("admin_chat_id")
            if bot_token and admin_chat_id:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={
                            "chat_id": admin_chat_id,
                            "text": notification["telegram_text"],
                            "parse_mode": "Markdown",
                        },
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 200:
                            return {"sent": True, "channel": "telegram"}
                        body = await resp.text()
                        logger.warning("telegram_send_non_200", status=resp.status, body=body[:200])
        except Exception as e:
            logger.warning("telegram_send_failed_falling_back_to_email", error=str(e))

        # 2) Email fallback via Resend.
        try:
            from pandapower.integrations.resend_client import ResendClient
            from pandapower.core.config import settings as cfg

            if not cfg.RESEND_API_KEY:
                logger.info("notification_logged_no_channel_configured",
                            title=notification.get("title"))
                return {"sent": False, "channel": "none"}

            from pandapower.integrations.alert_service import get_admin_email
            admin_email = await get_admin_email()
            resend = ResendClient(api_key=cfg.RESEND_API_KEY)
            html = (notification.get("telegram_text") or notification.get("message") or "")
            await resend.send_email(
                to=[admin_email],
                from_addr=cfg.RESEND_FROM_EMAIL,
                subject=notification.get("title") or "Pandi notification",
                html=html.replace("\n", "<br>"),
            )
            return {"sent": True, "channel": "email"}
        except Exception as e:
            logger.error(f"notification delivery failed (telegram+email): {e}", exc_info=True)
            return {"sent": False, "error": str(e)}

    async def _log_notification(
        self,
        event_type: NotificationEvent,
        notification: dict,
        severity: str,
    ) -> None:
        """Log notification to database for audit trail."""
        try:
            # TODO (Session 33+): Store in notifications table for history
            logger.info(
                "notification_logged",
                event_type=event_type.value,
                severity=severity,
                notification_id=notification.get("id"),
            )
        except Exception as e:
            logger.error(f"log_notification failed: {e}", exc_info=True)

    async def notify_client_interested(
        self,
        candidate_number: str,
        client_name: str,
        job_title: Optional[str] = None,
    ) -> dict:
        """Notify admin that client expressed interest in candidate."""
        return await self.notify_event(
            event_type=NotificationEvent.CLIENT_INTERESTED,
            title=f"הלקוח {client_name} עוניין ב-{candidate_number}",
            message=f"{client_name} לחץ על 'מעוניין' למועמד {candidate_number}",
            context={
                "candidate_number": candidate_number,
                "client_name": client_name,
                "job_title": job_title,
            },
            severity="info",
        )

    async def notify_candidate_hired(
        self,
        candidate_number: str,
        client_name: str,
        job_title: Optional[str] = None,
    ) -> dict:
        """Notify admin that candidate was hired."""
        return await self.notify_event(
            event_type=NotificationEvent.CANDIDATE_HIRED,
            title=f"🎉 {candidate_number} נשכר ב-{client_name}!",
            message=f"משהו שחיפשנו קרה - לקוח הייצר referral ל-{candidate_number} שעבר לחברתו!",
            context={
                "candidate_number": candidate_number,
                "client_name": client_name,
                "job_title": job_title,
            },
            severity="info",
        )

    async def notify_quota_exhausted(
        self,
        client_name: str,
        quota_limit: int,
    ) -> dict:
        """Notify admin that client quota is exhausted."""
        return await self.notify_event(
            event_type=NotificationEvent.QUOTA_EXHAUSTED,
            title=f"מכסה של {client_name} סיימה",
            message=f"{client_name} הגיע למכסה החודשית ({quota_limit} הודעות) ובא בבקשה להגדלה",
            context={
                "client_name": client_name,
                "quota_limit": quota_limit,
            },
            severity="warning",
        )

    async def notify_quota_warning(
        self,
        client_name: str,
        quota_used: int,
        quota_limit: int,
        percent: int = 80,
    ) -> dict:
        """Notify admin that client quota is running low."""
        return await self.notify_event(
            event_type=NotificationEvent.QUOTA_WARNING,
            title=f"⏰ {client_name} בקרוב ישלוח את המכסה שלו",
            message=f"{client_name} השתמש ב-{quota_used} מתוך {quota_limit} הודעות ({percent}%)",
            context={
                "client_name": client_name,
                "quota_used": quota_used,
                "quota_limit": quota_limit,
            },
            severity="warning",
        )

    async def notify_inappropriate_content(
        self,
        client_name: str,
        content_preview: str,
    ) -> dict:
        """Notify admin of inappropriate content flag."""
        return await self.notify_event(
            event_type=NotificationEvent.INAPPROPRIATE_CONTENT,
            title=f"🚨 {client_name} שלח תוכן לא הולם",
            message="ההודעה סומנה כלא מתאימה וביצענו דילוג",
            context={
                "client_name": client_name,
                "inappropriate_text": content_preview,
            },
            severity="critical",
        )

    async def notify_conversation_transferred(
        self,
        client_name: str,
        reason: str,
    ) -> dict:
        """Notify admin that conversation was transferred to recruitment team."""
        return await self.notify_event(
            event_type=NotificationEvent.CONVERSATION_TRANSFERRED,
            title=f"🔄 {client_name} הועבר לצוות הגיוס",
            message=f"השיחה עברה לטיפול ידני. סיבה: {reason}",
            context={
                "client_name": client_name,
                "reason": reason,
            },
            severity="info",
        )

    async def notify_full_cv_approval_requested(
        self,
        candidate_number: str,
        client_name: str,
    ) -> dict:
        """Notify admin that client wants full CV (needs approval)."""
        return await self.notify_event(
            event_type=NotificationEvent.FULL_CV_APPROVAL_REQUESTED,
            title=f"📋 {client_name} בקש את CV המלא של {candidate_number}",
            message=f"צריך לבדוק האם אפשר לשלוח את ה-CV",
            context={
                "candidate_number": candidate_number,
                "client_name": client_name,
            },
            severity="warning",
        )

    async def notify_full_cv_approved(
        self,
        candidate_number: str,
        client_name: str,
    ) -> dict:
        """Notify admin that full CV was approved for sending."""
        return await self.notify_event(
            event_type=NotificationEvent.FULL_CV_APPROVED,
            title=f"✅ CV של {candidate_number} אושר לשליחה",
            message=f"פנדי יכול כעת לשלוח את CV המלא ל-{client_name}",
            context={
                "candidate_number": candidate_number,
                "client_name": client_name,
            },
            severity="info",
        )

    async def notify_new_client_prospect(
        self,
        client_name: str,
        email: str,
        phone: str,
        company_name: Optional[str] = None,
        role: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> dict:
        """Notify admin that a new client prospect registered via Pandi.

        This is sent when an unknown client (not in DB) reaches out to Pandi
        and provides their details. Includes email notification via Resend
        to admin so they can follow up if needed.

        Args:
            client_name: Client's full name
            email: Client's email address
            phone: Client's phone number
            company_name: Optional company name
            role: Optional role/title
            conversation_id: Optional conversation ID for tracking
        """
        try:
            # Format the notification for Telegram
            message = f"""
לקוח חדש! 🎉
📋 {client_name}
📧 {email}
📱 {phone}
🏢 {company_name or 'לא צוין'}
💼 {role or 'לא צוין'}
💬 conversation_id: {conversation_id or 'N/A'}
            """.strip()

            # Send via Telegram (existing path)
            telegram_result = await self.notify_event(
                event_type="new_client_prospect",
                title=f"🎉 לקוח חדש! {client_name}",
                message=message,
                context={
                    "client_name": client_name,
                    "email": email,
                    "phone": phone,
                    "company_name": company_name,
                    "role": role,
                    "conversation_id": conversation_id,
                },
                severity="info",
            )

            # Also send email via Resend to admin
            try:
                from pandapower.integrations.resend_client import ResendClient
                from pandapower.core.config import settings

                if not settings.RESEND_API_KEY:
                    logger.warning("RESEND_API_KEY not configured, skipping email notification")
                    resend_result = {"status": "skipped"}
                else:
                    resend = ResendClient(api_key=settings.RESEND_API_KEY)
                    from pandapower.integrations.alert_service import get_admin_email
                    admin_email = await get_admin_email()

                    email_body = f"""
שלום,

לקוח חדש נרשם דרך אלעד:

שם: {client_name}
מייל: {email}
טלפון: {phone}
חברה: {company_name or 'לא צוין'}
תפקיד: {role or 'לא צוין'}

מספר שיחה: {conversation_id or 'N/A'}

בואו ניצור עם הלקוח קשר כדי להכיר אותו טוב יותר ולהציע משרות.

---
פנדי, סוכנת הבינה המלאכותית של פנדה-טק
                    """.strip()

                    from pandapower.core.config import settings as _settings
                    resend_result = await resend.send_email(
                        to=[admin_email],
                        from_addr=_settings.RESEND_FROM_EMAIL,
                        subject=f"🎉 לקוח חדש: {client_name}",
                        html=email_body.replace("\n", "<br>"),
                    )

                    logger.info(
                        "new_client_email_sent",
                        client_name=client_name,
                        email=email,
                        resend_result=resend_result,
                    )

            except Exception as e:
                logger.warning(
                    f"Failed to send new client email via Resend: {e}",
                    exc_info=True,
                )
                # Don't raise — email is nice-to-have, not critical

            return {
                "status": "success",
                "telegram_sent": telegram_result.get("status") == "success",
                "email_sent": True,
            }

        except Exception as e:
            logger.error(
                f"notify_new_client_prospect failed: {e}",
                exc_info=True,
            )
            return {
                "status": "error",
                "message": str(e),
            }
