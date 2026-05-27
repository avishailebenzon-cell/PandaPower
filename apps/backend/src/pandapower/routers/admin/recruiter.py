"""Recruiter dashboard endpoints for Tal and Elad."""

import logging
from typing import Any, Optional, List
from datetime import datetime
from fastapi import APIRouter, Query, Depends, HTTPException

from pydantic import BaseModel
from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/recruiter", tags=["admin", "recruiter"])


# ============================================================================
# Response Models
# ============================================================================

class StatusMetrics(BaseModel):
    """Recruiter status metrics."""
    pending_tal: int
    in_conversation_tal: int
    awaiting_elad: int
    in_conversation_elad: int
    hired: int
    failed: int


class MatchInfo(BaseModel):
    """Match information for recruiter queue."""
    id: str
    candidate_name: str
    job_title: str
    company: str
    match_score: float  # 0-1
    status: str  # e.g., "sent_to_tal", "tal_conversation", etc.
    state: str  # e.g., "sent_to_tal", "tal_approved", etc.
    created_at: str  # ISO format
    last_activity: Optional[str] = None
    candidate_id: str
    job_id: str
    days_in_stage: int


class MatchesResponse(BaseModel):
    """Response with matches list."""
    matches: List[MatchInfo]
    total: int
    page: int
    limit: int


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
        # All .execute() calls below MUST be awaited — the async Supabase
        # client returns a coroutine and forgetting `await` causes `.data`
        # to be missing and the whole endpoint to 500.

        # Get Tal-related matches
        tal_pending_result = await supabase.table("matches").select("id").eq(
            "current_state", "sent_to_tal"
        ).execute()
        pending_tal = len(tal_pending_result.data) if tal_pending_result.data else 0

        tal_conversation_result = await supabase.table("matches").select("id").eq(
            "current_state", "tal_conversation"
        ).execute()
        in_conversation_tal = len(tal_conversation_result.data) if tal_conversation_result.data else 0

        # Get Elad-related matches
        awaiting_elad_result = await supabase.table("matches").select("id").eq(
            "current_state", "sent_to_elad"
        ).execute()
        awaiting_elad = len(awaiting_elad_result.data) if awaiting_elad_result.data else 0

        elad_conversation_result = await supabase.table("matches").select("id").eq(
            "current_state", "elad_conversation"
        ).execute()
        in_conversation_elad = len(elad_conversation_result.data) if elad_conversation_result.data else 0

        # Final outcomes
        hired_result = await supabase.table("matches").select("id").eq(
            "current_state", "hired"
        ).execute()
        hired = len(hired_result.data) if hired_result.data else 0

        failed_result = await supabase.table("matches").select("id").in_(
            "current_state", ["tal_rejected", "elad_rejected", "placement_failed"]
        ).execute()
        failed = len(failed_result.data) if failed_result.data else 0

        return StatusMetrics(
            pending_tal=pending_tal,
            in_conversation_tal=in_conversation_tal,
            awaiting_elad=awaiting_elad,
            in_conversation_elad=in_conversation_elad,
            hired=hired,
            failed=failed
        )

    except Exception as e:
        logger.error(f"Error getting recruiter status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get recruiter status")


@router.get("/matches", response_model=MatchesResponse)
async def get_recruiter_matches(
    tab: str = Query("tal-queue", description="Tab: tal-queue, tal-history, elad-queue, elad-history"),
    limit: int = Query(50, le=100),
    page: int = Query(1, ge=1),
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
        if tab == "tal-queue":
            states = ["sent_to_tal", "tal_conversation"]
        elif tab == "tal-history":
            states = ["tal_approved", "tal_rejected"]
        elif tab == "elad-queue":
            states = ["sent_to_elad", "elad_conversation"]
        elif tab == "elad-history":
            states = ["elad_approved", "hired", "placement_failed"]
        else:
            raise HTTPException(status_code=400, detail="Invalid tab parameter")

        # Query matches with related data.
        # NOTE: .isin() is the (deprecated) old name; .in_() is current. Also
        # note we filter by is_valid so Phase-4 invalidations don't show up.
        query = supabase.table("matches").select(
            "id, candidate_id, job_id, current_state, match_score, created_at, updated_at, "
            "candidates(name), jobs(job_title)"
        ).in_("current_state", states).eq("is_valid", True).order("created_at", desc=True)

        # Get total count (separate query, awaited)
        total_result = await supabase.table("matches").select("id", count="exact").in_(
            "current_state", states
        ).eq("is_valid", True).execute()
        total = total_result.count if hasattr(total_result, "count") else 0

        # Get paginated results
        result = await query.range(offset, offset + limit - 1).execute()

        matches = []
        if result.data:
            for row in result.data:
                candidate = row.get("candidates") or {}
                job = row.get("jobs") or {}

                # Calculate days in stage (defensive against missing/invalid timestamps)
                try:
                    created_at_dt = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                    days_in_stage = (datetime.now(created_at_dt.tzinfo) - created_at_dt).days
                except Exception:
                    days_in_stage = 0

                match_info = MatchInfo(
                    id=row["id"],
                    candidate_name=candidate.get("name", "Unknown") if isinstance(candidate, dict) else "Unknown",
                    # DB column is job_title, NOT title (matches the rest of the codebase).
                    job_title=job.get("job_title", "Unknown") if isinstance(job, dict) else "Unknown",
                    # Organization name isn't joinable in production schema (see
                    # recruitment_departments.py for the same caveat); leave blank
                    # rather than ship fake data.
                    company="",
                    match_score=row.get("match_score", 0.0),
                    status=row.get("current_state", "unknown"),
                    state=row.get("current_state", "unknown"),
                    created_at=row["created_at"],
                    last_activity=row.get("updated_at"),
                    candidate_id=row["candidate_id"],
                    job_id=row["job_id"],
                    days_in_stage=days_in_stage,
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
