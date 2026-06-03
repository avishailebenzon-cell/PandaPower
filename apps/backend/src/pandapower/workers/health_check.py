"""Health check worker for all system integrations.

Monitors:
- ConvertAPI (text extraction)
- Pipedrive (CRM sync)
- Azure Email (incoming emails)
- Supabase (database)
- Anthropic API (Claude)

Sends alerts via the unified Alert Service (alert_admin) which handles
throttling, snoozing, and user acknowledgement via /admin/alerts.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from pandapower.integrations.convertapi_client import (
    ConvertApiClient,
    get_convertapi_config,
)
from pandapower.integrations.pipedrive import PipedriveClient
from pandapower.integrations.azure import AzureGraphClient
from pandapower.integrations.claude_api import AnthropicClient
from pandapower.core.config import settings
from pandapower.integrations.alert_service import alert_admin

logger = logging.getLogger(__name__)


class HealthCheckWorker:
    """Check all integrations and send alerts via Alert Service if issues found."""

    def __init__(self, supabase_client: Any):
        self.supabase = supabase_client
        self.issues = []

    async def run_checks(self) -> dict[str, Any]:
        """Run all health checks. Returns dict with status of each integration."""
        result = {
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {},
            "issues": [],
            "overall_status": "healthy",
        }

        # Run all checks
        result["checks"]["convertapi"] = await self._check_convertapi()
        result["checks"]["pipedrive"] = await self._check_pipedrive()
        result["checks"]["azure_email"] = await self._check_azure_email()
        result["checks"]["supabase"] = await self._check_supabase()
        result["checks"]["anthropic"] = await self._check_anthropic()

        # Collect issues
        for check_name, check_result in result["checks"].items():
            if check_result["status"] != "healthy":
                self.issues.append({
                    "component": check_name,
                    "status": check_result["status"],
                    "message": check_result.get("message"),
                })

        result["issues"] = self.issues
        result["overall_status"] = "unhealthy" if self.issues else "healthy"

        # Send alert if issues found
        if self.issues:
            logger.warning(f"Health check found {len(self.issues)} issues")
            await self._send_alert(result)
        else:
            logger.info("Health check: All systems healthy ✓")

        return result

    async def _check_convertapi(self) -> dict[str, Any]:
        """Check ConvertAPI integration."""
        try:
            cfg = await get_convertapi_config(self.supabase)

            if not cfg.get("enabled"):
                return {
                    "status": "disabled",
                    "message": "ConvertAPI is disabled (no secret configured)",
                }

            if not cfg.get("secret"):
                return {
                    "status": "error",
                    "message": "ConvertAPI secret missing from configuration",
                }

            # Test the API
            client = ConvertApiClient(cfg["secret"])
            try:
                user = await client.get_user()
                credits = user.get("ConversionsLeft") or user.get("SecondsLeft")

                if credits and credits < 100:
                    return {
                        "status": "warning",
                        "message": f"Low credits: {credits} remaining",
                    }

                return {
                    "status": "healthy",
                    "message": f"Credits: {credits}",
                }
            finally:
                await client.close()

        except Exception as e:
            return {
                "status": "error",
                "message": f"ConvertAPI test failed: {str(e)}",
            }

    async def _check_pipedrive(self) -> dict[str, Any]:
        """Check Pipedrive integration."""
        try:
            # Get Pipedrive config from system_settings
            cfg_response = await self.supabase.table("pipedrive_config").select("api_token, is_active").limit(1).execute()

            if not cfg_response.data:
                return {
                    "status": "not_configured",
                    "message": "Pipedrive not configured",
                }

            config = cfg_response.data[0]
            if not config.get("is_active"):
                return {
                    "status": "disabled",
                    "message": "Pipedrive integration disabled",
                }

            api_token = config.get("api_token")
            if not api_token:
                return {
                    "status": "error",
                    "message": "Pipedrive API token missing",
                }

            # Validate token format
            if len(api_token.strip()) < 10:
                return {
                    "status": "error",
                    "message": "Pipedrive API token appears invalid",
                }

            # If token exists and is valid length, assume healthy
            # (actual API validation happens on first use)
            return {
                "status": "healthy",
                "message": "Pipedrive token configured",
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Pipedrive check failed: {str(e)}",
            }

    async def _check_azure_email(self) -> dict[str, Any]:
        """Check Azure email integration."""
        try:
            # Get Azure config from system_settings
            settings_response = await self.supabase.table("system_settings").select(
                "setting_key, setting_value"
            ).in_(
                "setting_key",
                [
                    "azure.tenant_id",
                    "azure.app_client_id",
                    "azure.client_secret",
                    "azure.target_mailbox",
                ],
            ).execute()

            settings_dict = {}
            for row in (settings_response.data or []):
                key = row["setting_key"].split(".")[-1]
                value = row["setting_value"].strip('"') if isinstance(row["setting_value"], str) else row["setting_value"]
                settings_dict[key] = value

            required_keys = ["tenant_id", "app_client_id", "client_secret", "target_mailbox"]
            missing = [k for k in required_keys if not settings_dict.get(k)]

            if missing:
                return {
                    "status": "error",
                    "message": f"Missing Azure config: {', '.join(missing)}",
                }

            # Test the connection
            client = AzureGraphClient(
                tenant_id=settings_dict["tenant_id"],
                client_id=settings_dict["app_client_id"],
                client_secret=settings_dict["client_secret"],
                target_mailbox=settings_dict["target_mailbox"],
            )

            try:
                await client.authenticate()
                # Try to list messages
                response = await client.list_messages(page_size=1)
                msg_count = response.get("@odata.count", 0)
                return {
                    "status": "healthy",
                    "message": f"Connected to {settings_dict['target_mailbox']}, {msg_count} emails",
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Azure connection failed: {str(e)}",
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Azure check failed: {str(e)}",
            }

    async def _check_supabase(self) -> dict[str, Any]:
        """Check Supabase database connection."""
        try:
            # Simple query to test connection
            result = await self.supabase.table("system_settings").select("setting_key").limit(1).execute()
            return {
                "status": "healthy",
                "message": "Database connection OK",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Database connection failed: {str(e)}",
            }

    async def _check_anthropic(self) -> dict[str, Any]:
        """Check Anthropic API."""
        try:
            if not settings.ANTHROPIC_API_KEY:
                return {
                    "status": "error",
                    "message": "ANTHROPIC_API_KEY not configured",
                }

            # Verify API key is valid (basic check)
            if len(settings.ANTHROPIC_API_KEY) < 20:
                return {
                    "status": "error",
                    "message": "ANTHROPIC_API_KEY appears invalid (too short)",
                }

            # If key exists and is valid length, assume healthy
            # (actual validation happens on first API call)
            return {
                "status": "healthy",
                "message": "API key configured",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Anthropic check failed: {str(e)}",
            }

    async def _send_alert(self, result: dict[str, Any]) -> None:
        """Send alert via the unified Alert Service.

        Uses alert_admin() which handles:
        - Resend email delivery
        - Telegram notifications
        - Throttling (30 min cooldown per component)
        - User snooze/acknowledge via /admin/alerts
        """
        # Format issues for details
        issues_text = "\n".join([
            f"• {issue['component'].upper()}: {issue['status']} - {issue['message']}"
            for issue in self.issues
        ])

        # Send one alert per issue so users can acknowledge/snooze individually
        for issue in self.issues:
            key = f"health-{issue['component']}"
            subject = f"System Health: {issue['component'].upper()}"
            details = f"""
{issue['component'].upper()}: {issue['status'].upper()}

Error: {issue['message']}

All issues detected:
{issues_text}

Check time: {result['timestamp']}
"""

            # Use alert_admin from alert_service.py
            # This handles cooldown, snooze, acknowledge, and both email + Telegram
            await alert_admin(
                key=key,
                subject=subject,
                details=details,
                severity="error" if issue['status'] == "error" else "warning",
            )
