"""
Pandi Job Context Builder - Extracts job requirements through conversation
"""

import json
from typing import Optional
from uuid import UUID

from anthropic import Anthropic
import structlog

from pandapower.integrations.anthropic_client import get_anthropic_client
from pandapower.core.supabase import get_supabase_client

logger = structlog.get_logger(__name__)


class JobContextBuilder:
    """Manages job context building through natural conversation."""

    def __init__(self):
        self.anthropic = get_anthropic_client()
        self._supabase = None

    async def _get_supabase(self):
        """Get Supabase client lazily."""
        if self._supabase is None:
            self._supabase = await get_supabase_client()
        return self._supabase

    async def extract_job_context(
        self,
        conversation_history: list,
        current_message: str,
    ) -> Optional[dict]:
        """
        Extract structured job context from conversation.

        Args:
            conversation_history: List of previous messages
            current_message: Latest message from client

        Returns:
            Updated job_context dict or None
        """
        # Build conversation text
        conv_text = "\n".join(
            [
                f"{msg['direction']}: {msg['text']}"
                for msg in conversation_history
            ]
        )
        conv_text += f"\nuser: {current_message}"

        prompt = f"""Extract job context from this client conversation.
Return JSON with these fields (use null for unknown):

{{
  "title": "Job title",
  "qualifications": "Required skills and experience",
  "location": "Work location or remote",
  "security_clearance": "Required security clearance level (or null)",
  "must_have": ["List of must-have skills"],
  "nice_to_have": ["List of nice-to-have skills"],
  "soft_skills_notes": "Cultural fit, team dynamics, personality traits",
  "other_notes": "Any other important info the client emphasized"
}}

Conversation:
{conv_text}

Guidelines:
- Extract only what's explicitly mentioned or strongly implied
- Don't hallucinate requirements
- Keep qualifications as a narrative (don't force a list)
- If the client mentions something multiple times, it's probably important
- Hebrew responses are OK for notes"""

        try:
            response = self.anthropic.messages.create(
                model="claude-opus-4-7",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse JSON response
            response_text = response.content[0].text
            # Extract JSON from response (might be wrapped in markdown code blocks)
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0]
            else:
                json_str = response_text

            job_context = json.loads(json_str.strip())
            return job_context

        except json.JSONDecodeError as e:
            logger.error("job_context_json_parse_failed", error=str(e))
            return None
        except Exception as e:
            logger.error("job_context_extraction_failed", error=str(e))
            return None

    async def update_conversation_job_context(
        self,
        conversation_id: UUID,
        new_context: dict,
    ) -> None:
        """
        Update the job context for a conversation (merge with existing).

        Args:
            conversation_id: UUID of conversation
            new_context: New context fields to merge
        """
        supabase = await self._get_supabase()
        # Get existing context
        _conv_res = await supabase.table(
            "pandi_conversations"
        ).select("job_context").eq("id", str(conversation_id)).limit(1).execute()
        conversation = _conv_res.data[0] if _conv_res.data else {}

        existing_context = (conversation.get("job_context") if conversation else None) or {}

        # Merge: prefer new values, keep existing if new is null
        merged_context = {**existing_context}
        for key, value in new_context.items():
            if value is not None:
                merged_context[key] = value

        # Update
        await supabase.table("pandi_conversations").update(
            {"job_context": merged_context}
        ).eq("id", str(conversation_id)).execute()

        logger.info(
            "job_context_updated",
            conversation_id=str(conversation_id),
            context=merged_context,
        )

    def has_sufficient_context(self, job_context: dict) -> bool:
        """
        Check if we have enough context to search for candidates.

        Args:
            job_context: Job context dict

        Returns:
            True if we have minimum required fields
        """
        # Minimum: title and qualifications
        return bool(
            job_context.get("title")
            and job_context.get("qualifications")
        )

    def context_to_search_query(self, job_context: dict) -> str:
        """
        Convert job context to a human-readable search query.

        Args:
            job_context: Job context dict

        Returns:
            String representation for logging/display
        """
        parts = []
        if job_context.get("title"):
            parts.append(f"תפקיד: {job_context['title']}")
        if job_context.get("location"):
            parts.append(f"מיקום: {job_context['location']}")
        if job_context.get("security_clearance"):
            parts.append(f"סיווג: {job_context['security_clearance']}")
        if job_context.get("must_have"):
            skills_str = ", ".join(job_context["must_have"][:3])
            parts.append(f"כישורים: {skills_str}")
        return " | ".join(parts)
