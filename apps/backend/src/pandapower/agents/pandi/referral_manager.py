"""
Session 32: Candidate Referral State Machine & History Tracking
Manages candidate-to-client referrals with state transitions and audit trail
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

import structlog

from pandapower.core.supabase import get_supabase_client

logger = structlog.get_logger(__name__)


class ReferralManager:
    """
    Manages candidate referrals with state machine and history tracking.

    Session 32 features:
    - Create referral records when candidate presented
    - Track referral history (state transitions)
    - Check if candidate was offered before
    - Prevent duplicate offers in same conversation
    - Handle referral status transitions
    """

    # Valid referral states (state machine)
    VALID_STATES = {
        "presented",                # Initial: candidate shown to client
        "client_interested",        # Client expressed interest
        "client_declined",          # Client declined
        "pending_full_cv_approval", # Waiting for admin to approve full CV
        "full_cv_approved",         # Admin approved, ready to send
        "full_cv_sent",             # Full CV sent to client
        "in_recruitment_process",   # Client is interviewing
        "hired",                    # Client hired the candidate
        "rejected_by_client",       # Client rejected after interviews
        "rejected_by_us",           # We withdrew (conflict, etc)
        "on_hold",                  # Paused, may resume later
    }

    # Valid state transitions (what states can follow what)
    VALID_TRANSITIONS = {
        "presented": [
            "client_interested",
            "client_declined",
            "pending_full_cv_approval",
            "on_hold",
        ],
        "client_interested": [
            "pending_full_cv_approval",
            "in_recruitment_process",
            "client_declined",
            "on_hold",
        ],
        "client_declined": [
            "on_hold",  # Can resurrect later
        ],
        "pending_full_cv_approval": [
            "full_cv_approved",
            "rejected_by_us",
        ],
        "full_cv_approved": [
            "full_cv_sent",
            "rejected_by_us",
        ],
        "full_cv_sent": [
            "in_recruitment_process",
            "client_declined",
            "on_hold",
        ],
        "in_recruitment_process": [
            "hired",
            "rejected_by_client",
        ],
        "hired": [],  # Terminal state
        "rejected_by_client": [
            "on_hold",
        ],
        "rejected_by_us": [],  # Terminal state
        "on_hold": [
            "client_interested",
            "client_declined",
            "presented",
        ],
    }

    def __init__(self):
        self._supabase = None

    async def _get_supabase(self):
        """Get Supabase client lazily."""
        if self._supabase is None:
            self._supabase = await get_supabase_client()
        return self._supabase

    async def create_referral(
        self,
        candidate_id: UUID,
        candidate_number: str,
        pandi_client_id: UUID,
        conversation_id: UUID,
        job_context: dict,
        presented_payload: dict,
        llm_match_reasoning: str,
        matched_job_id: Optional[UUID] = None,
    ) -> dict:
        """
        Create a referral record when candidate is presented to client.

        Args:
            candidate_id: UUID of candidate
            candidate_number: Public candidate number (C000XXX)
            pandi_client_id: UUID of client
            conversation_id: UUID of conversation
            job_context: Job context snapshot at time of presentation
            presented_payload: Anonymized data sent to client
            llm_match_reasoning: Why this candidate was selected
            matched_job_id: Optional internal job ID

        Returns:
            Created referral dict with ID
        """
        try:
            supabase = await get_supabase_client()

            # Check if already offered in this conversation
            _existing_res = await supabase.table("candidate_referrals").select(
                "id"
            ).eq("candidate_id", str(candidate_id)).eq(
                "conversation_id", str(conversation_id)
            ).limit(1).execute()

            if _existing_res.data:
                logger.warning(
                    "duplicate_referral_same_conversation",
                    candidate_id=str(candidate_id),
                    conversation_id=str(conversation_id),
                )
                return {
                    "status": "error",
                    "message": f"Candidate {candidate_number} already offered in this conversation",
                    "error": "duplicate_offer_same_conversation",
                    "referral_id": _existing_res.data[0]["id"],
                }

            # Create referral record
            _ref_res = await supabase.table("candidate_referrals").insert(
                {
                    "candidate_id": str(candidate_id),
                    "candidate_number": candidate_number,
                    "pandi_client_id": str(pandi_client_id),
                    "conversation_id": str(conversation_id),
                    "job_context": job_context,
                    "matched_job_id": str(matched_job_id) if matched_job_id else None,
                    "presented_payload": presented_payload,
                    "llm_match_reasoning": llm_match_reasoning,
                    "status": "presented",
                }
            ).execute()
            referral = _ref_res.data[0] if _ref_res.data else None
            if not referral:
                return {
                    "status": "error",
                    "message": "Failed to record referral",
                    "error": "insert_returned_no_row",
                }

            # Create history entry (best-effort — never fail the referral on this)
            try:
                await supabase.table("candidate_referral_history").insert(
                    {
                        "referral_id": referral["id"],
                        "from_status": None,
                        "to_status": "presented",
                        "reasoning": "Initial presentation to client",
                    }
                ).execute()
            except Exception as _he:
                logger.warning(f"referral history insert failed: {_he}")

            logger.info(
                "referral_created",
                referral_id=referral["id"],
                candidate_number=candidate_number,
                pandi_client_id=str(pandi_client_id),
            )

            return {
                "status": "success",
                "referral_id": referral["id"],
                "message": f"Recorded presentation of {candidate_number}",
            }

        except Exception as e:
            logger.error(f"create_referral failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": "Failed to record referral",
                "error": str(e),
            }

    async def check_referral_history(
        self,
        candidate_id: UUID,
        pandi_client_id: UUID,
    ) -> dict:
        """
        Check if candidate was offered to this client before.

        Args:
            candidate_id: UUID of candidate
            pandi_client_id: UUID of client

        Returns:
            History dict with previous offers, declines, and outcomes
        """
        try:
            supabase = await get_supabase_client()

            # Query all referrals for this candidate-client pair
            _ref_res = await supabase.table("candidate_referrals").select(
                "id, status, presented_at, status_updated_at"
            ).eq("candidate_id", str(candidate_id)).eq(
                "pandi_client_id", str(pandi_client_id)
            ).order("presented_at", desc=True).execute()

            referrals = _ref_res.data or []

            if not referrals:
                return {
                    "status": "success",
                    "previous_offers": 0,
                    "previous_decline": False,
                    "outcomes": [],
                }

            # Analyze history
            outcomes = [r["status"] for r in referrals]
            previous_decline = "client_declined" in outcomes or "rejected_by_client" in outcomes
            hired = "hired" in outcomes

            return {
                "status": "success",
                "previous_offers": len(referrals),
                "previous_decline": previous_decline,
                "hired": hired,
                "last_presented": referrals[0].get("presented_at"),
                "outcomes": outcomes,
            }

        except Exception as e:
            logger.error(f"check_referral_history failed: {e}", exc_info=True)
            return {
                "status": "error",
                "previous_offers": 0,
                "previous_decline": False,
                "error": str(e),
            }

    async def update_referral_status(
        self,
        referral_id: UUID,
        new_status: str,
        triggered_by_pandi_client_id: Optional[UUID] = None,
        triggered_by_user_id: Optional[UUID] = None,
        reasoning: Optional[str] = None,
        status_notes: Optional[str] = None,
    ) -> dict:
        """
        Update referral status with validation and history tracking.

        Args:
            referral_id: UUID of referral to update
            new_status: New status (must be in VALID_STATES)
            triggered_by_pandi_client_id: If client triggered (e.g., expressed interest)
            triggered_by_user_id: If admin triggered
            reasoning: Why the status changed
            status_notes: Additional notes

        Returns:
            Update result dict
        """
        try:
            if new_status not in self.VALID_STATES:
                return {
                    "status": "error",
                    "message": f"Invalid status: {new_status}",
                    "error": "invalid_status",
                }

            supabase = await get_supabase_client()

            # Get current referral
            _cur_res = await supabase.table("candidate_referrals").select(
                "status, candidate_number"
            ).eq("id", str(referral_id)).limit(1).execute()
            referral = _cur_res.data[0] if _cur_res.data else None

            if not referral:
                return {
                    "status": "error",
                    "message": "Referral not found",
                    "error": "not_found",
                }

            current_status = referral["status"]

            # Validate transition
            if new_status not in self.VALID_TRANSITIONS.get(current_status, []):
                return {
                    "status": "error",
                    "message": f"Cannot transition from {current_status} to {new_status}",
                    "error": "invalid_transition",
                    "valid_next_states": self.VALID_TRANSITIONS.get(current_status, []),
                }

            # Update referral
            await supabase.table("candidate_referrals").update(
                {
                    "status": new_status,
                    "status_updated_at": datetime.utcnow().isoformat(),
                    "status_updated_by_user_id": str(triggered_by_user_id)
                    if triggered_by_user_id
                    else None,
                    "status_notes": status_notes,
                }
            ).eq("id", str(referral_id)).execute()

            # Create history entry (best-effort)
            try:
                await supabase.table("candidate_referral_history").insert(
                    {
                        "referral_id": str(referral_id),
                        "from_status": current_status,
                        "to_status": new_status,
                        "triggered_by_pandi_client_id": str(triggered_by_pandi_client_id)
                        if triggered_by_pandi_client_id
                        else None,
                        "triggered_by_user_id": str(triggered_by_user_id)
                        if triggered_by_user_id
                        else None,
                        "reasoning": reasoning,
                    }
                ).execute()
            except Exception as _he:
                logger.warning(f"referral history insert failed: {_he}")

            logger.info(
                "referral_status_updated",
                referral_id=str(referral_id),
                from_status=current_status,
                to_status=new_status,
                candidate_number=referral["candidate_number"],
            )

            return {
                "status": "success",
                "referral_id": str(referral_id),
                "from_status": current_status,
                "to_status": new_status,
                "message": f"Status updated to {new_status}",
            }

        except Exception as e:
            logger.error(f"update_referral_status failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": "Failed to update referral status",
                "error": str(e),
            }

    async def mark_client_interested(
        self,
        candidate_number: str,
        candidate_id: UUID,
        pandi_client_id: UUID,
        conversation_id: UUID,
        interest_reason: Optional[str] = None,
        client_name: Optional[str] = None,
    ) -> dict:
        """
        Mark that client expressed interest in candidate (Session 32).

        Replaces mock implementation from Session 29.
        Session 33: Sends admin notification on interest

        Args:
            candidate_number: Public candidate number (C000XXX)
            candidate_id: UUID of candidate
            pandi_client_id: UUID of client
            conversation_id: UUID of conversation
            interest_reason: Optional reason for interest
            client_name: Client name for notification

        Returns:
            Result dict with status and referral update info
        """
        try:
            supabase = await get_supabase_client()

            # Find the referral created when this candidate was presented in this
            # conversation. If the client picks a candidate we never presented
            # (model hallucination / typo), there is nothing to mark.
            _ref_res = await supabase.table("candidate_referrals").select(
                "id, status"
            ).eq("candidate_id", str(candidate_id)).eq(
                "conversation_id", str(conversation_id)
            ).order("presented_at", desc=True).limit(1).execute()
            referral = _ref_res.data[0] if _ref_res.data else None

            if not referral:
                logger.warning(
                    "client_interested_no_referral",
                    candidate_number=candidate_number,
                    conversation_id=str(conversation_id),
                )
                return {
                    "status": "error",
                    "message": f"No referral found for {candidate_number} in this conversation",
                    "error": "no_referral",
                }

            # Already past 'presented' (e.g. interested again) — idempotent success.
            if referral.get("status") and referral["status"] != "presented":
                return {
                    "status": "success",
                    "referral_id": referral["id"],
                    "message": f"רשום שהלקוח מעוניין ב-{candidate_number}",
                }

            # Update status
            result = await self.update_referral_status(
                referral_id=UUID(referral["id"]),
                new_status="client_interested",
                triggered_by_pandi_client_id=pandi_client_id,
                reasoning=interest_reason or "Client expressed interest via Pandi",
            )

            if result["status"] == "success":
                # Session 33: Send admin notification
                try:
                    from .notification_service import NotificationService

                    notifier = NotificationService()
                    await notifier.notify_client_interested(
                        candidate_number=candidate_number,
                        client_name=client_name or "לקוח",
                    )
                except Exception as e:
                    logger.warning(f"Failed to send notification: {e}")
                    # Don't fail the referral update if notification fails

                return {
                    "status": "success",
                    "referral_id": referral["id"],
                    "message": f"צוות הגיוס שלנו יצרו קשר איתך עם {candidate_number} בקרוב 📬",
                }
            else:
                return result

        except Exception as e:
            logger.error(f"mark_client_interested failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": "Failed to record interest",
                "error": str(e),
            }

    async def get_referral_summary(self, referral_id: UUID) -> dict:
        """
        Get summary of a referral including history.

        Args:
            referral_id: UUID of referral

        Returns:
            Summary dict with current status and history
        """
        try:
            supabase = await get_supabase_client()

            # Get referral
            _ref_res = await supabase.table("candidate_referrals").select(
                "*"
            ).eq("id", str(referral_id)).limit(1).execute()
            referral = _ref_res.data[0] if _ref_res.data else None

            if not referral:
                return {"status": "error", "message": "Referral not found"}

            # Get history
            _hist_res = await supabase.table("candidate_referral_history").select(
                "from_status, to_status, created_at, reasoning"
            ).eq("referral_id", str(referral_id)).order("created_at", desc=False).execute()

            history = _hist_res.data or []

            return {
                "status": "success",
                "referral": {
                    "id": referral["id"],
                    "candidate_number": referral["candidate_number"],
                    "current_status": referral["status"],
                    "presented_at": referral["presented_at"],
                    "status_updated_at": referral["status_updated_at"],
                },
                "history": history,
            }

        except Exception as e:
            logger.error(f"get_referral_summary failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": "Failed to get referral summary",
                "error": str(e),
            }

    def get_status_description(self, status: str) -> str:
        """Get Hebrew description of referral status."""
        descriptions = {
            "presented": "הוצע ללקוח",
            "client_interested": "הלקוח מעוניין",
            "client_declined": "הלקוח דחה",
            "pending_full_cv_approval": "ממתין לאישור CV מלא",
            "full_cv_approved": "CV מלא אושר",
            "full_cv_sent": "CV מלא נשלח ללקוח",
            "in_recruitment_process": "בתהליך גיוס",
            "hired": "נשכר!",
            "rejected_by_client": "הלקוח דחה בסיבוב הראשון",
            "rejected_by_us": "הוסרנו מתהליך",
            "on_hold": "השהיה זמנית",
        }
        return descriptions.get(status, status)
