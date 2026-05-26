"""Analytics endpoints for PandaPower dashboard."""
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Response Models
# ============================================================================

class KPISummaryResponse(BaseModel):
    """KPI summary metrics."""
    total_hired: int
    placement_rate: float  # 0-1
    pending_matches: int
    avg_time_to_hire_days: float
    active_conversations: int
    failed_matches: int
    failure_rate: float  # 0-1


class RecruiterPerformanceMetric(BaseModel):
    """Per-recruiter performance metrics."""
    recruiter_name: str  # 'tal' or 'elad'
    conversations_count: int
    approvals_count: int
    approval_rate: float  # 0-1
    hires_count: int
    hire_rate: float  # hires / approvals
    avg_days_in_stage: float
    queue_count: int
    workload_pct: float  # percentage of total workload


class RecruiterPerformanceResponse(BaseModel):
    """Response for recruiter performance."""
    data: list[RecruiterPerformanceMetric]


class MatchFunnelResponse(BaseModel):
    """Match funnel metrics."""
    found: int
    carmit_approved: int
    sent_to_recruiter: int
    recruiter_approved: int
    hired: int
    failed: int
    conversion_rate: float  # hired / found


class TimeToPlacementPoint(BaseModel):
    """Single point in time-to-placement timeline."""
    date: str  # ISO format
    avg_days: float
    hires_count: int
    failed_count: int


class TimeToPlacementResponse(BaseModel):
    """Response for time-to-placement data."""
    data: list[TimeToPlacementPoint]


class RejectionReasonMetric(BaseModel):
    """Rejection reason breakdown."""
    rejection_stage: str  # e.g., 'carmit_quality_gate', 'tal_rejected'
    reason: str  # e.g., 'Match score too low'
    count: int
    percentage: float  # 0-100


class RejectionReasonsResponse(BaseModel):
    """Response for rejection reasons."""
    data: list[RejectionReasonMetric]


class AgentPerformanceMetric(BaseModel):
    """Per-agent performance metrics."""
    agent_code: str
    matches_found: int
    matches_approved: int
    approval_rate: float  # 0-1
    placements: int
    placement_rate: float  # 0-1
    avg_score: float  # 0-1


class AgentPerformanceResponse(BaseModel):
    """Response for agent performance."""
    data: list[AgentPerformanceMetric]


# ============================================================================
# Helper Functions
# ============================================================================

def get_date_range(period: str) -> tuple[datetime, datetime]:
    """Convert period string to date range."""
    end_date = datetime.utcnow().date()

    if period == "week":
        start_date = end_date - timedelta(days=7)
    elif period == "month":
        start_date = end_date - timedelta(days=30)
    elif period == "quarter":
        start_date = end_date - timedelta(days=90)
    elif period == "year":
        start_date = end_date - timedelta(days=365)
    else:
        # Default to month
        start_date = end_date - timedelta(days=30)

    return datetime.combine(start_date, datetime.min.time()), datetime.combine(end_date, datetime.max.time())


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/admin/analytics/kpi-summary", response_model=KPISummaryResponse)
async def get_kpi_summary(
    period: str = Query("month", description="Time period: week, month, quarter, year")
) -> KPISummaryResponse:
    """
    Get KPI summary metrics for the selected period.

    Returns:
    - total_hired: Total candidates hired
    - placement_rate: Percentage of matches that resulted in hire
    - pending_matches: Matches awaiting recruiter or elad decision
    - avg_time_to_hire_days: Average days from match creation to hire
    - active_conversations: Ongoing recruiter conversations
    - failed_matches: Matches that failed
    - failure_rate: Percentage of matches that failed
    """
    start_date, end_date = get_date_range(period)

    logger.info(f"Fetching KPI summary for period {period} ({start_date} to {end_date})")

    # This will be populated from database queries in implementation
    # For now, return mock data
    return KPISummaryResponse(
        total_hired=42,
        placement_rate=0.68,
        pending_matches=15,
        avg_time_to_hire_days=12.5,
        active_conversations=8,
        failed_matches=19,
        failure_rate=0.32,
    )


@router.get("/admin/analytics/recruiter-performance", response_model=RecruiterPerformanceResponse)
async def get_recruiter_performance(
    recruiter: Optional[str] = Query(None, description="Filter by recruiter: 'tal' or 'elad'"),
    period: str = Query("month", description="Time period: week, month, quarter, year"),
) -> RecruiterPerformanceResponse:
    """
    Get recruiter performance metrics.

    Returns per-recruiter metrics:
    - conversations_count: Number of conversations conducted
    - approvals_count: Number of approvals given
    - approval_rate: Percentage of reviews that resulted in approval
    - hires_count: Number of successful hires
    - hire_rate: Percentage of approvals that resulted in hire
    - avg_days_in_stage: Average time match stays in recruiter's queue
    - queue_count: Current items awaiting decision
    - workload_pct: Percentage of total workload assigned to this recruiter
    """
    start_date, end_date = get_date_range(period)

    logger.info(f"Fetching recruiter performance for {recruiter or 'all'} in period {period}")

    # Mock data - will be populated from database queries
    data = [
        RecruiterPerformanceMetric(
            recruiter_name="tal",
            conversations_count=24,
            approvals_count=18,
            approval_rate=0.75,
            hires_count=12,
            hire_rate=0.67,
            avg_days_in_stage=3.2,
            queue_count=5,
            workload_pct=45,
        ),
        RecruiterPerformanceMetric(
            recruiter_name="elad",
            conversations_count=20,
            approvals_count=17,
            approval_rate=0.85,
            hires_count=14,
            hire_rate=0.82,
            avg_days_in_stage=2.8,
            queue_count=3,
            workload_pct=38,
        ),
    ]

    # Filter by recruiter if specified
    if recruiter:
        data = [m for m in data if m.recruiter_name == recruiter.lower()]

    return RecruiterPerformanceResponse(data=data)


@router.get("/admin/analytics/match-funnel", response_model=MatchFunnelResponse)
async def get_match_funnel(
    period: str = Query("month", description="Time period: week, month, quarter, year")
) -> MatchFunnelResponse:
    """
    Get match funnel metrics showing drop-off at each stage.

    Flow:
    found → carmit_approved → sent_to_recruiter → recruiter_approved → hired
                           ↘ carmit_rejected                        ↘ failed

    Returns conversion rate: hired / found
    """
    start_date, end_date = get_date_range(period)

    logger.info(f"Fetching match funnel for period {period}")

    # Mock data
    return MatchFunnelResponse(
        found=100,
        carmit_approved=68,
        sent_to_recruiter=68,
        recruiter_approved=45,
        hired=32,
        failed=36,
        conversion_rate=0.32,
    )


@router.get("/admin/analytics/time-to-placement", response_model=TimeToPlacementResponse)
async def get_time_to_placement(
    days: int = Query(90, description="Number of days to include in analysis"),
) -> TimeToPlacementResponse:
    """
    Get time-to-placement trends over time.

    Returns daily metrics:
    - date: ISO format date
    - avg_days: Average days from match creation to hire on that date
    - hires_count: Number of hires completed that day
    - failed_count: Number of failed matches that day
    """
    end_date = datetime.utcnow().date()
    start_date = (end_date - timedelta(days=days)).date()

    logger.info(f"Fetching time-to-placement for {days} days")

    # Generate mock data for each day
    data = []
    current_date = start_date
    while current_date <= end_date:
        data.append(
            TimeToPlacementPoint(
                date=current_date.isoformat(),
                avg_days=12.5 + (current_date.day % 5),  # Mock variation
                hires_count=3 + (current_date.day % 4),
                failed_count=2 + (current_date.day % 3),
            )
        )
        current_date += timedelta(days=1)

    return TimeToPlacementResponse(data=data)


@router.get("/admin/analytics/rejection-reasons", response_model=RejectionReasonsResponse)
async def get_rejection_reasons(
    period: str = Query("month", description="Time period: week, month, quarter, year")
) -> RejectionReasonsResponse:
    """
    Get breakdown of rejection reasons by stage.

    Returns reasons like:
    - carmit_quality_gate: Match score too low
    - carmit_clearance_gate: Insufficient clearance
    - tal_rejected: Recruiter rejected during conversation
    - elad_rejected: Final placement failed
    """
    start_date, end_date = get_date_range(period)

    logger.info(f"Fetching rejection reasons for period {period}")

    # Mock data
    data = [
        RejectionReasonMetric(
            rejection_stage="carmit_quality_gate",
            reason="Match score too low",
            count=12,
            percentage=25.5,
        ),
        RejectionReasonMetric(
            rejection_stage="carmit_clearance_gate",
            reason="Insufficient security clearance",
            count=8,
            percentage=17.0,
        ),
        RejectionReasonMetric(
            rejection_stage="tal_rejected",
            reason="Candidate not interested",
            count=15,
            percentage=31.9,
        ),
        RejectionReasonMetric(
            rejection_stage="elad_rejected",
            reason="Salary negotiation failed",
            count=9,
            percentage=19.1,
        ),
        RejectionReasonMetric(
            rejection_stage="elad_rejected",
            reason="Candidate accepted other offer",
            count=3,
            percentage=6.4,
        ),
    ]

    return RejectionReasonsResponse(data=data)


@router.get("/admin/analytics/agent-performance", response_model=AgentPerformanceResponse)
async def get_agent_performance() -> AgentPerformanceResponse:
    """
    Get agent performance metrics.

    Returns per-agent metrics:
    - agent_code: Agent identifier (naama, ofir, alik, etc.)
    - matches_found: Total matches found by agent
    - matches_approved: Matches that passed Carmit review
    - approval_rate: Percentage of agent's matches approved by Carmit
    - placements: Number of successful placements
    - placement_rate: Percentage of approved matches that resulted in hire
    - avg_score: Average match score given by agent
    """
    logger.info("Fetching agent performance metrics")

    # Mock data
    data = [
        AgentPerformanceMetric(
            agent_code="naama",
            matches_found=45,
            matches_approved=30,
            approval_rate=0.67,
            placements=20,
            placement_rate=0.67,
            avg_score=0.78,
        ),
        AgentPerformanceMetric(
            agent_code="ofir",
            matches_found=38,
            matches_approved=26,
            approval_rate=0.68,
            placements=18,
            placement_rate=0.69,
            avg_score=0.76,
        ),
        AgentPerformanceMetric(
            agent_code="alik",
            matches_found=32,
            matches_approved=22,
            approval_rate=0.69,
            placements=15,
            placement_rate=0.68,
            avg_score=0.74,
        ),
        AgentPerformanceMetric(
            agent_code="dganit",
            matches_found=28,
            matches_approved=18,
            approval_rate=0.64,
            placements=11,
            placement_rate=0.61,
            avg_score=0.72,
        ),
    ]

    return AgentPerformanceResponse(data=data)
