"""
Match Flow Pipeline Dashboard
Shows metrics and details of matches through recruitment pipeline stages.
"""

import logging
from typing import Any, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Path
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

        logger.info(f"Flow metrics: {total_in_pipeline} in pipeline, {total_completed} completed")

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

        # Fetch matches for this stage with candidate and job info
        matches_response = await supabase.table("matches").select(
            "id, match_score, current_state, created_at, updated_at, "
            "tal_summary, carmit_review_notes, "
            "candidates(name), jobs(title)"
        ).eq("current_state", stage).order("updated_at", desc=True).execute()

        matches = matches_response.data or []

        # Transform to response format
        result = []
        for match in matches:
            # Extract nested data from relations
            candidates = match.get("candidates", {})
            jobs = match.get("jobs", {})

            candidate_name = "Unknown"
            if isinstance(candidates, list) and len(candidates) > 0:
                candidate_name = candidates[0].get("name", "Unknown")
            elif isinstance(candidates, dict):
                candidate_name = candidates.get("name", "Unknown")

            job_title = "Unknown"
            if isinstance(jobs, list) and len(jobs) > 0:
                job_title = jobs[0].get("title", "Unknown")
            elif isinstance(jobs, dict):
                job_title = jobs.get("title", "Unknown")

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

        logger.info(f"Fetched {len(result)} matches in stage '{stage}'")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting matches by stage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get matches: {str(e)}")
