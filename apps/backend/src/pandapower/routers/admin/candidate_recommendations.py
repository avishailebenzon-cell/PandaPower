"""
Candidate recommendations endpoint: match a candidate to jobs and client contacts.

GET /admin/candidates/{candidate_id}/recommendations
"""

import logging
from typing import Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/candidates", tags=["admin", "candidates"])


# Response models
class JobMatchResult(BaseModel):
    job_id: str
    job_title: str
    match_score: float
    match_details: dict[str, Any]
    priority: Optional[int] = None


class ContactMatchResult(BaseModel):
    contact_id: str
    contact_name: str
    contact_status: str
    professional_domain: Optional[str] = None
    match_score: float
    match_details: dict[str, Any]


class CandidateRecommendationsResponse(BaseModel):
    candidate_id: str
    candidate_name: str
    candidate_domain: Optional[str] = None
    candidate_clearance: Optional[str] = None
    job_matches: list[JobMatchResult]
    contact_recommendations: list[ContactMatchResult]
    generated_at: str


# Endpoints
@router.get("/{candidate_id}/recommendations", response_model=CandidateRecommendationsResponse)
async def get_candidate_recommendations(
    candidate_id: str = Path(..., description="Candidate ID (UUID)"),
):
    """
    Get job and contact recommendations for a candidate.

    Matches the candidate to:
    1. Active jobs (≥80% match on domain, clearance, experience)
    2. Client/potential client contacts (≥80% match on professional domain + clearance)

    Returns top 5 matches for each category, sorted by match score.
    """
    try:
        from pandapower.core.supabase import get_supabase_client
        from pandapower.workers.candidate_matching import CandidateMatchingEngine

        supabase = await get_supabase_client()

        # Fetch candidate (select all fields in case of schema variations)
        candidate_response = await supabase.table("candidates").select("*").eq("id", candidate_id).single().execute()

        if not candidate_response.data:
            raise HTTPException(status_code=404, detail="Candidate not found")

        candidate = candidate_response.data

        # Initialize matching engine
        engine = CandidateMatchingEngine(supabase, threshold=0.80)

        # Find job matches
        job_matches = await engine.find_job_matches(candidate)

        # Find contact recommendations
        contact_matches = await engine.find_contact_recommendations(candidate)

        logger.info(
            f"Generated recommendations for candidate {candidate_id}: "
            f"{len(job_matches)} job matches, {len(contact_matches)} contact matches"
        )

        return CandidateRecommendationsResponse(
            candidate_id=candidate_id,
            candidate_name=candidate.get("name", "Unknown"),
            candidate_domain=candidate.get("primary_domain"),
            candidate_clearance=candidate.get("security_clearance_level"),
            job_matches=[JobMatchResult(**m) for m in job_matches],
            contact_recommendations=[ContactMatchResult(**m) for m in contact_matches],
            generated_at=datetime.utcnow().isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating recommendations: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate recommendations: {str(e)}"
        )
