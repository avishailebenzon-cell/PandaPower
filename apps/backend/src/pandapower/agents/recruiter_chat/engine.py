"""Recruiter Chat Engine — shared by Tal (candidates) and Elad (clients).

Generates the recruiter's WhatsApp replies for a given recruiter_conversation,
grounded in the specific match (candidate + job). Respects the conversation's
`auto_reply_paused` flag: when a human has taken over, the engine never
auto-replies — but human messages are still delivered as if the agent sent
them, and the agent resumes the thread once un-paused.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pandapower.integrations.anthropic_client import get_anthropic_client
from pandapower.core.supabase import get_supabase_client
from .prompts import get_system_prompt

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1200
HISTORY_LIMIT = 40
VALID_RECRUITERS = ("tal", "elad")


def normalize_phone(raw: Optional[str]) -> str:
    """Reduce a phone string to digits only, for tolerant matching."""
    return re.sub(r"\D", "", raw or "")


class RecruiterChatEngine:
    """LLM-driven conversation engine for a recruiter ('tal' or 'elad')."""

    def __init__(self, recruiter: str = "tal"):
        self.recruiter = recruiter if recruiter in VALID_RECRUITERS else "tal"
        self.anthropic = get_anthropic_client()
        self._supabase = None

    async def _get_supabase(self):
        if self._supabase is None:
            self._supabase = await get_supabase_client()
        return self._supabase

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def save_human_message(self, conversation_id: UUID, text: str) -> dict:
        """Persist an operator message written *as the agent* and send it to the
        counterpart over WhatsApp. Does NOT invoke the AI."""
        supabase = await self._get_supabase()
        await self._save_message(conversation_id, "outbound", text, supabase, author="human")
        sent = await self._send_whatsapp(conversation_id, text, supabase)
        return {"text": text, "delivered": sent}

    async def record_inbound(self, conversation_id: UUID, text: str) -> None:
        """Persist a counterpart's incoming message."""
        supabase = await self._get_supabase()
        await self._save_message(conversation_id, "inbound", text, supabase, author="candidate")

    async def generate_opening(self, conversation_id: UUID) -> dict:
        """Send the agent's first, *initiated* outreach message for a freshly
        activated conversation (the "Tal/Elad initiates contact" behaviour).

        No-op if the conversation already has messages or is paused. Builds the
        opening from the match context and delivers it over WhatsApp."""
        supabase = await self._get_supabase()

        conv = await self._load_conversation(conversation_id, supabase)
        if not conv:
            return {"text": "", "skipped": True}
        if conv.get("auto_reply_paused"):
            return {"text": "", "skipped": True}

        # Only initiate once — never duplicate the opening.
        history = await self._load_recent_messages(conversation_id, supabase)
        if history:
            return {"text": "", "skipped": True}

        match_context = await self._build_match_context(conv.get("match_id"), supabase)
        addendum = await self._load_behavior_addendum(supabase)
        system_prompt = get_system_prompt(self.recruiter, match_context, addendum)

        if self.recruiter == "elad":
            cue = (
                "זוהי תחילת פנייה יזומה אל הלקוח לגבי המועמד והמשרה שבהקשר. "
                "כתוב הודעת וואטסאפ ראשונה קצרה: הצג את עצמך כאלעד מפנדה-טק, ציין "
                "שיש לך מועמד שעשוי להתאים למשרה הרלוונטית, ושאל אם מעניין אותו לשמוע פרטים. "
                "כתוב אך ורק את ההודעה עצמה, בלי הסברים."
            )
        else:
            cue = (
                "זוהי תחילת פנייה יזומה אל המועמד לגבי המשרה שבהקשר. "
                "כתבי הודעת וואטסאפ ראשונה קצרה: הציגי את עצמך כטל מפנדה-טק, הזכירי את "
                "המשרה הרלוונטית בקצרה, ושאלי אם זה מעניין אותו. "
                "כתבי אך ורק את ההודעה עצמה, בלי הסברים."
            )

        try:
            response = self.anthropic.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": cue}],
            )
            await self._record_usage(response)
            text_blocks = [
                b.text for b in response.content if getattr(b, "type", "") == "text"
            ]
            reply_text = "\n".join(text_blocks).strip()
        except Exception as e:
            logger.error(f"{self.recruiter} opening generation failed: {e}", exc_info=True)
            return {"text": "", "skipped": True, "error": True}

        if not reply_text:
            return {"text": "", "skipped": True}

        await self._save_message(conversation_id, "outbound", reply_text, supabase, author="agent")
        await self._send_whatsapp(conversation_id, reply_text, supabase)
        return {"text": reply_text, "skipped": False}

    async def generate_reply(self, conversation_id: UUID) -> dict:
        """Produce the agent's next reply from history + match context, persist
        it (author='agent'), and deliver it over WhatsApp.

        Returns {"text": ..., "skipped": bool}. If paused, returns skipped=True
        without calling the model."""
        supabase = await self._get_supabase()

        conv = await self._load_conversation(conversation_id, supabase)
        if not conv:
            return {"text": "", "skipped": True}
        if conv.get("auto_reply_paused"):
            logger.info(f"{self.recruiter} auto-reply paused for {conversation_id} — skipping")
            return {"text": "", "skipped": True}

        history = await self._load_recent_messages(conversation_id, supabase)
        if not history:
            return {"text": "", "skipped": True}

        messages = [
            {
                "role": "user" if m["direction"] == "inbound" else "assistant",
                "content": m["text"] or "",
            }
            for m in history
            if (m.get("text") or "").strip()
        ]
        while messages and messages[0]["role"] == "assistant":
            messages.pop(0)
        if not messages:
            return {"text": "", "skipped": True}

        match_context = await self._build_match_context(conv.get("match_id"), supabase)
        addendum = await self._load_behavior_addendum(supabase)
        system_prompt = get_system_prompt(self.recruiter, match_context, addendum)

        try:
            response = self.anthropic.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=messages,
            )
            await self._record_usage(response)
            text_blocks = [
                b.text for b in response.content if getattr(b, "type", "") == "text"
            ]
            reply_text = "\n".join(text_blocks).strip()
        except Exception as e:
            logger.error(f"{self.recruiter} Claude call failed: {e}", exc_info=True)
            return {"text": "", "skipped": True, "error": True}

        if not reply_text:
            return {"text": "", "skipped": True}

        await self._save_message(conversation_id, "outbound", reply_text, supabase, author="agent")
        await self._send_whatsapp(conversation_id, reply_text, supabase)
        return {"text": reply_text, "skipped": False}

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------
    async def _load_conversation(self, conversation_id: UUID, supabase) -> Optional[dict]:
        res = await supabase.table("recruiter_conversations").select(
            "id, match_id, recruiter, status, auto_reply_paused, candidate_phone"
        ).eq("id", str(conversation_id)).limit(1).execute()
        return res.data[0] if res.data else None

    async def _load_test_fields(self, match_id, supabase) -> dict:
        """Read the self-contained test columns off a match, defensively.

        Returns {} if the columns aren't present (pre-migration) or on any error,
        so test support never breaks the normal flow."""
        if not match_id:
            return {}
        try:
            res = await supabase.table("matches").select(
                "is_test, test_phone, test_meta"
            ).eq("id", str(match_id)).limit(1).execute()
            return res.data[0] if res.data else {}
        except Exception:
            return {}

    async def _build_match_context(self, match_id, supabase) -> str:
        if not match_id:
            return ""
        # Test matches are self-contained — build the context from test_meta.
        test = await self._load_test_fields(match_id, supabase)
        if test.get("is_test"):
            meta = test.get("test_meta") or {}
            if isinstance(meta, dict):
                lines = []
                if meta.get("contact_name"):
                    lines.append(f"מועמד: {meta['contact_name']}")
                if meta.get("candidate_clearance"):
                    lines.append(f"סיווג המועמד: {meta['candidate_clearance']}")
                if meta.get("job_title"):
                    lines.append(f"משרה: {meta['job_title']}")
                if meta.get("organization_name"):
                    lines.append(f"ארגון/לקוח: {meta['organization_name']}")
                if meta.get("job_location"):
                    lines.append(f"מיקום: {meta['job_location']}")
                if meta.get("job_security_clearance"):
                    lines.append(f"סיווג נדרש: {meta['job_security_clearance']}")
                if meta.get("job_description"):
                    lines.append(f"תיאור המשרה: {str(meta['job_description'])[:600]}")
                if meta.get("job_qualifications"):
                    lines.append(f"דרישות: {str(meta['job_qualifications'])[:600]}")
                if lines:
                    return "\n".join(lines)
        try:
            res = await supabase.table("matches").select(
                "id, match_score, match_reasoning, carmit_review_notes, "
                "candidates(name, clearance_level), "
                "jobs(job_title, job_description, job_qualifications, "
                "job_location, job_security_clearance, organization_name)"
            ).eq("id", str(match_id)).limit(1).execute()
            if not res.data:
                return ""
            row = res.data[0]
            cand = row.get("candidates") or {}
            job = row.get("jobs") or {}
            lines = []
            if cand.get("name"):
                lines.append(f"מועמד: {cand['name']}")
            if cand.get("clearance_level"):
                lines.append(f"סיווג המועמד: {cand['clearance_level']}")
            if job.get("job_title"):
                lines.append(f"משרה: {job['job_title']}")
            if job.get("organization_name"):
                lines.append(f"ארגון/לקוח: {job['organization_name']}")
            if job.get("job_location"):
                lines.append(f"מיקום: {job['job_location']}")
            if job.get("job_security_clearance"):
                lines.append(f"סיווג נדרש: {job['job_security_clearance']}")
            if job.get("job_description"):
                lines.append(f"תיאור המשרה: {str(job['job_description'])[:600]}")
            if job.get("job_qualifications"):
                lines.append(f"דרישות: {str(job['job_qualifications'])[:600]}")
            if row.get("match_reasoning"):
                lines.append(f"למה ההתאמה טובה: {str(row['match_reasoning'])[:400]}")
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"{self.recruiter} context build failed for match {match_id}: {e}")
            return ""

    async def _load_behavior_addendum(self, supabase) -> str:
        try:
            res = await supabase.table("system_settings").select(
                "setting_value"
            ).eq("setting_key", f"{self.recruiter}.system_prompt_addendum").limit(1).execute()
            if res.data:
                return res.data[0].get("setting_value") or ""
        except Exception:
            pass
        return ""

    async def _load_recent_messages(self, conversation_id: UUID, supabase) -> list:
        res = await supabase.table("recruiter_messages").select(
            "direction, text, created_at"
        ).eq("conversation_id", str(conversation_id)).order(
            "created_at", desc=False
        ).limit(HISTORY_LIMIT).execute()
        return res.data or []

    async def _save_message(
        self, conversation_id: UUID, direction: str, text: str, supabase,
        author: str = "agent",
    ) -> None:
        row = {
            "conversation_id": str(conversation_id),
            "recruiter": self.recruiter,
            "direction": direction,
            "message_type": "text",
            "text": text,
            "author": author,
        }
        try:
            await supabase.table("recruiter_messages").insert(row).execute()
        except Exception as e:
            if "author" in str(e).lower() or "PGRST204" in str(e):
                row.pop("author", None)
                await supabase.table("recruiter_messages").insert(row).execute()
            else:
                raise
        try:
            await supabase.table("recruiter_conversations").update(
                {"updated_at": datetime.utcnow().isoformat()}
            ).eq("id", str(conversation_id)).execute()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # WhatsApp delivery
    # ------------------------------------------------------------------
    async def _resolve_chat_id(self, conversation_id: UUID, supabase) -> Optional[str]:
        """Find the counterpart's WhatsApp chatId (phone@c.us).

        Uses the cached candidate_phone first. For Tal, falls back to the
        candidate's phone on the match. (For Elad the counterpart is the client;
        their number is expected to be cached on the conversation.)"""
        conv = await self._load_conversation(conversation_id, supabase)
        if not conv:
            return None
        phone = normalize_phone(conv.get("candidate_phone"))
        # Test matches carry their destination phone on the match itself.
        if not phone and conv.get("match_id"):
            test = await self._load_test_fields(conv.get("match_id"), supabase)
            if test.get("is_test"):
                phone = normalize_phone(test.get("test_phone"))
        if not phone and self.recruiter == "tal" and conv.get("match_id"):
            try:
                res = await supabase.table("matches").select(
                    "candidates(phone)"
                ).eq("id", str(conv["match_id"])).limit(1).execute()
                if res.data:
                    cand = res.data[0].get("candidates") or {}
                    phone = normalize_phone(cand.get("phone"))
                    if phone:
                        await supabase.table("recruiter_conversations").update(
                            {"candidate_phone": phone}
                        ).eq("id", str(conversation_id)).execute()
            except Exception as e:
                logger.warning(f"{self.recruiter} could not resolve phone: {e}")
        if not phone:
            return None
        return f"{phone}@c.us"

    async def _send_whatsapp(self, conversation_id: UUID, text: str, supabase) -> bool:
        """Best-effort WhatsApp delivery via this recruiter's Green-API instance.
        Never raises — a delivery failure must not lose the saved message."""
        try:
            chat_id = await self._resolve_chat_id(conversation_id, supabase)
            if not chat_id:
                logger.info(f"{self.recruiter}: no phone — message stored but not sent")
                return False
            creds = await self._load_green_api_creds(supabase)
            if not creds:
                logger.info(f"{self.recruiter}: Green-API not configured — stored but not sent")
                return False
            from pandapower.integrations.green_api import GreenAPIClient

            client = GreenAPIClient(instance_id=creds["instance_id"], token=creds["token"])
            try:
                result = await client.send_message(chat_id, text)
                return bool(result.get("success"))
            finally:
                await client.close()
        except Exception as e:
            logger.warning(f"{self.recruiter} WhatsApp send failed (message still saved): {e}")
            return False

    async def _load_green_api_creds(self, supabase) -> Optional[dict]:
        try:
            res = await supabase.table("system_settings").select(
                "setting_key, setting_value"
            ).in_("setting_key", [f"{self.recruiter}.instance_id", f"{self.recruiter}.token"]).execute()
            d = {r["setting_key"]: (r.get("setting_value") or "").strip() for r in (res.data or [])}
            instance_id = d.get(f"{self.recruiter}.instance_id", "")
            token = d.get(f"{self.recruiter}.token", "")
            if instance_id and token:
                return {"instance_id": instance_id, "token": token}
        except Exception as e:
            logger.warning(f"Could not load {self.recruiter} Green-API creds: {e}")
        return None

    async def _record_usage(self, response) -> None:
        try:
            from pandapower.integrations.usage_tracker import record_usage
            await record_usage(
                stage=f"{self.recruiter}_conversation",
                model=MODEL,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception:
            pass
