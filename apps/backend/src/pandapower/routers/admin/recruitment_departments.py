"""Admin routes for recruitment department management."""

import logging
from typing import Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/departments", tags=["admin", "departments"])


# Hebrew security-clearance hierarchy (low -> high).
# Verified against real values in the production jobs.job_security_clearance
# column: {'ללא', 'ללא סווג', 'רמה 1', 'רמה 3', 'רמה 1 + שוס'}.
# Higher rank = higher clearance.
_CLEARANCE_RANK = {
    # "No clearance" variants — anything goes
    "ללא": 0,
    "ללא סווג": 0,
    "ללא סיווג": 0,
    "none": 0,
    # Level 1 (basic confidential)
    "רמה 1": 1,
    "סודי": 1,
    "secret": 1,
    # Level 2
    "רמה 2": 2,
    "סודי ביותר": 2,
    "top secret": 2,
    "ts": 2,
    "טופ סיקרט": 2,
    # Level 3 (top secret + polygraph or higher)
    "רמה 3": 3,
    "רמה 1 + שוס": 3,
    "רמה 2 + שוס": 3,
    "רמה 3 + שוס": 3,
}


def _normalize_clearance(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return str(value).strip().lower()


def _clearance_rank(value: Optional[str]) -> Optional[int]:
    norm = _normalize_clearance(value)
    if norm is None:
        return None
    # Direct lookup
    if norm in _CLEARANCE_RANK:
        return _CLEARANCE_RANK[norm]
    # Fallback heuristics for free-text values we haven't enumerated
    # "ללא X" / "no X" → no requirement (rank 0)
    if norm.startswith("ללא") or norm.startswith("none"):
        return 0
    # "רמה N" or "level N" → use the number if we can parse it
    import re as _re
    m = _re.search(r"\b(\d)\b", norm)
    if m and ("רמה" in norm or "level" in norm):
        return int(m.group(1))
    return None


def _compute_clearance_match(candidate_clearance: Optional[str], required_clearance: Optional[str]) -> str:
    """Return one of: match | partial | mismatch | unknown.

    Semantics:
    - "ללא" / "none" / empty in the required field means "no clearance required" —
      every candidate is a match (regardless of their own clearance).
    - If the candidate side is unknown but the job requires real clearance: mismatch.
    - Higher candidate rank than required: match. Same rank: match. Lower: partial.
    """
    req_rank = _clearance_rank(required_clearance)

    # No real requirement (missing OR explicitly "ללא"/rank 0) — anyone is fine.
    if not required_clearance or req_rank == 0:
        return "match"

    if not candidate_clearance:
        return "mismatch"

    cand_rank = _clearance_rank(candidate_clearance)

    if cand_rank is None or req_rank is None:
        # Free-text values we don't recognise — fall back to string equality.
        if _normalize_clearance(candidate_clearance) == _normalize_clearance(required_clearance):
            return "match"
        return "partial"

    if cand_rank >= req_rank:
        return "match"
    if cand_rank > 0:
        return "partial"
    return "mismatch"


class DepartmentMatch(BaseModel):
    """Match in department view."""
    id: str
    candidateName: str
    candidateId: Optional[str] = None
    jobId: str
    jobTitle: str
    company: str
    phone: Optional[str] = None
    email: Optional[str] = None
    status: str
    matchScore: float
    dateAdded: str
    lastActivity: Optional[str] = None
    notes: Optional[str] = None
    # Match-quality detail (already produced by agent_matching.py)
    matchReasoning: Optional[str] = None
    strengths: List[str] = []
    gaps: List[str] = []
    # Security-clearance comparison
    candidateClearance: Optional[str] = None
    candidateClearanceConfidence: Optional[float] = None
    requiredClearance: Optional[str] = None
    clearanceMatch: str = "unknown"  # "match" | "partial" | "mismatch" | "unknown"


class UpdateStatusRequest(BaseModel):
    """Request to update match status."""
    status: str
    notes: Optional[str] = None


class DepartmentStats(BaseModel):
    """Statistics for a department."""
    totalMatches: int
    inProgress: int
    approved: int
    rejected: int
    approvalRate: float


class RecordConversationRequest(BaseModel):
    """Request to record conversation."""
    notes: str
    timestamp: Optional[str] = None


class AssignedJob(BaseModel):
    """Job assigned to an agent."""
    id: str
    job_title: str
    job_description: Optional[str] = None
    assigned_agent_code: str
    priority: int
    status: str
    match_count: int
    approved_count: int
    found_count: int
    organization_name: Optional[str] = None
    contact_person_name: Optional[str] = None


@router.get("/{department_code}/assigned-jobs", response_model=List[AssignedJob])
async def get_assigned_jobs(
    department_code: str,
    supabase = Depends(get_supabase_client),
) -> List[AssignedJob]:
    """Get jobs assigned to a specific department/agent.

    Args:
        department_code: Agent code (naama, alik, dganit, ofir, itai, lior, gc)
        supabase: Supabase client

    Returns:
        List of jobs assigned to the agent
    """
    try:
        # Query jobs table - fetch all jobs first, then filter for assigned ones
        # Try to get jobs with wildcard to see all available columns
        jobs_result = await supabase.table("jobs").select("*").order("priority", desc=True).execute()

        if not jobs_result.data:
            return []

        assigned_jobs = []
        for job in jobs_result.data:
            # Check both assigned_agent_code and agent_code
            agent_code = job.get("assigned_agent_code") or job.get("agent_code")

            # Only include jobs assigned to this department/agent
            if agent_code != department_code:
                continue

            # Only include open jobs
            if job.get("status") != "open":
                continue

            job_id = str(job.get("id", ""))

            # Get match counts for this job from this agent (who found them)
            matches_result = await supabase.table("matches").select(
                "id, current_state"
            ).eq("job_id", job_id).eq(
                "matched_by_agent_code", department_code
            ).eq("is_valid", True).execute()

            matches = matches_result.data or []
            match_count = len(matches)
            approved_count = sum(1 for m in matches if m["current_state"] in ["carmit_approved", "sent_to_tal", "tal_approved"])
            found_count = sum(1 for m in matches if m["current_state"] == "found")

            # Ensure priority is a valid integer (default to 5 if None or invalid)
            priority = job.get("priority")
            if priority is None:
                priority = 5
            else:
                try:
                    priority = int(priority)
                except (ValueError, TypeError):
                    priority = 5

            assigned_jobs.append(
                AssignedJob(
                    id=job_id,
                    job_title=job.get("job_title", "Unknown"),
                    job_description=job.get("job_description"),
                    assigned_agent_code=agent_code or "",
                    priority=priority,
                    status=job.get("status", "open"),
                    match_count=match_count,
                    approved_count=approved_count,
                    found_count=found_count,
                    organization_name=job.get("organization_name"),  # ארגון
                    contact_person_name=job.get("contact_person_name"),  # איש קשר
                )
            )

        return assigned_jobs

    except Exception as e:
        logger.error(f"Get assigned jobs failed for {department_code}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get assigned jobs: {str(e)}")


@router.get("/{department_code}/matches", response_model=List[DepartmentMatch])
async def get_department_matches(
    department_code: str,
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    supabase = Depends(get_supabase_client),
) -> List[DepartmentMatch]:
    """Get matches for a specific department/agent.

    Args:
        department_code: Agent code (naama, alik, dganit, ofir, itai, lior, gc)
        status: Optional status filter (found, approved, rejected, etc.)
        limit: Number of matches to return
        offset: Pagination offset
        supabase: Supabase client

    Returns:
        List of matches for the department
    """
    try:
        # Query matches table for this agent (matched_by_agent_code is the agent who found the match).
        # Filter by is_valid=True (Phase 4: only show non-invalidated matches).
        # Pull candidate clearance + job required clearance via joined relations so we can
        # show a security-clearance badge in the row without an extra round-trip.
        # NOTE: actual DB column names (verified in production Supabase):
        #   candidates.clearance_level         (not security_clearance_level)
        #   jobs.job_security_clearance        (not required_security_clearance)
        query = supabase.table("matches").select(
            "*, "
            "candidates(id,name,email,phone,clearance_level), "
            "jobs(id,job_title,job_security_clearance)"
        ).eq("matched_by_agent_code", department_code).eq(
            "is_valid", True
        )

        if status:
            query = query.eq("current_state", status)

        result = await query.range(offset, offset + limit - 1).order(
            "created_at", desc=True
        ).execute()

        if not result.data:
            return []

        # Batch-load strengths/gaps for these matches from agent_logs.output_payload.
        # The agent_matching worker writes them as JSONB on the "find_match" action.
        match_ids = [str(r.get("id")) for r in result.data if r.get("id")]
        strengths_by_match: dict[str, list[str]] = {}
        gaps_by_match: dict[str, list[str]] = {}
        if match_ids:
            try:
                logs_result = await supabase.table("agent_logs").select(
                    "related_match_id, output_payload"
                ).in_("related_match_id", match_ids).eq("action", "find_match").execute()
                for log in logs_result.data or []:
                    mid = str(log.get("related_match_id") or "")
                    payload = log.get("output_payload") or {}
                    if isinstance(payload, dict):
                        s = payload.get("strengths") or []
                        g = payload.get("gaps") or []
                        if isinstance(s, list) and s and mid not in strengths_by_match:
                            strengths_by_match[mid] = [str(x) for x in s]
                        if isinstance(g, list) and g and mid not in gaps_by_match:
                            gaps_by_match[mid] = [str(x) for x in g]
            except Exception as log_err:
                # Non-fatal — show matches without strengths/gaps if agent_logs lookup fails
                logger.warning(f"Could not load strengths/gaps from agent_logs: {log_err}")

        # Map to response model
        matches = []
        for row in result.data:
            # Extract candidate info from joined data
            candidate = row.get("candidates", {}) or {}
            candidate_name = candidate.get("name") or "Unknown"
            candidate_email = candidate.get("email")
            candidate_phone = candidate.get("phone")
            candidate_clearance = candidate.get("clearance_level")
            # confidence column doesn't exist in current schema — leave as None
            candidate_clearance_conf = None

            # Extract job info from joined data
            job = row.get("jobs", {}) or {}
            job_id = str(row.get("job_id", ""))
            job_title = job.get("job_title") or "Unknown Job"
            required_clearance = job.get("job_security_clearance")

            match_id = str(row.get("id", ""))

            matches.append(
                DepartmentMatch(
                    id=match_id,
                    candidateName=candidate_name,
                    candidateId=str(candidate.get("id")) if candidate.get("id") else None,
                    jobId=job_id,
                    jobTitle=job_title,
                    company=row.get("company", "Unknown Company"),
                    phone=candidate_phone,
                    email=candidate_email,
                    status=row.get("current_state", "unknown"),
                    matchScore=float(row.get("match_score", 0)),
                    dateAdded=row.get("created_at", ""),
                    lastActivity=row.get("updated_at"),
                    notes=row.get("notes"),
                    matchReasoning=row.get("match_reasoning"),
                    strengths=strengths_by_match.get(match_id, []),
                    gaps=gaps_by_match.get(match_id, []),
                    candidateClearance=candidate_clearance,
                    candidateClearanceConfidence=(
                        float(candidate_clearance_conf) if candidate_clearance_conf is not None else None
                    ),
                    requiredClearance=required_clearance,
                    clearanceMatch=_compute_clearance_match(candidate_clearance, required_clearance),
                )
            )

        return matches

    except Exception as e:
        logger.error(f"Get department matches failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get department matches")


@router.put(
    "/{department_code}/matches/{match_id}/status",
    response_model=DepartmentMatch,
)
async def update_match_status(
    department_code: str,
    match_id: str,
    request: UpdateStatusRequest,
    supabase = Depends(get_supabase_client),
) -> DepartmentMatch:
    """Update match status.

    Args:
        department_code: Agent code
        match_id: Match ID to update
        request: New status and notes
        supabase: Supabase client

    Returns:
        Updated match
    """
    try:
        # Update match status
        update_data = {
            "current_state": request.status,
            "updated_at": datetime.utcnow().isoformat(),
        }

        if request.notes:
            update_data["notes"] = request.notes

        result = await supabase.table("matches").update(update_data).eq("id", match_id).eq(
            "matched_by_agent_code", department_code
        ).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Match not found")

        row = result.data[0]
        return DepartmentMatch(
            id=str(row.get("id", "")),
            candidateName=row.get("candidate_name", "Unknown"),
            jobId=str(row.get("job_id", "")),
            jobTitle=row.get("job_title", "Unknown Job"),
            company=row.get("company_name", "Unknown Company"),
            phone=row.get("candidate_phone"),
            email=row.get("candidate_email"),
            status=row.get("current_state", "unknown"),
            matchScore=float(row.get("match_score", 0)),
            dateAdded=row.get("created_at", ""),
            lastActivity=row.get("last_activity_at"),
            notes=row.get("notes"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update match status failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update match status")


@router.get("/{department_code}/stats", response_model=DepartmentStats)
async def get_department_stats(
    department_code: str,
    supabase = Depends(get_supabase_client),
) -> DepartmentStats:
    """Get statistics for a department.

    Args:
        department_code: Agent code
        supabase: Supabase client

    Returns:
        Department statistics
    """
    try:
        # Get all valid matches for this department (Phase 4: only count valid matches)
        result = await supabase.table("matches").select(
            "id, current_state"
        ).eq("matched_by_agent_code", department_code).eq(
            "is_valid", True
        ).execute()

        matches = result.data or []

        total = len(matches)
        in_progress = sum(1 for m in matches if m["current_state"] in ["found", "carmit_approved"])
        approved = sum(1 for m in matches if m["current_state"] == "tal_approved")
        rejected = sum(1 for m in matches if m["current_state"] in ["carmit_rejected", "tal_rejected"])

        approval_rate = (approved / (approved + rejected)) if (approved + rejected) > 0 else 0

        return DepartmentStats(
            totalMatches=total,
            inProgress=in_progress,
            approved=approved,
            rejected=rejected,
            approvalRate=round(approval_rate * 100, 1),
        )

    except Exception as e:
        logger.error(f"Get department stats failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get department stats")


@router.post(
    "/{department_code}/matches/{match_id}/conversation",
    response_model=dict,
)
async def record_conversation(
    department_code: str,
    match_id: str,
    request: RecordConversationRequest,
    supabase = Depends(get_supabase_client),
) -> dict:
    """Record a conversation with a candidate.

    Args:
        department_code: Agent code
        match_id: Match ID
        request: Conversation notes
        supabase: Supabase client

    Returns:
        Success response
    """
    try:
        timestamp = request.timestamp or datetime.utcnow().isoformat()

        # Update match with conversation activity
        update_data = {
            "last_activity_at": timestamp,
            "conversation_notes": request.notes,
            "updated_at": timestamp,
        }

        result = await supabase.table("matches").update(update_data).eq("id", match_id).eq(
            "matched_by_agent_code", department_code
        ).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Match not found")

        return {
            "status": "success",
            "match_id": match_id,
            "timestamp": timestamp,
            "notes": request.notes,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Record conversation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to record conversation")
