import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Response models
class GateResult(BaseModel):
    passed: bool
    reason: Optional[str] = None


class MatchReviewResult(BaseModel):
    match_id: str
    new_state: str
    decision: str  # 'approved' or 'rejected'
    gate_results: dict[str, GateResult]
    reasoning: str
    timestamp: str


class JobRoutingResult(BaseModel):
    job_id: str
    assigned_agent_code: str
    assigned_agent_name: str
    confidence: float
    reasoning: str
    timestamp: str


class PendingMatchResponse(BaseModel):
    id: str
    candidate_name: str
    job_title: str
    match_score: float
    agent_code: str
    created_at: str


class RoutingDecision(BaseModel):
    job_id: str
    assigned_agent_code: str
    assigned_agent_name: str
    confidence: float
    reasoning: str
    timestamp: str


class ReviewHistoryEntry(BaseModel):
    match_id: str
    decision: str  # 'approved' or 'rejected'
    reasoning: str
    timestamp: str


class CarmitDecision(BaseModel):
    """Carmit's decision on a match with all gate results and reasoning."""
    match_id: str
    candidate_name: str
    job_title: str
    decision: str  # 'approved' or 'rejected'
    match_score: float
    gate_results: dict[str, GateResult]
    reasoning: str
    decided_at: str
    candidate_id: Optional[str] = None
    job_id: Optional[str] = None


# Request models
class OverrideRoutingRequest(BaseModel):
    override_agent_code: Optional[str] = None


class OverrideReviewRequest(BaseModel):
    force_approve: Optional[bool] = None
    override_reason: Optional[str] = None


# Create router
router = APIRouter(prefix="/admin/carmit", tags=["admin", "carmit"])


# Import Supabase client for use in endpoints
from pandapower.core.supabase import get_supabase_client


def get_claude():
    """Get Claude client from dependency injection."""
    from pandapower.integrations.claude_api import AnthropicClient
    from pandapower.core.config import get_settings

    settings = get_settings()
    return AnthropicClient(settings.ANTHROPIC_API_KEY)


def get_pipedrive():
    """Get Pipedrive client from dependency injection."""
    from pandapower.integrations.pipedrive import PipedriveClient
    from pandapower.core.config import get_settings

    settings = get_settings()
    return PipedriveClient(settings.PIPEDRIVE_API_TOKEN, settings.PIPEDRIVE_API_DOMAIN)


# ==================== Endpoints ====================

@router.post("/route-job/{job_id}", response_model=JobRoutingResult)
async def route_job_manual(
    job_id: str,
    request: OverrideRoutingRequest = None,
):
    """Manually trigger job routing for a specific job.

    Args:
        job_id: Job ID to route
        request: Optional override agent code

    Returns:
        Routing decision details
    """
    try:
        logger.info(f"Manual job routing triggered for job_id={job_id}")

        from pandapower.workers.carmit import CarmitOrchestrator
        from pandapower.core.config import get_settings

        supabase = await get_supabase_client()
        claude = get_claude()
        pipedrive = get_pipedrive()
        settings = get_settings()

        # Create orchestrator instance
        orchestrator = CarmitOrchestrator(
            supabase_client=supabase,
            anthropic_client=claude,
            pipedrive_client=pipedrive,
            settings=settings,
        )

        # Route job
        result = await orchestrator.route_job_to_agent(job_id)

        # Handle override if provided
        if request and request.override_agent_code:
            logger.info(f"Overriding agent assignment to {request.override_agent_code}")
            result["assigned_agent_code"] = request.override_agent_code
            result["assigned_agent_name"] = orchestrator.agent_specialties.get(
                request.override_agent_code, {}
            ).get("name", "Unknown")
            # Update job in database
            await supabase.table("jobs").update({
                "assigned_agent_code": request.override_agent_code,
            }).eq("id", job_id).execute()

        return JobRoutingResult(**result)

    except Exception as e:
        logger.error(f"Manual job routing failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Job routing failed: {str(e)}")


@router.post("/review-match/{match_id}", response_model=MatchReviewResult)
async def review_match_manual(
    match_id: str,
    request: OverrideReviewRequest = None,
):
    """Manually trigger match review for a specific match.

    Args:
        match_id: Match ID to review
        request: Optional override force_approve or custom reason

    Returns:
        Match review results with gate outcomes
    """
    try:
        logger.info(f"Manual match review triggered for match_id={match_id}")

        from pandapower.workers.carmit import CarmitOrchestrator
        from pandapower.core.config import get_settings

        supabase = await get_supabase_client()
        claude = get_claude()
        pipedrive = get_pipedrive()
        settings = get_settings()

        # Create orchestrator instance
        orchestrator = CarmitOrchestrator(
            supabase_client=supabase,
            anthropic_client=claude,
            pipedrive_client=pipedrive,
            settings=settings,
        )

        # Review match
        result = await orchestrator.review_match(match_id)

        # Handle override if provided
        if request and request.force_approve is not None:
            if request.force_approve:
                logger.info(f"Forcing match approval for {match_id}")
                result["new_state"] = "carmit_approved"
                result["decision"] = "approved"
                result["reasoning"] = "Manually approved by admin: " + (
                    request.override_reason or "No reason provided"
                )
                # Update match in database
                await supabase.table("matches").update({
                    "current_state": "carmit_approved",
                }).eq("id", match_id).execute()
            else:
                logger.info(f"Forcing match rejection for {match_id}")
                result["new_state"] = "carmit_rejected"
                result["decision"] = "rejected"
                result["reasoning"] = "Manually rejected by admin: " + (
                    request.override_reason or "No reason provided"
                )
                # Update match in database
                await supabase.table("matches").update({
                    "current_state": "carmit_rejected",
                }).eq("id", match_id).execute()

        return MatchReviewResult(**result)

    except Exception as e:
        logger.error(f"Manual match review failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Match review failed: {str(e)}")


@router.get("/pending-review")
async def get_pending_review(
    filter_agent: Optional[str] = Query(None),
    filter_state: Optional[str] = Query("found"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get matches awaiting Carmit review.

    Args:
        filter_agent: Optional agent code to filter by
        filter_state: Match state to filter by (default: 'found')
        limit: Number of matches to return
        offset: Pagination offset

    Returns:
        List of pending matches with metadata
    """
    try:
        supabase = await get_supabase_client()

        # Build query - fetch only necessary fields
        query = supabase.table("matches").select(
            "id, candidate_id, job_id, match_score, matched_by_agent_code, created_at"
        ).eq("current_state", filter_state or "found").eq("is_valid", True)

        if filter_agent:
            query = query.eq("matched_by_agent_code", filter_agent)

        # Execute query with pagination
        response = await query.range(offset, offset + limit - 1).execute()

        # Format response
        matches = []
        for match in response.data or []:
            candidate_name = "Unknown"
            job_title = "Unknown"

            # Try to fetch candidate name
            try:
                candidate_id = match.get("candidate_id")
                if candidate_id:
                    candidate_query = supabase.table("candidates").select("name").eq("id", candidate_id)
                    candidate_response = await candidate_query.execute()
                    if candidate_response.data and len(candidate_response.data) > 0:
                        cand_data = candidate_response.data[0]
                        candidate_name = cand_data.get("name") or "Unknown"
            except Exception as e:
                logger.warning(f"Failed to fetch candidate {match.get('candidate_id')}: {str(e)}")

            # Try to fetch job title
            try:
                job_id = match.get("job_id")
                if job_id:
                    job_query = supabase.table("jobs").select("title").eq("id", job_id)
                    job_response = await job_query.execute()
                    if job_response.data and len(job_response.data) > 0:
                        job_data = job_response.data[0]
                        job_title = job_data.get("title", "Unknown")
            except Exception as e:
                logger.warning(f"Failed to fetch job {match.get('job_id')}: {str(e)}")

            matches.append({
                "id": match["id"],
                "candidate_id": match.get("candidate_id", ""),
                "job_id": match.get("job_id", ""),
                "candidate_name": candidate_name,
                "job_title": job_title,
                "match_score": match.get("match_score", 0.0),
                "agent_code": match.get("matched_by_agent_code", ""),
                "created_at": match.get("created_at", ""),
            })

        return {
            "matches": matches,
            "total": len(matches),
            "offset": offset,
            "limit": limit,
        }

    except Exception as e:
        logger.error(f"Failed to get pending matches: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch pending matches: {str(e)}")


@router.get("/routing-history")
async def get_routing_history(
    agent_code: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get audit trail of job routing decisions.

    Args:
        agent_code: Optional agent code to filter by
        limit: Number of decisions to return
        offset: Pagination offset

    Returns:
        List of routing decisions
    """
    try:
        supabase = await get_supabase_client()

        # Query agent_logs for routing decisions
        query = supabase.table("agent_logs").select("*").eq(
            "log_type", "job_routing"
        ).order("created_at", desc=True)

        if agent_code:
            query = query.eq("agent_code", agent_code)

        # Execute query with pagination
        response = await query.range(offset, offset + limit - 1).execute()

        # Format response
        decisions = []
        for log in response.data or []:
            details = log.get("details", {})
            decisions.append({
                "job_id": log.get("job_id", ""),
                "assigned_agent_code": log.get("agent_code", ""),
                "confidence": details.get("confidence", 0.0),
                "reasoning": details.get("reasoning", ""),
                "timestamp": details.get("timestamp") or log.get("created_at", ""),
            })

        return {
            "decisions": decisions,
            "total": len(decisions),
            "offset": offset,
            "limit": limit,
        }

    except Exception as e:
        logger.error(f"Failed to get routing history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch routing history: {str(e)}")


@router.get("/review-history")
async def get_review_history(
    state: Optional[str] = Query(None),  # 'approved' or 'rejected'
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get audit trail of match review decisions.

    Args:
        state: Filter by decision state ('approved' or 'rejected')
        limit: Number of reviews to return
        offset: Pagination offset

    Returns:
        List of match review decisions
    """
    try:
        supabase = await get_supabase_client()

        # Query match_state_history for review decisions
        query = supabase.table("match_state_history").select("*").in_(
            "to_state", ["carmit_approved", "carmit_rejected"]
        ).order("created_at", desc=True)

        # Execute query with pagination
        response = await query.range(offset, offset + limit - 1).execute()

        # Format response
        reviews = []
        for entry in response.data or []:
            details = entry.get("details", {})
            to_state = entry.get("to_state", "")

            # Filter by state if specified
            if state == "approved" and to_state != "carmit_approved":
                continue
            if state == "rejected" and to_state != "carmit_rejected":
                continue

            reviews.append({
                "match_id": entry.get("match_id", ""),
                "decision": "approved" if to_state == "carmit_approved" else "rejected",
                "reasoning": details.get("decision_reasoning", ""),
                "timestamp": details.get("timestamp") or entry.get("created_at", ""),
            })

        return {
            "reviews": reviews,
            "total": len(reviews),
            "offset": offset,
            "limit": limit,
        }

    except Exception as e:
        logger.error(f"Failed to get review history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch review history: {str(e)}")


@router.get("/status")
async def get_carmit_status():
    """Get Carmit orchestrator status and stats.

    Returns:
        Current status and metrics
    """
    try:
        supabase = await get_supabase_client()

        # Get counts
        pending_matches_response = await supabase.table("matches").select("id").eq("current_state", "found").eq("is_valid", True).execute()
        approved_response = await supabase.table("matches").select("id").eq("current_state", "carmit_approved").eq("is_valid", True).execute()
        rejected_response = await supabase.table("matches").select("id").eq("current_state", "carmit_rejected").eq("is_valid", True).execute()
        # Count jobs with assigned agents
        routed_jobs_response = await supabase.table("jobs").select("*").eq("is_active", True).execute()
        routed_jobs = [j for j in routed_jobs_response.data if j.get("assigned_agent_code")]

        return {
            "status": "operational",
            "pending_review_count": len(pending_matches_response.data or []),
            "approved_count": len(approved_response.data or []),
            "rejected_count": len(rejected_response.data or []),
            "routed_jobs_count": len(routed_jobs),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get Carmit status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch status: {str(e)}")


@router.get("/kpi-summary")
async def get_kpi_summary():
    """Get Carmit KPI summary metrics.

    Returns:
        KPI metrics including pending matches, approved, rejected, and approval rate
    """
    try:
        supabase = await get_supabase_client()

        # Get counts for valid matches only
        pending_response = await supabase.table("matches").select("count", count="exact").eq(
            "current_state", "found"
        ).eq("is_valid", True).execute()

        approved_response = await supabase.table("matches").select("count", count="exact").eq(
            "current_state", "carmit_approved"
        ).eq("is_valid", True).execute()

        rejected_response = await supabase.table("matches").select("count", count="exact").eq(
            "current_state", "carmit_rejected"
        ).eq("is_valid", True).execute()

        pending_count = pending_response.count or 0
        approved_count = approved_response.count or 0
        rejected_count = rejected_response.count or 0
        total_matches = pending_count + approved_count + rejected_count

        # Calculate approval rate
        decided_matches = approved_count + rejected_count
        approval_rate = (approved_count / decided_matches) if decided_matches > 0 else 0

        return {
            "pendingReview": pending_count,
            "approvedMatches": approved_count,
            "rejectedMatches": rejected_count,
            "totalMatches": total_matches,
            "approvalRate": approval_rate,
            "jobsToRoute": 0,  # Placeholder - can be computed if needed
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get KPI summary: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch KPI summary: {str(e)}")


@router.get("/jobs-to-route")
async def get_jobs_to_route():
    """Get jobs waiting to be routed to agents.

    Returns:
        List of jobs without assigned agents, ordered by priority
    """
    try:
        supabase = await get_supabase_client()

        # Get unassigned jobs (no assigned_agent_code), ordered by priority (highest first)
        jobs_response = await supabase.table("jobs").select("*").is_(
            "assigned_agent_code", None
        ).eq("is_active", True).order("priority", desc=True).limit(50).execute()

        jobs = []
        for job in jobs_response.data or []:
            jobs.append({
                "id": job.get("id"),
                "title": job.get("title", "Unknown"),
                "description": job.get("description", ""),
                "priority": job.get("priority", 5),
                "candidateCount": 0,  # Placeholder - can be computed from matches if needed
                "organization_name": job.get("organization_name"),  # ארגון
                "contact_person_name": job.get("contact_person_name"),  # איש קשר
                "createdAt": job.get("created_at"),
            })

        return {
            "jobs": jobs,
            "total": len(jobs),
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get jobs to route: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch jobs to route: {str(e)}")


@router.get("/decisions")
async def get_carmit_decisions(
    decision_filter: Optional[str] = Query("all"),  # 'all', 'approved', 'rejected'
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get Carmit's already-made decisions with gate results and reasoning.

    This endpoint shows matches that Carmit has already decided on
    (carmit_approved or carmit_rejected) along with her reasoning and gate results.

    Args:
        decision_filter: Filter by 'approved', 'rejected', or 'all' (default: 'all')
        limit: Number of decisions to return
        offset: Pagination offset

    Returns:
        List of Carmit's decisions with detailed gate results and reasoning
    """
    try:
        supabase = await get_supabase_client()

        # Determine which states to query based on filter
        states = []
        if decision_filter in ["all", "approved"]:
            states.append("carmit_approved")
        if decision_filter in ["all", "rejected"]:
            states.append("carmit_rejected")

        if not states:
            states = ["carmit_approved", "carmit_rejected"]

        # Query matches with Carmit decisions (approved or rejected)
        query = supabase.table("matches").select(
            "id, candidate_id, job_id, match_score, current_state, updated_at"
        ).in_("current_state", states).eq("is_valid", True).order("updated_at", desc=True)

        # Execute query with pagination
        response = await query.range(offset, offset + limit - 1).execute()

        # Format response with enriched data
        decisions = []
        for match in response.data or []:
            match_id = match.get("id")
            candidate_id = match.get("candidate_id")
            job_id = match.get("job_id")
            match_score = float(match.get("match_score", 0))
            current_state = match.get("current_state", "")
            updated_at = match.get("updated_at", "")

            candidate_name = "Unknown"
            job_title = "Unknown"
            gate_results = {}
            reasoning = ""

            # Fetch candidate name
            try:
                if candidate_id:
                    candidate_query = supabase.table("candidates").select(
                        "full_name_he, full_name_en"
                    ).eq("id", candidate_id)
                    candidate_response = await candidate_query.execute()
                    if candidate_response.data and len(candidate_response.data) > 0:
                        cand_data = candidate_response.data[0]
                        candidate_name = (
                            cand_data.get("full_name_he") or
                            cand_data.get("full_name_en") or
                            "Unknown"
                        )
            except Exception as e:
                logger.warning(f"Failed to fetch candidate {candidate_id}: {str(e)}")

            # Fetch job title
            try:
                if job_id:
                    job_query = supabase.table("jobs").select("title").eq("id", job_id)
                    job_response = await job_query.execute()
                    if job_response.data and len(job_response.data) > 0:
                        job_data = job_response.data[0]
                        job_title = job_data.get("title", "Unknown")
            except Exception as e:
                logger.warning(f"Failed to fetch job {job_id}: {str(e)}")

            # Fetch gate results and reasoning from match_state_history
            try:
                history_query = supabase.table("match_state_history").select(
                    "details"
                ).eq("match_id", match_id).in_(
                    "to_state", ["carmit_approved", "carmit_rejected"]
                ).order("created_at", desc=True).limit(1)
                history_response = await history_query.execute()

                if history_response.data and len(history_response.data) > 0:
                    history_entry = history_response.data[0]
                    details = history_entry.get("details", {})

                    # Extract gate results from JSONB
                    raw_gate_results = details.get("gate_results", {})
                    for gate_name, gate_info in raw_gate_results.items():
                        if isinstance(gate_info, dict):
                            gate_results[gate_name] = GateResult(
                                passed=gate_info.get("passed", False),
                                reason=gate_info.get("reason", "")
                            )
                        else:
                            # Handle case where gate_info might be a boolean
                            gate_results[gate_name] = GateResult(
                                passed=bool(gate_info),
                                reason=""
                            )

                    # Extract decision reasoning
                    reasoning = details.get("decision_reasoning", "")
            except Exception as e:
                logger.warning(f"Failed to fetch match state history for {match_id}: {str(e)}")

            decisions.append({
                "match_id": match_id,
                "candidate_id": candidate_id,
                "candidate_name": candidate_name,
                "job_id": job_id,
                "job_title": job_title,
                "decision": "approved" if current_state == "carmit_approved" else "rejected",
                "match_score": match_score,
                "gate_results": {k: v.dict() for k, v in gate_results.items()},
                "reasoning": reasoning,
                "decided_at": updated_at,
            })

        return {
            "decisions": decisions,
            "total": len(decisions),
            "offset": offset,
            "limit": limit,
            "filter": decision_filter,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get Carmit decisions: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch Carmit decisions: {str(e)}")
