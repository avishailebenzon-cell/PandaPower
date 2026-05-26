"""Tool handlers for Pandi conversation engine tool calls."""

import logging
from typing import Any, Optional
from uuid import UUID

from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)


async def handle_update_job_context(
    conversation_id: UUID,
    pandi_client_id: UUID,
    **context_fields: Any
) -> dict[str, Any]:
    """Handle update_job_context tool call.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        **context_fields: Job context fields to update

    Returns:
        Result of update operation
    """
    try:
        from .job_context_builder import JobContextBuilder

        builder = JobContextBuilder()

        # Prepare context dict (filter None values)
        new_context = {k: v for k, v in context_fields.items() if v is not None}

        if not new_context:
            return {"status": "success", "message": "No new context to update"}

        # Update conversation job context
        await builder.update_conversation_job_context(
            conversation_id=conversation_id,
            new_context=new_context,
        )

        logger.info(
            "job_context_updated_via_tool",
            conversation_id=str(conversation_id),
            fields=list(new_context.keys()),
        )

        return {
            "status": "success",
            "message": "עדכנתי את הדרישות שלך לתפקיד",
            "updated_fields": list(new_context.keys()),
        }

    except Exception as e:
        logger.error(f"update_job_context failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בעדכון הדרישות",
            "error": str(e),
        }


async def handle_search_candidates(
    conversation_id: UUID,
    pandi_client_id: UUID,
    context_summary: str,
    limit: int = 3,
) -> dict[str, Any]:
    """Handle search_candidates tool call.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        context_summary: Summary of what we're looking for
        limit: Max candidates to return

    Returns:
        Search results with candidates
    """
    try:
        from .candidate_matching import search_candidates_for_context

        # Load full job context from conversation
        supabase = await get_supabase_client()
        conversation = await supabase.table("pandi_conversations").select(
            "job_context"
        ).eq("id", str(conversation_id)).single()

        job_context = conversation.get("job_context", {}) if conversation else {}

        # Call real search implementation (Session 30)
        result = await search_candidates_for_context(job_context, limit)

        if result.get("status") == "success":
            candidates = result.get("candidates", [])
            logger.info(
                "candidates_searched",
                conversation_id=str(conversation_id),
                count=len(candidates),
            )

            # Session 32: Create referral records for each candidate presented
            from .referral_manager import ReferralManager

            manager = ReferralManager()
            formatted_candidates = []

            for candidate in candidates:
                # Get candidate ID for referral creation
                candidate_number = candidate.get("candidate_number")
                candidate_result = await supabase.table("candidates").select(
                    "id"
                ).eq("candidate_number", candidate_number).single()

                if candidate_result:
                    candidate_id = candidate_result["id"]

                    # Create referral record (if not already in this conversation)
                    referral = await manager.create_referral(
                        candidate_id=UUID(candidate_id),
                        candidate_number=candidate_number,
                        pandi_client_id=pandi_client_id,
                        conversation_id=conversation_id,
                        job_context=job_context,
                        presented_payload={
                            "number": candidate_number,
                            "score": candidate.get("match_score"),
                            "years_experience": candidate.get("years_experience"),
                            "skills": candidate.get("top_skills", []),
                            "summary": candidate.get("summary"),
                        },
                        llm_match_reasoning=candidate.get("reasoning"),
                    )

                    if referral.get("status") != "error":
                        logger.info(
                            "referral_created_for_presentation",
                            candidate_number=candidate_number,
                            referral_id=referral.get("referral_id"),
                        )

                # Format for LLM response
                formatted_candidates.append({
                    "number": candidate_number,
                    "score": candidate.get("match_score"),
                    "years_experience": candidate.get("years_experience"),
                    "skills": candidate.get("top_skills", []),
                    "summary": candidate.get("summary"),
                    "reasoning": candidate.get("reasoning"),
                })

            return {
                "status": "success",
                "candidates": formatted_candidates,
                "total": len(candidates),
                "message": f"מצאתי {len(candidates)} מועמדים שנראים מתאימים",
            }
        else:
            return {
                "status": "no_candidates",
                "message": "לא מצאתי מועמדים התואמים כרגע. בואו נזומת יותר על הדרישות שלך.",
            }

    except Exception as e:
        logger.error(f"search_candidates failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בחיפוש המועמדים",
            "error": str(e),
        }


async def handle_mark_client_interested(
    conversation_id: UUID,
    pandi_client_id: UUID,
    candidate_number: str,
    interest_reason: Optional[str] = None,
) -> dict[str, Any]:
    """Handle mark_client_interested tool call.

    Session 32: Uses real referral manager instead of mock.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        candidate_number: Candidate number (e.g., C000123)
        interest_reason: Optional reason for interest

    Returns:
        Result of marking interest
    """
    try:
        from .referral_manager import ReferralManager

        # Get candidate ID from candidate_number
        supabase = await get_supabase_client()
        candidate = await supabase.table("candidates").select(
            "id"
        ).eq("candidate_number", candidate_number).single()

        if not candidate:
            logger.warning(
                "candidate_not_found_by_number",
                candidate_number=candidate_number,
            )
            return {
                "status": "error",
                "message": f"סליחה, לא מצאתי את המועמד {candidate_number}",
            }

        # Use real referral manager
        manager = ReferralManager()
        result = await manager.mark_client_interested(
            candidate_number=candidate_number,
            candidate_id=UUID(candidate["id"]),
            pandi_client_id=pandi_client_id,
            conversation_id=conversation_id,
            interest_reason=interest_reason,
        )

        if result.get("status") == "success":
            logger.info(
                "client_interested_marked",
                conversation_id=str(conversation_id),
                candidate_number=candidate_number,
                pandi_client_id=str(pandi_client_id),
                referral_id=result.get("referral_id"),
            )

            return {
                "status": "success",
                "message": result.get("message"),
            }
        else:
            return {
                "status": "error",
                "message": result.get("message", "סליחה, קצת בעיה בתיעוד ההעניין"),
            }

    except Exception as e:
        logger.error(f"mark_client_interested failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בתיעוד ההעניין",
            "error": str(e),
        }


async def handle_check_referral_history(
    conversation_id: UUID,
    pandi_client_id: UUID,
    candidate_number: str,
) -> dict[str, Any]:
    """Handle check_referral_history tool call.

    Session 32: Uses real referral manager to check actual history.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        candidate_number: Candidate number to check

    Returns:
        Referral history information
    """
    try:
        from .referral_manager import ReferralManager

        # Get candidate ID from candidate_number
        supabase = await get_supabase_client()
        candidate = await supabase.table("candidates").select(
            "id"
        ).eq("candidate_number", candidate_number).single()

        if not candidate:
            logger.warning(
                "candidate_not_found_for_history",
                candidate_number=candidate_number,
            )
            return {
                "status": "success",
                "message": f"לא מצאתי את המועמד {candidate_number} במערכת",
                "previous_offers": 0,
                "previous_decline": False,
            }

        # Use real referral manager
        manager = ReferralManager()
        history = await manager.check_referral_history(
            candidate_id=UUID(candidate["id"]),
            pandi_client_id=pandi_client_id,
        )

        if history.get("status") == "success":
            previous_offers = history.get("previous_offers", 0)
            previous_decline = history.get("previous_decline", False)
            hired = history.get("hired", False)

            message = f"עבור {candidate_number}: "
            if previous_offers == 0:
                message += "לא הצענו את המועמד הזה קודם. חדש לחלוטין! ✨"
            elif hired:
                message += f"כבר הצענו את המועמד הזה ו... הוא נשכר! 🎉"
            else:
                message += f"הצענו את המועמד הזה {previous_offers} פעם/ים "
                if previous_decline:
                    message += "אבל הוא דחה בעבר. אפשר לנסות שוב אם התנאים השתנו. 🤔"
                else:
                    message += "ויש סיכוי טוב שיהיה מעוניין! 👍"

            logger.info(
                "referral_history_checked",
                conversation_id=str(conversation_id),
                candidate_number=candidate_number,
                previous_offers=previous_offers,
            )

            return {
                "status": "success",
                "message": message,
                "previous_offers": previous_offers,
                "previous_decline": previous_decline,
                "hired": hired,
                "outcomes": history.get("outcomes", []),
            }
        else:
            return {
                "status": "error",
                "message": "סליחה, לא הצלחתי לבדוק את ההיסטוריה",
            }

    except Exception as e:
        logger.error(f"check_referral_history failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בבדיקת ההיסטוריה",
            "error": str(e),
        }


async def handle_request_quota_increase(
    conversation_id: UUID,
    pandi_client_id: UUID,
    additional_messages: int = 50,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """Handle request_quota_increase tool call.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        additional_messages: Number of additional messages requested
        reason: Reason for the increase

    Returns:
        Result of quota increase request
    """
    try:
        from .tools import request_quota_increase_impl

        result = await request_quota_increase_impl(
            additional_messages=additional_messages,
            reason=reason,
        )

        if result.get("status") == "success":
            logger.info(
                "quota_increase_requested",
                conversation_id=str(conversation_id),
                pandi_client_id=str(pandi_client_id),
                additional_messages=additional_messages,
            )

            return {
                "status": "success",
                "message": f"בקשתך להגדלת מכסה ב-{additional_messages} הודעות נשלחה לאדמין. אנחנו נעדכן אותך כשהיא תאושר! 📈",
            }
        else:
            return {
                "status": "error",
                "message": "סליחה, קצת בעיה בשליחת הבקשה",
            }

    except Exception as e:
        logger.error(f"request_quota_increase failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בשליחת בקשת ההגדלה",
            "error": str(e),
        }


async def handle_transfer_to_recruitment(
    conversation_id: UUID,
    pandi_client_id: UUID,
    summary: str,
) -> dict[str, Any]:
    """Handle transfer_to_recruitment tool call.

    Args:
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client
        summary: Summary of conversation to hand off

    Returns:
        Result of transfer operation
    """
    try:
        from .tools import transfer_to_recruitment_impl

        result = await transfer_to_recruitment_impl(summary)

        if result.get("status") == "success":
            # Update conversation status to transferred_to_recruitment
            supabase = await get_supabase_client()
            await supabase.table("pandi_conversations").update(
                {"status": "transferred_to_recruitment"}
            ).eq("id", str(conversation_id))

            logger.info(
                "conversation_transferred",
                conversation_id=str(conversation_id),
                pandi_client_id=str(pandi_client_id),
            )

            return {
                "status": "success",
                "message": "העברתי את הטיפול לצוות הגיוס שלנו. הם יצרו אתך קשר בקרוב! 🤝",
            }
        else:
            return {
                "status": "error",
                "message": "סליחה, קצת בעיה בהעברה לצוות",
            }

    except Exception as e:
        logger.error(f"transfer_to_recruitment failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": "סליחה, קצת בעיה בהעברה לצוות",
            "error": str(e),
        }


# Tool dispatcher
TOOL_HANDLERS = {
    "update_job_context": handle_update_job_context,
    "search_candidates": handle_search_candidates,
    "mark_client_interested": handle_mark_client_interested,
    "check_referral_history": handle_check_referral_history,
    "request_quota_increase": handle_request_quota_increase,
    "transfer_to_recruitment": handle_transfer_to_recruitment,
}


async def execute_tool(
    tool_name: str,
    tool_input: dict,
    conversation_id: UUID,
    pandi_client_id: UUID,
) -> dict[str, Any]:
    """Execute a tool by name with the given input.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        conversation_id: UUID of conversation
        pandi_client_id: UUID of Pandi client

    Returns:
        Tool execution result
    """
    handler = TOOL_HANDLERS.get(tool_name)

    if not handler:
        logger.error(f"Unknown tool: {tool_name}")
        return {"status": "error", "message": f"Unknown tool: {tool_name}"}

    try:
        # Call handler with conversation/client IDs and tool inputs
        result = await handler(
            conversation_id=conversation_id,
            pandi_client_id=pandi_client_id,
            **tool_input,
        )
        return result
    except Exception as e:
        logger.error(f"Tool execution failed: {tool_name}: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"סליחה, קצת בעיה בביצוע הפעולה",
            "error": str(e),
        }
