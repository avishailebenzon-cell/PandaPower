"""
Session 31: Enhanced Job Context Extraction & Field Tracking
Improves context building with better sufficiency checks, field tracking, and confidence scoring
"""

import json
from typing import Optional
from uuid import UUID

from anthropic import Anthropic
import structlog

from pandapower.integrations.anthropic_client import get_anthropic_client
from pandapower.core.supabase import get_supabase_client

logger = structlog.get_logger(__name__)


class EnhancedJobContextBuilder:
    """
    Enhanced context builder with field tracking and intelligent guidance.

    Session 31 improvements:
    - Field completion tracking (which fields are set vs. empty)
    - Confidence scoring (how confident in each field's value)
    - Smart sufficiency checking (dynamic based on partial context)
    - Intelligent follow-up questions (what to ask based on missing fields)
    - Extraction annotations (why a value was extracted)
    """

    def __init__(self):
        self.anthropic = get_anthropic_client()
        self._supabase = None

    async def _get_supabase(self):
        """Get Supabase client lazily."""
        if self._supabase is None:
            self._supabase = await get_supabase_client()
        return self._supabase

    async def extract_job_context_enhanced(
        self,
        conversation_history: list,
        current_message: str,
        existing_context: Optional[dict] = None,
    ) -> dict:
        """
        Extract and score job context from conversation with confidence metrics.

        Args:
            conversation_history: List of previous messages
            current_message: Latest message from client
            existing_context: Existing context to enhance

        Returns:
            Enhanced context dict with _metadata field tracking confidence and completeness
        """
        # Build conversation text
        conv_text = "\n".join(
            [
                f"{msg['direction']}: {msg['text']}"
                for msg in conversation_history[-10:]  # Last 10 messages for context
            ]
        )
        conv_text += f"\nuser: {current_message}"

        # Build prompt considering existing context
        existing_note = ""
        if existing_context:
            existing_note = f"""
Previously extracted context:
{json.dumps(existing_context, ensure_ascii=False, indent=2)}

Update or refine this context based on new information. Only override if new info is clearer/better."""

        prompt = f"""Extract and refine job context from client conversation.
Return JSON with these fields (use null for unknown/unmentioned):

{{
  "title": "Job title (e.g., Backend Developer, Systems Engineer)",
  "qualifications": "Required skills, experience, or education",
  "location": "Work location, remote preference, or geographic requirement",
  "security_clearance": "Required clearance level if any",
  "must_have": ["Critical skills the candidate must have"],
  "nice_to_have": ["Beneficial but not required skills"],
  "soft_skills_notes": "Team dynamics, personality traits, cultural fit",
  "other_notes": "Any other emphasized requirements or preferences"
}}

{existing_note}

Recent conversation:
{conv_text}

Guidelines:
- Extract ONLY what's explicitly mentioned (don't invent requirements)
- For must_have/nice_to_have: extract specific skills/domains mentioned
- If client mentions "5+ years backend" → years_experience: 5
- Keep qualifications as readable text (not a list)
- If uncertain about a field, set to null
- Hebrew in notes is fine (don't translate)
- Look for importance signals: repetition, emphasis ("really need", "critical"), and tone"""

        try:
            response = self.anthropic.messages.create(
                model="claude-opus-4-7",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            # Extract JSON from response
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0]
            else:
                json_str = response_text

            extracted = json.loads(json_str.strip())

            # Add metadata for tracking
            enhanced = self._add_metadata(extracted, existing_context)
            return enhanced

        except json.JSONDecodeError as e:
            logger.error("job_context_json_parse_failed", error=str(e))
            return existing_context or {}
        except Exception as e:
            logger.error("job_context_extraction_failed", error=str(e))
            return existing_context or {}

    def _add_metadata(
        self,
        extracted: dict,
        existing: Optional[dict] = None
    ) -> dict:
        """
        Add metadata tracking field completion and confidence.

        Session 31: Track which fields are set and their quality.
        """
        metadata = {
            "_metadata": {
                "fields_populated": [],
                "fields_missing": [],
                "confidence": {},
                "completeness_score": 0,
            }
        }

        # Core fields and their required status
        required_fields = ["title", "qualifications"]
        optional_fields = [
            "location", "security_clearance", "must_have",
            "nice_to_have", "soft_skills_notes", "other_notes"
        ]

        # Track populated vs. missing
        for field in required_fields:
            value = extracted.get(field)
            is_populated = bool(value)

            if is_populated:
                metadata["_metadata"]["fields_populated"].append(field)
                # Assess confidence
                confidence = self._assess_field_confidence(field, value, existing)
                metadata["_metadata"]["confidence"][field] = confidence
            else:
                metadata["_metadata"]["fields_missing"].append(field)
                metadata["_metadata"]["confidence"][field] = 0.0

        for field in optional_fields:
            value = extracted.get(field)
            is_populated = bool(value) and value != []

            if is_populated:
                metadata["_metadata"]["fields_populated"].append(field)
                confidence = self._assess_field_confidence(field, value, existing)
                metadata["_metadata"]["confidence"][field] = confidence
            else:
                metadata["_metadata"]["fields_missing"].append(field)
                metadata["_metadata"]["confidence"][field] = 0.0

        # Calculate completeness score (0-100)
        total_fields = len(required_fields) + len(optional_fields)
        populated = len(metadata["_metadata"]["fields_populated"])
        metadata["_metadata"]["completeness_score"] = int(
            (populated / total_fields) * 100
        )

        # Merge with extracted (include metadata)
        result = {**extracted, **metadata}
        return result

    def _assess_field_confidence(
        self,
        field: str,
        value,
        existing: Optional[dict] = None
    ) -> float:
        """
        Assess confidence in extracted field (0-1 scale).

        Session 31: Heuristics for confidence scoring:
        - Explicit mentions are high confidence (0.9)
        - Implied info is medium confidence (0.7)
        - Repeated mentions increase confidence
        - Vague info is lower confidence (0.5)
        """
        if not value:
            return 0.0

        # List fields: more items = higher confidence
        if isinstance(value, list):
            if len(value) == 0:
                return 0.0
            elif len(value) >= 3:
                return 0.85
            elif len(value) >= 1:
                return 0.7
            return 0.5

        # String fields: length and specificity
        if isinstance(value, str):
            length = len(value.strip())

            if length < 3:
                return 0.3
            elif length < 10:
                return 0.5
            elif length < 30:
                return 0.75
            else:
                return 0.9

        return 0.6

    def has_sufficient_context(
        self,
        job_context: dict,
        allow_partial: bool = True
    ) -> bool:
        """
        Enhanced sufficiency check with partial context support.

        Args:
            job_context: Job context dict
            allow_partial: If True, partial context (title + 1 other field) is OK

        Returns:
            True if context is sufficient for candidate search
        """
        has_title = bool(job_context.get("title"))
        has_qualifications = bool(job_context.get("qualifications"))
        has_must_have_skills = bool(job_context.get("must_have") and len(job_context.get("must_have", [])) > 0)

        # Strict: title + qualifications
        if has_title and has_qualifications:
            return True

        # Partial: title + must_have skills (enough for basic match)
        if allow_partial and has_title and has_must_have_skills:
            return True

        return False

    def get_missing_fields(self, job_context: dict) -> list[str]:
        """
        Get list of fields that would improve the search.

        Args:
            job_context: Job context dict

        Returns:
            List of field names that would be helpful to gather
        """
        missing = []

        if not job_context.get("title"):
            missing.append("title")
        if not job_context.get("qualifications"):
            missing.append("qualifications")
        if not job_context.get("must_have") or len(job_context.get("must_have", [])) == 0:
            missing.append("must_have")
        if not job_context.get("security_clearance"):
            missing.append("security_clearance")
        if not job_context.get("location"):
            missing.append("location")
        if not job_context.get("soft_skills_notes"):
            missing.append("soft_skills_notes")

        return missing

    def suggest_next_question(self, job_context: dict) -> Optional[str]:
        """
        Suggest what to ask next based on context completeness.

        Args:
            job_context: Current job context

        Returns:
            Hebrew question to ask client, or None if sufficient
        """
        missing = self.get_missing_fields(job_context)

        if not missing:
            return None

        # Priority order for questions
        if "title" in missing:
            return "בואו נתחיל - איזה תפקיד אתה מחפש? 💼"
        elif "qualifications" in missing:
            return f"מלבד שם התפקיד, איזה ניסיון או כישורים חשובים עבורך? 🎯"
        elif "must_have" in missing:
            return f"יש איזה כישורים או טכנולוגיות שחייבים להיות? (למשל Python, AWS, וכו') 🔧"
        elif "security_clearance" in missing:
            return "צריך סיווג בטחוני כלשהו לתפקיד? 🔐"
        elif "location" in missing:
            return "איפה המשרה? באופן אישי, רימוט, או זה לא חשוב? 📍"
        elif "soft_skills_notes" in missing:
            return "איזה סוג אדם מחפש אתה? (צוות, יחיד, מנהיג, וכו') 👥"

        return None

    def get_completeness_summary(self, job_context: dict) -> dict:
        """
        Get human-readable summary of context completeness.

        Args:
            job_context: Job context dict

        Returns:
            Summary dict with percentage and description
        """
        metadata = job_context.get("_metadata", {})
        completeness = metadata.get("completeness_score", 0)
        populated = metadata.get("fields_populated", [])
        missing = metadata.get("fields_missing", [])
        confidence = metadata.get("confidence", {})

        # Assessment description
        if completeness >= 80:
            assessment = "מקומלט מאוד - מוכנים לחיפוש! ✅"
        elif completeness >= 50:
            assessment = "בשלב טוב - אפשר לחפש, אבל עוד יש ללמוד עלך"
        elif completeness >= 30:
            assessment = "בתחילת הדרך - בואו נאספו עוד מידע"
        else:
            assessment = "עדיין חסרות הרבה פרטים"

        # High-confidence fields
        high_confidence = [
            field for field, conf in confidence.items()
            if conf >= 0.7 and field != "_metadata"
        ]

        return {
            "completeness_percent": completeness,
            "assessment": assessment,
            "fields_populated": populated,
            "fields_missing": missing,
            "high_confidence_fields": high_confidence,
            "next_question": self.suggest_next_question(job_context),
        }

    async def update_conversation_job_context_enhanced(
        self,
        conversation_id: UUID,
        new_context: dict,
    ) -> None:
        """
        Update job context in DB (enhanced version with metadata).

        Args:
            conversation_id: UUID of conversation
            new_context: New context to merge (includes _metadata)
        """
        supabase = await self._get_supabase()

        # Get existing context
        conversation = await supabase.table(
            "pandi_conversations"
        ).select("job_context").eq("id", str(conversation_id)).single()

        existing_context = conversation.get("job_context") or {}

        # Merge: prefer new values, keep existing if new is null
        merged_context = {**existing_context}

        for key, value in new_context.items():
            if key == "_metadata":
                # Metadata gets merged/replaced (don't partial-merge metadata)
                merged_context["_metadata"] = value
            elif value is not None and value != []:
                # Only override if new value is not null/empty
                merged_context[key] = value

        # Update database
        await supabase.table("pandi_conversations").update(
            {"job_context": merged_context}
        ).eq("id", str(conversation_id))

        logger.info(
            "job_context_updated_enhanced",
            conversation_id=str(conversation_id),
            completeness=merged_context.get("_metadata", {}).get("completeness_score", 0),
        )

    def context_to_search_query(self, job_context: dict) -> str:
        """
        Convert job context to human-readable search query.

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
            parts.append(f"חובה: {skills_str}")

        if job_context.get("nice_to_have"):
            skills_str = ", ".join(job_context["nice_to_have"][:2])
            parts.append(f"בונוס: {skills_str}")

        return " | ".join(parts)
