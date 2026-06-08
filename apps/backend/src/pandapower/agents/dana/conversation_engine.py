"""Dana Conversation Engine — web chat, file-aware, agentic tool loop."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

import structlog

from pandapower.integrations.anthropic_client import get_anthropic_client
from pandapower.core.supabase import get_supabase_client
from .prompts.system import get_system_prompt
from .tools import get_dana_tools
from .tool_handlers import execute_tool, REQUIRED_FIELDS, FIELD_LABELS_HE

logger = structlog.get_logger(__name__)

MODEL = "claude-opus-4-7"
MAX_TOOL_ITERATIONS = 6


class DanaConversationEngine:
    """LLM-driven job-intake conversation for Dana."""

    def __init__(self):
        self.anthropic = get_anthropic_client()
        self._supabase = None

    async def _get_supabase(self):
        if self._supabase is None:
            self._supabase = await get_supabase_client()
        return self._supabase

    async def handle_message(
        self, conversation_id: UUID, incoming_text: str
    ) -> dict:
        """Process one user message and return Dana's reply text."""
        supabase = await self._get_supabase()

        # Persist the inbound message.
        await self._save_message(conversation_id, "inbound", incoming_text, supabase)

        # Build the running message history (mapped to Anthropic roles).
        history = await self._load_recent_messages(conversation_id, supabase)
        messages = [
            {
                "role": "user" if m["direction"] == "inbound" else "assistant",
                "content": m["text"],
            }
            for m in history
        ]
        # Anthropic requires the first message to use the 'user' role. Dana's
        # seeded opening greeting is an assistant turn, so drop any leading
        # assistant messages before the first user message.
        while messages and messages[0]["role"] == "assistant":
            messages.pop(0)

        from pandapower.agents.company_profile import load_company_extra
        company_extra = await load_company_extra(supabase)
        job_context = await self._load_job_context(conversation_id, supabase)
        system_prompt = get_system_prompt(self._context_guidance(job_context), company_extra)
        tools = get_dana_tools()

        reply_text = ""
        try:
            for _ in range(MAX_TOOL_ITERATIONS):
                response = self.anthropic.messages.create(
                    model=MODEL,
                    max_tokens=1500,
                    system=system_prompt,
                    tools=tools,
                    messages=messages,
                )
                await self._record_usage(response)

                text_blocks = [b.text for b in response.content if getattr(b, "type", "") == "text"]
                tool_uses = [b for b in response.content if getattr(b, "type", "") == "tool_use"]
                if text_blocks:
                    reply_text = "\n".join(text_blocks).strip()

                if not tool_uses:
                    break  # final natural-language answer

                # Echo assistant turn (with tool_use) then run each tool.
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for tu in tool_uses:
                    result = await execute_tool(
                        tool_name=tu.name,
                        tool_input=tu.input,
                        conversation_id=conversation_id,
                        supabase=supabase,
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": _stringify_result(result),
                    })
                    # Refresh guidance after context-changing tools.
                    if tu.name in ("update_job_context", "create_deal"):
                        job_context = await self._load_job_context(conversation_id, supabase)
                        system_prompt = get_system_prompt(self._context_guidance(job_context), company_extra)
                messages.append({"role": "user", "content": tool_results})
            else:
                logger.warning("dana_tool_loop_exhausted", conversation_id=str(conversation_id))
        except Exception as e:
            logger.error("dana_claude_call_failed", error=str(e))
            # Make it explicit to the user that the task was NOT completed,
            # and why — then persist it so it stays in the conversation history.
            err_text = _explain_llm_error(e)
            try:
                await self._save_message(conversation_id, "outbound", err_text, supabase)
            except Exception:
                pass
            return {"text": err_text, "error": True}

        if not reply_text:
            reply_text = "קיבלתי. נמשיך 🙂"

        await self._save_message(conversation_id, "outbound", reply_text, supabase)
        return {"text": reply_text}

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------
    def _context_guidance(self, ctx: dict) -> str:
        if not ctx:
            return "עדיין לא נאספו פרטים. התחילי בקבלת הנתונים מהמשתמש."
        filled = [FIELD_LABELS_HE[f] for f in REQUIRED_FIELDS if ctx.get(f)]
        missing = [FIELD_LABELS_HE[f] for f in REQUIRED_FIELDS if not ctx.get(f)]
        lines = [
            f"נאספו: {', '.join(filled) if filled else 'כלום עדיין'}",
            f"חסר (חובה): {', '.join(missing) if missing else 'הכול נאסף — אפשר לאשר ולפתוח דיל'}",
        ]
        if ctx.get("job_security_clearance"):
            lines.append(f"סיווג ביטחוני: {ctx['job_security_clearance']}")
        return "\n".join(lines)

    async def _load_job_context(self, conversation_id: UUID, supabase) -> dict:
        res = await supabase.table("dana_conversations").select("job_context").eq(
            "id", str(conversation_id)
        ).single().execute()
        return (res.data or {}).get("job_context") or {}

    async def _load_recent_messages(self, conversation_id: UUID, supabase, limit: int = 40) -> list:
        res = (
            await supabase.table("dana_messages")
            .select("direction, text, sent_at")
            .eq("conversation_id", str(conversation_id))
            .order("sent_at", desc=False)
            .limit(limit)
            .execute()
        )
        return res.data or []

    async def _save_message(
        self, conversation_id: UUID, direction: str, text: str, supabase
    ) -> None:
        await supabase.table("dana_messages").insert({
            "conversation_id": str(conversation_id),
            "direction": direction,
            "text": text,
            "llm_model": MODEL if direction == "outbound" else None,
        }).execute()
        await supabase.table("dana_conversations").update(
            {"updated_at": datetime.utcnow().isoformat()}
        ).eq("id", str(conversation_id)).execute()

    async def _record_usage(self, response) -> None:
        try:
            from pandapower.integrations.usage_tracker import record_usage
            await record_usage(
                stage="dana_conversation",
                model=MODEL,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception:
            pass


def _stringify_result(result: dict) -> str:
    """Compact, Claude-friendly rendering of a tool result."""
    import json
    return json.dumps(result, ensure_ascii=False)


def _explain_llm_error(e: Exception) -> str:
    """Build a clear Hebrew message stating the task was NOT done, and why.

    Distinguishes the Anthropic usage/quota limit (the known blocker) from
    rate-limiting, temporary overload, auth, and generic failures so the user
    understands the task did not run and what to do about it.
    """
    status = getattr(e, "status_code", None)
    name = type(e).__name__
    text = str(e).lower()

    prefix = "⚠️ לא הצלחתי לבצע את המשימה — המשרה לא נוצרה ולא נשמרה."

    # Usage / quota / billing limit (the documented Anthropic blocker).
    if (
        any(k in text for k in ("credit", "billing", "quota", "usage limit", "spend", "plan"))
        or (status == 400 and "rate" not in text and "limit" in text)
    ):
        return (
            f"{prefix}\n"
            "הסיבה: שירות ה-AI (Anthropic) חרג ממכסת השימוש/התקציב, ולכן איני "
            "יכולה לעבד את הבקשה כרגע.\n"
            "מה לעשות: יש להעלות את מכסת השימוש ב-Anthropic Console, ואז לנסות שוב. "
            "כל הפרטים שכבר מסרת נשמרו וימשיכו מכאן."
        )

    # Rate limited (429) — transient.
    if status == 429 or "rate limit" in text or name == "RateLimitError":
        return (
            f"{prefix}\n"
            "הסיבה: שירות ה-AI (Anthropic) מוגבל כרגע בקצב הבקשות (rate limit).\n"
            "מה לעשות: נסה שוב בעוד כמה דקות. הפרטים שמסרת נשמרו."
        )

    # Temporary overload / server / connection issues.
    if (
        (isinstance(status, int) and status >= 500)
        or name in ("InternalServerError", "APIConnectionError", "APITimeoutError", "APIStatusError")
        or any(k in text for k in ("overloaded", "timeout", "connection"))
    ):
        return (
            f"{prefix}\n"
            "הסיבה: שירות ה-AI (Anthropic) אינו זמין כרגע (עומס/תקלה זמנית).\n"
            "מה לעשות: נסה שוב בעוד מספר דקות. הפרטים שמסרת נשמרו."
        )

    # Authentication / configuration.
    if status in (401, 403) or name == "AuthenticationError" or "api key" in text or "authentication" in text:
        return (
            f"{prefix}\n"
            "הסיבה: בעיית הרשאה/הגדרה במפתח ה-AI (Anthropic).\n"
            "מה לעשות: יש לפנות למנהל המערכת לבדיקת מפתח ה-API."
        )

    # Unknown.
    return (
        f"{prefix}\n"
        "הסיבה: תקלה טכנית בשירות ה-AI ולא ניתן היה לעבד את הבקשה כעת.\n"
        "מה לעשות: נסה שוב בעוד רגע; אם זה חוזר, פנה למנהל המערכת. הפרטים שמסרת נשמרו."
    )
