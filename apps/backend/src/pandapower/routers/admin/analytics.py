"""Analytics endpoints for PandaPower dashboard.

All metrics are computed from real data in the `matches` table (and related
tables). The pipeline state machine is:

    found → carmit_approved → sent_to_tal → tal_conversation → tal_approved
          → sent_to_elad → elad_conversation → offer_sent → hired
    (rejections: carmit_rejected, tal_rejected, elad_rejected, placement_failed)
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client

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
# State machine groupings
# ============================================================================

# Every state that means the match got past Carmit's gate (i.e. was approved
# by Carmit at some point, regardless of where it ended up).
PASSED_CARMIT = {
    "carmit_approved", "sent_to_tal", "tal_conversation", "tal_approved",
    "sent_to_elad", "elad_conversation", "offer_sent", "hired",
    "tal_rejected", "elad_rejected", "placement_failed",
}
# States that reached (or passed) Tal / the first recruiter.
REACHED_RECRUITER = {
    "sent_to_tal", "tal_conversation", "tal_approved",
    "sent_to_elad", "elad_conversation", "offer_sent", "hired",
    "tal_rejected", "elad_rejected", "placement_failed",
}
# States where the recruiter (Tal) approved and pushed the candidate onward.
RECRUITER_APPROVED = {
    "tal_approved", "sent_to_elad", "elad_conversation", "offer_sent",
    "hired", "elad_rejected", "placement_failed",
}
# States that reached / passed Elad.
REACHED_ELAD = {
    "sent_to_elad", "elad_conversation", "offer_sent",
    "hired", "elad_rejected", "placement_failed",
}
# Elad effectively approved (sent an offer to the client).
ELAD_APPROVED = {"offer_sent", "hired", "placement_failed"}

FAILED_STATES = {"carmit_rejected", "tal_rejected", "elad_rejected", "placement_failed"}
TERMINAL_STATES = {"hired"} | FAILED_STATES
# Excluded from the pipeline: sub-70 agent evaluations kept only for visibility.
NON_PIPELINE_STATES = {"evaluated_but_rejected"}

ACTIVE_CONVERSATION_STATES = {"tal_conversation", "elad_conversation"}

REASON_COLUMN_BY_STATE = {
    "carmit_rejected": "carmit_blocked_reason",
    "tal_rejected": "tal_decision_reason",
    "elad_rejected": "tal_decision_reason",
    "placement_failed": "tal_decision_reason",
}

REJECTION_STAGE_LABEL = {
    "carmit_rejected": "carmit_review",
    "tal_rejected": "tal_rejected",
    "elad_rejected": "elad_rejected",
    "placement_failed": "placement_failed",
}


# ============================================================================
# Helper Functions
# ============================================================================

def get_date_range(period: str) -> tuple[datetime, datetime]:
    """Convert period string to UTC datetime range (inclusive)."""
    end_date = datetime.now(timezone.utc).date()

    if period == "week":
        start_date = end_date - timedelta(days=7)
    elif period == "month":
        start_date = end_date - timedelta(days=30)
    elif period == "quarter":
        start_date = end_date - timedelta(days=90)
    elif period == "year":
        start_date = end_date - timedelta(days=365)
    else:
        start_date = end_date - timedelta(days=30)

    start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
    return start, end


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp from Supabase into a tz-aware datetime."""
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


async def _fetch_matches(
    supabase: Any,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> list[dict]:
    """Fetch all valid matches (paginated) with the columns analytics needs.

    When start/end are provided, filters by created_at within the range.
    """
    columns = (
        "id, current_state, match_score, matched_by_agent_code, created_at, "
        "state_updated_at, evaluated_score_raw, carmit_blocked_reason, "
        "tal_decision_reason"
    )
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        query = supabase.table("matches").select(columns).eq("is_valid", True)
        if start_date is not None:
            query = query.gte("created_at", start_date.isoformat())
        if end_date is not None:
            query = query.lte("created_at", end_date.isoformat())
        result = await query.order("created_at", desc=True).range(
            offset, offset + page_size - 1
        ).execute()
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _days_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if start is None or end is None:
        return None
    delta = end - start
    return max(delta.total_seconds() / 86400.0, 0.0)


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/admin/analytics/kpi-summary", response_model=KPISummaryResponse)
async def get_kpi_summary(
    period: str = Query("month", description="Time period: week, month, quarter, year"),
    supabase: Any = Depends(get_supabase_client),
) -> KPISummaryResponse:
    """Get KPI summary metrics for the selected period (computed from matches)."""
    start_date, end_date = get_date_range(period)
    logger.info(f"Fetching KPI summary for period {period} ({start_date} to {end_date})")

    matches = await _fetch_matches(supabase, start_date, end_date)
    pipeline = [m for m in matches if m.get("current_state") not in NON_PIPELINE_STATES]
    total = len(pipeline)

    hired = [m for m in pipeline if m.get("current_state") == "hired"]
    failed = [m for m in pipeline if m.get("current_state") in FAILED_STATES]
    pending = [m for m in pipeline if m.get("current_state") not in TERMINAL_STATES]
    active = [m for m in pipeline if m.get("current_state") in ACTIVE_CONVERSATION_STATES]

    hire_days = [
        d for m in hired
        if (d := _days_between(_parse_ts(m.get("created_at")), _parse_ts(m.get("state_updated_at")))) is not None
    ]
    avg_time_to_hire = round(sum(hire_days) / len(hire_days), 1) if hire_days else 0.0

    return KPISummaryResponse(
        total_hired=len(hired),
        placement_rate=round(len(hired) / total, 3) if total else 0.0,
        pending_matches=len(pending),
        avg_time_to_hire_days=avg_time_to_hire,
        active_conversations=len(active),
        failed_matches=len(failed),
        failure_rate=round(len(failed) / total, 3) if total else 0.0,
    )


@router.get("/admin/analytics/recruiter-performance", response_model=RecruiterPerformanceResponse)
async def get_recruiter_performance(
    recruiter: Optional[str] = Query(None, description="Filter by recruiter: 'tal' or 'elad'"),
    period: str = Query("month", description="Time period: week, month, quarter, year"),
    supabase: Any = Depends(get_supabase_client),
) -> RecruiterPerformanceResponse:
    """Get recruiter (Tal / Elad) performance metrics from real match data."""
    start_date, end_date = get_date_range(period)
    logger.info(f"Fetching recruiter performance for {recruiter or 'all'} in period {period}")

    matches = await _fetch_matches(supabase, start_date, end_date)
    now = datetime.now(timezone.utc)

    def avg_queue_age(states: set[str]) -> float:
        ages = [
            d for m in matches if m.get("current_state") in states
            if (d := _days_between(_parse_ts(m.get("state_updated_at")), now)) is not None
        ]
        return round(sum(ages) / len(ages), 1) if ages else 0.0

    # Tal metrics
    tal_conversations = sum(1 for m in matches if m.get("current_state") in REACHED_RECRUITER)
    tal_approvals = sum(1 for m in matches if m.get("current_state") in RECRUITER_APPROVED)
    tal_hires = sum(1 for m in matches if m.get("current_state") == "hired")
    tal_queue = sum(1 for m in matches if m.get("current_state") in {"sent_to_tal", "tal_conversation"})

    # Elad metrics
    elad_conversations = sum(1 for m in matches if m.get("current_state") in REACHED_ELAD)
    elad_approvals = sum(1 for m in matches if m.get("current_state") in ELAD_APPROVED)
    elad_hires = sum(1 for m in matches if m.get("current_state") == "hired")
    elad_queue = sum(1 for m in matches if m.get("current_state") in {"sent_to_elad", "elad_conversation"})

    total_queue = tal_queue + elad_queue

    data = [
        RecruiterPerformanceMetric(
            recruiter_name="tal",
            conversations_count=tal_conversations,
            approvals_count=tal_approvals,
            approval_rate=round(tal_approvals / tal_conversations, 3) if tal_conversations else 0.0,
            hires_count=tal_hires,
            hire_rate=round(tal_hires / tal_approvals, 3) if tal_approvals else 0.0,
            avg_days_in_stage=avg_queue_age({"sent_to_tal", "tal_conversation"}),
            queue_count=tal_queue,
            workload_pct=round(tal_queue / total_queue * 100, 1) if total_queue else 0.0,
        ),
        RecruiterPerformanceMetric(
            recruiter_name="elad",
            conversations_count=elad_conversations,
            approvals_count=elad_approvals,
            approval_rate=round(elad_approvals / elad_conversations, 3) if elad_conversations else 0.0,
            hires_count=elad_hires,
            hire_rate=round(elad_hires / elad_approvals, 3) if elad_approvals else 0.0,
            avg_days_in_stage=avg_queue_age({"sent_to_elad", "elad_conversation"}),
            queue_count=elad_queue,
            workload_pct=round(elad_queue / total_queue * 100, 1) if total_queue else 0.0,
        ),
    ]

    if recruiter:
        data = [m for m in data if m.recruiter_name == recruiter.lower()]

    return RecruiterPerformanceResponse(data=data)


@router.get("/admin/analytics/match-funnel", response_model=MatchFunnelResponse)
async def get_match_funnel(
    period: str = Query("month", description="Time period: week, month, quarter, year"),
    supabase: Any = Depends(get_supabase_client),
) -> MatchFunnelResponse:
    """Get match funnel metrics showing drop-off at each stage (real data)."""
    start_date, end_date = get_date_range(period)
    logger.info(f"Fetching match funnel for period {period}")

    matches = await _fetch_matches(supabase, start_date, end_date)
    pipeline = [m for m in matches if m.get("current_state") not in NON_PIPELINE_STATES]

    found = len(pipeline)
    carmit_approved = sum(1 for m in pipeline if m.get("current_state") in PASSED_CARMIT)
    sent_to_recruiter = sum(1 for m in pipeline if m.get("current_state") in REACHED_RECRUITER)
    recruiter_approved = sum(1 for m in pipeline if m.get("current_state") in RECRUITER_APPROVED)
    hired = sum(1 for m in pipeline if m.get("current_state") == "hired")
    failed = sum(1 for m in pipeline if m.get("current_state") in FAILED_STATES)

    return MatchFunnelResponse(
        found=found,
        carmit_approved=carmit_approved,
        sent_to_recruiter=sent_to_recruiter,
        recruiter_approved=recruiter_approved,
        hired=hired,
        failed=failed,
        conversion_rate=round(hired / found, 3) if found else 0.0,
    )


@router.get("/admin/analytics/time-to-placement", response_model=TimeToPlacementResponse)
async def get_time_to_placement(
    days: int = Query(90, description="Number of days to include in analysis"),
    supabase: Any = Depends(get_supabase_client),
) -> TimeToPlacementResponse:
    """Get time-to-placement trends over time from real hire/failure events."""
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)
    logger.info(f"Fetching time-to-placement for {days} days")

    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    # Use a wide created_at window (matches may have been created before the
    # window but resolved within it); fetch all valid matches then filter on
    # the resolution date (state_updated_at).
    matches = await _fetch_matches(supabase)

    # Bucket by resolution day.
    hire_days_by_date: dict[str, list[float]] = defaultdict(list)
    failed_by_date: dict[str, int] = defaultdict(int)

    for m in matches:
        state = m.get("current_state")
        resolved = _parse_ts(m.get("state_updated_at"))
        if resolved is None or resolved < start_dt:
            continue
        day = resolved.date().isoformat()
        if state == "hired":
            d = _days_between(_parse_ts(m.get("created_at")), resolved)
            if d is not None:
                hire_days_by_date[day].append(d)
        elif state in FAILED_STATES:
            failed_by_date[day] += 1

    data = []
    current_date = start_date
    while current_date <= end_date:
        day = current_date.isoformat()
        hires = hire_days_by_date.get(day, [])
        data.append(
            TimeToPlacementPoint(
                date=day,
                avg_days=round(sum(hires) / len(hires), 1) if hires else 0.0,
                hires_count=len(hires),
                failed_count=failed_by_date.get(day, 0),
            )
        )
        current_date += timedelta(days=1)

    return TimeToPlacementResponse(data=data)


# Maps a raw gate/keyword token (as found in match_state_history.reasoning)
# to a (stage, human-readable Hebrew reason) pair.
_GATE_LABELS: list[tuple[tuple[str, ...], str, str]] = [
    (("relevant_skills", "skills mismatch", "no skills"), "carmit_skills", "כישורים לא תואמים"),
    (("quality_threshold", "score", "<"), "carmit_quality", "ציון מתחת לסף"),
    (("clearance_match", "clearance mismatch"), "carmit_clearance", "סיווג ביטחוני לא מספיק"),
    (("conflict_of_interest",), "carmit_conflict", "ניגוד עניינים"),
    (("already_declined",), "carmit_declined", "המועמד דחה בעבר"),
    (("past_rejection",), "carmit_past_rejection", "נדחה בעבר לתפקיד"),
]


def _classify_reasoning(reasoning: str) -> list[tuple[str, str]]:
    """Parse a free-text reasoning string into (stage, reason) categories.

    A single rejection can list several failed gates, so this may return
    multiple categories. Falls back to a generic bucket when nothing matches.
    """
    text = (reasoning or "").lower()
    found: list[tuple[str, str]] = []
    for tokens, stage, label in _GATE_LABELS:
        if any(tok in text for tok in tokens):
            found.append((stage, label))
    return found or [("other", "אחר / לא מסווג")]


@router.get("/admin/analytics/rejection-reasons", response_model=RejectionReasonsResponse)
async def get_rejection_reasons(
    period: str = Query("month", description="Time period: week, month, quarter, year"),
    supabase: Any = Depends(get_supabase_client),
) -> RejectionReasonsResponse:
    """Get breakdown of rejection reasons by stage from real audit data.

    Reasons live in ``match_state_history.reasoning`` (e.g. "Failed gates:
    relevant_skills"), NOT in matches.carmit_blocked_reason — which was empty
    for historical rows. We parse the reasoning text into readable categories.
    """
    start_date, end_date = get_date_range(period)
    logger.info(f"Fetching rejection reasons for period {period}")

    rejected_states = list(FAILED_STATES)

    # Fetch rejection events from the state-history audit trail (paginated).
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    while True:
        result = await (
            supabase.table("match_state_history")
            .select("to_state, reasoning, created_at")
            .in_("to_state", rejected_states)
            .gte("created_at", start_date.isoformat())
            .lte("created_at", end_date.isoformat())
            .range(offset, offset + page_size - 1)
            .execute()
        )
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    total_rejections = len(rows)
    buckets: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        for stage, label in _classify_reasoning(row.get("reasoning")):
            buckets[(stage, label)] += 1

    data = [
        RejectionReasonMetric(
            rejection_stage=stage,
            reason=reason,
            count=count,
            # Percentage of rejection EVENTS that involved this reason. May sum
            # to >100% because a single rejection can fail several gates.
            percentage=round(count / total_rejections * 100, 1) if total_rejections else 0.0,
        )
        for (stage, reason), count in sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return RejectionReasonsResponse(data=data)


@router.get("/admin/analytics/agent-performance", response_model=AgentPerformanceResponse)
async def get_agent_performance(
    supabase: Any = Depends(get_supabase_client),
) -> AgentPerformanceResponse:
    """Get per-agent performance metrics aggregated from real match data."""
    logger.info("Fetching agent performance metrics")

    matches = await _fetch_matches(supabase)

    found: dict[str, int] = defaultdict(int)
    approved: dict[str, int] = defaultdict(int)
    placements: dict[str, int] = defaultdict(int)
    score_sum: dict[str, float] = defaultdict(float)
    score_count: dict[str, int] = defaultdict(int)

    for m in matches:
        agent = m.get("matched_by_agent_code")
        if not agent:
            continue
        state = m.get("current_state")
        if state in NON_PIPELINE_STATES:
            continue
        found[agent] += 1
        if state in PASSED_CARMIT:
            approved[agent] += 1
        if state == "hired":
            placements[agent] += 1
        score = m.get("match_score")
        if score is not None:
            try:
                score_sum[agent] += float(score)
                score_count[agent] += 1
            except (ValueError, TypeError):
                pass

    data = [
        AgentPerformanceMetric(
            agent_code=agent,
            matches_found=found[agent],
            matches_approved=approved[agent],
            approval_rate=round(approved[agent] / found[agent], 3) if found[agent] else 0.0,
            placements=placements[agent],
            placement_rate=round(placements[agent] / approved[agent], 3) if approved[agent] else 0.0,
            avg_score=round(score_sum[agent] / score_count[agent], 3) if score_count[agent] else 0.0,
        )
        for agent in sorted(found, key=lambda a: found[a], reverse=True)
    ]

    return AgentPerformanceResponse(data=data)
