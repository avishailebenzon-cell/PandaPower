"""
Admin API endpoints for agent-based matching control.

Phase 4: Sub-Agent Matching Implementation
- Trigger matching for jobs and candidates
- Monitor agent activity and statistics
- View matches created by each agent
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from pandapower.core.config import settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.claude_api import AnthropicClient
from pandapower.workers.agent_matching import AgentMatchingWorker, AGENT_CONFIGS
from pandapower.workers.tasks import match_job_candidates_task, match_candidate_jobs_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/agent-matching", tags=["admin", "agent-matching"])


# ============================================================================
# Demo Data Function
# ============================================================================
def _get_demo_system_status() -> "SystemStatus":
    """Return sample data for testing the dashboard."""
    from datetime import datetime, timedelta

    now = datetime.utcnow()

    return SystemStatus(
        timestamp=now.isoformat(),
        system_summary=SystemSummary(
            total_active_jobs=12,
            total_pending_candidates=47,
            total_matches_in_progress=28,
            priority_distribution={
                "priority_1": 3,
                "priority_2": 2,
                "priority_3": 4,
                "priority_4": 2,
                "priority_5": 1,
            },
        ),
        carmit_status=CarmitStatus(
            status="processing",
            last_action="Routed Senior Python Developer to Naama",
            last_action_at=(now - timedelta(minutes=3)).isoformat(),
            jobs_routed_today=18,
            jobs_routed_this_week=94,
            average_routing_confidence=0.82,
        ),
        agent_statuses=[
            AgentStatus(
                agent_code="naama",
                agent_name="נעמה",
                domain="Software & Cloud",
                status="processing",
                current_task="Scoring 5 candidates for Senior Python Developer",
                current_job_id="job-001",
                progress="3/5 completed",
                matches_found_today=4,
                matches_found_week=28,
                last_active_at=(now - timedelta(minutes=2)).isoformat(),
                next_scheduled_check=(now + timedelta(minutes=8)).isoformat(),
                workload="medium",
                success_rate_today=0.92,
            ),
            AgentStatus(
                agent_code="alik",
                agent_name="אליק",
                domain="DevOps & Infrastructure",
                status="idle",
                current_task="Waiting for next job assignment",
                current_job_id="",
                progress="Ready",
                matches_found_today=2,
                matches_found_week=15,
                last_active_at=(now - timedelta(minutes=45)).isoformat(),
                next_scheduled_check=(now + timedelta(minutes=5)).isoformat(),
                workload="light",
                success_rate_today=0.88,
            ),
            AgentStatus(
                agent_code="dganit",
                agent_name="דגנית",
                domain="QA & Testing",
                status="processing",
                current_task="Evaluating 3 QA candidates for Lead QA position",
                current_job_id="job-003",
                progress="1/3 candidates scored",
                matches_found_today=1,
                matches_found_week=12,
                last_active_at=(now - timedelta(minutes=5)).isoformat(),
                next_scheduled_check=(now + timedelta(minutes=10)).isoformat(),
                workload="light",
                success_rate_today=0.95,
            ),
            AgentStatus(
                agent_code="ofir",
                agent_name="אופיר",
                domain="Data & Analytics",
                status="idle",
                current_task="Waiting for next job assignment",
                current_job_id="",
                progress="Ready",
                matches_found_today=3,
                matches_found_week=22,
                last_active_at=(now - timedelta(minutes=120)).isoformat(),
                next_scheduled_check=(now + timedelta(minutes=3)).isoformat(),
                workload="light",
                success_rate_today=0.89,
            ),
            AgentStatus(
                agent_code="itai",
                agent_name="איתי",
                domain="Product & Management",
                status="waiting",
                current_task="Waiting for candidates to be assigned",
                current_job_id="job-002",
                progress="Queued",
                matches_found_today=0,
                matches_found_week=8,
                last_active_at=(now - timedelta(minutes=240)).isoformat(),
                next_scheduled_check=(now + timedelta(minutes=12)).isoformat(),
                workload="light",
                success_rate_today=0.85,
            ),
            AgentStatus(
                agent_code="lior",
                agent_name="ליאור",
                domain="Finance & Legal",
                status="idle",
                current_task="Waiting for next job assignment",
                current_job_id="",
                progress="Ready",
                matches_found_today=2,
                matches_found_week=10,
                last_active_at=(now - timedelta(minutes=60)).isoformat(),
                next_scheduled_check=(now + timedelta(minutes=7)).isoformat(),
                workload="light",
                success_rate_today=0.87,
            ),
            AgentStatus(
                agent_code="gc",
                agent_name="GC",
                domain="Generalist Coordinator",
                status="processing",
                current_task="Analyzing candidates across multiple positions",
                current_job_id="job-004",
                progress="2/8 candidates scored",
                matches_found_today=3,
                matches_found_week=18,
                last_active_at=(now - timedelta(minutes=1)).isoformat(),
                next_scheduled_check=(now + timedelta(minutes=9)).isoformat(),
                workload="high",
                success_rate_today=0.78,
            ),
        ],
        recent_activities=[
            Activity(
                timestamp=(now - timedelta(minutes=1)).isoformat(),
                type="match_created",
                agent_code="naama",
                candidate_name="David Cohen",
                job_title="Senior Python Developer",
                match_score=0.91,
                status="found",
            ),
            Activity(
                timestamp=(now - timedelta(minutes=3)).isoformat(),
                type="job_routed",
                agent_code="naama",
                job_title="Senior Python Developer",
                priority=1,
                routing_confidence=0.95,
            ),
            Activity(
                timestamp=(now - timedelta(minutes=7)).isoformat(),
                type="match_created",
                agent_code="gc",
                candidate_name="Sarah Mirsky",
                job_title="Data Engineer",
                match_score=0.78,
                status="found",
            ),
            Activity(
                timestamp=(now - timedelta(minutes=12)).isoformat(),
                type="match_created",
                agent_code="dganit",
                candidate_name="Yael Stein",
                job_title="QA Lead",
                match_score=0.85,
                status="found",
            ),
            Activity(
                timestamp=(now - timedelta(minutes=18)).isoformat(),
                type="job_routed",
                agent_code="alik",
                job_title="DevOps Engineer",
                priority=2,
                routing_confidence=0.88,
            ),
        ],
        matches_in_progress=[
            MatchInProgress(
                candidate_id="cand-001",
                candidate_name="David Cohen",
                job_id="job-001",
                job_title="Senior Python Developer",
                agent_handling="naama",
                status="found",
                score=0.91,
                created_at=(now - timedelta(minutes=1)).isoformat(),
                last_updated_at=(now - timedelta(seconds=30)).isoformat(),
                next_review_at=(now + timedelta(hours=1)).isoformat(),
            ),
            MatchInProgress(
                candidate_id="cand-002",
                candidate_name="Yael Stein",
                job_id="job-003",
                job_title="QA Lead",
                agent_handling="dganit",
                status="carmit_approved",
                score=0.85,
                created_at=(now - timedelta(hours=2)).isoformat(),
                last_updated_at=(now - timedelta(minutes=30)).isoformat(),
                next_review_at=(now + timedelta(hours=2)).isoformat(),
            ),
            MatchInProgress(
                candidate_id="cand-003",
                candidate_name="Sarah Mirsky",
                job_id="job-002",
                job_title="Data Engineer",
                agent_handling="gc",
                status="found",
                score=0.78,
                created_at=(now - timedelta(hours=1)).isoformat(),
                last_updated_at=(now - timedelta(minutes=45)).isoformat(),
                next_review_at=(now + timedelta(minutes=45)).isoformat(),
            ),
        ],
        recent_job_changes=[
            JobChange(
                job_id="job-001",
                job_title="Senior Python Developer",
                change_type="priority_changed",
                changed_at=(now - timedelta(hours=1)).isoformat(),
                fields_changed=["priority"],
                matches_invalidated=2,
                rematch_status="completed",
            ),
            JobChange(
                job_id="job-005",
                job_title="Frontend Developer",
                change_type="specs_changed",
                changed_at=(now - timedelta(hours=4)).isoformat(),
                fields_changed=["qualifications", "required_skills"],
                matches_invalidated=1,
                rematch_status="in_progress",
            ),
        ],
        change_detection_metrics=ChangeDetectionMetrics(
            matches_invalidated_today=5,
            rematches_triggered_today=3,
            total_job_changes_today=2,
        ),
    )


# ============================================================================
# Request/Response Models
# ============================================================================


class MatchingRequest(BaseModel):
    """Request to trigger matching for a job or candidate."""

    job_id: Optional[str] = None
    candidate_id: Optional[str] = None
    agent_code: str


class MatchingResponse(BaseModel):
    """Result of a matching operation."""

    status: str
    total_evaluated: int
    matches_found: int
    tokens_used: int
    duration_ms: float
    errors: list


class AgentInfo(BaseModel):
    """Information about an agent."""

    code: str
    name: str
    domain: str
    keywords: str
    skill_categories: list[str]


class AgentStats(BaseModel):
    """Statistics about an agent's activity."""

    agent_code: str
    period_days: int
    total_logs: int
    successful_runs: int
    failed_runs: int
    total_tokens_used: int
    matches_created: int
    success_rate: float


class Match(BaseModel):
    """A candidate-job match created by an agent."""

    id: str
    candidate_id: str
    candidate_name: str
    job_id: str
    job_title: str
    match_score: float
    match_reasoning: str
    matched_by_agent_code: str
    current_state: str
    created_at: str


class RecentMatches(BaseModel):
    """Recent matches from all agents."""

    total: int
    by_agent: dict[str, int]
    recent: list[Match]


# ============================================================================
# System Status Models (for Real-Time Dashboard)
# ============================================================================


class SystemSummary(BaseModel):
    """High-level summary of system state."""

    total_active_jobs: int
    total_pending_candidates: int
    total_matches_in_progress: int
    priority_distribution: dict[str, int]


class CarmitStatus(BaseModel):
    """Current status of Carmit Orchestrator."""

    status: str  # idle | processing
    last_action: Optional[str] = None
    last_action_at: Optional[str] = None
    jobs_routed_today: int = 0
    jobs_routed_this_week: int = 0
    average_routing_confidence: float = 0.0


class AgentStatus(BaseModel):
    """Current status of a single agent."""

    agent_code: str
    agent_name: str
    domain: str
    status: str  # idle | processing | waiting
    current_task: Optional[str] = None
    current_job_id: Optional[str] = None
    progress: str = "0/0"
    matches_found_today: int = 0
    matches_found_week: int = 0
    last_active_at: Optional[str] = None
    next_scheduled_check: Optional[str] = None
    workload: str = "light"  # light | medium | high
    success_rate_today: float = 1.0


class Activity(BaseModel):
    """A single system activity (match created, job routed, etc)."""

    timestamp: str
    type: str  # match_created | job_routed | match_reviewed
    agent_code: Optional[str] = None
    candidate_name: Optional[str] = None
    job_title: Optional[str] = None
    match_score: Optional[float] = None
    status: Optional[str] = None
    priority: Optional[int] = None
    routing_confidence: Optional[float] = None


class MatchInProgress(BaseModel):
    """A match currently in the pipeline."""

    candidate_id: str
    candidate_name: str
    job_id: str
    job_title: str
    agent_handling: str
    status: str  # found | carmit_approved | sent_to_recruiter | etc
    score: float
    created_at: str
    last_updated_at: str
    next_review_at: Optional[str] = None


class JobChange(BaseModel):
    """A recent change to a job specification."""

    job_id: str
    job_title: str
    change_type: str  # specs_changed | priority_changed | manual_rematch_request
    changed_at: str
    fields_changed: list[str]  # ["priority", "qualifications"]
    matches_invalidated: int
    rematch_status: str  # idle | in_progress | completed


class ChangeDetectionMetrics(BaseModel):
    """Metrics about job changes and re-matching activity."""

    matches_invalidated_today: int = 0
    rematches_triggered_today: int = 0
    avg_matches_per_change: float = 0.0
    total_job_changes_today: int = 0


class SystemStatus(BaseModel):
    """Complete real-time system status for dashboard."""

    timestamp: str
    system_summary: SystemSummary
    carmit_status: CarmitStatus
    agent_statuses: list[AgentStatus]
    recent_activities: list[Activity]
    matches_in_progress: list[MatchInProgress]
    recent_job_changes: Optional[list[JobChange]] = None
    change_detection_metrics: Optional[ChangeDetectionMetrics] = None


# ============================================================================
# Agent Configuration Endpoints
# ============================================================================


@router.get("/agents", response_model=list[AgentInfo])
async def get_all_agents() -> list[AgentInfo]:
    """List all 7 agents and their specializations."""
    agents = []
    for code, config in AGENT_CONFIGS.items():
        agents.append(
            AgentInfo(
                code=code,
                name=config["name"],
                domain=config["domain"],
                keywords=config["keywords"],
                skill_categories=config["skill_categories"],
            )
        )
    return agents


@router.get("/agents/{agent_code}", response_model=AgentInfo)
async def get_agent(agent_code: str) -> AgentInfo:
    """Get details for a specific agent."""
    if agent_code not in AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent {agent_code} not found")

    config = AGENT_CONFIGS[agent_code]
    return AgentInfo(
        code=agent_code,
        name=config["name"],
        domain=config["domain"],
        keywords=config["keywords"],
        skill_categories=config["skill_categories"],
    )


# ============================================================================
# Matching Trigger Endpoints
# ============================================================================


@router.post("/match-job", response_model=MatchingResponse)
async def trigger_job_matching(
    request: MatchingRequest = Body(...), supabase=Depends(get_supabase_client)
) -> MatchingResponse:
    """Trigger matching for a specific job.

    Finds candidate matches for the given job using the specified agent.
    This is done synchronously via the matching worker for immediate feedback.

    Args:
        request: {
            "job_id": "uuid",
            "agent_code": "alik|naama|dganit|ofir|itai|lior|gc"
        }
    """

    if not request.job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    if request.agent_code not in AGENT_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Invalid agent_code: {request.agent_code}")

    try:
        # Verify job exists
        job_response = supabase.table("jobs").select("*").eq("id", request.job_id).single().execute()
        if not job_response.data:
            raise HTTPException(status_code=404, detail=f"Job {request.job_id} not found")

        # Initialize Claude client if available
        if not settings.ANTHROPIC_API_KEY:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

        claude_client = AnthropicClient(settings.ANTHROPIC_API_KEY)
        worker = AgentMatchingWorker(supabase, claude_client)

        # Run matching synchronously for admin endpoints
        result = await worker.find_matches_for_job(request.job_id, request.agent_code)

        await claude_client.close()

        return MatchingResponse(
            status="completed" if result.get("errors") is None or len(result["errors"]) == 0 else "partial",
            total_evaluated=result.get("total_candidates_evaluated", 0),
            matches_found=result.get("matches_found", 0),
            tokens_used=result.get("tokens_used", 0),
            duration_ms=result.get("duration_ms", 0),
            errors=result.get("errors", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job matching failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Matching failed: {str(e)}")


@router.post("/match-candidate", response_model=MatchingResponse)
async def trigger_candidate_matching(
    request: MatchingRequest = Body(...), supabase=Depends(get_supabase_client)
) -> MatchingResponse:
    """Trigger matching for a specific candidate.

    Finds job matches for the given candidate using the specified agent.
    This is done synchronously via the matching worker for immediate feedback.

    Args:
        request: {
            "candidate_id": "uuid",
            "agent_code": "alik|naama|dganit|ofir|itai|lior|gc"
        }
    """

    if not request.candidate_id:
        raise HTTPException(status_code=400, detail="candidate_id is required")

    if request.agent_code not in AGENT_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Invalid agent_code: {request.agent_code}")

    try:
        # Verify candidate exists
        cand_response = (
            supabase.table("candidates").select("*").eq("id", request.candidate_id).single().execute()
        )
        if not cand_response.data:
            raise HTTPException(status_code=404, detail=f"Candidate {request.candidate_id} not found")

        # Initialize Claude client
        if not settings.ANTHROPIC_API_KEY:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

        claude_client = AnthropicClient(settings.ANTHROPIC_API_KEY)
        worker = AgentMatchingWorker(supabase, claude_client)

        # Run matching synchronously
        result = await worker.find_matches_for_candidate(request.candidate_id, request.agent_code)

        await claude_client.close()

        return MatchingResponse(
            status="completed" if result.get("errors") is None or len(result["errors"]) == 0 else "partial",
            total_evaluated=result.get("total_jobs_evaluated", 0),
            matches_found=result.get("matches_found", 0),
            tokens_used=result.get("tokens_used", 0),
            duration_ms=result.get("duration_ms", 0),
            errors=result.get("errors", []),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Candidate matching failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Matching failed: {str(e)}")


# ============================================================================
# Monitoring & Statistics Endpoints
# ============================================================================


@router.get("/agents/{agent_code}/stats", response_model=AgentStats)
async def get_agent_stats(
    agent_code: str, days: int = 7, supabase=Depends(get_supabase_client)
) -> AgentStats:
    """Get matching statistics for an agent.

    Shows matching activity over the past N days.

    Args:
        agent_code: Agent code (alik, naama, etc.)
        days: Number of days to look back (default 7)
    """

    if agent_code not in AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent {agent_code} not found")

    try:
        # Fetch agent logs from the past N days
        from_date = datetime.utcnow().timestamp() - (days * 86400)

        response = (
            supabase.table("agent_logs")
            .select("*")
            .eq("agent_code", agent_code)
            .gte("created_at", datetime.fromtimestamp(from_date).isoformat())
            .execute()
        )

        logs = response.data or []

        # Calculate stats
        total_logs = len(logs)
        successful = len([l for l in logs if l.get("status") == "success"])
        failed = len([l for l in logs if l.get("status") == "failed"])
        total_tokens = sum([l.get("tokens_used", 0) for l in logs])

        # Get matches created
        matches_response = (
            supabase.table("matches")
            .select("id")
            .eq("matched_by_agent_code", agent_code)
            .gte("created_at", datetime.fromtimestamp(from_date).isoformat())
            .execute()
        )

        return AgentStats(
            agent_code=agent_code,
            period_days=days,
            total_logs=total_logs,
            successful_runs=successful,
            failed_runs=failed,
            total_tokens_used=total_tokens,
            matches_created=len(matches_response.data or []),
            success_rate=successful / total_logs if total_logs > 0 else 0.0,
        )

    except Exception as e:
        logger.error(f"Error getting agent stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve stats: {str(e)}")


@router.get("/matches/recent", response_model=RecentMatches)
async def get_recent_matches(limit: int = 50, supabase=Depends(get_supabase_client)) -> RecentMatches:
    """Get recent matches created by all agents.

    Shows the most recently created matches with agent breakdown.

    Args:
        limit: Maximum number of matches to return
    """

    try:
        # Fetch recent matches with candidate and job info
        response = (
            supabase.table("matches")
            .select(
                "id, candidate_id, job_id, match_score, match_reasoning, "
                "matched_by_agent_code, current_state, created_at"
            )
            .select(
                "candidates(name)",
                "jobs(job_title)",
            )
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        matches = response.data or []

        # Build Match objects
        match_objects = []
        by_agent = {}

        for m in matches:
            agent = m.get("matched_by_agent_code", "unknown")
            by_agent[agent] = by_agent.get(agent, 0) + 1

            match_objects.append(
                Match(
                    id=m["id"],
                    candidate_id=m["candidate_id"],
                    candidate_name=m.get("candidates", {}).get("name", "Unknown"),
                    job_id=m["job_id"],
                    job_title=m.get("jobs", {}).get("title", "Unknown"),
                    match_score=float(m.get("match_score", 0)),
                    match_reasoning=m.get("match_reasoning", ""),
                    matched_by_agent_code=agent,
                    current_state=m.get("current_state", "found"),
                    created_at=m.get("created_at", ""),
                )
            )

        return RecentMatches(total=len(match_objects), by_agent=by_agent, recent=match_objects)

    except Exception as e:
        logger.error(f"Error fetching recent matches: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve matches: {str(e)}")


@router.get("/matches/by-agent/{agent_code}")
async def get_matches_by_agent(
    agent_code: str, limit: int = 20, supabase=Depends(get_supabase_client)
) -> RecentMatches:
    """Get matches created by a specific agent."""

    if agent_code not in AGENT_CONFIGS:
        raise HTTPException(status_code=404, detail=f"Agent {agent_code} not found")

    try:
        response = (
            supabase.table("matches")
            .select(
                "id, candidate_id, job_id, match_score, match_reasoning, "
                "matched_by_agent_code, current_state, created_at"
            )
            .select(
                "candidates(name)",
                "jobs(job_title)",
            )
            .eq("matched_by_agent_code", agent_code)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        matches = response.data or []

        match_objects = []
        for m in matches:
            match_objects.append(
                Match(
                    id=m["id"],
                    candidate_id=m["candidate_id"],
                    candidate_name=m.get("candidates", {}).get("name", "Unknown"),
                    job_id=m["job_id"],
                    job_title=m.get("jobs", {}).get("title", "Unknown"),
                    match_score=float(m.get("match_score", 0)),
                    match_reasoning=m.get("match_reasoning", ""),
                    matched_by_agent_code=agent_code,
                    current_state=m.get("current_state", "found"),
                    created_at=m.get("created_at", ""),
                )
            )

        return RecentMatches(total=len(match_objects), by_agent={agent_code: len(match_objects)}, recent=match_objects)

    except Exception as e:
        logger.error(f"Error fetching agent matches: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve matches: {str(e)}")


# ============================================================================
# Real-Time System Status Endpoint (Dashboard)
# ============================================================================


@router.get("/system-status", response_model=SystemStatus)
async def get_system_status(
    supabase_client=Depends(get_supabase_client),
    demo: bool = False
) -> SystemStatus:
    """Get real-time system status for the recruitment dashboard.

    Returns:
    - Current state of Carmit Orchestrator
    - Status of all 7 agents (what they're doing now)
    - System summary (active jobs, candidates, matches)
    - Recent activities (matches created, jobs routed)
    - Matches in progress with their status in the pipeline

    Pass ?demo=true to get sample data for testing the dashboard.
    """
    # Return demo data if requested
    if demo:
        return _get_demo_system_status()

    try:
        from datetime import timedelta

        # ===== SYSTEM SUMMARY =====
        # Count active jobs (status = 'open')
        active_jobs = await supabase_client.table("jobs").select("count", count="exact").eq(
            "status", "open"
        ).execute()
        total_active_jobs = active_jobs.count or 0

        # Count pending candidates - candidates with recent activity (created in last 7 days)
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        pending_candidates = await supabase_client.table("candidates").select("count", count="exact").gte(
            "created_at", week_ago
        ).execute()
        total_pending_candidates = pending_candidates.count or 0

        # Count matches in progress (valid matches in states: found, carmit_approved, sent_to_tal)
        in_progress_matches = await supabase_client.table("matches").select(
            "count", count="exact"
        ).in_("current_state", ["found", "carmit_approved", "sent_to_tal"]).eq(
            "is_valid", True
        ).execute()
        total_matches_in_progress = in_progress_matches.count or 0

        # Get priority distribution of active jobs
        jobs_response = await supabase_client.table("jobs").select(
            "priority"
        ).eq("status", "open").execute()
        jobs = jobs_response.data or []
        priority_dist = {}
        for priority_level in range(1, 6):
            priority_dist[f"priority_{priority_level}"] = len([
                j for j in jobs
                if str(j.get("priority", "")).isdigit() and int(j.get("priority", 0)) == priority_level
            ])

        system_summary = SystemSummary(
            total_active_jobs=total_active_jobs,
            total_pending_candidates=total_pending_candidates,
            total_matches_in_progress=total_matches_in_progress,
            priority_distribution=priority_dist,
        )

        # ===== CARMIT STATUS =====
        # Get recent routing logs from agent_logs
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = today - timedelta(days=7)

        carmit_logs_response = await supabase_client.table("agent_logs").select(
            "*"
        ).gte("created_at", today.isoformat()).order("created_at", desc=True).limit(1).execute()

        carmit_logs = carmit_logs_response.data or []
        last_routing_log = carmit_logs[0] if carmit_logs else None

        jobs_routed_today = len(
            [
                l
                for l in (
                    await supabase_client.table("agent_logs").select(
                        "*"
                    ).eq("action", "job_routing").gte("created_at", today.isoformat()).execute()
                ).data
                or []
            ]
        )

        jobs_routed_week = len(
            [
                l
                for l in (
                    await supabase_client.table("agent_logs").select(
                        "*"
                    ).eq("action", "job_routing").gte("created_at", week_ago.isoformat()).execute()
                ).data
                or []
            ]
        )

        # Calculate average routing confidence
        confidence_values = []
        if jobs_routed_week > 0:
            routing_logs = (
                await supabase_client.table("agent_logs").select(
                    "*"
                ).eq("action", "job_routing").gte("created_at", week_ago.isoformat()).execute()
            ).data or []
            for log in routing_logs:
                details = log.get("details", {})
                confidence = details.get("confidence", 0.5)
                confidence_values.append(float(confidence))

        avg_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else 0.0
        )

        carmit_status = CarmitStatus(
            status="idle",  # TODO: Can enhance this with a carmit_state table if needed
            last_action=f"Routed job to agent {last_routing_log.get('agent_code', 'N/A')}"
            if last_routing_log
            else "No recent activity",
            last_action_at=last_routing_log.get("created_at") if last_routing_log else None,
            jobs_routed_today=jobs_routed_today,
            jobs_routed_this_week=jobs_routed_week,
            average_routing_confidence=avg_confidence,
        )

        # ===== AGENT STATUSES =====
        agent_statuses = []
        for agent_code, agent_config in AGENT_CONFIGS.items():
            # Get agent runtime state
            agent_state_response = await supabase_client.table(
                "agent_runtime_state"
            ).select("*").eq("agent_code", agent_code).execute()
            agent_state = (
                agent_state_response.data[0] if agent_state_response.data else {}
            )

            # Get matches created today
            matches_today = len(
                [
                    m
                    for m in (
                        await supabase_client.table("matches").select(
                            "*"
                        ).eq("matched_by_agent_code", agent_code).gte(
                            "created_at", today.isoformat()
                        ).execute()
                    ).data
                    or []
                ]
            )

            # Get matches created this week
            matches_week = len(
                [
                    m
                    for m in (
                        await supabase_client.table("matches").select(
                            "*"
                        ).eq("matched_by_agent_code", agent_code).gte(
                            "created_at", week_ago.isoformat()
                        ).execute()
                    ).data
                    or []
                ]
            )

            # Get success rate from agent logs
            logs_today_response = await supabase_client.table("agent_logs").select(
                "*"
            ).eq("agent_code", agent_code).gte("created_at", today.isoformat()).execute()
            logs_today = logs_today_response.data or []
            successful = len([l for l in logs_today if l.get("status") == "success"])
            success_rate = (successful / len(logs_today)) if logs_today else 1.0

            # Determine workload
            current_job = agent_state.get("current_job_id")
            workload = "medium" if current_job else "light"

            agent_statuses.append(
                AgentStatus(
                    agent_code=agent_code,
                    agent_name=agent_config["name"],
                    domain=agent_config["domain"],
                    status=agent_state.get("status", "idle"),
                    current_task=agent_state.get("current_task_description"),
                    current_job_id=current_job,
                    progress="Evaluating candidates..."
                    if current_job
                    else "Ready for next assignment",
                    matches_found_today=matches_today,
                    matches_found_week=matches_week,
                    last_active_at=agent_state.get("last_active_at"),
                    next_scheduled_check=agent_state.get("next_scheduled_at"),
                    workload=workload,
                    success_rate_today=success_rate,
                )
            )

        # ===== RECENT ACTIVITIES =====
        activities_response = await supabase_client.table("agent_logs").select(
            "*"
        ).order("created_at", desc=True).limit(20).execute()
        activities_data = activities_response.data or []

        recent_activities = []
        for log in activities_data:
            activity_type = log.get("action", "unknown")
            timestamp = log.get("created_at", datetime.utcnow().isoformat())

            activity = Activity(
                timestamp=timestamp,
                type=activity_type,
                agent_code=log.get("agent_code"),
                job_title=None,  # Will be populated based on related data
                match_score=None,
                status=log.get("status"),
            )

            # Enrich based on action type
            if activity_type == "find_match":
                output = log.get("output_payload", {})
                activity.match_score = output.get("score")
            elif activity_type == "job_routing":
                details = log.get("details", {})
                activity.job_title = details.get("job_title")

            recent_activities.append(activity)

        # ===== MATCHES IN PROGRESS =====
        # Get matches in relevant states (excluding completed/rejected)
        matches_in_progress_response = await supabase_client.table("matches").select(
            "*, candidates(id,name), jobs(id,job_title)"
        ).in_("current_state", ["found", "carmit_approved", "sent_to_tal"]).eq(
            "is_valid", True
        ).order(
            "created_at", desc=True
        ).limit(100).execute()

        matches_data = matches_in_progress_response.data or []
        matches_in_progress = []

        for match in matches_data:
            candidate_name = (
                match.get("candidates", {}).get("name")
                or "Unknown"
            )
            job_title = match.get("jobs", {}).get("job_title", "Unknown")

            match_obj = MatchInProgress(
                candidate_id=match.get("candidate_id", ""),
                candidate_name=candidate_name,
                job_id=match.get("job_id", ""),
                job_title=job_title,
                agent_handling=match.get("matched_by_agent_code", ""),
                status=match.get("current_state", "found"),
                score=float(match.get("match_score", 0)),
                created_at=match.get("created_at", ""),
                last_updated_at=match.get("state_updated_at", ""),
                next_review_at=(
                    (datetime.utcnow() + timedelta(minutes=15)).isoformat()
                    if match.get("current_state") == "found"
                    else None
                ),
            )
            matches_in_progress.append(match_obj)

        # ===== RECENT JOB CHANGES (Phase 4E) =====
        recent_job_changes = []
        change_detection_metrics = ChangeDetectionMetrics()

        try:
            # Fetch recent job changes (last 24 hours)
            from_date = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            changes_response = await supabase_client.table("job_changes").select(
                "*, jobs(id, title)"
            ).gte("changed_at", from_date).order("changed_at", desc=True).limit(20).execute()

            changes_data = changes_response.data or []

            # Build recent job changes list
            for change in changes_data:
                job_title = change.get("jobs", {}).get("title", "Unknown")
                fields_changed = change.get("fields_changed", [])
                affected_count = change.get("affected_matches_count", 0)

                change_obj = JobChange(
                    job_id=change.get("job_id", ""),
                    job_title=job_title,
                    change_type=change.get("change_type", "modified"),
                    changed_at=change.get("changed_at", ""),
                    fields_changed=fields_changed,
                    matches_invalidated=affected_count,
                    rematch_status="completed"  # Assume completed after record created
                )
                recent_job_changes.append(change_obj)

            # Calculate change detection metrics for today
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            today_changes = [c for c in changes_data if c.get("changed_at", "") >= today_start]

            total_invalidated_today = sum(c.get("affected_matches_count", 0) for c in today_changes)
            total_changes_today = len(today_changes)

            change_detection_metrics = ChangeDetectionMetrics(
                matches_invalidated_today=total_invalidated_today,
                rematches_triggered_today=total_changes_today,
                avg_matches_per_change=(
                    total_invalidated_today / total_changes_today
                    if total_changes_today > 0
                    else 0.0
                ),
                total_job_changes_today=total_changes_today
            )

        except Exception as changes_error:
            logger.warning(f"Failed to fetch job changes: {changes_error}")
            # Don't fail the endpoint if job changes fetch fails

        # ===== RETURN SYSTEM STATUS =====
        return SystemStatus(
            timestamp=datetime.utcnow().isoformat(),
            system_summary=system_summary,
            carmit_status=carmit_status,
            agent_statuses=agent_statuses,
            recent_activities=recent_activities,
            matches_in_progress=matches_in_progress,
            recent_job_changes=recent_job_changes,
            change_detection_metrics=change_detection_metrics,
        )

    except Exception as e:
        logger.error(f"Error fetching system status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve system status: {str(e)}")


# ============================================================================
# Phase 4D: Job Change Detection & Re-Matching Endpoint
# ============================================================================


class InvalidateRematchRequest(BaseModel):
    """Request to invalidate matches and trigger re-matching for a job."""

    reason: str = "manual_rematch_request"
    previous_values: Optional[dict] = None
    requested_by: str = "manual_api"
    notes: Optional[str] = None


class InvalidationStats(BaseModel):
    """Statistics about match invalidation."""

    total_invalidated: int
    states_affected: dict
    protected_states_count: Optional[int] = 0


class InvalidateRematchResponse(BaseModel):
    """Response from invalidate-and-rematch endpoint."""

    status: str  # "success" or "error"
    job_id: str
    invalidation_stats: Optional[InvalidationStats] = None
    rematch_triggered: Optional[dict] = None
    error: Optional[str] = None


@router.post(
    "/jobs/{job_id}/invalidate-and-rematch",
    response_model=InvalidateRematchResponse,
    summary="Invalidate job matches and trigger re-matching",
    tags=["job-management", "change-detection"]
)
async def invalidate_and_rematch_job(
    job_id: str,
    request: InvalidateRematchRequest,
    supabase_client = Depends(get_supabase_client),
):
    """
    Manually invalidate all existing matches for a job and trigger re-matching.

    This endpoint is used when:
    - A job's specifications were updated externally (not via Pipedrive)
    - Job was modified via direct database update (bypassing sync)
    - User wants to force re-evaluation of all candidates for a job
    - Job priority or requirements changed and matches need re-scoring

    **Process:**
    1. Fetch current job details
    2. Mark all valid matches as invalid (except protected states)
    3. Record change in job_changes history table
    4. Queue re-matching task for the assigned agent
    5. Return invalidation statistics

    **Protected States:**
    - Matches in "sent_to_tal" or "tal_approved" states are NOT invalidated
    - These matches have already entered the recruitment pipeline

    **Response:**
    - invalidation_stats: How many matches were invalidated by state
    - rematch_triggered: Status of queued re-matching task
    - timestamp: When the operation completed

    **Error Handling:**
    - Returns 404 if job not found
    - Returns 400 if job not yet assigned to agent
    - Returns 500 for database errors

    Example:
    ```bash
    POST /admin/agent-matching/jobs/uuid/invalidate-and-rematch
    {
      "reason": "priority_increased",
      "previous_values": {"priority": 3},
      "requested_by": "user@example.com",
      "notes": "User updated priority from 3 to 1"
    }
    ```
    """
    try:
        logger.info(
            f"Invalidate-and-rematch request for job {job_id} "
            f"(reason: {request.reason}, requested_by: {request.requested_by})"
        )

        # Fetch current job
        try:
            job_response = supabase_client.table("jobs").select("*").eq(
                "id", job_id
            ).single().execute()
            job = job_response.data
        except Exception as fetch_error:
            logger.warning(f"Job {job_id} not found: {fetch_error}")
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found"
            )

        # Check if job is assigned to an agent
        agent_code = job.get("assigned_agent_code")
        if not agent_code:
            logger.warning(f"Job {job_id} not assigned to any agent yet")
            raise HTTPException(
                status_code=400,
                detail="Job is not yet assigned to an agent. Carmit will assign it during next routing cycle."
            )

        # Invalidate all matches for this job
        worker = AgentMatchingWorker(supabase_client, None)  # Don't need Claude client for invalidation
        invalidation_stats = await worker.invalidate_matches_for_job_change(
            job_id=job_id,
            change_reason=request.reason,
            previous_values=request.previous_values or {},
            new_values={},  # Empty for manual requests (we don't know what changed)
            invalidated_by=request.requested_by
        )

        # Trigger re-matching for this job
        rematch_result = await worker.trigger_job_rematching(job_id)

        logger.info(
            f"Successfully invalidated {invalidation_stats.get('total_invalidated', 0)} matches "
            f"and queued re-matching for job {job_id}"
        )

        return InvalidateRematchResponse(
            status="success",
            job_id=job_id,
            invalidation_stats=InvalidationStats(
                total_invalidated=invalidation_stats.get("total_invalidated", 0),
                states_affected=invalidation_stats.get("states_affected", {}),
                protected_states_count=invalidation_stats.get("protected_states_count", 0)
            ),
            rematch_triggered=rematch_result
        )

    except HTTPException:
        # Re-raise HTTP exceptions (404, 400, etc.)
        raise
    except Exception as e:
        logger.error(
            f"Error invalidating and re-matching job {job_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to invalidate and re-match job: {str(e)}"
        )


# ============================================================================
# Carmit Orchestrator Endpoints
# ============================================================================

class CarmitKPISummary(BaseModel):
    """KPI summary for Carmit orchestrator."""
    jobs_routed_today: int
    jobs_routed_this_week: int
    current_status: str  # "idle" or "processing"
    last_active_at: Optional[str] = None
    next_scheduled_at: Optional[str] = None
    average_routing_confidence: float = 0.0


class JobsToRouteResponse(BaseModel):
    """Response containing jobs waiting to be routed."""
    total_waiting: int
    jobs: list = []
    timestamp: str


class JobToRoute(BaseModel):
    """A job waiting to be routed to an agent."""
    id: str
    title: str
    description: Optional[str] = None
    priority: int
    qualifications: Optional[str] = None
    created_at: str
    is_active: bool


@router.get("/carmit/kpi-summary", response_model=CarmitKPISummary)
async def get_carmit_kpi_summary(
    supabase_client=Depends(get_supabase_client),
) -> CarmitKPISummary:
    """Get Carmit orchestrator KPI summary.

    Shows routing statistics and current status of the Carmit orchestrator.
    """
    try:
        from datetime import timedelta

        # Get Carmit's agent_runtime_state
        carmit_state_response = await supabase_client.table("agent_runtime_state").select(
            "*"
        ).eq("agent_code", "carmit_orchestrator").single().execute()

        carmit_state = carmit_state_response.data or {}

        # Calculate time periods
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = today - timedelta(days=7)

        # Get today's routing count
        jobs_routed_today_response = await supabase_client.table("agent_logs").select(
            "count", count="exact"
        ).eq("agent_code", "carmit_orchestrator").eq("action", "route_job").gte(
            "created_at", today.isoformat()
        ).execute()
        jobs_routed_today = jobs_routed_today_response.count or 0

        # Get week's routing count
        jobs_routed_week_response = await supabase_client.table("agent_logs").select(
            "count", count="exact"
        ).eq("agent_code", "carmit_orchestrator").eq("action", "route_job").gte(
            "created_at", week_ago.isoformat()
        ).execute()
        jobs_routed_week = jobs_routed_week_response.count or 0

        # Get average routing confidence from recent logs
        routing_logs_response = await supabase_client.table("agent_logs").select(
            "output_payload"
        ).eq("agent_code", "carmit_orchestrator").eq("action", "route_job").gte(
            "created_at", week_ago.isoformat()
        ).order("created_at", desc=True).limit(20).execute()

        routing_logs = routing_logs_response.data or []
        confidence_values = []
        for log in routing_logs:
            payload = log.get("output_payload", {})
            confidence = payload.get("routing_confidence", payload.get("confidence", 0.75))
            if isinstance(confidence, (int, float)):
                confidence_values.append(float(confidence))

        avg_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else 0.75
        )

        return CarmitKPISummary(
            jobs_routed_today=jobs_routed_today,
            jobs_routed_this_week=jobs_routed_week,
            current_status=carmit_state.get("status", "idle"),
            last_active_at=carmit_state.get("last_active_at"),
            next_scheduled_at=carmit_state.get("next_scheduled_at"),
            average_routing_confidence=avg_confidence,
        )

    except Exception as e:
        logger.error(f"Error fetching Carmit KPI summary: {e}", exc_info=True)
        # Return default values on error rather than failing
        return CarmitKPISummary(
            jobs_routed_today=0,
            jobs_routed_this_week=0,
            current_status="error",
            average_routing_confidence=0.0,
        )


@router.get("/carmit/jobs-to-route", response_model=JobsToRouteResponse)
async def get_jobs_to_route(
    limit: int = 20,
    supabase_client=Depends(get_supabase_client),
) -> JobsToRouteResponse:
    """Get jobs waiting to be routed by Carmit.

    Returns open jobs without assigned agents, ordered by priority.
    These jobs are waiting for Carmit to process and assign to agents.

    Args:
        limit: Maximum number of jobs to return
    """
    try:
        # Get open jobs without assigned agents, ordered by priority
        # Note: jobs table uses 'status' field (default 'open') not 'is_active'
        # and doesn't have 'assigned_agent_code' - that's in separate matching logic
        unassigned_jobs_response = await supabase_client.table("jobs").select(
            "id, job_title, job_description, priority, job_qualifications, created_at, status"
        ).eq("status", "open").order("priority", desc=True).limit(limit).execute()

        jobs_data = unassigned_jobs_response.data or []
        jobs_to_route = []

        for job in jobs_data:
            jobs_to_route.append({
                "id": job["id"],
                "title": job.get("job_title", "Untitled Job"),
                "description": job.get("job_description"),
                "priority": int(job.get("priority", 5)) if isinstance(job.get("priority"), (int, str)) else 5,
                "qualifications": job.get("job_qualifications"),
                "created_at": job["created_at"],
                "is_active": job.get("status") == "open",
            })

        return JobsToRouteResponse(
            total_waiting=len(jobs_to_route),
            jobs=jobs_to_route,
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Error fetching jobs to route: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve jobs: {str(e)}"
        )


@router.get("/all-jobs-with-assignments")
async def get_all_jobs_with_assignments(
    limit: int = 500,
    offset: int = 0,
    supabase_client=Depends(get_supabase_client),
) -> dict:
    """Get all jobs with their Carmit assignments and routing history.

    Returns all jobs including:
    - Jobs routed to agents
    - Jobs awaiting routing
    - Job metadata and timestamps

    Args:
        limit: Maximum number of jobs to return
        offset: Pagination offset
    """
    try:
        # Fetch all jobs ordered by creation date (newest first)
        # First, try to fetch with wildcard to see all available columns
        jobs_response = await supabase_client.table("jobs").select("*").order("created_at", desc=True).range(offset, offset + limit - 1).execute()

        jobs_data = jobs_response.data or []
        jobs_with_assignments = []

        for job in jobs_data:
            # Try assigned_agent_code first, fall back to agent_code if it doesn't exist
            agent_code = job.get("assigned_agent_code") or job.get("agent_code")

            # Get agent name in Hebrew if available
            agent_name = None
            if agent_code:
                agent_config = AGENT_CONFIGS.get(agent_code)
                if agent_config:
                    agent_name = agent_config.get("name_he", agent_code)
                else:
                    agent_name = agent_code

            jobs_with_assignments.append({
                "id": job["id"],
                "title": job.get("job_title", "Untitled"),
                "description": job.get("job_description"),
                "priority": int(job.get("priority", 5)) if isinstance(job.get("priority"), (int, str)) else 5,
                "status": job.get("status", "unknown"),
                "assigned_agent_code": agent_code,
                "assigned_agent_name": agent_name,
                "contact_person_name": job.get("contact_person_name"),  # New field: Contact person name
                "job_opening_date": job.get("job_opening_date"),  # New field: Job opening date
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "is_routed": agent_code is not None,
            })

        return {
            "total": len(jobs_with_assignments),
            "jobs": jobs_with_assignments,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error fetching all jobs with assignments: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve jobs: {str(e)}"
        )


class OverrideJobAssignmentRequest(BaseModel):
    """Request to override a job's agent assignment."""

    job_id: str
    new_agent_code: str
    override_reason: str = "manual_override"
    override_user_id: Optional[str] = None


@router.post("/override-job-assignment")
async def override_job_assignment(
    request: OverrideJobAssignmentRequest,
    supabase_client=Depends(get_supabase_client),
) -> dict:
    """Override Carmit's job assignment and assign to a different agent.

    When a user overrides the agent assignment:
    1. Updates the job to be assigned to the new agent (via RPC to bypass schema cache)
    2. Deletes all matches created by the previous agent for this job
    3. Triggers a new matching task for the new agent with this job
    4. Logs the override action for audit trail

    Args:
        job_id: ID of the job to reassign
        new_agent_code: Code of the new agent to assign the job to
        override_reason: Reason for the override (default: manual_override)
        override_user_id: User ID who initiated the override
    """
    try:
        # Fetch the current job to get old agent and other details
        job_response = await supabase_client.table("jobs").select("*").eq(
            "id", request.job_id
        ).single().execute()

        if not job_response.data:
            raise HTTPException(status_code=404, detail="Job not found")

        job = job_response.data
        old_agent_code = job.get("assigned_agent_code")

        # Update job with new agent assignment using RPC function
        # This bypasses Supabase schema cache issues by using a stored procedure
        try:
            rpc_response = await supabase_client.rpc(
                "override_job_assignment",
                {
                    "p_job_id": request.job_id,
                    "p_new_agent_code": request.new_agent_code,
                    "p_updated_at": datetime.utcnow().isoformat(),
                }
            ).execute()

            # Check if RPC was successful
            if not rpc_response.data:
                raise Exception("RPC returned no data")

            # The RPC returns an array with one row
            rpc_result = rpc_response.data[0] if isinstance(rpc_response.data, list) else rpc_response.data

            if not rpc_result.get("success"):
                raise Exception(f"RPC failed: {rpc_result.get('message', 'Unknown error')}")

            logger.info(f"Job {request.job_id} assigned to {request.new_agent_code}, old agent: {rpc_result.get('old_agent_code')}")

        except Exception as rpc_error:
            logger.error(f"RPC error: {rpc_error}", exc_info=True)
            raise Exception(f"Failed to update job assignment: {str(rpc_error)}")

        # Delete all matches created by the old agent for this job
        if old_agent_code:
            delete_response = await supabase_client.table("matches").delete().eq(
                "job_id", request.job_id
            ).eq("matched_by_agent_code", old_agent_code).eq(
                "current_state", "found"  # Only delete "found" state matches
            ).execute()

            logger.info(f"Deleted {len(delete_response.data) if delete_response.data else 0} matches for job {request.job_id} from agent {old_agent_code}")

        # Log the override action to agent_logs
        try:
            await supabase_client.table("agent_logs").insert({
                "agent_code": "carmit_orchestrator",
                "action": "override_assignment",
                "related_job_id": request.job_id,
                "output_payload": {
                    "old_agent_code": old_agent_code,
                    "new_agent_code": request.new_agent_code,
                    "override_reason": request.override_reason,
                    "override_user_id": request.override_user_id,
                    "job_title": job.get("title"),
                }
            }).execute()
        except Exception as log_error:
            logger.warning(f"Failed to log override action: {log_error}")

        # Trigger matching task for new agent with this job
        from pandapower.workers.tasks import match_job_candidates_task
        match_job_candidates_task.delay(request.job_id, request.new_agent_code)

        # Log for the new agent
        try:
            await supabase_client.table("agent_logs").insert({
                "agent_code": request.new_agent_code,
                "action": "receive_job_override",
                "related_job_id": request.job_id,
                "output_payload": {
                    "previous_agent": old_agent_code,
                    "reason": request.override_reason,
                    "job_title": job.get("title"),
                }
            }).execute()
        except Exception as log_error:
            logger.warning(f"Failed to log new agent assignment: {log_error}")

        return {
            "status": "success",
            "job_id": request.job_id,
            "previous_agent": old_agent_code,
            "new_agent": request.new_agent_code,
            "message": f"Successfully reassigned job from {old_agent_code or 'unassigned'} to {request.new_agent_code}",
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error overriding job assignment: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to override job assignment: {str(e)}"
        )
