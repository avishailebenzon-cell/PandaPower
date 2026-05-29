"""
Match Flow Pipeline Dashboard
Shows metrics and details of matches through recruitment pipeline stages.
Includes bottleneck detection and alerts.
"""

import logging
from typing import Any, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/matches", tags=["admin", "matches"])


# Response models
class MatchFlowMetrics(BaseModel):
    stage_found: int
    stage_carmit_approved: int
    stage_sent_to_tal: int
    stage_tal_conversation: int
    stage_tal_accepted: int
    stage_sent_to_elad: int
    stage_hired: int
    stage_rejected_tal: int
    stage_rejected_elad: int
    total_in_pipeline: int
    total_completed: int
    success_rate: float
    avg_time_in_tal: float
    avg_time_in_elad: float


class StageMatch(BaseModel):
    id: str
    candidate_name: str
    job_title: str
    match_score: float
    current_state: str
    created_at: str
    updated_at: str
    tal_summary: Optional[str] = None
    carmit_review_notes: Optional[str] = None


class BottleneckAlert(BaseModel):
    alert_type: str
    level: str
    title: str
    description: str
    metrics: dict
    recommendation: str
    detected_at: str


class BottleneckCheckResponse(BaseModel):
    status: str
    alerts_detected: int
    alerts: list[BottleneckAlert]
    alerts_sent: int


# Endpoints
@router.get("/flow-metrics", response_model=MatchFlowMetrics)
async def get_flow_metrics():
    """
    Get metrics for the recruitment pipeline flow.

    Returns counts for each stage and calculated KPIs:
    - Stage counts
    - Total in pipeline
    - Success rate
    - Average time in Tal/Elad
    """
    try:
        from pandapower.core.supabase import get_supabase_client

        supabase = await get_supabase_client()

        # Fetch all matches with their details
        matches_response = await supabase.table("matches").select(
            "id, current_state, match_score, created_at, updated_at, "
            "tal_summary, carmit_review_notes"
        ).execute()

        matches = matches_response.data or []

        # Count by stage
        stages = {
            "found": 0,
            "carmit_approved": 0,
            "sent_to_tal": 0,
            "tal_conversation": 0,
            "tal_accepted": 0,
            "sent_to_elad": 0,
            "hired": 0,
            "rejected_tal": 0,
            "rejected_elad": 0,
        }

        time_in_tal = []
        time_in_elad = []

        for match in matches:
            state = match.get("current_state", "found")
            if state in stages:
                stages[state] += 1

            # Calculate time in stage
            created = datetime.fromisoformat(match["created_at"].replace("Z", "+00:00"))
            updated = datetime.fromisoformat(match["updated_at"].replace("Z", "+00:00"))
            days_in_stage = (updated - created).days

            if state in ["sent_to_tal", "tal_conversation", "tal_accepted"]:
                time_in_tal.append(days_in_stage)

            if state in ["sent_to_elad"]:
                time_in_elad.append(days_in_stage)

        # Calculate KPIs
        total_in_pipeline = sum([v for k, v in stages.items() if k not in ["hired", "rejected_tal", "rejected_elad"]])
        total_completed = stages["hired"] + stages["rejected_tal"] + stages["rejected_elad"]
        success_rate = stages["hired"] / total_completed if total_completed > 0 else 0
        avg_time_in_tal = sum(time_in_tal) / len(time_in_tal) if time_in_tal else 0
        avg_time_in_elad = sum(time_in_elad) / len(time_in_elad) if time_in_elad else 0

        logger.info(f"Flow metrics: {total_in_pipeline} in pipeline, {total_completed} completed. Stage counts: {stages}")

        return MatchFlowMetrics(
            stage_found=stages["found"],
            stage_carmit_approved=stages["carmit_approved"],
            stage_sent_to_tal=stages["sent_to_tal"],
            stage_tal_conversation=stages["tal_conversation"],
            stage_tal_accepted=stages["tal_accepted"],
            stage_sent_to_elad=stages["sent_to_elad"],
            stage_hired=stages["hired"],
            stage_rejected_tal=stages["rejected_tal"],
            stage_rejected_elad=stages["rejected_elad"],
            total_in_pipeline=total_in_pipeline,
            total_completed=total_completed,
            success_rate=success_rate,
            avg_time_in_tal=avg_time_in_tal,
            avg_time_in_elad=avg_time_in_elad,
        )

    except Exception as e:
        logger.error(f"Error getting flow metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/by-stage/{stage}", response_model=list[StageMatch])
async def get_matches_by_stage(
    stage: str = Path(..., description="Pipeline stage (e.g., found, sent_to_tal, hired)"),
):
    """
    Get all matches in a specific pipeline stage.

    Stages:
    - found, carmit_approved, sent_to_tal, tal_conversation, tal_accepted, sent_to_elad
    - hired, rejected_tal, rejected_elad

    Ordered by most recently updated first.
    """
    try:
        from pandapower.core.supabase import get_supabase_client

        supabase = await get_supabase_client()

        # Validate stage
        valid_stages = [
            "found", "carmit_approved", "sent_to_tal", "tal_conversation",
            "tal_accepted", "sent_to_elad", "hired", "rejected_tal", "rejected_elad"
        ]
        if stage not in valid_stages:
            raise HTTPException(status_code=400, detail=f"Invalid stage: {stage}")

        # Fetch matches for this stage
        matches_response = await supabase.table("matches").select(
            "id, match_score, current_state, created_at, updated_at, "
            "tal_summary, carmit_review_notes, candidate_id, job_id"
        ).eq("current_state", stage).order("updated_at", desc=True).execute()

        matches = matches_response.data or []

        logger.debug(f"Fetched {len(matches)} matches in stage '{stage}'. Sample: {matches[:1] if matches else 'none'}")

        # Fetch candidate and job info for all matches
        candidate_ids = list(set(m.get("candidate_id") for m in matches if m.get("candidate_id")))
        job_ids = list(set(m.get("job_id") for m in matches if m.get("job_id")))

        logger.debug(f"Found {len(candidate_ids)} unique candidates, {len(job_ids)} unique jobs")

        candidates_map = {}
        jobs_map = {}

        if candidate_ids:
            try:
                candidates_response = await supabase.table("candidates").select("id, name").in_("id", candidate_ids).execute()
                candidates_map = {c["id"]: c["name"] for c in (candidates_response.data or [])}
                logger.debug(f"Fetched {len(candidates_map)} candidate names")
            except Exception as e:
                logger.warning(f"Failed to fetch candidate names: {e}")

        if job_ids:
            try:
                jobs_response = await supabase.table("jobs").select("id, title").in_("id", job_ids).execute()
                jobs_map = {j["id"]: j["title"] for j in (jobs_response.data or [])}
                logger.debug(f"Fetched {len(jobs_map)} job titles")
            except Exception as e:
                logger.warning(f"Failed to fetch job titles: {e}")

        # Transform to response format
        result = []
        for match in matches:
            candidate_name = candidates_map.get(match.get("candidate_id"), "Unknown")
            job_title = jobs_map.get(match.get("job_id"), "Unknown")

            result.append(
                StageMatch(
                    id=match.get("id", ""),
                    candidate_name=candidate_name,
                    job_title=job_title,
                    match_score=match.get("match_score", 0),
                    current_state=match.get("current_state", ""),
                    created_at=match.get("created_at", ""),
                    updated_at=match.get("updated_at", ""),
                    tal_summary=match.get("tal_summary"),
                    carmit_review_notes=match.get("carmit_review_notes"),
                )
            )

        logger.info(f"Returning {len(result)} matches in stage '{stage}'")
        if result:
            logger.debug(f"Sample result: {result[0].__dict__}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting matches by stage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get matches: {str(e)}")


@router.get("/timeline", response_model=list[dict])
async def get_timeline_data(
    range: str = Query("month", regex="^(week|month|quarter)$"),
):
    """
    Get timeline data showing match progression through stages over time.

    Shows daily/weekly counts of matches in each pipeline stage.
    Useful for:
    - Visualizing flow velocity
    - Identifying bottleneck formation
    - Tracking success trends

    Args:
        range: Time range for the data (week, month, or quarter)

    Returns:
        List of timeline data points with date, stage, and count
    """
    try:
        from pandapower.core.supabase import get_supabase_client
        from datetime import datetime, timedelta

        supabase = await get_supabase_client()

        # Determine date range
        end_date = datetime.utcnow()
        if range == "week":
            start_date = end_date - timedelta(days=7)
        elif range == "month":
            start_date = end_date - timedelta(days=30)
        else:  # quarter
            start_date = end_date - timedelta(days=90)

        # Fetch all matches
        matches_response = await supabase.table("matches").select(
            "id, current_state, created_at, updated_at"
        ).execute()

        matches = matches_response.data or []

        # Build timeline: count matches in each stage per day
        timeline_data = []
        current_date = start_date.date()

        while current_date <= end_date.date():
            date_str = current_date.isoformat()

            # For each stage, count matches that were in that stage on this date
            stages = [
                "found", "carmit_approved", "sent_to_tal", "tal_conversation",
                "tal_accepted", "sent_to_elad", "hired", "rejected_tal", "rejected_elad"
            ]

            for stage in stages:
                # Count matches in this stage on this date
                count = 0
                for match in matches:
                    created = datetime.fromisoformat(match["created_at"].replace("Z", "+00:00"))
                    updated = datetime.fromisoformat(match["updated_at"].replace("Z", "+00:00"))

                    # If match was created before this date and (still in this stage or updated after this date)
                    if created.date() <= current_date:
                        # Check if match is in this stage as of this date
                        if match.get("current_state") == stage:
                            # Match is currently in this stage
                            if updated.date() <= current_date:
                                count += 1
                        elif updated.date() > current_date:
                            # Match has moved past, but was in this stage before moving
                            # This is a simplified heuristic - in production, use state history
                            pass

                if count > 0:
                    timeline_data.append({
                        "date": date_str,
                        "stage": stage,
                        "count": count,
                    })

            current_date += timedelta(days=1)

        logger.info(f"Timeline data: {len(timeline_data)} data points for {range}")
        return timeline_data

    except Exception as e:
        logger.error(f"Error getting timeline: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get timeline: {str(e)}")


@router.post("/check-bottlenecks", response_model=BottleneckCheckResponse)
async def check_bottlenecks(send_alerts: bool = Query(True)):
    """
    Manually trigger bottleneck detection and optionally send alerts.

    Checks for:
    - Tal screening overload (sent_to_tal > tal_accepted * 2)
    - Elad placement delays (tal_accepted > sent_to_elad * 2)
    - Stagnant matches (>7 days in same stage)
    - High rejection rates (>35%)

    Args:
        send_alerts: Whether to send email alerts for detected bottlenecks

    Returns:
        Detected alerts with metrics and recommendations
    """
    try:
        from pandapower.core.supabase import get_supabase_client
        from pandapower.workers.bottleneck_alerts import check_and_alert_bottlenecks
        from pandapower.integrations.resend import ResendAlertService
        from pandapower.core.config import get_settings

        supabase = await get_supabase_client()
        settings = get_settings()

        # Initialize alert service if enabled
        alert_service = None
        if send_alerts and settings.RESEND_API_KEY:
            alert_service = ResendAlertService(api_key=settings.RESEND_API_KEY)

        # Run bottleneck detection
        result = await check_and_alert_bottlenecks(supabase, alert_service)

        logger.info(
            f"Bottleneck check: {result['alerts_detected']} alerts detected, "
            f"{result['alerts_sent']} alerts sent"
        )

        return BottleneckCheckResponse(
            status=result["status"],
            alerts_detected=result["alerts_detected"],
            alerts=[BottleneckAlert(**a) for a in result["alerts"]],
            alerts_sent=result["alerts_sent"],
        )

    except Exception as e:
        logger.error(f"Error checking bottlenecks: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check bottlenecks: {str(e)}"
        )
