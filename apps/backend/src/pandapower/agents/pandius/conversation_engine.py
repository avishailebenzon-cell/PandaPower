"""Pandius conversation engine — deliberately lean to control LLM cost.

Compared to Pandi's engine this is intentionally minimal: no enhanced job-context
extraction, no referral machinery, a cheaper model, a tight token cap, and a hard
per-conversation message ceiling. Pandius's whole job is short and transactional:
collect details → save → invite CV → look up a job → wrap up.
"""

from typing import Optional
from uuid import UUID

import structlog

from pandapower.integrations.anthropic_client import get_anthropic_client
from pandapower.core.supabase import get_supabase_client
from .prompts.system import get_system_prompt
from .tools import get_pandius_tools

logger = structlog.get_logger(__name__)

# Cost guardrails — Pandius can be a heavy spender, so keep him cheap and bounded.
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 600
MAX_HISTORY = 16            # recent messages fed to the model
MAX_INBOUND_PER_CONVERSATION = 30  # hard ceiling; after this, hand off to humans


class PandiusConversationEngine:
    """Manages LLM-powered conversations with Pandius (job seekers)."""

    def __init__(self):
        self.anthropic = get_anthropic_client()
        self._supabase = None

    async def _get_supabase(self):
        if self._supabase is None:
            self._supabase = await get_supabase_client()
        return self._supabase

    async def handle_message(
        self,
        conversation_id: UUID,
        pandius_client_id: UUID,
        incoming_text: str,
    ) -> Optional[dict]:
        """Handle one inbound text message and produce Pandius's reply."""
        supabase = await self._get_supabase()

        # Hard message ceiling — protects against runaway cost on a single thread.
        inbound_count = await self._count_inbound(conversation_id, supabase)
        if inbound_count > MAX_INBOUND_PER_CONVERSATION:
            text = (
                "תודה רבה! העברתי את הפנייה שלך לצוות הגיוס שלנו והם יחזרו אליך. 🙏"
            )
            await self._save_message(
                conversation_id, pandius_client_id, "outbound", text, supabase=supabase
            )
            await supabase.table("pandius_conversations").update(
                {"status": "transferred_to_recruitment"}
            ).eq("id", str(conversation_id)).execute()
            return {"text": text, "blocked": True, "reason": "message_cap"}

        # Load light context.
        conversation = await self._load_conversation(conversation_id, supabase)
        recent = await self._load_recent_messages(conversation_id, supabase)

        messages = [
            {"role": m["direction"], "content": m["text"]}
            for m in recent
            if m.get("text")
        ]
        messages.append({"role": "user", "content": incoming_text})

        try:
            response = await self._call_claude(messages)
        except Exception as e:
            logger.error("pandius_claude_failed", error=str(e))
            return {
                "text": "סליחה, יש לי תקלה טכנית קטנה. אפשר לנסות שוב בעוד רגע?",
                "blocked": False,
                "reason": "llm_error",
            }

        # Execute tool calls.
        from .tool_handlers import execute_tool

        response_text = response.get("text", "")
        for block in response.get("content", []):
            if hasattr(block, "type") and block.type == "tool_use":
                logger.info("pandius_tool", tool=block.name)
                result = await execute_tool(
                    tool_name=block.name,
                    tool_input=block.input,
                    conversation_id=conversation_id,
                    pandius_client_id=pandius_client_id,
                )
                if result.get("message"):
                    response_text = (response_text + "\n\n" + result["message"]).strip()

        if response_text:
            await self._save_message(
                conversation_id,
                pandius_client_id,
                "outbound",
                response_text,
                llm_model=MODEL,
                llm_input_tokens=response.get("input_tokens", 0),
                llm_output_tokens=response.get("output_tokens", 0),
                supabase=supabase,
            )

        return {"text": response_text, "blocked": False}

    async def _call_claude(self, messages: list) -> dict:
        from pandapower.agents.company_profile import load_company_extra

        try:
            supabase = await self._get_supabase()
            company_extra = await load_company_extra(supabase)
        except Exception:
            company_extra = ""

        system_prompt = get_system_prompt("1.0", company_extra=company_extra)

        response = self.anthropic.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            tools=get_pandius_tools(),
            messages=messages,
        )

        text_content = ""
        for block in response.content:
            if hasattr(block, "text"):
                text_content += block.text

        try:
            from pandapower.integrations.usage_tracker import record_usage
            await record_usage(
                stage="pandius_conversation",
                model=MODEL,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception:
            pass

        return {
            "text": text_content,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "content": response.content,
        }

    async def _count_inbound(self, conversation_id: UUID, supabase) -> int:
        try:
            res = await supabase.table("pandius_messages").select(
                "id", count="exact"
            ).eq("conversation_id", str(conversation_id)).eq(
                "direction", "inbound"
            ).execute()
            return res.count or 0
        except Exception:
            return 0

    async def _load_conversation(self, conversation_id: UUID, supabase) -> dict:
        res = await supabase.table("pandius_conversations").select("*").eq(
            "id", str(conversation_id)
        ).limit(1).execute()
        return res.data[0] if res.data else {}

    async def _load_recent_messages(self, conversation_id: UUID, supabase) -> list:
        res = await supabase.table("pandius_messages").select(
            "direction, text, sent_at"
        ).eq("conversation_id", str(conversation_id)).order(
            "sent_at", desc=False
        ).limit(MAX_HISTORY).execute()
        return res.data or []

    async def _save_message(
        self,
        conversation_id: UUID,
        pandius_client_id: UUID,
        direction: str,
        text: str,
        llm_model: Optional[str] = None,
        llm_input_tokens: int = 0,
        llm_output_tokens: int = 0,
        supabase=None,
    ) -> None:
        if supabase is None:
            supabase = await self._get_supabase()
        await supabase.table("pandius_messages").insert({
            "conversation_id": str(conversation_id),
            "pandius_client_id": str(pandius_client_id),
            "direction": direction,
            "message_type": "text",
            "text": text,
            "llm_invoked": llm_model is not None,
            "llm_model": llm_model,
            "llm_input_tokens": llm_input_tokens,
            "llm_output_tokens": llm_output_tokens,
        }).execute()
