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


# Hebrew security-clearance hierarchy.
# Verified against real values in the production jobs.job_security_clearance
# column: {'ללא', 'ללא סווג', 'רמה 1', 'רמה 3', 'רמה 1 + שוס'}.
#
# IMPORTANT: in the Israeli scheme רמה 1 is the HIGHEST clearance and רמה 3 the
# lowest. We store an internal rank where a HIGHER number = HIGHER clearance
# (so all comparisons can use cand_rank >= req_rank), which means the numbered
# level is INVERTED: רמה 1 → 3, רמה 2 → 2, רמה 3 → 1. "+ שוס" is an extra
# vetting layer that sits strictly above every plain numbered level.
_CLEARANCE_RANK = {
    # "No clearance" variants — anything goes
    "ללא": 0,
    "ללא סווג": 0,
    "ללא סיווג": 0,
    "none": 0,
    # Numbered levels (inverted: רמה 1 is highest)
    "רמה 3": 1,
    "רמה 2": 2,
    "רמה 1": 3,
    # "+ שוס" tier — strictly above all plain levels, same inverted order within
    "רמה 3 + שוס": 4,
    "רמה 2 + שוס": 5,
    "רמה 1 + שוס": 6,
    # English / colloquial equivalents (best-effort, rarely seen in real data)
    "סודי": 1,
    "secret": 1,
    "סודי ביותר": 2,
    "top secret": 2,
    "ts": 2,
    "טופ סיקרט": 2,
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
    # "רמה N" / "level N" / a bare "N" → invert the number (רמה 1 is the
    # highest) and add a bonus for the "+ שוס" tier so it ranks above plain
    # levels. NOTE: candidate clearances are often stored as a bare digit
    # ("2", "3") while jobs use "רמה 1" — both must rank identically.
    import re as _re
    m = _re.search(r"\b(\d)\b", norm)
    if m and ("רמה" in norm or "level" in norm or norm == m.group(1)):
        n = int(m.group(1))
        base = max(0, 4 - n) if 1 <= n <= 3 else 0
        if base > 0 and "שוס" in norm:
            base += 3
        return base
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


class EvaluatedCandidate(BaseModel):
    """Candidate evaluated against a job (pass or fail)."""
    id: str  # match record ID
    candidateId: str
    candidateName: str
    candidateEmail: Optional[str] = None
    score: int  # 0-100 absolute score
    isPassing: bool  # True if ≥70, False if <70
    reasoning: Optional[str] = None
    strengths: List[str] = []
    gaps: List[str] = []
    evaluatedAt: str  # ISO timestamp
    evaluatedByAgent: str  # agent code


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
    # When the job first arrived in the system (jobs.created_at).
    created_at: Optional[str] = None
    # Best proxy we have for "assigned to this agent at" — no separate audit log,
    # so we surface jobs.updated_at (changes when assigned_agent_code is set/changed).
    assigned_at: Optional[str] = None
    # Deadline from Pipedrive sync (jobs.deadline). Often null — UI hides if null.
    deadline: Optional[str] = None
    # Pipedrive numeric IDs — useful as fallback labels when names aren't synced.
    pipedrive_org_id: Optional[int] = None
    pipedrive_person_id: Optional[int] = None


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

        # First pass: keep only this department's open jobs (not expired).
        # We do this so we can batch-load contact names by pipedrive_person_id below
        # (avoids an N+1 lookup per job).
        relevant_jobs = []
        today = datetime.now().date()
        for job in jobs_result.data:
            agent_code = job.get("assigned_agent_code") or job.get("agent_code")
            if agent_code != department_code:
                continue
            if job.get("status") != "open":
                continue
            # Skip jobs with passed deadlines
            deadline_str = job.get("deadline")
            if deadline_str:
                try:
                    deadline_date = datetime.fromisoformat(deadline_str.replace('Z', '+00:00')).date()
                    if deadline_date < today:
                        # Job deadline has passed — skip it (don't show to agent)
                        continue
                except (ValueError, AttributeError):
                    # Invalid deadline format — include job anyway (let user deal with it)
                    pass
            relevant_jobs.append(job)

        # Batch-resolve contact names: contacts.pipedrive_person_id BIGINT -> full_name.
        # (jobs.person_id holds the Pipedrive numeric id, not contacts.id UUID.)
        contact_name_by_pid: dict[int, str] = {}
        person_ids = sorted({int(j["person_id"]) for j in relevant_jobs if j.get("person_id")})
        if person_ids:
            try:
                contacts_resp = await supabase.table("contacts").select(
                    "pipedrive_person_id, full_name"
                ).in_("pipedrive_person_id", person_ids).execute()
                for c in contacts_resp.data or []:
                    pid = c.get("pipedrive_person_id")
                    if pid is not None and c.get("full_name"):
                        contact_name_by_pid[int(pid)] = c["full_name"]
            except Exception as ce:
                logger.warning(f"Failed to batch-resolve contact names: {ce}")

        assigned_jobs = []
        for job in relevant_jobs:
            agent_code = job.get("assigned_agent_code") or job.get("agent_code")
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

            # Resolve organization name: prefer denormalized column, else show
            # the Pipedrive ID as a recognisable fallback ("ארגון #1880"). We
            # can't join organizations.pipedrive_org_id because the column doesn't
            # exist in the deployed schema.
            org_name = job.get("organization_name")
            org_pid = job.get("org_id")
            if not org_name and org_pid:
                org_name = f"ארגון #{org_pid}"

            # Resolve contact name: prefer denormalized column, else look up
            # the batched dict by pipedrive person id.
            person_pid_raw = job.get("person_id")
            person_pid = int(person_pid_raw) if person_pid_raw is not None else None
            contact_name = job.get("contact_person_name")
            if not contact_name and person_pid is not None:
                contact_name = contact_name_by_pid.get(person_pid)

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
                    organization_name=org_name,  # ארגון
                    contact_person_name=contact_name,  # איש קשר
                    created_at=job.get("created_at"),  # תאריך הגעת המשרה
                    assigned_at=job.get("updated_at"),  # best proxy for date-of-assignment
                    deadline=job.get("deadline"),  # דדליין (Pipedrive)
                    pipedrive_org_id=int(org_pid) if org_pid is not None else None,
                    pipedrive_person_id=person_pid,
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


@router.get(
    "/{department_code}/jobs/{job_id}/evaluated-candidates",
    response_model=List[EvaluatedCandidate],
)
async def get_evaluated_candidates(
    department_code: str,
    job_id: str,
    supabase = Depends(get_supabase_client),
) -> List[EvaluatedCandidate]:
    """Get all candidates evaluated against a specific job.

    Returns ALL evaluations (both passing ≥70 and failing <70) with reasoning.

    Args:
        department_code: Agent code who performed evaluations
        job_id: Job ID to get evaluations for
        supabase: Supabase client

    Returns:
        List of evaluated candidates sorted by: is_passing DESC, score DESC
    """
    try:
        # Get all matches for this job+agent (all evaluations)
        result = await supabase.table("matches").select(
            "*, "
            "candidates(id,name,email)"
        ).eq("job_id", job_id).eq(
            "matched_by_agent_code", department_code
        ).order("is_passing", desc=True).order(
            "evaluated_score_raw", desc=True
        ).execute()

        matches = result.data or []

        if not matches:
            return []

        # Batch-load strengths/gaps from agent_logs
        match_ids = [str(m["id"]) for m in matches]
        strengths_by_match = {}
        gaps_by_match = {}

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
                logger.warning(f"Could not load strengths/gaps from agent_logs: {log_err}")

        # Map to response model
        candidates = []
        for row in matches:
            candidate = row.get("candidates", {}) or {}
            match_id = str(row.get("id", ""))

            # Default to 0 if evaluated_score_raw is NULL (for old matches pre-migration)
            score = row.get("evaluated_score_raw") or 0
            if score == 0 and row.get("match_score"):
                # Fallback: convert normalized score to 0-100
                score = round(float(row["match_score"]) * 100)

            candidates.append(
                EvaluatedCandidate(
                    id=match_id,
                    candidateId=str(candidate.get("id", "")),
                    candidateName=candidate.get("name") or "Unknown",
                    candidateEmail=candidate.get("email"),
                    score=score,
                    isPassing=row.get("is_passing", False),
                    reasoning=row.get("match_reasoning"),
                    strengths=strengths_by_match.get(match_id, []),
                    gaps=gaps_by_match.get(match_id, []),
                    evaluatedAt=row.get("created_at", ""),
                    evaluatedByAgent=department_code,
                )
            )

        return candidates

    except Exception as e:
        logger.error(f"Get evaluated candidates failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get evaluated candidates")


@router.delete("/{department_code}/jobs/{job_id}")
async def delete_job(
    department_code: str,
    job_id: str,
    supabase = Depends(get_supabase_client),
) -> dict:
    """Delete a job from the database.

    This is for cleanup of expired or irrelevant jobs.

    Args:
        department_code: Agent code (for audit trail)
        job_id: Job ID to delete
        supabase: Supabase client

    Returns:
        Success response
    """
    try:
        # Verify job exists and is assigned to this agent
        job_result = await supabase.table("jobs").select("id, assigned_agent_code").eq("id", job_id).execute()

        if not job_result.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = job_result.data[0]
        assigned_agent = job.get("assigned_agent_code")
        if assigned_agent != department_code:
            raise HTTPException(status_code=403, detail="Not authorized to delete this job")

        # Delete job (cascades handled by database constraints)
        result = await supabase.table("jobs").delete().eq("id", job_id).execute()

        logger.info(f"Job {job_id} deleted by agent {department_code}")

        return {
            "status": "success",
            "message": f"Job {job_id} deleted",
            "job_id": job_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete job failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete job")
