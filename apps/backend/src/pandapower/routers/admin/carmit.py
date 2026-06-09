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


@router.post("/run-review-now")
async def run_carmit_review_now():
    """Manually trigger Carmit's batch match-review task.

    Use when the scheduler isn't running (e.g. before the Render worker
    service + Redis are provisioned) or to force-process a backlog. Picks
    up the next 20 "found" matches, runs the quality gates, and flips
    each to carmit_approved / carmit_rejected.

    Returns the same shape the Celery task produces:
        {status, matches_reviewed, approved, rejected}
    """
    try:
        # Import here to avoid loading the whole celery wiring at module-load.
        from pandapower.workers.tasks import _carmit_review_matches_async

        result = await _carmit_review_matches_async()
        logger.info(f"Manual carmit review: {result}")
        return result
    except Exception as e:
        logger.error(f"Manual carmit review failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Carmit review failed: {str(e)}")


@router.post("/run-watchdog-now")
async def run_pipeline_watchdog_now():
    """Manually trigger the pipeline watchdog.

    Checks for matches stuck in transient states ("found" > 2h, or
    "carmit_approved" > 1h) and re-runs the corresponding task. Useful
    as a one-shot pipeline catch-up after deploys or worker restarts.

    Returns: {status, stuck_found, stuck_carmit_approved, actions[]}
    """
    try:
        from pandapower.workers.tasks import _pipeline_watchdog_async

        result = await _pipeline_watchdog_async()
        logger.info(f"Manual pipeline watchdog: {result}")
        return result
    except Exception as e:
        logger.error(f"Manual pipeline watchdog failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Watchdog failed: {str(e)}")


@router.post("/run-handoff-to-tal-now")
async def run_carmit_handoff_to_tal_now():
    """Manually trigger the Carmit → Tal handoff task.

    Moves the next 20 carmit_approved matches into Tal's queue
    (current_state = "sent_to_tal"). Companion to /run-review-now so the
    admin can complete the pipeline without waiting for the scheduler.

    Returns: {status, handed_off, errors}
    """
    try:
        from pandapower.workers.tasks import _carmit_handoff_to_tal_async

        result = await _carmit_handoff_to_tal_async()
        logger.info(f"Manual carmit→tal handoff: {result}")
        return result
    except Exception as e:
        logger.error(f"Manual carmit→tal handoff failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Carmit handoff failed: {str(e)}")


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

        # Count jobs with assigned agents (not checking is_active to avoid column issues)
        routed_jobs_response = await supabase.table("jobs").select("id").execute()
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

        # Pending = matches still awaiting Carmit's review.
        pending_response = await supabase.table("matches").select("count", count="exact").eq(
            "current_state", "found"
        ).eq("is_valid", True).execute()
        pending_count = pending_response.count or 0

        # Approved/rejected must be derived from the match's CURRENT downstream
        # state, not from current_state == "carmit_approved": an approved match
        # immediately moves on (carmit_approved → sent_to_tal → ...) so it no
        # longer sits in "carmit_approved". Counting that state therefore reported
        # ~0 approvals and a permanent 0% rate. A REJECTED match, by contrast,
        # stays put in "carmit_rejected". This mirrors the source-of-truth set
        # used by the /decision-history endpoint below.
        APPROVED_STATES = [
            "carmit_approved", "sent_to_tal", "tal_conversation",
            "tal_accepted", "tal_approved", "tal_rejected",
            "sent_to_elad", "elad_conversation", "elad_approved",
            "rejected_tal", "rejected_elad", "hired", "placement_failed",
        ]

        approved_response = await supabase.table("matches").select(
            "count", count="exact"
        ).in_("current_state", APPROVED_STATES).eq("is_valid", True).execute()

        rejected_response = await supabase.table("matches").select(
            "count", count="exact"
        ).eq("current_state", "carmit_rejected").eq("is_valid", True).execute()

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
        # Note: Not filtering by is_active to avoid potential schema issues
        jobs_response = await supabase.table("jobs").select("*").is_(
            "assigned_agent_code", None
        ).order("priority", desc=True).limit(50).execute()

        jobs = []
        for job in jobs_response.data or []:
            jobs.append({
                "id": job.get("id"),
                "title": job.get("job_title", "Unknown"),
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
    """Get Carmit's already-made decisions with current state and reasoning.

    Shows ALL matches that Carmit approved/rejected, including their current
    state in the pipeline (e.g., if approved but already handed to Tal/Elad).

    Args:
        decision_filter: Filter by 'approved', 'rejected', or 'all' (default: 'all')
        limit: Number of decisions to return
        offset: Pagination offset

    Returns:
        List of Carmit's decisions with current state and status explanation
    """
    try:
        supabase = await get_supabase_client()

        # SOURCE OF TRUTH = the matches table, NOT match_state_history.
        # Carmit's ruling lives in matches.current_state; history rows are only
        # used below to enrich the row with reasoning/gates. Driving off history
        # silently hid every match whose transition was never logged (e.g. the
        # 82 carmit_rejected matches that the agent-matches tab DOES show).
        #
        # A REJECTED match stays in current_state == "carmit_rejected".
        # An APPROVED match has moved on — it sits in carmit_approved or any
        # downstream state, so we treat all of those as "approved".
        APPROVED_STATES = [
            "carmit_approved", "sent_to_tal", "tal_conversation",
            "tal_accepted", "tal_approved", "tal_rejected",
            "sent_to_elad", "elad_conversation", "elad_approved",
            "rejected_tal", "rejected_elad", "hired", "placement_failed",
        ]
        REJECTED_STATES = ["carmit_rejected"]

        current_states: list[str] = []
        if decision_filter in ["all", "approved"]:
            current_states += APPROVED_STATES
        if decision_filter in ["all", "rejected"]:
            current_states += REJECTED_STATES
        if not current_states:
            current_states = APPROVED_STATES + REJECTED_STATES

        # Total count (for pagination) of all matches Carmit decided on.
        count_resp = await (
            supabase.table("matches")
            .select("id", count="exact")
            .eq("is_valid", True)
            .in_("current_state", current_states)
            .execute()
        )
        total = getattr(count_resp, "count", None) or len(count_resp.data or [])

        # Page of matches, newest decision first.
        matches_response = await (
            supabase.table("matches")
            .select("id, candidate_id, job_id, match_score, current_state, updated_at, state_updated_at, carmit_blocked_reason")
            .eq("is_valid", True)
            .in_("current_state", current_states)
            .order("state_updated_at", desc=True)
            .order("updated_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        page_matches = matches_response.data or []
        paginated_ids = [m["id"] for m in page_matches]

        if not paginated_ids:
            return {
                "decisions": [],
                "total": total,
                "offset": offset,
                "limit": limit,
                "filter": decision_filter,
                "timestamp": datetime.utcnow().isoformat(),
            }

        # Enrich (optional) with the Carmit transition from history — gives us
        # decision_reasoning + gate_results + the exact decision timestamp.
        seen_matches: dict[str, dict] = {}
        try:
            history_response = await (
                supabase.table("match_state_history")
                .select("match_id, to_state, created_at, details, reasoning")
                .in_("match_id", paginated_ids)
                .in_("to_state", ["carmit_approved", "carmit_rejected"])
                .order("created_at", desc=True)
                .execute()
            )
            for entry in history_response.data or []:
                mid = entry.get("match_id")
                if mid and mid not in seen_matches:
                    seen_matches[mid] = entry
        except Exception as hist_err:
            logger.warning(f"decisions: history enrichment failed: {hist_err}")

        matches_by_id = {m["id"]: m for m in page_matches}

        # Build decisions with current state and explanation
        decisions = []
        for match_id in paginated_ids:
            history_entry = seen_matches.get(match_id) or {}
            match = matches_by_id.get(match_id)
            if not match:
                continue

            match_id = match.get("id")
            candidate_id = match.get("candidate_id")
            job_id = match.get("job_id")
            match_score = float(match.get("match_score", 0))
            current_state = match.get("current_state", "")
            updated_at = match.get("updated_at", "")

            # Decision is derived from current_state (source of truth); fall back
            # to history only for the precise decision timestamp.
            decision_made = "rejected" if current_state in REJECTED_STATES else "approved"
            decision_timestamp = (
                history_entry.get("created_at")
                or match.get("state_updated_at")
                or updated_at
            )

            candidate_name = "Unknown"
            job_title = "Unknown"
            company_name = None
            pipedrive_deal_id = None
            gate_results = {}
            reasoning = ""

            # Fetch candidate name
            try:
                if candidate_id:
                    candidate_response = await supabase.table("candidates").select(
                        "name"
                    ).eq("id", candidate_id).execute()
                    if candidate_response.data:
                        candidate_name = candidate_response.data[0].get("name") or "Unknown"
            except Exception as e:
                logger.warning(f"Failed to fetch candidate {candidate_id}: {str(e)}")

            # Fetch job title
            try:
                if job_id:
                    job_response = await supabase.table("jobs").select(
                        "job_title, organization_name, pipedrive_deal_id"
                    ).eq("id", job_id).execute()
                    if job_response.data:
                        job_title = job_response.data[0].get("job_title", "Unknown")
                        company_name = job_response.data[0].get("organization_name")
                        pipedrive_deal_id = job_response.data[0].get("pipedrive_deal_id")
            except Exception as e:
                logger.warning(f"Failed to fetch job {job_id}: {str(e)}")

            # Extract gate results and reasoning. The rich per-gate breakdown
            # lives in the JSONB `details` column — but production's schema does
            # not have it, so in practice we fall back to the plain `reasoning`
            # TEXT column (always written) and matches.carmit_blocked_reason.
            try:
                details = history_entry.get("details") or {}
                raw_gate_results = details.get("gate_results", {}) if isinstance(details, dict) else {}
                for gate_name, gate_info in raw_gate_results.items():
                    if isinstance(gate_info, dict):
                        gate_results[gate_name] = GateResult(
                            passed=gate_info.get("passed", False),
                            reason=gate_info.get("reason", "")
                        )
                    else:
                        gate_results[gate_name] = GateResult(
                            passed=bool(gate_info),
                            reason=""
                        )
                # Reasoning: prefer JSONB, then the history TEXT column, then the
                # reason persisted on the match row.
                reasoning = (
                    (details.get("decision_reasoning") if isinstance(details, dict) else "")
                    or history_entry.get("reasoning")
                    or match.get("carmit_blocked_reason")
                    or ""
                )
                # If we have no structured gate_results (the common prod case),
                # reconstruct the failed-gate list from the reasoning text so the
                # UI still shows WHICH gates failed. Handles both the Hebrew
                # ("נכשל במבחנים: a, b") and legacy English ("Failed gates: a, b")
                # formats.
                if not gate_results and reasoning:
                    import re as _re
                    m_txt = _re.search(r"(?:נכשל במבחנים|Failed gates)\s*:\s*(.+)", reasoning)
                    if m_txt:
                        for gname in [g.strip() for g in m_txt.group(1).split(",") if g.strip()]:
                            gate_results[gname] = GateResult(passed=False, reason="")
            except Exception as e:
                logger.warning(f"Failed to extract gate results: {str(e)}")

            # Build status explanation based on current state
            state_display = ""
            state_label = ""
            if current_state == "carmit_approved":
                state_display = "ממתינה להעברה לטל"
                state_label = "waiting"
            elif current_state == "sent_to_tal":
                state_display = "הועברה לטל - בהמתנה לתגובה"
                state_label = "with_tal"
            elif current_state in ["tal_conversation", "tal_accepted"]:
                state_display = "בשיחה עם טל או אושרה"
                state_label = "tal_reviewing"
            elif current_state == "sent_to_elad":
                state_display = "הועברה לאלעד - בהמתנה לתגובה"
                state_label = "with_elad"
            elif current_state == "hired":
                state_display = "✅ הועסקה!"
                state_label = "hired"
            elif current_state == "rejected_tal":
                state_display = "דחויה על ידי טל"
                state_label = "rejected_tal"
            elif current_state == "rejected_elad":
                state_display = "דחויה על ידי אלעד"
                state_label = "rejected_elad"
            else:
                state_display = f"סטטוס: {current_state}"
                state_label = current_state

            decisions.append({
                "match_id": match_id,
                "candidate_id": candidate_id,
                "candidate_name": candidate_name,
                "job_id": job_id,
                "job_title": job_title,
                "company_name": company_name,
                "pipedrive_deal_id": pipedrive_deal_id,
                "decision": "approved" if "approved" in decision_made else "rejected",
                "match_score": match_score,
                "gate_results": {k: v.dict() for k, v in gate_results.items()},
                "reasoning": reasoning,
                "decided_at": decision_timestamp,
                "current_state": current_state,
                "state_display": state_display,
                "state_label": state_label,
            })

        return {
            "decisions": decisions,
            "total": total,
            "offset": offset,
            "limit": limit,
            "filter": decision_filter,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get Carmit decisions: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch Carmit decisions: {str(e)}")


# ============================================================================
#  /admin/carmit/agent-matches
#  --------------------------------------------------------------------------
#  Single feed for the Carmit "התאמות מסוכני הגיוס" tab: every still-valid
#  match (Phase-4 is_valid=true) from any of the 8 recruitment agents,
#  scored at 70% or better. Paginated, ordered by score desc then date desc.
#  Excludes Tal/Elad/Pandi etc. — only candidates the recruitment agents
#  themselves flagged.
# ============================================================================

# Single source of truth: who counts as a "recruitment agent" for this feed.
RECRUITMENT_AGENT_CODES = ("naama", "alik", "dganit", "ofir", "itai", "lior", "gc", "mani")


# Whitelist of column names we'll accept as sort keys, mapped to the
# DB column the order clause actually references. Anything not in this
# map falls back to "match_score" so a malformed ?sort_by= can't crash
# the endpoint.
_AGENT_MATCH_SORT_COLUMNS = {
    "score": "match_score",
    "agent": "matched_by_agent_code",
    "state": "current_state",
    "date": "created_at",
}
# Sort keys that need to be applied client-side (Python list.sort) because
# they live on JOINED tables — postgrest's .order() over an embedded
# resource has gotchas, especially with .range() pagination. The values
# refer to the FINAL response keys, not DB columns.
_AGENT_MATCH_CLIENT_SORT_KEYS = {"candidate", "job", "clearance"}


class BulkMatchStatusRequest(BaseModel):
    match_ids: list[str]
    action: str  # 'hired' or 'rejected'
    notes: Optional[str] = None


@router.post("/update-matches-status")
async def update_matches_status(request: BulkMatchStatusRequest):
    """Bulk update match status (hire/reject).

    Args:
        match_ids: List of match IDs to update
        action: 'hired' or 'rejected'
        notes: Optional notes for the action

    Returns:
        List of updated matches
    """
    try:
        if not request.match_ids:
            raise HTTPException(status_code=400, detail="No match IDs provided")

        if request.action not in ["hired", "rejected"]:
            raise HTTPException(status_code=400, detail="Action must be 'hired' or 'rejected'")

        supabase = await get_supabase_client()

        # Map action to new state
        new_state = "hired" if request.action == "hired" else "placement_failed"

        # Update matches
        updated_matches = []
        for match_id in request.match_ids:
            try:
                # Update match state
                await supabase.table("matches").update({
                    "current_state": new_state,
                }).eq("id", match_id).execute()

                # Log the state transition
                await supabase.table("match_state_history").insert({
                    "match_id": match_id,
                    "from_state": "unknown",  # Could be any state
                    "to_state": new_state,
                    "details": {
                        "action": request.action,
                        "notes": request.notes or "",
                        "updated_by": "admin",
                    }
                }).execute()

                updated_matches.append({
                    "id": match_id,
                    "new_state": new_state,
                    "action": request.action,
                })
            except Exception as e:
                logger.error(f"Failed to update match {match_id}: {str(e)}")
                # Continue with other matches

        logger.info(f"Updated {len(updated_matches)} matches with action={request.action}")

        return {
            "status": "success",
            "updated_count": len(updated_matches),
            "updated_matches": updated_matches,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk match status update failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Status update failed: {str(e)}")


@router.get("/agent-matches")
async def get_agent_matches(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_score: float = Query(0.70, ge=0.0, le=1.0),
    sort_by: str = Query("score"),
    sort_dir: str = Query("desc"),
):
    """Carmit's "all high-quality agent matches" view.

    Args:
        limit:     page size (default 25, max 200)
        offset:    rows to skip (page = offset / limit)
        min_score: lower-bound score, 0.0–1.0 (default 0.70 — the "70%+ only"
                   filter the user asked for; exposed in case we ever want to
                   relax it for diagnostics)
        sort_by:   column key. One of score / candidate / job / agent / state /
                   clearance / date. Unknown values silently fall back to "score".
        sort_dir:  "asc" or "desc". Anything else is treated as "desc".

    Returns: paginated matches with candidate name, job title, agent code,
             score, current state, reasoning preview, security clearance,
             and the timestamps used by the UI.
    """
    try:
        supabase = await get_supabase_client()
        descending = (sort_dir or "").lower() != "asc"

        # ── total count, for pagination UI ─────────────────────────────────
        # Note: postgrest returns count separately when count="exact".
        count_resp = await (
            supabase.table("matches")
            .select("id", count="exact")
            .eq("is_valid", True)
            .gte("match_score", min_score)
            .in_("matched_by_agent_code", list(RECRUITMENT_AGENT_CODES))
            .execute()
        )
        total = getattr(count_resp, "count", None) or len(count_resp.data or [])

        # ── page of rows + joined related data ─────────────────────────────
        # Wide projection: the UI shows clickable rows that open a candidate
        # modal AND a match-detail modal, both need richer fields than the
        # table itself — pulling them here avoids per-row round-trips.
        # Sort strategy:
        #   • DB-side sort for native columns (score / agent / state / date)
        #     so pagination works on the server.
        #   • For "candidate"/"job"/"clearance" we DB-sort by match_score
        #     (so paging is stable) and re-order the page client-side at
        #     the end — close enough for a 25-row page.
        sort_col_db = _AGENT_MATCH_SORT_COLUMNS.get(sort_by)
        query = (
            supabase.table("matches")
            .select(
                "id, candidate_id, job_id, matched_by_agent_code, match_score, "
                "current_state, match_reasoning, created_at, updated_at, "
                "candidates(id,name,email,phone,location,clearance_level,"
                "years_of_experience,key_skills,top_education,experiences,"
                "detected_language,recommendation_score), "
                "jobs(id,job_title,job_security_clearance,job_description,"
                "organization_name,pipedrive_deal_id)"
            )
            .eq("is_valid", True)
            .gte("match_score", min_score)
            .in_("matched_by_agent_code", list(RECRUITMENT_AGENT_CODES))
        )
        if sort_col_db:
            # Primary order is the user-chosen column; created_at is the
            # tie-breaker so paging stays deterministic across ties.
            query = query.order(sort_col_db, desc=descending)
            if sort_col_db != "created_at":
                query = query.order("created_at", desc=True)
        else:
            # Unknown / client-side key → DB-sort by score for stable pages.
            query = query.order("match_score", desc=True).order("created_at", desc=True)

        resp = await query.range(offset, offset + limit - 1).execute()

        # ── Batch-load strengths/gaps from agent_logs.output_payload ───────
        # The agent_matching worker writes them as JSONB under action="find_match".
        # Mirroring the pattern already in routers/admin/recruitment_departments.py.
        rows = resp.data or []
        match_ids = [str(r.get("id")) for r in rows if r.get("id")]
        strengths_by_match: dict[str, list[str]] = {}
        gaps_by_match: dict[str, list[str]] = {}
        if match_ids:
            try:
                logs_resp = await (
                    supabase.table("agent_logs")
                    .select("related_match_id, output_payload")
                    .in_("related_match_id", match_ids)
                    .eq("action", "find_match")
                    .execute()
                )
                for log in logs_resp.data or []:
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
                # Non-fatal — table-row rendering doesn't need strengths/gaps,
                # only the modal does, and the modal degrades gracefully.
                logger.warning(f"agent_matches: strengths/gaps lookup failed: {log_err}")

        # ── Batch-load Carmit's decision reasoning from match_state_history ─
        # For rows Carmit already ruled on (carmit_rejected / carmit_approved)
        # we surface WHY in the row: the decision_reasoning + the list of gates
        # that failed with their specific reasons. Same batch pattern as above
        # to avoid a per-row round-trip.
        carmit_decision_by_match: dict[str, dict[str, Any]] = {}
        if match_ids:
            try:
                hist_resp = await (
                    supabase.table("match_state_history")
                    .select("match_id, to_state, created_at, details, reasoning")
                    .in_("match_id", match_ids)
                    .in_("to_state", ["carmit_rejected", "carmit_approved"])
                    .order("created_at", desc=True)
                    .execute()
                )
                import re as _re
                for h in hist_resp.data or []:
                    mid = str(h.get("match_id") or "")
                    if not mid or mid in carmit_decision_by_match:
                        continue  # keep most recent (rows are date-desc)
                    details = h.get("details") or {}
                    raw_gates = details.get("gate_results") if isinstance(details, dict) else None
                    raw_gates = raw_gates or {}
                    failed_gates = []
                    if isinstance(raw_gates, dict):
                        for gname, ginfo in raw_gates.items():
                            if isinstance(ginfo, dict) and not ginfo.get("passed", False):
                                failed_gates.append({
                                    "gate": gname,
                                    "reason": ginfo.get("reason") or "",
                                })
                    # Prod has no `details` JSONB → derive from the reasoning text.
                    reasoning = (
                        (details.get("decision_reasoning") if isinstance(details, dict) else "")
                        or h.get("reasoning")
                        or ""
                    )
                    if not failed_gates and reasoning:
                        m_txt = _re.search(r"(?:נכשל במבחנים|Failed gates)\s*:\s*(.+)", reasoning)
                        if m_txt:
                            for gname in [g.strip() for g in m_txt.group(1).split(",") if g.strip()]:
                                failed_gates.append({"gate": gname, "reason": ""})
                    carmit_decision_by_match[mid] = {
                        "decision": "rejected" if "rejected" in (h.get("to_state") or "") else "approved",
                        "reasoning": reasoning,
                        "failed_gates": failed_gates,
                        "decided_at": h.get("created_at"),
                    }
            except Exception as hist_err:
                logger.warning(f"agent_matches: carmit decision lookup failed: {hist_err}")

        # ── Clearance comparison helper (computed match/partial/mismatch) ──
        # Reuse the same logic the per-agent screens use so the badge is
        # consistent across all dashboards.
        from pandapower.routers.admin.recruitment_departments import (
            _compute_clearance_match,
        )

        out = []
        for row in rows:
            cand = row.get("candidates") or {}
            job = row.get("jobs") or {}
            reasoning = row.get("match_reasoning") or ""
            match_id = str(row.get("id") or "")
            cand_clearance = cand.get("clearance_level")
            req_clearance = job.get("job_security_clearance")
            out.append({
                "id": match_id,
                "candidate_id": str(row.get("candidate_id") or ""),
                "candidate_name": cand.get("name") or "ללא שם",
                "candidate_email": cand.get("email"),
                "candidate_phone": cand.get("phone"),
                "candidate_location": cand.get("location"),
                "candidate_clearance": cand_clearance,
                "candidate_years": cand.get("years_of_experience"),
                "candidate_key_skills": cand.get("key_skills") or [],
                "candidate_top_education": cand.get("top_education"),
                "candidate_experiences": cand.get("experiences") or [],
                "candidate_language": cand.get("detected_language"),
                "candidate_recommendation_score": cand.get("recommendation_score"),
                "job_id": str(row.get("job_id") or ""),
                "job_title": job.get("job_title") or "ללא תפקיד",
                # Client/organization name + Pipedrive deal number (4-digit) so
                # every Carmit table can always show full job title + client + job #.
                "company_name": job.get("organization_name"),
                "pipedrive_deal_id": job.get("pipedrive_deal_id"),
                "job_description": job.get("job_description"),
                "required_clearance": req_clearance,
                "clearance_match": _compute_clearance_match(cand_clearance, req_clearance),
                "agent_code": row.get("matched_by_agent_code") or "",
                "match_score": float(row.get("match_score") or 0.0),
                "current_state": row.get("current_state") or "found",
                "match_reasoning": reasoning,  # full text — modal renders it
                "reasoning_preview": (reasoning[:140] + "…") if len(reasoning) > 140 else reasoning,
                "strengths": strengths_by_match.get(match_id, []),
                "gaps": gaps_by_match.get(match_id, []),
                # Carmit's quality-gate ruling (None if she hasn't ruled yet).
                # Lets the UI explain WHY a match was rejected/approved per row.
                "carmit_decision": carmit_decision_by_match.get(match_id),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            })

        # ── Client-side sort for keys that live on joined tables ───────────
        # When sort_by is a join-side key we fetched a page sorted by score
        # (for stable paging) — now re-order just this page in Python.
        if sort_by in _AGENT_MATCH_CLIENT_SORT_KEYS:
            client_key_fn = {
                # casefold gives locale-insensitive case-insensitive compare,
                # works for Hebrew too (lowercases nothing but still consistent).
                "candidate": lambda m: (m.get("candidate_name") or "").casefold(),
                "job":       lambda m: (m.get("job_title") or "").casefold(),
                # Clearance ordering by status verdict, then by raw value.
                # Order is informative: match → partial → mismatch → unknown.
                "clearance": lambda m: (
                    {"match": 0, "partial": 1, "mismatch": 2, "unknown": 3}.get(
                        m.get("clearance_match", "unknown"), 9
                    ),
                    (m.get("required_clearance") or "").casefold(),
                ),
            }[sort_by]
            out.sort(key=client_key_fn, reverse=descending)

        return {
            "matches": out,
            "total": total,
            "offset": offset,
            "limit": limit,
            "min_score": min_score,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to get Carmit agent matches: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch agent matches: {e}")
