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
from pandapower.core import phone as phone_utils
from .prompts import get_system_prompt

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1200
HISTORY_LIMIT = 40
VALID_RECRUITERS = ("tal", "elad")


def normalize_phone(raw: Optional[str]) -> str:
    """Reduce a phone string to digits only, for tolerant matching.

    Delegates to the shared phone utilities so every caller shares one
    definition. Prefer :func:`pandapower.core.phone.to_chat_id` for anything
    that actually sends over Green API."""
    return phone_utils.normalize_phone(raw)


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
        delivery = await self._send_whatsapp(conversation_id, text, supabase)
        return {"text": text, "delivered": delivery["sent"], "delivery_reason": delivery["reason"]}

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
        from pandapower.agents.company_profile import load_company_extra
        company_extra = await load_company_extra(supabase)
        system_prompt = get_system_prompt(self.recruiter, match_context, addendum, company_extra)

        if self.recruiter == "elad":
            cue = (
                "זוהי תחילת פנייה יזומה אל הלקוח לגבי המועמד והמשרה שבהקשר. "
                "כתוב הודעת וואטסאפ ראשונה קצרה: הצג את עצמך כאלעד מפנדה-טק, חברת הנדסה "
                "בתחום הביטחון וההייטק, ציין שיש לך מועמד שעשוי להתאים למשרה הרלוונטית, "
                "ושאל אם מעניין אותו לשמוע פרטים. "
                "נסח בנימה עניינית ומדודה, בלי הגזמות בהבטחות. "
                "כתוב אך ורק את ההודעה עצמה, בלי הסברים."
            )
        else:
            cue = (
                "זוהי תחילת פנייה יזומה אל המועמד לגבי המשרה שבהקשר. "
                "כתבי הודעת וואטסאפ ראשונה קצרה: הציגי את עצמך כטל מפנדה-טק, חברת הנדסה "
                "בתחום הביטחון. הסבירי שקיבלת את קורות החיים שלו מתוך המאגר של החברה — "
                "כלומר הוא שלח אלינו קורות חיים מתישהו בעבר, ולכן את פונה אליו — "
                "ושנראה לך שהוא יכול להתאים למשרה הרלוונטית, הזכירי את המשרה בקצרה, "
                "ושאלי אם זה נשמע רלוונטי. "
                "אל תכתבי שראית 'פרופיל' שלו (אין פרופיל — רק קורות חיים מהמאגר), "
                "ואל תגזימי בהבטחות ('מתאים מעולה' וכד') — נסחי בנימה עניינית ומדודה. "
                "פני אל המועמד במין הדקדוקי הנכון לפי שמו. "
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
        delivery = await self._send_whatsapp(conversation_id, reply_text, supabase)

        # Elad: opening = first client outreach → mark "client_contacted".
        if self.recruiter == "elad" and conv.get("match_id"):
            try:
                from pandapower.agents.recruiter_chat import elad_flow
                await elad_flow.ensure_iron_number(self, conv["match_id"])
                await elad_flow._set_stage(self, conv["match_id"], elad_flow.STAGE_CONTACTED)
            except Exception as e:
                logger.warning(f"elad: opening stage update failed: {e}")

        return {"text": reply_text, "skipped": False,
                "delivered": delivery["sent"], "delivery_reason": delivery["reason"]}

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
        from pandapower.agents.company_profile import load_company_extra
        company_extra = await load_company_extra(supabase)
        system_prompt = get_system_prompt(self.recruiter, match_context, addendum, company_extra)

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
        delivery = await self._send_whatsapp(conversation_id, reply_text, supabase)

        # Elad: after replying, progress the visible status and (on clear client
        # interest) offer the CV via buttons. Never sends the CV itself.
        if self.recruiter == "elad" and conv.get("match_id"):
            try:
                from pandapower.agents.recruiter_chat import elad_flow
                fresh = await self._load_recent_messages(conversation_id, supabase)
                await elad_flow.advance_after_turn(self, conversation_id, conv, fresh)
            except Exception as e:
                logger.warning(f"elad: post-reply advance failed: {e}")

        return {"text": reply_text, "skipped": False,
                "delivered": delivery["sent"], "delivery_reason": delivery["reason"]}

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
        """Build the per-match context Tal/Elad are grounded in.

        For both real and test matches we always surface the match analysis and
        Carmit's notes as "פערים אפשריים בהתאמה" — these are the gaps Tal must
        walk the candidate through to decide real fit. Job/candidate display
        fields come from test_meta for test matches, otherwise from the joins."""
        if not match_id:
            return ""
        test = await self._load_test_fields(match_id, supabase)
        is_test = bool(test.get("is_test"))
        meta = test.get("test_meta") if (is_test and isinstance(test.get("test_meta"), dict)) else {}

        row: dict = {}
        try:
            res = await supabase.table("matches").select(
                "id, candidate_id, iron_number, match_score, match_reasoning, "
                "carmit_review_notes, carmit_blocked_reason, "
                "candidates(name, clearance_level), "
                "jobs(job_title, job_description, job_qualifications, "
                "job_location, job_security_clearance, organization_name)"
            ).eq("id", str(match_id)).limit(1).execute()
            if res.data:
                row = res.data[0]
        except Exception as e:
            logger.warning(f"{self.recruiter} context build failed for match {match_id}: {e}")
            if not is_test:
                return ""

        cand = row.get("candidates") or {}
        job = row.get("jobs") or {}

        def field(meta_key: str, src: dict, src_key: str):
            """Prefer the test-meta value for test matches, else the joined row."""
            if is_test and meta.get(meta_key):
                return meta.get(meta_key)
            return src.get(src_key)

        # The candidate being presented. For Elad's bypass-Tal test flow the
        # counterpart is the client, so the candidate is carried separately in
        # candidate_name; fall back to contact_name (Tal's counterpart IS the
        # candidate) and then the joined candidate row.
        name = (meta.get("candidate_name") if is_test else None) or field(
            "contact_name", cand, "name"
        )
        cand_clear = field("candidate_clearance", cand, "clearance_level")
        title = field("job_title", job, "job_title")
        org = field("organization_name", job, "organization_name")
        loc = field("job_location", job, "job_location")
        clear_req = field("job_security_clearance", job, "job_security_clearance")
        desc = field("job_description", job, "job_description")
        quals = field("job_qualifications", job, "job_qualifications")

        # Elad presents the candidate to the CLIENT in sales language, with a
        # full *anonymised* dossier (no phone/email) keyed by an iron number.
        if self.recruiter == "elad":
            return await self._build_elad_context(
                match_id, row, job, name, title, org, loc, clear_req, desc, quals,
                meta, is_test, supabase,
            )

        lines = []
        if name:
            lines.append(f"מועמד: {name}")
        if cand_clear:
            lines.append(f"סיווג המועמד: {cand_clear}")
        if title:
            lines.append(f"משרה: {title}")
        if org:
            lines.append(f"ארגון/לקוח: {org}")
        if loc:
            lines.append(f"מיקום: {loc}")
        if clear_req:
            lines.append(f"סיווג נדרש: {clear_req}")
        if desc:
            lines.append(f"תיאור המשרה: {str(desc)[:600]}")
        if quals:
            lines.append(f"דרישות: {str(quals)[:600]}")

        # The gaps Tal must clarify with the candidate.
        gaps = []
        if row.get("match_reasoning"):
            gaps.append(f"ניתוח הסוכן: {str(row['match_reasoning'])[:600]}")
        if row.get("carmit_review_notes"):
            gaps.append(f"הערות כרמית: {str(row['carmit_review_notes'])[:400]}")
        if row.get("carmit_blocked_reason"):
            gaps.append(f"הסתייגות כרמית: {str(row['carmit_blocked_reason'])[:300]}")
        if gaps:
            lines.append(
                "פערים אפשריים בהתאמה (לברר מול המועמד — ייתכן שחלקם רק לא נכתבו בקו\"ח):\n"
                + "\n".join(f"  • {g}" for g in gaps)
            )
        return "\n".join(lines)

    async def _build_elad_context(
        self, match_id, row, job, name, title, org, loc, clear_req, desc, quals,
        meta, is_test, supabase,
    ) -> str:
        """Client-facing context for Elad: the job + a full anonymised candidate
        dossier (no phone/email) + iron number + Carmit's fit assessment."""
        from pandapower.agents.recruiter_chat import elad_flow

        iron = row.get("iron_number") or await elad_flow.ensure_iron_number(self, match_id)

        # Pull the full candidate row for the dossier (joined select only had
        # name/clearance). Test matches may have no real candidate — fall back to
        # a minimal row built from test_meta.
        cand_full: dict = {}
        cand_id = row.get("candidate_id")
        if cand_id:
            try:
                cres = await supabase.table("candidates").select(
                    "name, clearance_level, location, top_education, experiences, "
                    "key_skills, years_of_experience, extracted_from_cv"
                ).eq("id", str(cand_id)).limit(1).execute()
                if cres.data:
                    cand_full = cres.data[0]
            except Exception as e:
                logger.warning(f"elad: candidate fetch failed for {cand_id}: {e}")
        if not cand_full and name:
            cand_full = {"name": name}

        carmit = row.get("carmit_review_notes") or row.get("match_reasoning") or ""
        dossier = elad_flow.build_candidate_dossier(cand_full, carmit, iron or "")

        lines = ["=== המועמד שאתה מציג ללקוח (פרטים מלאים, ללא טלפון/אימייל) ==="]
        if dossier:
            lines.append(dossier)
        lines.append("=== המשרה הפתוחה אצל הלקוח ===")
        if title:
            lines.append(f"משרה: {title}")
        if org:
            lines.append(f"ארגון/לקוח: {org}")
        if loc:
            lines.append(f"מיקום: {loc}")
        if clear_req:
            lines.append(f"סיווג נדרש: {clear_req}")
        if desc:
            lines.append(f"תיאור המשרה: {str(desc)[:600]}")
        if quals:
            lines.append(f"דרישות: {str(quals)[:600]}")
        return "\n".join(lines)

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
    async def _resolve_phone(self, conversation_id: UUID, supabase) -> Optional[str]:
        """Find the counterpart's raw phone number (any format).

        Uses the cached candidate_phone first. For Tal, falls back to the
        candidate's phone on the match. (For Elad the counterpart is the client;
        their number is expected to be cached on the conversation.) Returns the
        number as stored — validation/normalization for Green API happens in
        :meth:`_send_whatsapp` so a bad number yields a clear reason."""
        conv = await self._load_conversation(conversation_id, supabase)
        if not conv:
            return None
        phone = (conv.get("candidate_phone") or "").strip()
        # Test matches carry their destination phone on the match itself.
        if not phone and conv.get("match_id"):
            test = await self._load_test_fields(conv.get("match_id"), supabase)
            if test.get("is_test"):
                phone = (test.get("test_phone") or "").strip()
        if not phone and self.recruiter == "tal" and conv.get("match_id"):
            try:
                res = await supabase.table("matches").select(
                    "candidates(phone)"
                ).eq("id", str(conv["match_id"])).limit(1).execute()
                if res.data:
                    cand = res.data[0].get("candidates") or {}
                    phone = (cand.get("phone") or "").strip()
                    if phone:
                        await supabase.table("recruiter_conversations").update(
                            {"candidate_phone": phone_utils.normalize_phone(phone)}
                        ).eq("id", str(conversation_id)).execute()
            except Exception as e:
                logger.warning(f"{self.recruiter} could not resolve phone: {e}")
        return phone or None

    async def _send_whatsapp(self, conversation_id: UUID, text: str, supabase) -> dict:
        """Best-effort WhatsApp delivery via this recruiter's Green-API instance.

        Never raises — a delivery failure must not lose the saved message.
        Returns ``{"sent": bool, "reason": str | None}`` so callers can surface
        *why* a message wasn't delivered instead of dropping it silently."""
        try:
            raw_phone = await self._resolve_phone(conversation_id, supabase)
            if not raw_phone:
                logger.info(f"{self.recruiter}: no phone — message stored but not sent")
                return {"sent": False, "reason": "no_phone"}
            chat_id = phone_utils.to_chat_id(raw_phone)
            if not chat_id:
                logger.warning(
                    f"{self.recruiter}: invalid phone '{raw_phone}' — message stored but not sent"
                )
                return {"sent": False, "reason": "invalid_phone"}
            creds = await self._load_green_api_creds(supabase)
            if not creds:
                logger.info(f"{self.recruiter}: Green-API not configured — stored but not sent")
                return {"sent": False, "reason": "not_configured"}
            from pandapower.integrations.green_api import GreenAPIClient

            client = GreenAPIClient(instance_id=creds["instance_id"], token=creds["token"])
            try:
                result = await client.send_message(chat_id, text)
                if result.get("success"):
                    return {"sent": True, "reason": None}
                logger.warning(
                    f"{self.recruiter}: Green-API rejected send to {chat_id}: {result.get('error')}"
                )
                return {"sent": False, "reason": "green_api_error"}
            finally:
                await client.close()
        except Exception as e:
            logger.warning(f"{self.recruiter} WhatsApp send failed (message still saved): {e}")
            return {"sent": False, "reason": "exception"}

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
