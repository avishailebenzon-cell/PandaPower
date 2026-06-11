"""
Pandi Conversation Engine - LLM-powered conversation management
"""

import json
from typing import Optional
from datetime import datetime
from uuid import UUID

from anthropic import Anthropic
import structlog

from pandapower.integrations.anthropic_client import get_anthropic_client
from pandapower.core.supabase import get_supabase_client
from .prompts.system import get_system_prompt
from .job_context_builder import JobContextBuilder
from .job_context_enhanced import EnhancedJobContextBuilder
from .tools import get_pandi_tools

logger = structlog.get_logger(__name__)

MAX_TOOL_TURNS = 5  # max model<->tool round trips before forcing a reply


class ConversationEngine:
    """Manages LLM-powered conversations with Pandi clients."""

    def __init__(self):
        self.anthropic = get_anthropic_client()
        self.job_context_builder = JobContextBuilder()
        self.enhanced_context_builder = EnhancedJobContextBuilder()
        self._supabase = None
        # System prompt will be generated dynamically with context guidance

    async def _get_supabase(self):
        """Get Supabase client lazily."""
        if self._supabase is None:
            self._supabase = await get_supabase_client()
        return self._supabase

    async def handle_message(
        self,
        conversation_id: UUID,
        pandi_client_id: UUID,
        incoming_text: str,
    ) -> Optional[dict]:
        """
        Handle an incoming message from a client.

        Flow:
        1. Check quota
        2. Check for inappropriate content (Haiku call)
        3. Increment quota usage
        4. Load conversation context
        5. Determine LLM mode
        6. Call LLM with tools
        7. Execute any tool calls
        8. Send response to client
        9. Update conversation summary periodically

        Args:
            conversation_id: UUID of the conversation
            pandi_client_id: UUID of the Pandi client
            incoming_text: Text of the incoming message

        Returns:
            Response dict with text and metadata, or None if blocked
        """
        logger.info(
            "handle_message",
            conversation_id=str(conversation_id),
            pandi_client_id=str(pandi_client_id),
            text_preview=incoming_text[:100],
        )

        # Get supabase client
        supabase = await self._get_supabase()

        # 1. Check quota
        quota_info = await self._check_quota(pandi_client_id, supabase)
        if quota_info["state"] == "exhausted":
            # Session 33: Send admin notification
            try:
                from .notification_service import NotificationService

                notifier = NotificationService()
                await notifier.notify_quota_exhausted(
                    client_name=quota_info.get("client_name", "לקוח"),
                    quota_limit=quota_info.get("limit", 100),
                )
            except Exception as e:
                logger.warning(f"Failed to send quota exhausted notification: {e}")

            response_text = (
                f"סליחה {quota_info['client_name']}, סיימת את מכסת ההודעות החודשית שלך ({quota_info['messages_used']}/{quota_info['limit']}).\n"
                "⏰ המכסה תתאפס בתחילת החודש הבא.\n"
                "📈 רוצה להגדיל את המכסה השנה? ענה 'תוסיף מכסה' ואני אשלח בקשה לאדמין."
            )
            return {"text": response_text, "blocked": True, "reason": "quota_exhausted"}

        # 2. Check for inappropriate content (fast check with Haiku)
        is_inappropriate = await self._check_inappropriate(incoming_text)
        if is_inappropriate:
            logger.warning(
                "inappropriate_message_flagged",
                conversation_id=str(conversation_id),
                text_preview=incoming_text[:100],
            )
            # Mark message as flagged in DB
            await self._flag_message(conversation_id, incoming_text, "inappropriate", supabase)

            # Session 33: Notify admin via Telegram
            try:
                from .notification_service import NotificationService

                notifier = NotificationService()
                await notifier.notify_inappropriate_content(
                    client_name=str(pandi_client_id),
                    content_preview=incoming_text[:100],
                )
            except Exception as e:
                logger.warning(f"Failed to send inappropriate content notification: {e}")

            return {
                "text": "סליחה, הודעה זו לא מתאימה. בואו נחזור לדיון על משרה 😊",
                "blocked": True,
                "reason": "inappropriate",
            }

        # 3. Increment quota (for incoming message)
        await self._increment_quota(pandi_client_id, 1, supabase)

        # 4. Load conversation context
        conversation = await self._load_conversation(conversation_id, supabase)
        recent_messages = await self._load_recent_messages(
            conversation_id, limit=30, supabase=supabase
        )
        job_context = conversation.get("job_context") or {}

        # 4a. Session 31: Enhance job context (extract + track fields)
        job_context = await self._enhance_job_context(
            conversation_id=conversation_id,
            job_context=job_context,
            recent_messages=recent_messages,
            current_message=incoming_text,
            supabase=supabase,
        )

        # 5. Determine LLM mode (uses enhanced context)
        mode = self._determine_mode(
            conversation.get("status"), job_context
        )
        logger.info("conversation_mode", mode=mode)

        # 5b. Build ground-truth client status so Pandi doesn't restart Phase 1
        # (identification) every turn — the root cause of "I haven't registered
        # you yet" appearing after the client was already created.
        client_status = await self._build_client_status(pandi_client_id, supabase)

        # 6. Call LLM with tools
        tools_list = get_pandi_tools()
        # Map our storage directions to Anthropic chat roles. inbound (from the
        # client) → "user"; outbound (Pandi) → "assistant". Using the raw
        # "inbound"/"outbound" strings here is an invalid-role API error.
        messages = [
            {
                "role": "user" if msg["direction"] == "inbound" else "assistant",
                "content": msg["text"] or "",
            }
            for msg in recent_messages
            if (msg.get("text") or "").strip()
        ]
        # The first turn must be a user turn for the Anthropic API.
        while messages and messages[0]["role"] == "assistant":
            messages.pop(0)
        # Add current user message
        messages.append({"role": "user", "content": incoming_text})

        # 6+7. Agentic tool loop: call the model, run any tools it requests, feed
        # the tool RESULTS back to the model, and let it write the final reply.
        # Tool result strings are internal context for the model — they are NEVER
        # appended to the reply verbatim (that leaked internal notes to clients and
        # left the model blind to what its own tools returned). The reply is only
        # the model's text from the turn that requests no more tools.
        from .tool_handlers import execute_tool
        import json as _json

        response = None
        response_text = ""
        try:
            for _ in range(MAX_TOOL_TURNS):
                response = await self._call_claude(
                    messages=messages,
                    tools=tools_list,
                    job_context=job_context,
                    model="claude-opus-4-7",
                    client_status=client_status,
                )
                content_blocks = response.get("content", [])
                text = response.get("text", "")
                tool_uses = [
                    b for b in content_blocks
                    if hasattr(b, "type") and b.type == "tool_use"
                ]

                if not tool_uses:
                    response_text = text
                    break

                messages.append({"role": "assistant", "content": content_blocks})
                tool_result_blocks = []
                for block in tool_uses:
                    logger.info(f"Executing tool: {block.name}")
                    tool_result = await execute_tool(
                        tool_name=block.name,
                        tool_input=block.input,
                        conversation_id=conversation_id,
                        pandi_client_id=pandi_client_id,
                    )
                    logger.info(f"Tool result: {tool_result}")
                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _json.dumps(tool_result, ensure_ascii=False),
                    })
                messages.append({"role": "user", "content": tool_result_blocks})
            else:
                # Exhausted tool turns without a clean text reply.
                response_text = response_text or (response.get("text", "") if response else "")
        except Exception as e:
            logger.error("claude_call_failed", error=str(e))
            return {
                "text": "סליחה, קצת בעיה טכנית. נסה שוב בעוד דקה.",
                "blocked": False,
                "reason": "llm_error",
            }

        # 8. Send response to client

        if response_text:
            # גילוי נאות — prepend the one-time AI disclosure on the very first
            # outbound message of the conversation (once per user, first message
            # only). Deterministic so the model can never drop or repeat it.
            response_text = await self._prepend_disclosure_if_first(
                conversation_id, response_text, supabase
            )
            # Save outgoing message to DB
            await self._save_message(
                conversation_id=conversation_id,
                pandi_client_id=pandi_client_id,
                direction="outbound",
                text=response_text,
                llm_model="claude-opus-4-7",
                llm_input_tokens=response.get("input_tokens", 0),
                llm_output_tokens=response.get("output_tokens", 0),
                supabase=supabase,
            )
            # Increment quota for outgoing message
            await self._increment_quota(pandi_client_id, 1, supabase)

        # 9. Update conversation summary every 10 messages
        message_count = await self._get_message_count(conversation_id, supabase)
        if message_count % 10 == 0:
            summary = await self._generate_summary(conversation_id, supabase)
            await self._update_conversation_summary(conversation_id, summary, supabase)

        return {
            "text": response_text,
            "blocked": False,
            "mode": mode,
            "tokens_used": response.get("input_tokens", 0)
            + response.get("output_tokens", 0),
        }

    async def _check_quota(self, pandi_client_id: UUID, supabase) -> dict:
        """Check current quota status for a client.

        Fail-open: if the check_quota DB function (or the quota table) isn't
        provisioned, we must NOT block the reply — quota is a soft guard rail,
        not a gate on Pandi responding at all. Any error returns an "ok" state.
        """
        try:
            result = await supabase.rpc(
                "check_quota",
                {"p_client_id": str(pandi_client_id)},
            ).execute()
            data = getattr(result, "data", None) or []
            return data[0] if data else {"state": "ok", "messages_used": 0}
        except Exception as e:
            logger.warning("check_quota unavailable — failing open", error=str(e))
            return {"state": "ok", "messages_used": 0}

    async def _check_inappropriate(self, text: str) -> bool:
        """Fast inappropriate content check using Haiku."""
        prompt = f"""Analyze this WhatsApp message for inappropriate content (rude, abusive, explicit).

Message: "{text}"

Respond with only: YES or NO"""
        try:
            response = self.anthropic.messages.create(
                model="claude-haiku-4-5",
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}],
            )
            result = response.content[0].text.strip().upper()
            return result == "YES"
        except Exception as e:
            logger.warning("inappropriate_check_failed", error=str(e))
            return False

    async def _flag_message(
        self, conversation_id: UUID, text: str, reason: str, supabase=None
    ) -> None:
        """Flag a message as inappropriate."""
        if supabase is None:
            supabase = await self._get_supabase()
        await supabase.table("pandi_messages").insert({
            "conversation_id": str(conversation_id),
            "direction": "inbound",
            "text": text,
            "inappropriate_flag": True,
            "flag_reason": reason,
        }).execute()

    async def _notify_admin_inappropriate(
        self, pandi_client_id: UUID, text: str
    ) -> None:
        """Notify admin via Telegram about inappropriate message."""
        # Placeholder for Telegram notification in Phase 28
        logger.warning(
            "admin_notification_needed",
            event="inappropriate_message",
            pandi_client_id=str(pandi_client_id),
            text=text[:100],
        )

    async def _increment_quota(
        self, pandi_client_id: UUID, count: int = 1, supabase=None
    ) -> None:
        """Increment quota usage. Best-effort — never blocks the reply."""
        if supabase is None:
            supabase = await self._get_supabase()
        try:
            await supabase.rpc(
                "increment_quota_usage",
                {"p_client_id": str(pandi_client_id), "p_count": count},
            ).execute()
        except Exception as e:
            logger.warning("increment_quota_usage unavailable — skipping", error=str(e))

    async def _build_client_status(self, pandi_client_id: UUID, supabase) -> str:
        """Describe whether this client is already identified/registered, with
        their known details, so the LLM never re-runs Phase 1 mid-conversation.

        Best-effort: any failure returns an empty hint rather than breaking the
        reply."""
        try:
            res = await supabase.table("pandi_clients").select(
                "intake_status, contact_id, intake_collected_data, phone"
            ).eq("id", str(pandi_client_id)).limit(1).execute()
            client = res.data[0] if res.data else {}
        except Exception:
            client = {}

        contact_id = client.get("contact_id")
        intake = (client.get("intake_status") or "").lower()
        collected = client.get("intake_collected_data") or {}

        name = email = company = None
        if contact_id:
            try:
                cres = await supabase.table("contacts").select(
                    "full_name, email"
                ).eq("id", str(contact_id)).limit(1).execute()
                if cres.data:
                    name = cres.data[0].get("full_name")
                    email = cres.data[0].get("email")
            except Exception:
                pass
        name = name or collected.get("name")
        email = email or collected.get("email")
        company = collected.get("company")

        # Registered if we have a contact link, OR intake already completed.
        registered = bool(contact_id) or intake in ("completed", "active", "identified")

        lines = []
        if registered:
            lines.append("הלקוח כבר זוהה ונרשם במערכת — שלב הזיהוי (Phase 1) הושלם.")
            lines.append("אל תציגי את עצמך מחדש, אל תבקשי שוב שם/מייל/חברה, ואל תקראי שוב ל-identify_client/create_client.")
            lines.append("המשיכי ישירות לשיחה על המשרה.")
        else:
            lines.append("הלקוח עדיין לא נרשם — זהו לקוח חדש שצריך לעבור את שלב הזיהוי (Phase 1).")
        if name:
            lines.append(f"שם הלקוח: {name}")
        if email:
            lines.append(f"מייל: {email}")
        if company:
            lines.append(f"חברה: {company}")
        return "\n".join(lines)

    async def _load_conversation(self, conversation_id: UUID, supabase=None) -> dict:
        """Load conversation record."""
        if supabase is None:
            supabase = await self._get_supabase()
        result = await supabase.table("pandi_conversations").select(
            "*"
        ).eq("id", str(conversation_id)).single().execute()
        return result.data or {}

    async def _load_recent_messages(
        self, conversation_id: UUID, limit: int = 30, supabase=None
    ) -> list:
        """Load the most recent `limit` messages, in chronological order.

        Fetch newest-first with the limit, then reverse — ordering ascending with
        a limit would return the OLDEST messages and freeze the model on the start
        of the conversation, dropping all recent context."""
        if supabase is None:
            supabase = await self._get_supabase()
        result = (
            await supabase.table("pandi_messages")
            .select("direction, text, sent_at")
            .eq("conversation_id", str(conversation_id))
            .order("sent_at", desc=True)
            .limit(limit)
            .execute()
        )
        return list(reversed(result.data or []))

    async def _save_message(
        self,
        conversation_id: UUID,
        pandi_client_id: UUID,
        direction: str,
        text: str,
        llm_model: Optional[str] = None,
        llm_input_tokens: int = 0,
        llm_output_tokens: int = 0,
        supabase=None,
    ) -> None:
        """Save message to DB."""
        if supabase is None:
            supabase = await self._get_supabase()
        await supabase.table("pandi_messages").insert({
            "conversation_id": str(conversation_id),
            "pandi_client_id": str(pandi_client_id),
            "direction": direction,
            "message_type": "text",
            "text": text,
            "llm_invoked": llm_model is not None,
            "llm_model": llm_model,
            "llm_input_tokens": llm_input_tokens,
            "llm_output_tokens": llm_output_tokens,
        }).execute()

    async def _prepend_disclosure_if_first(
        self, conversation_id: UUID, text: str, supabase=None
    ) -> str:
        """Prepend the one-time AI disclosure if no outbound message exists yet
        in this conversation. Fail-open — never blocks the reply."""
        if supabase is None:
            supabase = await self._get_supabase()
        try:
            res = (
                await supabase.table("pandi_messages")
                .select("id", count="exact")
                .eq("conversation_id", str(conversation_id))
                .eq("direction", "outbound")
                .limit(1)
                .execute()
            )
            if (getattr(res, "count", 0) or 0) == 0:
                from pandapower.agents.company_profile import prepend_disclosure
                return prepend_disclosure("pandi", text)
        except Exception as e:
            logger.warning("pandi_disclosure_check_failed", error=str(e))
        return text

    async def _get_message_count(self, conversation_id: UUID, supabase=None) -> int:
        """Get total message count in conversation."""
        if supabase is None:
            supabase = await self._get_supabase()
        result = (
            await supabase.table("pandi_messages")
            .select("id", count="exact")
            .eq("conversation_id", str(conversation_id))
            .execute()
        )
        return getattr(result, "count", 0) or 0

    async def _generate_summary(self, conversation_id: UUID, supabase=None) -> str:
        """Generate LLM summary of conversation."""
        if supabase is None:
            supabase = await self._get_supabase()
        messages = await self._load_recent_messages(conversation_id, limit=50, supabase=supabase)
        text_history = "\n".join(
            [f"{m['direction']}: {m['text']}" for m in messages]
        )

        prompt = f"""Summarize this client conversation in 2-3 sentences (Hebrew):

{text_history}

Focus on: what the client is looking for (job type, requirements, preferences)."""

        try:
            response = self.anthropic.messages.create(
                model="claude-haiku-4-5",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as e:
            logger.error("summary_generation_failed", error=str(e))
            return ""

    async def _update_conversation_summary(
        self, conversation_id: UUID, summary: str, supabase=None
    ) -> None:
        """Update conversation summary."""
        if supabase is None:
            supabase = await self._get_supabase()
        await supabase.table("pandi_conversations").update(
            {"summary": summary}
        ).eq("id", str(conversation_id)).execute()

    async def _enhance_job_context(
        self,
        conversation_id: UUID,
        job_context: dict,
        recent_messages: list,
        current_message: str,
        supabase,
    ) -> dict:
        """
        Session 31: Use enhanced builder to improve context extraction.

        Args:
            conversation_id: UUID of conversation
            job_context: Current job context
            recent_messages: Recent conversation messages
            current_message: Latest client message
            supabase: Supabase client

        Returns:
            Enhanced job context with metadata tracking
        """
        try:
            # Extract enhanced context
            enhanced = await self.enhanced_context_builder.extract_job_context_enhanced(
                conversation_history=recent_messages,
                current_message=current_message,
                existing_context=job_context,
            )

            # Update in DB
            await self.enhanced_context_builder.update_conversation_job_context_enhanced(
                conversation_id=conversation_id,
                new_context=enhanced,
            )

            logger.info(
                "job_context_enhanced",
                conversation_id=str(conversation_id),
                completeness=enhanced.get("_metadata", {}).get("completeness_score", 0),
            )

            return enhanced

        except Exception as e:
            logger.error("job_context_enhancement_failed", error=str(e))
            return job_context

    def _determine_mode(
        self, conversation_status: str, job_context: dict
    ) -> str:
        """
        Determine the conversation mode based on status and context.

        Session 31: Enhanced mode determination with partial context support.
        """
        if not conversation_status or conversation_status == "open":
            return "opening"
        elif conversation_status == "awaiting_job_definition":
            # Check sufficiency with enhanced builder
            if self.enhanced_context_builder.has_sufficient_context(job_context, allow_partial=True):
                return "searching"
            else:
                return "job_context_building"
        elif conversation_status == "presenting_candidates":
            return "presenting"
        elif conversation_status == "awaiting_selection":
            return "awaiting_selection"
        else:
            return "closing"

    def _generate_context_guidance(self, job_context: dict) -> str:
        """
        Session 31: Generate context guidance for system prompt.

        Args:
            job_context: Current job context with metadata

        Returns:
            Human-readable guidance about context completeness
        """
        if not job_context:
            return "No job context yet. Start by asking what they're looking for."

        summary = self.enhanced_context_builder.get_completeness_summary(job_context)
        next_q = summary.get("next_question")

        guidance = f"""Current context: {summary['assessment']} ({summary['completeness_percent']}% complete)
- Filled: {', '.join(summary['fields_populated']) if summary['fields_populated'] else 'none yet'}
- Missing: {', '.join(summary['fields_missing']) if summary['fields_missing'] else 'none'}"""

        if next_q:
            guidance += f"\n- If context is incomplete, ask: {next_q}"

        return guidance

    async def _call_claude(
        self,
        messages: list,
        tools: list,
        job_context: dict,
        model: str = "claude-opus-4-7",
        client_status: str = "",
    ) -> dict:
        """
        Call Claude API with tools and dynamic context guidance.

        Args:
            messages: Message history
            tools: Available tools
            job_context: Current job context (for guidance)
            model: Model to use
        """
        # Generate dynamic context guidance
        context_guidance = self._generate_context_guidance(job_context)

        # Get system prompt with context guidance (Session 31)
        from pandapower.agents.company_profile import load_company_extra
        try:
            supabase = await self._get_supabase()
            company_extra = await load_company_extra(supabase)
        except Exception:
            company_extra = ""
        system_prompt = get_system_prompt(
            "1.0", context_guidance=context_guidance, company_extra=company_extra,
            client_status=client_status,
        )

        response = self.anthropic.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        # Extract text response and capture full response for tool processing
        text_content = ""
        for block in response.content:
            if hasattr(block, "text"):
                text_content += block.text

        # Record token usage for the cost dashboard (best-effort).
        try:
            from pandapower.integrations.usage_tracker import record_usage
            await record_usage(
                stage="pandi_conversation",
                model=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )
        except Exception:
            pass

        return {
            "text": text_content,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "content": response.content,  # Full response content for tool execution
        }
