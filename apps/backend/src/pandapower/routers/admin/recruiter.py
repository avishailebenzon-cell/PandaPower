"""Recruiter dashboard endpoints for Tal and Elad."""

import logging
from typing import Any, Optional, List
from datetime import datetime
from fastapi import APIRouter, Query, Depends, HTTPException
from enum import Enum

from pydantic import BaseModel
from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/recruiter", tags=["admin", "recruiter"])


class ActionType(str, Enum):
    """Match action types."""
    ACTIVATE = "activate"              # Move to conversation state
    REJECT = "reject"                  # Reject match
    DELETE = "delete"                  # Permanently remove match (soft-delete, never re-created)
    WAIT = "wait"                      # Keep in queue (no change)
    HAND_TO_HUMAN = "hand_to_human"    # A human takes over the candidate contact
    RETURN_FROM_HUMAN = "return_from_human"  # Undo hand-off, back to the agent queue
    MARK_COMPANY_EMPLOYEE = "mark_company_employee"  # Candidate is a company employee — never contact
    MARK_COMPANY_CLIENT = "mark_company_client"      # Candidate is a company client — never contact


# States used when a candidate is flagged as do-not-contact. ALL of that
# candidate's matches are moved to the chosen state so no agent ever reaches
# out to them (a person who already works for, or is a client of, the company).
COMPANY_EMPLOYEE_STATE = "company_employee_do_not_contact"
COMPANY_CLIENT_STATE = "company_client_do_not_contact"

# Terminal state for a match the user explicitly deleted ("מחיקת התאמה").
# CRITICAL: we never DELETE the row — the matching engine's dedup keys off any
# existing (candidate_id, job_id) row regardless of state, so keeping a "deleted"
# row is exactly what guarantees the same match is never re-created (no loop).
DELETED_STATE = "deleted"
DO_NOT_CONTACT_ACTIONS = {
    ActionType.MARK_COMPANY_EMPLOYEE: COMPANY_EMPLOYEE_STATE,
    ActionType.MARK_COMPANY_CLIENT: COMPANY_CLIENT_STATE,
}


# ============================================================================
# Response Models
# ============================================================================

class CurrentWork(BaseModel):
    """The candidate/job an agent is currently working on, if any."""
    candidate_name: str
    job_title: str
    match_id: str


class StatusMetrics(BaseModel):
    """Recruiter status metrics."""
    pending_carmit: int
    carmit_approved: int
    carmit_rejected: int
    pending_tal: int
    in_conversation_tal: int
    awaiting_elad: int
    in_conversation_elad: int
    hired: int
    failed: int
    # The candidate/job each agent is actively working on right now (most
    # recently updated match in that agent's active states), or null if idle.
    carmit_current: Optional[CurrentWork] = None
    tal_current: Optional[CurrentWork] = None
    elad_current: Optional[CurrentWork] = None


class MatchInfo(BaseModel):
    """Match information for recruiter queue."""
    id: str
    candidate_name: str
    job_title: str
    company: str
    pipedrive_deal_id: Optional[int] = None  # 4-digit Pipedrive job number
    match_score: float  # 0-1
    status: str  # e.g., "sent_to_tal", "tal_conversation", etc.
    state: str  # e.g., "sent_to_tal", "tal_approved", etc.
    created_at: str  # ISO format
    last_activity: Optional[str] = None
    candidate_id: str
    job_id: str
    days_in_stage: int
    geographic_mismatch: bool = False
    geographic_mismatch_reason: Optional[str] = None
    # Favorite/starred flag — can be toggled at any stage, orthogonal to the
    # match state machine. Starred matches show an orange star and can be
    # filtered in every agent queue.
    is_starred: bool = False


class MatchDetailInfo(BaseModel):
    """Full match breakdown (reasoning, strengths, gaps, clearance) — same
    shape the agent screens use, so the frontend MatchDetailModal can render
    a Tal-queue match exactly like a Carmit-queue match."""
    id: str
    candidate_name: str
    candidate_id: Optional[str] = None
    job_id: str
    job_title: str
    company: str = ""
    phone: Optional[str] = None
    email: Optional[str] = None
    match_score: float
    match_reasoning: Optional[str] = None
    strengths: List[str] = []
    gaps: List[str] = []
    candidate_clearance: Optional[str] = None
    required_clearance: Optional[str] = None
    clearance_match: str = "unknown"
    # Geographic fit — flagged separately from the score (the candidate may
    # relocate). Surfaced as a bold red badge in every match table.
    geographic_mismatch: bool = False
    geographic_mismatch_reason: Optional[str] = None
    # What Carmit (the quality gate) concluded about this match — her decision,
    # reasoning, and per-gate breakdown. Surfaced so Tal has the full picture
    # before reaching out to the candidate.
    carmit_review: Optional[str] = None


class CandidateMatchInfo(BaseModel):
    """Complete match information for candidate decision matrix."""
    id: str
    candidate_id: str
    candidate_name: str
    job_id: str
    job_title: str
    organization_name: Optional[str] = None
    pipedrive_deal_id: Optional[int] = None  # 4-digit Pipedrive job number
    match_score: float  # 0-1
    current_state: str
    matched_by_agent_code: str
    match_reasoning: Optional[str] = None
    created_at: str
    evaluated_score_raw: Optional[int] = None
    geographic_mismatch: bool = False
    geographic_mismatch_reason: Optional[str] = None


class AllCandidateMatchesResponse(BaseModel):
    """Response with all candidate matches."""
    matches: List[CandidateMatchInfo]
    total: int
    jobs: List[dict] = []  # List of available jobs for filtering


class MatchesResponse(BaseModel):
    """Response with matches list."""
    matches: List[MatchInfo]
    total: int
    page: int
    limit: int


class MatchActionRequest(BaseModel):
    """Request to perform an action on a match."""
    action: ActionType
    notes: Optional[str] = None


class MatchActionResponse(BaseModel):
    """Response from match action."""
    success: bool
    matchId: str
    oldState: str
    newState: str
    action: str
    timestamp: str


class ConversationMessage(BaseModel):
    """A single message in a conversation."""
    id: str
    direction: str  # "inbound" or "outbound"
    text: Optional[str] = None
    createdAt: str


class ConversationInfo(BaseModel):
    """Conversation details."""
    id: str
    matchId: str
    recruiter: str
    startedAt: str
    endedAt: Optional[str] = None
    status: str
    messages: List[ConversationMessage] = []
    notes: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/status", response_model=StatusMetrics)
async def get_recruiter_status(
    supabase = Depends(get_supabase_client)
) -> StatusMetrics:
    """Get current recruiter queue status metrics.

    Returns counts of matches in each recruiter workflow stage.
    """
    try:
        # Use count="exact" — a plain select caps at PostgREST's 1000-row
        # default, which silently undercounts once a queue exceeds 1000.
        async def _count(state) -> int:
            q = supabase.table("matches").select("id", count="exact")
            q = q.in_("current_state", state) if isinstance(state, list) else q.eq("current_state", state)
            r = await q.limit(1).execute()
            return r.count or 0

        async def _current(states) -> Optional[CurrentWork]:
            """Most recently updated active match in the given states."""
            try:
                q = supabase.table("matches").select(
                    "id, updated_at, candidates(name), jobs(job_title)"
                ).in_("current_state", states).eq("is_valid", True).order(
                    "updated_at", desc=True
                ).limit(1)
                r = await q.execute()
                if not r.data:
                    return None
                row = r.data[0]
                candidate = row.get("candidates") or {}
                job = row.get("jobs") or {}
                return CurrentWork(
                    candidate_name=candidate.get("name", "ללא שם") if isinstance(candidate, dict) else "ללא שם",
                    job_title=job.get("job_title", "ללא משרה") if isinstance(job, dict) else "ללא משרה",
                    match_id=row["id"],
                )
            except Exception as e:
                logger.warning(f"Failed to fetch current work for {states}: {e}")
                return None

        pending_carmit = await _count("found")
        carmit_approved = await _count("carmit_approved")
        carmit_rejected = await _count("carmit_rejected")
        pending_tal = await _count("sent_to_tal")
        in_conversation_tal = await _count("tal_conversation")
        awaiting_elad = await _count("sent_to_elad")
        in_conversation_elad = await _count("elad_conversation")
        hired = await _count("hired")
        failed = await _count(["tal_rejected", "elad_rejected", "placement_failed"])

        carmit_current = await _current(["found"])
        tal_current = await _current(["tal_conversation", "sent_to_tal"])
        elad_current = await _current(["elad_conversation", "sent_to_elad"])

        return StatusMetrics(
            pending_carmit=pending_carmit,
            carmit_approved=carmit_approved,
            carmit_rejected=carmit_rejected,
            pending_tal=pending_tal,
            in_conversation_tal=in_conversation_tal,
            awaiting_elad=awaiting_elad,
            in_conversation_elad=in_conversation_elad,
            hired=hired,
            failed=failed,
            carmit_current=carmit_current,
            tal_current=tal_current,
            elad_current=elad_current,
        )

    except Exception as e:
        logger.error(f"Error getting recruiter status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get recruiter status")


@router.get("/matches", response_model=MatchesResponse)
async def get_recruiter_matches(
    tab: str = Query("tal-queue", description="Tab: tal-queue, tal-history, elad-queue, elad-history"),
    limit: int = Query(50, le=100),
    page: int = Query(1, ge=1),
    favorites_only: bool = Query(False, description="Only return matches starred as favorites"),
    supabase = Depends(get_supabase_client)
) -> MatchesResponse:
    """Get matches for recruiter queues.

    Args:
        tab: Queue to fetch (tal-queue, tal-history, elad-queue, elad-history)
        limit: Items per page (max 100)
        page: Page number (1-indexed)
    """
    try:
        offset = (page - 1) * limit

        # Determine which states to query based on tab
        if tab == "carmit-queue":
            states = ["found"]
        elif tab == "carmit-history":
            states = ["carmit_approved", "carmit_rejected"]
        elif tab == "tal-queue":
            states = ["sent_to_tal", "tal_conversation", "tal_handed_to_human"]
        elif tab == "tal-history":
            states = ["tal_approved", "tal_rejected"]
        elif tab == "elad-queue":
            states = ["sent_to_elad", "elad_conversation", "elad_handed_to_human"]
        elif tab == "elad-history":
            states = ["elad_approved", "hired", "placement_failed"]
        else:
            raise HTTPException(status_code=400, detail="Invalid tab parameter")

        # Query matches with related data.
        # NOTE: .isin() is the (deprecated) old name; .in_() is current. Also
        # note we filter by is_valid so Phase-4 invalidations don't show up.
        query = supabase.table("matches").select(
            "id, candidate_id, job_id, current_state, match_score, created_at, updated_at, "
            "geographic_mismatch, geographic_mismatch_reason, is_starred, "
            "candidates(name), jobs(job_title, organization_name, pipedrive_deal_id)"
        ).in_("current_state", states).eq("is_valid", True)
        if favorites_only:
            query = query.eq("is_starred", True)
        query = query.order("created_at", desc=True)

        # Get total count (separate query, awaited)
        count_query = supabase.table("matches").select("id", count="exact").in_(
            "current_state", states
        ).eq("is_valid", True)
        if favorites_only:
            count_query = count_query.eq("is_starred", True)
        total_result = await count_query.execute()
        total = total_result.count if hasattr(total_result, "count") else 0

        # Get paginated results
        result = await query.range(offset, offset + limit - 1).execute()

        # For any test matches on this page, pull their self-contained display
        # fields (contact name + job title live on the match, not on joined
        # candidate/job rows). Schema-defensive: a no-op before migration 015.
        test_map: dict = {}
        try:
            page_ids = [r["id"] for r in (result.data or [])]
            if page_ids:
                t = await supabase.table("matches").select(
                    "id, is_test, test_phone, test_meta"
                ).in_("id", page_ids).eq("is_test", True).execute()
                for tr in (t.data or []):
                    test_map[tr["id"]] = tr
        except Exception:
            test_map = {}

        matches = []
        if result.data:
            for row in result.data:
                candidate = row.get("candidates") or {}
                job = row.get("jobs") or {}
                test = test_map.get(row["id"]) or {}
                test_meta = (test.get("test_meta") or {}) if isinstance(test, dict) else {}

                # Calculate days in stage (defensive against missing/invalid timestamps)
                try:
                    created_at_dt = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                    days_in_stage = (datetime.now(created_at_dt.tzinfo) - created_at_dt).days
                except Exception:
                    days_in_stage = 0

                cand_name = candidate.get("name") if isinstance(candidate, dict) else None
                job_title = job.get("job_title") if isinstance(job, dict) else None
                # Fall back to the test row's self-contained fields.
                if not cand_name:
                    cand_name = test_meta.get("contact_name") or "Unknown"
                if not job_title:
                    job_title = test_meta.get("job_title") or "Unknown"

                match_info = MatchInfo(
                    id=row["id"],
                    candidate_name=cand_name,
                    # DB column is job_title, NOT title (matches the rest of the codebase).
                    job_title=job_title,
                    # Prefer the real job's organization; fall back to a test
                    # match's self-contained org name.
                    company=(job.get("organization_name") if isinstance(job, dict) else None)
                    or test_meta.get("organization_name", "")
                    or "",
                    pipedrive_deal_id=(job.get("pipedrive_deal_id") if isinstance(job, dict) else None),
                    match_score=row.get("match_score", 0.0),
                    status=row.get("current_state", "unknown"),
                    state=row.get("current_state", "unknown"),
                    created_at=row["created_at"],
                    last_activity=row.get("updated_at"),
                    candidate_id=row.get("candidate_id") or "",
                    job_id=row.get("job_id") or "",
                    days_in_stage=days_in_stage,
                    geographic_mismatch=bool(row.get("geographic_mismatch")),
                    geographic_mismatch_reason=row.get("geographic_mismatch_reason"),
                    is_starred=bool(row.get("is_starred")),
                )
                matches.append(match_info)

        return MatchesResponse(
            matches=matches,
            total=total,
            page=page,
            limit=limit
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting recruiter matches: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get recruiter matches")


async def _record_candidate_decline(supabase, candidate_id, job_id) -> None:
    """Append job_id to a candidate's declining_status list (idempotent).

    Powers Carmit Gate 2 (already_declined): once a candidate declines a job
    (a recruiter REJECT), that (candidate, job) pair should never be surfaced
    again. declining_status is a JSONB list of job IDs stored as strings.

    Best-effort: a failure here must not break the recruiter action. If the
    declining_status column is missing (pre-migration), we log and move on.
    """
    if not candidate_id or not job_id:
        return
    try:
        result = await supabase.table("candidates").select(
            "declining_status"
        ).eq("id", candidate_id).single().execute()
        declining = (result.data or {}).get("declining_status") or []
        if not isinstance(declining, list):
            declining = []
        existing = {str(j) for j in declining}
        if str(job_id) in existing:
            return  # already recorded
        declining.append(str(job_id))
        await supabase.table("candidates").update({
            "declining_status": declining,
        }).eq("id", candidate_id).execute()
    except Exception as e:
        logger.warning(
            f"Failed to record decline for candidate={candidate_id} "
            f"job={job_id}: {e}"
        )


async def _seed_test_phone_if_any(supabase, match_id, conversation_id) -> None:
    """If this match is a test match, copy its test_phone onto the conversation
    so the agent's WhatsApp messages reach the test number. Best-effort and
    schema-defensive (the test columns may not exist pre-migration)."""
    try:
        res = await supabase.table("matches").select(
            "is_test, test_phone"
        ).eq("id", match_id).limit(1).execute()
        row = res.data[0] if res.data else {}
        if row.get("is_test") and row.get("test_phone"):
            import re
            digits = re.sub(r"\D", "", str(row["test_phone"]))
            if digits:
                await supabase.table("recruiter_conversations").update(
                    {"candidate_phone": digits}
                ).eq("id", conversation_id).execute()
    except Exception as e:
        logger.warning(f"Could not seed test phone for match {match_id}: {e}")


async def _trigger_agent_opening(recruiter: str, conversation_id) -> None:
    """Fire the agent's opening outreach message in the background so the action
    endpoint returns immediately. Never raises."""
    import asyncio
    from uuid import UUID
    from pandapower.agents.recruiter_chat.engine import RecruiterChatEngine

    async def _run():
        try:
            await RecruiterChatEngine(recruiter).generate_opening(UUID(str(conversation_id)))
        except Exception as e:
            logger.error(f"{recruiter} opening message failed: {e}", exc_info=True)

    try:
        asyncio.create_task(_run())
    except Exception as e:
        logger.error(f"Could not schedule {recruiter} opening: {e}")


@router.post("/{match_id}/action", response_model=MatchActionResponse)
async def perform_match_action(
    match_id: str,
    body: MatchActionRequest,
    supabase = Depends(get_supabase_client)
) -> MatchActionResponse:
    """Perform an action on a match (activate, reject, wait).

    Args:
        match_id: The match ID
        body: Action request with action type and optional notes

    Returns:
        Result of the action including old/new states
    """
    try:
        # Fetch the match
        match_result = await supabase.table("matches").select(
            "id, current_state, candidate_id, job_id, candidates(name), jobs(job_title)"
        ).eq("id", match_id).execute()

        if not match_result.data:
            raise HTTPException(status_code=404, detail="Match not found")

        match = match_result.data[0]
        old_state = match.get("current_state", "unknown")

        # "Do not contact" flags (company employee / company client): these are
        # candidate-wide, not match-specific. Flagging one match moves EVERY
        # match of that candidate to the do-not-contact state and pauses any open
        # conversations, so no agent ever reaches out to a person who already
        # works for, or is a client of, the company.
        if body.action in DO_NOT_CONTACT_ACTIONS:
            target_state = DO_NOT_CONTACT_ACTIONS[body.action]
            candidate_id = match.get("candidate_id")
            if not candidate_id:
                raise HTTPException(
                    status_code=400, detail="Match has no candidate to flag"
                )

            now = datetime.utcnow().isoformat()
            await supabase.table("matches").update({
                "current_state": target_state,
                "updated_at": now,
            }).eq("candidate_id", candidate_id).execute()

            # Pause auto-reply on all of this candidate's conversations so the
            # agents stop messaging them. Best-effort — never blocks the action.
            try:
                match_ids = [
                    r["id"]
                    for r in (
                        await supabase.table("matches")
                        .select("id")
                        .eq("candidate_id", candidate_id)
                        .execute()
                    ).data or []
                ]
                if match_ids:
                    await supabase.table("recruiter_conversations").update({
                        "auto_reply_paused": True,
                    }).in_("match_id", match_ids).execute()
            except Exception as e:
                logger.warning(
                    f"Could not pause conversations for candidate {candidate_id}: {e}"
                )

            return MatchActionResponse(
                success=True,
                matchId=match_id,
                oldState=old_state,
                newState=target_state,
                action=body.action.value,
                timestamp=now,
            )

        # DELETE ("מחיקת התאמה"): mark the match deleted from ANY stage (Tal /
        # Elad / Carmit queue / found / conversation). We deliberately keep the
        # row — it stays as a tombstone so the matching engine's (candidate, job)
        # dedup never re-creates it, preventing an infinite delete/re-match loop.
        if body.action == ActionType.DELETE:
            now = datetime.utcnow().isoformat()
            if old_state != DELETED_STATE:
                update_result = await supabase.table("matches").update({
                    "current_state": DELETED_STATE,
                    "updated_at": now,
                }).eq("id", match_id).execute()
                if not update_result.data:
                    raise HTTPException(status_code=500, detail="Failed to delete match")

                # Record the decline on the candidate so Carmit's Gate 2
                # (already_declined) won't re-present this job to them later.
                await _record_candidate_decline(
                    supabase, match.get("candidate_id"), match.get("job_id")
                )

                # Pause auto-reply on any open conversation for this match so no
                # agent keeps messaging about a deleted match. Best-effort.
                try:
                    await supabase.table("recruiter_conversations").update({
                        "auto_reply_paused": True,
                    }).eq("match_id", match_id).execute()
                except Exception as e:
                    logger.warning(
                        f"Could not pause conversations for deleted match {match_id}: {e}"
                    )

            return MatchActionResponse(
                success=True,
                matchId=match_id,
                oldState=old_state,
                newState=DELETED_STATE,
                action=body.action.value,
                timestamp=now,
            )

        # Determine new state based on action
        # Detect which recruiter stage we're in. The "handed_to_human" state is
        # a per-recruiter holding state: the candidate/client is contacted by a
        # human, so the agent never reaches out. It lives in the recruiter's
        # active queue and can be toggled back to the normal waiting state.
        if old_state in ["sent_to_tal", "tal_conversation", "tal_handed_to_human"]:
            recruiter = "tal"
            if body.action == ActionType.ACTIVATE:
                new_state = "tal_conversation"
            elif body.action == ActionType.REJECT:
                new_state = "tal_rejected"
            elif body.action == ActionType.HAND_TO_HUMAN:
                new_state = "tal_handed_to_human"
            elif body.action == ActionType.RETURN_FROM_HUMAN:
                new_state = "sent_to_tal"
            else:  # WAIT
                new_state = "sent_to_tal"
        elif old_state in ["sent_to_elad", "elad_conversation", "elad_handed_to_human"]:
            recruiter = "elad"
            if body.action == ActionType.ACTIVATE:
                new_state = "elad_conversation"
            elif body.action == ActionType.REJECT:
                new_state = "elad_rejected"
            elif body.action == ActionType.HAND_TO_HUMAN:
                new_state = "elad_handed_to_human"
            elif body.action == ActionType.RETURN_FROM_HUMAN:
                new_state = "sent_to_elad"
            else:  # WAIT
                new_state = "sent_to_elad"
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot perform action on match in state: {old_state}"
            )

        # Update match state if it changed
        if new_state != old_state:
            update_result = await supabase.table("matches").update({
                "current_state": new_state,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", match_id).execute()

            if not update_result.data:
                raise HTTPException(status_code=500, detail="Failed to update match")

        # On rejection, record the decline on the candidate so Carmit's Gate 2
        # (already_declined) won't re-present this job to them later. The column
        # is a JSONB list of job IDs (stored as strings); append idempotently.
        if body.action == ActionType.REJECT and new_state != old_state:
            await _record_candidate_decline(
                supabase, match.get("candidate_id"), match.get("job_id")
            )

        # Handing to / returning from a human flips the agent's auto-reply on any
        # existing conversation: paused while a human owns the contact, resumed
        # when control returns to the agent. Best-effort — never blocks the action.
        if body.action in (ActionType.HAND_TO_HUMAN, ActionType.RETURN_FROM_HUMAN):
            try:
                await supabase.table("recruiter_conversations").update({
                    "auto_reply_paused": body.action == ActionType.HAND_TO_HUMAN,
                }).eq("match_id", match_id).eq("recruiter", recruiter).execute()
            except Exception as e:
                logger.warning(
                    f"Could not toggle auto_reply_paused for match {match_id}: {e}"
                )

        # Create conversation record if moving to conversation state, then have
        # the agent INITIATE contact (send the opening WhatsApp message) — this
        # is the real "Tal/Elad reaches out" behaviour, identical for real and
        # test matches.
        if body.action == ActionType.ACTIVATE and old_state != new_state:
            # Check if conversation already exists
            conv_result = await supabase.table("recruiter_conversations").select("id").eq(
                "match_id", match_id
            ).eq("recruiter", recruiter).execute()

            conversation_id = None
            if conv_result.data:
                conversation_id = conv_result.data[0]["id"]
            else:
                created = await supabase.table("recruiter_conversations").insert({
                    "match_id": match_id,
                    "recruiter": recruiter,
                    "status": "active",
                    "notes": body.notes or ""
                }).execute()
                if created.data:
                    conversation_id = created.data[0]["id"]

            if conversation_id:
                # For test matches, copy the destination phone onto the
                # conversation so the agent messages the test number.
                await _seed_test_phone_if_any(supabase, match_id, conversation_id)
                # Have the agent send its opening outreach message.
                await _trigger_agent_opening(recruiter, conversation_id)

        return MatchActionResponse(
            success=True,
            matchId=match_id,
            oldState=old_state,
            newState=new_state,
            action=body.action.value,
            timestamp=datetime.utcnow().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error performing match action: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to perform action")


class FavoriteRequest(BaseModel):
    """Request to set/unset a match as favorite (starred)."""
    is_starred: bool


class FavoriteResponse(BaseModel):
    """Response from toggling a match favorite."""
    success: bool
    matchId: str
    isStarred: bool


@router.post("/{match_id}/favorite", response_model=FavoriteResponse)
async def set_match_favorite(
    match_id: str,
    body: FavoriteRequest,
    supabase = Depends(get_supabase_client)
) -> FavoriteResponse:
    """Star/unstar a match as a favorite.

    Favorites are orthogonal to the match state machine — a match can be
    starred at any stage (Carmit, Tal, Elad) and surfaces with an orange star
    plus a "favorites only" filter in every agent queue.
    """
    try:
        now = datetime.utcnow().isoformat()
        update_result = await supabase.table("matches").update({
            "is_starred": body.is_starred,
            "starred_at": now if body.is_starred else None,
            "updated_at": now,
        }).eq("id", match_id).execute()

        if not update_result.data:
            raise HTTPException(status_code=404, detail="Match not found")

        return FavoriteResponse(
            success=True,
            matchId=match_id,
            isStarred=body.is_starred,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting match favorite: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to set favorite")


# ---------------------------------------------------------------------------
# Panda-Tech formatted CV (human-in-the-loop before Elad sends it to a client)
# ---------------------------------------------------------------------------
class FormattedCvInfo(BaseModel):
    matchId: str
    status: Optional[str] = None  # generated | approved | rejected | None
    path: Optional[str] = None
    previewUrl: Optional[str] = None
    generatedAt: Optional[str] = None
    approvedAt: Optional[str] = None
    approvedBy: Optional[str] = None
    rejectedReason: Optional[str] = None
    clientApproved: bool = False  # client already pressed "yes" in WhatsApp
    error: Optional[str] = None


class RejectFormattedCvRequest(BaseModel):
    reason: Optional[str] = None


async def _formatted_cv_preview_url(supabase, path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    try:
        from pandapower.integrations.supabase_storage import SupabaseStorageManager
        storage = SupabaseStorageManager(supabase)
        return await storage.create_signed_url(path, expires_in_seconds=3600)
    except Exception as e:
        logger.warning(f"formatted-cv: signed URL failed for {path}: {e}")
        return None


async def _load_formatted_cv_row(supabase, match_id: str) -> dict:
    res = await supabase.table("matches").select(
        "id, elad_stage, elad_cv_decision, formatted_cv_path, formatted_cv_status, "
        "formatted_cv_generated_at, formatted_cv_approved_at, formatted_cv_approved_by, "
        "formatted_cv_rejected_reason"
    ).eq("id", str(match_id)).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Match not found")
    return res.data[0]


@router.get("/{match_id}/formatted-cv", response_model=FormattedCvInfo)
async def get_formatted_cv(
    match_id: str,
    supabase = Depends(get_supabase_client)
) -> FormattedCvInfo:
    """Return the current Panda-Tech CV review state + a short-lived preview URL."""
    row = await _load_formatted_cv_row(supabase, match_id)
    return FormattedCvInfo(
        matchId=match_id,
        status=row.get("formatted_cv_status"),
        path=row.get("formatted_cv_path"),
        previewUrl=await _formatted_cv_preview_url(supabase, row.get("formatted_cv_path")),
        generatedAt=row.get("formatted_cv_generated_at"),
        approvedAt=row.get("formatted_cv_approved_at"),
        approvedBy=row.get("formatted_cv_approved_by"),
        rejectedReason=row.get("formatted_cv_rejected_reason"),
        clientApproved=row.get("elad_cv_decision") == "approved",
    )


@router.post("/{match_id}/formatted-cv/generate", response_model=FormattedCvInfo)
async def generate_formatted_cv_endpoint(
    match_id: str,
    force: bool = Query(False, description="Regenerate even if one already exists"),
    supabase = Depends(get_supabase_client)
) -> FormattedCvInfo:
    """(Re)render the Panda-Tech CV from extracted data and stage it for review."""
    from pandapower.agents.recruiter_chat import cv_formatter
    result = await cv_formatter.generate_formatted_cv(supabase, match_id, force=force)
    row = await _load_formatted_cv_row(supabase, match_id)
    return FormattedCvInfo(
        matchId=match_id,
        status=row.get("formatted_cv_status"),
        path=row.get("formatted_cv_path"),
        previewUrl=await _formatted_cv_preview_url(supabase, row.get("formatted_cv_path")),
        generatedAt=row.get("formatted_cv_generated_at"),
        clientApproved=row.get("elad_cv_decision") == "approved",
        error=result.get("error"),
    )


@router.post("/{match_id}/formatted-cv/approve", response_model=FormattedCvInfo)
async def approve_formatted_cv(
    match_id: str,
    supabase = Depends(get_supabase_client)
) -> FormattedCvInfo:
    """Approve the rendered CV. If the client already asked for it, send it now."""
    row = await _load_formatted_cv_row(supabase, match_id)
    if not row.get("formatted_cv_path"):
        raise HTTPException(status_code=400, detail="No generated CV to approve")

    now = datetime.utcnow().isoformat()
    reviewer = "avishai.lebenzon@gmail.com"
    await supabase.table("matches").update({
        "formatted_cv_status": "approved",
        "formatted_cv_approved_at": now,
        "formatted_cv_approved_by": reviewer,
        "formatted_cv_rejected_reason": None,
    }).eq("id", str(match_id)).execute()

    # If the client already pressed "receive full CV" and we were holding for
    # this approval, deliver it now and advance the placement stage.
    client_approved = row.get("elad_cv_decision") == "approved"
    awaiting = row.get("elad_stage") == "awaiting_cv_decision"
    sent = False
    if client_approved and awaiting:
        try:
            sent = await _deliver_approved_cv(supabase, match_id)
        except Exception as e:
            logger.error(f"formatted-cv: delivery after approve failed for {match_id}: {e}")

    refreshed = await _load_formatted_cv_row(supabase, match_id)
    return FormattedCvInfo(
        matchId=match_id,
        status=refreshed.get("formatted_cv_status"),
        path=refreshed.get("formatted_cv_path"),
        previewUrl=await _formatted_cv_preview_url(supabase, refreshed.get("formatted_cv_path")),
        approvedAt=refreshed.get("formatted_cv_approved_at"),
        approvedBy=refreshed.get("formatted_cv_approved_by"),
        clientApproved=client_approved,
        error=None if (not client_approved or sent) else "approved, but automatic send failed",
    )


@router.post("/{match_id}/formatted-cv/reject", response_model=FormattedCvInfo)
async def reject_formatted_cv(
    match_id: str,
    body: RejectFormattedCvRequest,
    supabase = Depends(get_supabase_client)
) -> FormattedCvInfo:
    """Reject the rendered CV (with an optional note) so it can be regenerated."""
    await _load_formatted_cv_row(supabase, match_id)
    await supabase.table("matches").update({
        "formatted_cv_status": "rejected",
        "formatted_cv_rejected_reason": (body.reason or None),
        "formatted_cv_approved_at": None,
        "formatted_cv_approved_by": None,
    }).eq("id", str(match_id)).execute()
    row = await _load_formatted_cv_row(supabase, match_id)
    return FormattedCvInfo(
        matchId=match_id,
        status=row.get("formatted_cv_status"),
        path=row.get("formatted_cv_path"),
        previewUrl=await _formatted_cv_preview_url(supabase, row.get("formatted_cv_path")),
        rejectedReason=row.get("formatted_cv_rejected_reason"),
        clientApproved=row.get("elad_cv_decision") == "approved",
    )


class EmailFormattedCvRequest(BaseModel):
    to: str
    subject: Optional[str] = None
    message: Optional[str] = None


class EmailFormattedCvResponse(BaseModel):
    success: bool
    error: Optional[str] = None


@router.post("/{match_id}/formatted-cv/email", response_model=EmailFormattedCvResponse)
async def email_formatted_cv(
    match_id: str,
    body: EmailFormattedCvRequest,
    supabase = Depends(get_supabase_client)
) -> EmailFormattedCvResponse:
    """Email the Panda-Tech CV PDF as an attachment (for sending outside WhatsApp).

    Only an approved CV may be emailed — the same human-in-the-loop gate as the
    WhatsApp delivery.
    """
    from pandapower.core.config import settings as _settings
    row = await _load_formatted_cv_row(supabase, match_id)
    if row.get("formatted_cv_status") != "approved" or not row.get("formatted_cv_path"):
        raise HTTPException(status_code=400, detail="CV must be generated and approved before emailing")
    if not _settings.RESEND_API_KEY:
        raise HTTPException(status_code=400, detail="Email not configured (RESEND_API_KEY missing)")

    storage_path = row["formatted_cv_path"]
    try:
        from pandapower.integrations.supabase_storage import SupabaseStorageManager
        storage = SupabaseStorageManager(supabase)
        pdf_bytes = await storage.download_file(storage_path)
    except Exception as e:
        logger.error(f"formatted-cv email: download failed for {storage_path}: {e}")
        raise HTTPException(status_code=500, detail="Could not read the CV file")

    import base64 as _b64
    filename = storage_path.rsplit("/", 1)[-1]
    subject = body.subject or "קורות חיים — PandaTech"
    html = (body.message or "מצורפים קורות החיים בפורמט פנדה-טק.").replace("\n", "<br/>")

    from pandapower.integrations.resend_client import ResendClient, ResendError
    try:
        async with ResendClient(api_key=_settings.RESEND_API_KEY) as client:
            await client.send_email(
                to=body.to,
                subject=subject,
                html=f"<div dir='rtl'>{html}</div>",
                attachments=[{
                    "filename": filename,
                    "content": _b64.b64encode(pdf_bytes).decode("ascii"),
                }],
            )
    except ResendError as e:
        logger.error(f"formatted-cv email: send failed for {match_id}: {e}")
        return EmailFormattedCvResponse(success=False, error=str(e))
    return EmailFormattedCvResponse(success=True)


async def _deliver_approved_cv(supabase, match_id: str) -> bool:
    """Send the approved Panda-Tech CV to the client over Elad's conversation,
    then advance the placement stage to cv_sent. Returns True if delivered."""
    conv_res = await supabase.table("recruiter_conversations").select(
        "id, match_id"
    ).eq("match_id", str(match_id)).eq("recruiter", "elad").order(
        "started_at", desc=True
    ).limit(1).execute()
    if not conv_res.data:
        logger.warning(f"formatted-cv: no elad conversation for match {match_id}")
        return False
    conversation_id = conv_res.data[0]["id"]

    from pandapower.agents.recruiter_chat.engine import RecruiterChatEngine
    from pandapower.agents.recruiter_chat import elad_flow
    engine = RecruiterChatEngine("elad")
    conv = {"match_id": match_id}
    ok = await elad_flow.send_cv_file(engine, conversation_id, conv)
    if ok:
        await elad_flow._set_stage(
            engine, match_id, elad_flow.STAGE_CV_SENT,
            elad_cv_decision="approved",
            elad_cv_sent_at=datetime.utcnow().isoformat(),
        )
        msg = "מצוין! שלחתי לכם כעת את קורות החיים המלאים 📄 אשמח לתאם את ההמשך מולכם."
        await engine._save_message(conversation_id, "outbound", msg, supabase, author="agent")
        await engine._send_whatsapp(conversation_id, msg, supabase)
    return ok


@router.get("/{match_id}/conversation", response_model=ConversationInfo)
async def get_match_conversation(
    match_id: str,
    supabase = Depends(get_supabase_client)
) -> ConversationInfo:
    """Get conversation details for a match.

    Args:
        match_id: The match ID

    Returns:
        Conversation info with messages
    """
    try:
        # Find conversation for this match
        conv_result = await supabase.table("recruiter_conversations").select(
            "id, match_id, recruiter, started_at, ended_at, status, notes"
        ).eq("match_id", match_id).execute()

        if not conv_result.data:
            raise HTTPException(status_code=404, detail="No conversation found for this match")

        conv = conv_result.data[0]
        conversation_id = conv["id"]

        # Fetch messages for this conversation
        messages_result = await supabase.table("recruiter_messages").select(
            "id, direction, text, created_at"
        ).eq("conversation_id", conversation_id).order("created_at", desc=False).execute()

        messages = []
        if messages_result.data:
            for msg in messages_result.data:
                messages.append(ConversationMessage(
                    id=msg["id"],
                    direction=msg["direction"],
                    text=msg.get("text"),
                    createdAt=msg["created_at"]
                ))

        return ConversationInfo(
            id=conversation_id,
            matchId=match_id,
            recruiter=conv["recruiter"],
            startedAt=conv["started_at"],
            endedAt=conv.get("ended_at"),
            status=conv.get("status", "active"),
            messages=messages,
            notes=conv.get("notes")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get conversation")


@router.get("/{match_id}/detail", response_model=MatchDetailInfo)
async def get_match_detail(
    match_id: str,
    supabase = Depends(get_supabase_client)
) -> MatchDetailInfo:
    """Get the full match breakdown as produced by the recruiting agent that
    made the match — reasoning, strengths, gaps, and clearance comparison.

    Mirrors the data the agent/Carmit screens show in MatchDetailModal so any
    recruiter queue (Tal, Elad) can display the same "why this match" view.
    """
    try:
        # Same joins as the department-matches endpoint (verified column names):
        #   candidates.clearance_level, jobs.job_security_clearance
        result = await supabase.table("matches").select(
            "id, candidate_id, job_id, current_state, match_score, match_reasoning, "
            "carmit_review_notes, carmit_blocked_reason, "
            "geographic_mismatch, geographic_mismatch_reason, "
            "candidates(id,name,email,phone,clearance_level), "
            "jobs(id,job_title,job_security_clearance)"
        ).eq("id", match_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Match not found")

        row = result.data[0]
        candidate = row.get("candidates") or {}
        job = row.get("jobs") or {}

        candidate_clearance = candidate.get("clearance_level") if isinstance(candidate, dict) else None
        required_clearance = job.get("job_security_clearance") if isinstance(job, dict) else None

        # Strengths/gaps live on the agent_matching worker's "find_match" log.
        strengths: List[str] = []
        gaps: List[str] = []
        try:
            logs_result = await supabase.table("agent_logs").select(
                "output_payload"
            ).eq("related_match_id", match_id).eq("action", "find_match").execute()
            for log in logs_result.data or []:
                payload = log.get("output_payload") or {}
                if isinstance(payload, dict):
                    s = payload.get("strengths") or []
                    g = payload.get("gaps") or []
                    if isinstance(s, list) and s and not strengths:
                        strengths = [str(x) for x in s]
                    if isinstance(g, list) and g and not gaps:
                        gaps = [str(x) for x in g]
        except Exception as log_err:
            logger.warning(f"Could not load strengths/gaps for match {match_id}: {log_err}")

        # Clearance comparison — reuse the agent-screen logic.
        try:
            from pandapower.routers.admin.recruitment_departments import _compute_clearance_match
            clearance_match = _compute_clearance_match(candidate_clearance, required_clearance)
        except Exception:
            clearance_match = "unknown"

        # What Carmit said about this match — so Tal has the full picture before
        # contacting the candidate. Build a human-readable summary from (in order
        # of richness): the match_state_history audit row (decision + per-gate
        # breakdown), then the persisted columns on the match row itself.
        carmit_review: Optional[str] = None
        try:
            hist = await supabase.table("match_state_history").select(
                "to_state, reasoning, details, created_at"
            ).eq("match_id", match_id).in_(
                "to_state", ["carmit_approved", "carmit_rejected"]
            ).order("created_at", desc=True).limit(1).execute()
            if hist.data:
                h = hist.data[0]
                approved = h.get("to_state") == "carmit_approved"
                lines = ["✅ כרמית אישרה את ההתאמה" if approved else "❌ כרמית דחתה את ההתאמה"]
                if h.get("reasoning"):
                    lines.append(str(h["reasoning"]))
                details = h.get("details") or {}
                gate_results = details.get("gate_results") if isinstance(details, dict) else None
                if isinstance(gate_results, dict):
                    gate_labels = {
                        "past_rejection": "היסטוריית דחיות",
                        "already_declined": "סירוב קודם",
                        "conflict_of_interest": "ניגוד עניינים",
                        "clearance_match": "סיווג ביטחוני",
                        "quality_threshold": "ציון איכות",
                        "relevant_skills": "כישורים רלוונטיים",
                    }
                    for key, gate in gate_results.items():
                        if not isinstance(gate, dict):
                            continue
                        mark = "✓" if gate.get("passed") else "✗"
                        label = gate_labels.get(key, key)
                        reason = gate.get("reason") or ""
                        lines.append(f"{mark} {label}: {reason}".rstrip())
                carmit_review = "\n".join(lines)
        except Exception as carmit_err:
            logger.warning(f"Could not load Carmit review for match {match_id}: {carmit_err}")

        # Fallback to the persisted columns if no audit row was available.
        if not carmit_review:
            notes = row.get("carmit_review_notes")
            blocked = row.get("carmit_blocked_reason")
            if blocked:
                carmit_review = f"❌ כרמית דחתה את ההתאמה\n{blocked}"
            elif notes:
                carmit_review = str(notes)
            elif row.get("current_state") not in ("found", None):
                # Match advanced past Carmit's gate without a recorded note.
                carmit_review = "✅ כרמית אישרה את ההתאמה (עברה את כל מבחני האיכות)"

        return MatchDetailInfo(
            id=str(row["id"]),
            candidate_name=candidate.get("name", "Unknown") if isinstance(candidate, dict) else "Unknown",
            candidate_id=str(candidate.get("id")) if isinstance(candidate, dict) and candidate.get("id") else None,
            job_id=str(row.get("job_id", "")),
            job_title=job.get("job_title", "Unknown") if isinstance(job, dict) else "Unknown",
            company="",
            phone=candidate.get("phone") if isinstance(candidate, dict) else None,
            email=candidate.get("email") if isinstance(candidate, dict) else None,
            match_score=float(row.get("match_score", 0) or 0),
            match_reasoning=row.get("match_reasoning"),
            strengths=strengths,
            gaps=gaps,
            candidate_clearance=candidate_clearance,
            required_clearance=required_clearance,
            clearance_match=clearance_match,
            geographic_mismatch=bool(row.get("geographic_mismatch")),
            geographic_mismatch_reason=row.get("geographic_mismatch_reason"),
            carmit_review=carmit_review,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting match detail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get match detail")


@router.get("/conversations/list", response_model=dict)
async def list_recruiter_conversations(
    recruiter: str = Query("tal", description="tal or elad"),
    limit: int = Query(50, le=100),
    page: int = Query(1, ge=1),
    supabase = Depends(get_supabase_client)
) -> dict:
    """List all conversations for a recruiter.

    Args:
        recruiter: tal or elad
        limit: Items per page
        page: Page number

    Returns:
        List of conversations
    """
    try:
        if recruiter not in ["tal", "elad"]:
            raise HTTPException(status_code=400, detail="Invalid recruiter")

        offset = (page - 1) * limit

        # Get total count
        total_result = await supabase.table("recruiter_conversations").select(
            "id", count="exact"
        ).eq("recruiter", recruiter).execute()
        total = total_result.count if hasattr(total_result, "count") else 0

        # Get conversations
        conv_result = await supabase.table("recruiter_conversations").select(
            "id, match_id, started_at, ended_at, status, notes, "
            "matches(id, candidate_id, job_id, candidates(name), jobs(job_title))"
        ).eq("recruiter", recruiter).order("started_at", desc=True).range(
            offset, offset + limit - 1
        ).execute()

        conversations = []
        if conv_result.data:
            for conv in conv_result.data:
                match_data = conv.get("matches") or {}
                candidate = match_data.get("candidates") or {} if isinstance(match_data, dict) else {}
                job = match_data.get("jobs") or {} if isinstance(match_data, dict) else {}

                conversations.append({
                    "id": conv["id"],
                    "matchId": conv["match_id"],
                    "candidateName": candidate.get("name", "Unknown") if isinstance(candidate, dict) else "Unknown",
                    "jobTitle": job.get("job_title", "Unknown") if isinstance(job, dict) else "Unknown",
                    "startedAt": conv["started_at"],
                    "endedAt": conv.get("ended_at"),
                    "status": conv.get("status", "active"),
                    "notes": conv.get("notes")
                })

        return {
            "recruiter": recruiter,
            "conversations": conversations,
            "total": total,
            "page": page,
            "limit": limit
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing conversations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@router.get("/all-candidate-matches", response_model=AllCandidateMatchesResponse)
async def get_all_candidate_matches(
    job_id: Optional[str] = Query(None, description="Filter by job ID"),
    agent_code: Optional[str] = Query(None, description="Filter by agent code (agent's evaluated candidates only)"),
    limit: int = Query(100, le=500),
    page: int = Query(1, ge=1),
    supabase = Depends(get_supabase_client)
) -> AllCandidateMatchesResponse:
    """Get all candidate matches with full reasoning.

    Shows all matches (not just specific states) with complete match reasoning,
    for candidate decision matrix / evaluation history.

    Args:
        job_id: Optional job ID to filter by
        agent_code: Optional agent code to show only candidates evaluated by that agent
        limit: Items per page (max 500)
        page: Page number (1-indexed)
    """
    try:
        offset = (page - 1) * limit

        # Build query for all matches (no state filter).
        # NOTE: jobs carries a denormalized organization_name column — there is
        # no matches→organizations relationship and no jobs.organization_id, so
        # we read the org name straight off jobs (the old join 500'd in prod).
        query = supabase.table("matches").select(
            "id, candidate_id, job_id, current_state, match_score, "
            "matched_by_agent_code, match_reasoning, created_at, evaluated_score_raw, "
            "geographic_mismatch, geographic_mismatch_reason, "
            "candidates(name), jobs(job_title, organization_name, pipedrive_deal_id)"
        ).eq("is_valid", True)

        # Optional job filter
        if job_id:
            query = query.eq("job_id", job_id)

        # Optional agent filter (show only candidates evaluated by this agent)
        if agent_code:
            query = query.eq("matched_by_agent_code", agent_code)

        # Get total count. NOTE: build the query first, await ONLY .execute().
        # (Awaiting the builder itself raised 'AsyncSelectRequestBuilder can't be
        # used in await' → the endpoint 500'd.)
        count_q = supabase.table("matches").select("id", count="exact").eq("is_valid", True)
        if job_id:
            count_q = count_q.eq("job_id", job_id)
        if agent_code:
            count_q = count_q.eq("matched_by_agent_code", agent_code)

        total_result = await count_q.execute()
        total = total_result.count if hasattr(total_result, "count") else 0

        # Get paginated results
        result = await query.order("created_at", desc=True).range(
            offset, offset + limit - 1
        ).execute()

        matches = []
        if result.data:
            for row in result.data:
                candidate = row.get("candidates") or {}
                job = row.get("jobs") or {}

                matches.append(CandidateMatchInfo(
                    id=row["id"],
                    candidate_id=row["candidate_id"],
                    candidate_name=candidate.get("name", "Unknown") if isinstance(candidate, dict) else "Unknown",
                    job_id=row["job_id"],
                    job_title=job.get("job_title", "Unknown") if isinstance(job, dict) else "Unknown",
                    organization_name=job.get("organization_name") if isinstance(job, dict) else None,
                    pipedrive_deal_id=job.get("pipedrive_deal_id") if isinstance(job, dict) else None,
                    match_score=row.get("match_score", 0.0),
                    current_state=row.get("current_state", "unknown"),
                    matched_by_agent_code=row.get("matched_by_agent_code", "unknown"),
                    match_reasoning=row.get("match_reasoning"),
                    created_at=row["created_at"],
                    evaluated_score_raw=row.get("evaluated_score_raw"),
                    geographic_mismatch=bool(row.get("geographic_mismatch")),
                    geographic_mismatch_reason=row.get("geographic_mismatch_reason"),
                ))

        # Get list of all jobs for filter dropdown
        jobs_result = await supabase.table("jobs").select(
            "id, job_title"
        ).order("job_title").execute()

        jobs_list = []
        if jobs_result.data:
            jobs_list = [
                {"id": j["id"], "title": j.get("job_title", "Unknown")}
                for j in jobs_result.data
            ]

        return AllCandidateMatchesResponse(
            matches=matches,
            total=total,
            jobs=jobs_list
        )

    except Exception as e:
        logger.error(f"Error getting all candidate matches: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get candidate matches")
