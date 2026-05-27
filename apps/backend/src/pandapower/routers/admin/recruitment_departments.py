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


class DepartmentMatch(BaseModel):
    """Match in department view."""
    id: str
    candidateName: str
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
        # Query matches table for this agent (matched_by_agent_code is the agent who found the match)
        # Also filter by is_valid=True (Phase 4: only show non-invalidated matches)
        query = supabase.table("matches").select(
            "*, candidates(id,name,email,phone), jobs(id,job_title)"
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

        # Map to response model
        matches = []
        for row in result.data:
            # Extract candidate info from joined data
            candidate = row.get("candidates", {}) or {}
            candidate_name = candidate.get("name") or "Unknown"
            candidate_email = candidate.get("email")
            candidate_phone = candidate.get("phone")

            # Extract job info from joined data
            job = row.get("jobs", {}) or {}
            job_id = str(row.get("job_id", ""))
            job_title = job.get("job_title") or "Unknown Job"

            matches.append(
                DepartmentMatch(
                    id=str(row.get("id", "")),
                    candidateName=candidate_name,
                    jobId=job_id,
                    jobTitle=job_title,
                    company=row.get("company", "Unknown Company"),  # May not have company info
                    phone=candidate_phone,
                    email=candidate_email,
                    status=row.get("current_state", "unknown"),
                    matchScore=float(row.get("match_score", 0)),
                    dateAdded=row.get("created_at", ""),
                    lastActivity=row.get("updated_at"),
                    notes=row.get("notes"),
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
