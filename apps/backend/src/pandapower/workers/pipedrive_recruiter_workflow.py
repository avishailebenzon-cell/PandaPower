"""Phase 6.4: Recruiter Workflow Integration with Pipedrive."""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from pandapower.integrations.pipedrive import PipedriveClient

logger = logging.getLogger(__name__)


class RecruiterWorkflowManager:
    """Manages Tal/Elad recruiter workflow with Pipedrive activities."""

    # Deal stage IDs (these would be configured per Pipedrive setup)
    DEAL_STAGES = {
        "carmit_approved": "1",  # Initial assessment
        "sent_to_tal": "2",  # With Tal for review
        "tal_conversation": "3",  # Tal actively discussing
        "tal_accepted": "4",  # Tal approved, ready for Elad
        "sent_to_elad": "5",  # With Elad for final placement
        "hired": "6",  # Successfully hired
        "rejected_tal": "7",  # Rejected by Tal
        "rejected_elad": "8",  # Rejected by Elad
        "placement_failed": "9",  # Failed to place
    }

    def __init__(self, pipedrive_client: PipedriveClient, supabase_client: Any):
        """Initialize recruiter workflow manager.

        Args:
            pipedrive_client: PipedriveClient instance
            supabase_client: Supabase client for data storage
        """
        self.pipedrive_client = pipedrive_client
        self.supabase_client = supabase_client

    async def send_match_to_recruiter(
        self,
        match_id: str,
        recruiter_name: str,
        recruiter_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send a Carmit-approved match to recruiter (Tal or Elad).

        Args:
            match_id: PandaPower match ID
            recruiter_name: 'tal' or 'elad'
            recruiter_id: Pipedrive user ID if known

        Returns:
            Activity creation result
        """
        try:
            # Get match details from database
            match_data = self.supabase_client.table("matches").select(
                "id, candidate_id, job_id, pipedrive_deal_id"
            ).eq("id", match_id).single().execute()

            if not match_data.data:
                return {"success": False, "error": "Match not found"}

            match = match_data.data
            deal_id = match.get("pipedrive_deal_id")

            if not deal_id:
                return {"success": False, "error": "Match not linked to Pipedrive deal"}

            # Update deal stage
            stage_key = f"sent_to_{recruiter_name}"
            stage_id = self.DEAL_STAGES.get(stage_key, "2")

            # Create activity in Pipedrive
            activity_subject = f"Match reviewed by {recruiter_name.upper()}"
            activity_result = await self._create_activity(
                deal_id,
                activity_subject,
                f"Match sent to {recruiter_name.upper()} for review",
                "call",
                recruiter_id,
            )

            # Update match state in PandaPower
            await self.supabase_client.table("matches").update({
                "current_state": stage_key,
            }).eq("id", match_id).execute()

            # Store state transition in audit trail
            await self._record_state_transition(
                match_id,
                "carmit_approved",
                stage_key,
                {"recruiter": recruiter_name, "activity_id": activity_result.get("id")},
            )

            return {
                "success": True,
                "match_id": match_id,
                "stage": stage_key,
                "activity_id": activity_result.get("id"),
            }

        except Exception as e:
            logger.error(f"Error sending match to recruiter: {e}")
            return {"success": False, "error": str(e)}

    async def record_recruiter_conversation(
        self,
        match_id: str,
        recruiter_name: str,
        conversation_summary: str,
        conversation_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record that a recruiter has started/continued conversation with candidate.

        Args:
            match_id: PandaPower match ID
            recruiter_name: 'tal' or 'elad'
            conversation_summary: Summary of conversation
            conversation_date: Date of conversation (ISO format)

        Returns:
            Activity creation result
        """
        try:
            # Get match and deal ID
            match_data = self.supabase_client.table("matches").select(
                "id, pipedrive_deal_id"
            ).eq("id", match_id).single().execute()

            if not match_data.data:
                return {"success": False, "error": "Match not found"}

            deal_id = match_data.data.get("pipedrive_deal_id")

            # Create activity for conversation
            activity_result = await self._create_activity(
                deal_id,
                "Conversation with candidate",
                conversation_summary,
                "meeting",
                due_date=conversation_date,
            )

            # Update match state to conversation state
            await self.supabase_client.table("matches").update({
                "current_state": f"{recruiter_name}_conversation",
            }).eq("id", match_id).execute()

            # Record conversation in history
            await self._record_state_transition(
                match_id,
                f"sent_to_{recruiter_name}",
                f"{recruiter_name}_conversation",
                {
                    "recruiter": recruiter_name,
                    "conversation_summary": conversation_summary,
                    "activity_id": activity_result.get("id"),
                },
            )

            return {
                "success": True,
                "match_id": match_id,
                "state": f"{recruiter_name}_conversation",
                "activity_id": activity_result.get("id"),
            }

        except Exception as e:
            logger.error(f"Error recording recruiter conversation: {e}")
            return {"success": False, "error": str(e)}

    async def record_recruiter_decision(
        self,
        match_id: str,
        recruiter_name: str,
        decision: str,  # 'accepted' or 'rejected'
        decision_reason: str,
    ) -> dict[str, Any]:
        """Record a recruiter's decision on a candidate.

        Args:
            match_id: PandaPower match ID
            recruiter_name: 'tal' or 'elad'
            decision: 'accepted' or 'rejected'
            decision_reason: Explanation for decision

        Returns:
            Update result
        """
        try:
            # Validate decision
            if decision not in ["accepted", "rejected"]:
                return {"success": False, "error": f"Invalid decision: {decision}"}

            # Get match and deal ID
            match_data = self.supabase_client.table("matches").select(
                "id, pipedrive_deal_id"
            ).eq("id", match_id).single().execute()

            if not match_data.data:
                return {"success": False, "error": "Match not found"}

            deal_id = match_data.data.get("pipedrive_deal_id")

            # Determine new state
            if decision == "accepted":
                new_state = "sent_to_elad" if recruiter_name == "tal" else "hired"
                activity_subject = f"{recruiter_name.upper()} accepted"
            else:
                new_state = f"{recruiter_name}_rejected"
                activity_subject = f"Rejected by {recruiter_name.upper()}"

            # Create activity in Pipedrive
            activity_result = await self._create_activity(
                deal_id,
                activity_subject,
                decision_reason,
                "email",
            )

            # Write note to deal
            note_text = f"{recruiter_name.upper()} Decision: {decision}\n\nReason: {decision_reason}"
            await self.pipedrive_client.write_note_to_deal(deal_id, note_text)

            # Update match state
            await self.supabase_client.table("matches").update({
                "current_state": new_state,
            }).eq("id", match_id).execute()

            # Record state transition
            await self._record_state_transition(
                match_id,
                f"{recruiter_name}_conversation",
                new_state,
                {
                    "recruiter": recruiter_name,
                    "decision": decision,
                    "reason": decision_reason,
                    "activity_id": activity_result.get("id"),
                },
            )

            return {
                "success": True,
                "match_id": match_id,
                "decision": decision,
                "new_state": new_state,
                "activity_id": activity_result.get("id"),
            }

        except Exception as e:
            logger.error(f"Error recording recruiter decision: {e}")
            return {"success": False, "error": str(e)}

    async def record_placement_outcome(
        self,
        match_id: str,
        outcome: str,  # 'hired' or 'placement_failed'
        notes: str,
    ) -> dict[str, Any]:
        """Record final placement outcome.

        Args:
            match_id: PandaPower match ID
            outcome: 'hired' or 'placement_failed'
            notes: Final notes

        Returns:
            Update result
        """
        try:
            if outcome not in ["hired", "placement_failed"]:
                return {"success": False, "error": f"Invalid outcome: {outcome}"}

            # Get match and deal ID
            match_data = self.supabase_client.table("matches").select(
                "id, pipedrive_deal_id, candidate_id"
            ).eq("id", match_id).single().execute()

            if not match_data.data:
                return {"success": False, "error": "Match not found"}

            match = match_data.data
            deal_id = match.get("pipedrive_deal_id")
            candidate_id = match.get("candidate_id")

            # Create final activity
            if outcome == "hired":
                activity_subject = "Placement successful - Candidate hired"
                deal_won = True
            else:
                activity_subject = "Placement failed - Candidate not hired"
                deal_won = False

            activity_result = await self._create_activity(
                deal_id,
                activity_subject,
                notes,
                "email",
            )

            # Update deal status in Pipedrive if possible
            # (This would require updating deal pipeline, which varies per setup)

            # Update match in PandaPower
            await self.supabase_client.table("matches").update({
                "current_state": outcome,
                "placement_outcome": outcome,
                "placement_notes": notes,
            }).eq("id", match_id).execute()

            # Update candidate status if hired
            if outcome == "hired":
                await self.supabase_client.table("candidates").update({
                    "placement_status": "hired",
                }).eq("id", candidate_id).execute()

            # Record final state transition
            await self._record_state_transition(
                match_id,
                "sent_to_elad",
                outcome,
                {
                    "outcome": outcome,
                    "notes": notes,
                    "activity_id": activity_result.get("id"),
                },
            )

            return {
                "success": True,
                "match_id": match_id,
                "outcome": outcome,
                "activity_id": activity_result.get("id"),
            }

        except Exception as e:
            logger.error(f"Error recording placement outcome: {e}")
            return {"success": False, "error": str(e)}

    async def _create_activity(
        self,
        deal_id: str,
        subject: str,
        description: str,
        activity_type: str = "note",
        user_id: Optional[str] = None,
        due_date: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create an activity in Pipedrive for audit trail.

        Args:
            deal_id: Pipedrive deal ID
            subject: Activity subject
            description: Activity description
            activity_type: Type of activity ('call', 'email', 'meeting', 'note')
            user_id: Pipedrive user ID
            due_date: Due date for activity

        Returns:
            Created activity object
        """
        try:
            payload = {
                "subject": subject,
                "type": activity_type,
                "deal_id": deal_id,
                "done": 1,  # Mark as completed
            }

            if description:
                payload["note"] = description
            if user_id:
                payload["user_id"] = user_id
            if due_date:
                payload["due_date"] = due_date

            response = await self.pipedrive_client._make_request(
                "POST", "/v1/activities", body=payload
            )

            if response.get("success"):
                return response.get("data", {})
            else:
                logger.warning(f"Failed to create activity: {response.get('error')}")
                return {}

        except Exception as e:
            logger.error(f"Error creating Pipedrive activity: {e}")
            return {}

    async def _record_state_transition(
        self,
        match_id: str,
        from_state: str,
        to_state: str,
        details: dict = None,
    ) -> None:
        """Record a state transition in match_state_history.

        Args:
            match_id: PandaPower match ID
            from_state: Previous state
            to_state: New state
            details: Additional context
        """
        try:
            if details is None:
                details = {}

            self.supabase_client.table("match_state_history").insert({
                "match_id": match_id,
                "from_state": from_state,
                "to_state": to_state,
                "details": json.dumps(details),
                "created_at": datetime.now().isoformat(),
            }).execute()

        except Exception as e:
            logger.error(f"Error recording state transition: {e}")
