"""
Admin API endpoints for candidate management.

Phase 9: API for viewing and managing candidates created from parsed CVs.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pandapower.core.config import settings
from pandapower.core.supabase import get_supabase_client

import structlog as _structlog
logger = _structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/candidates", tags=["admin", "candidates"])


class CandidateStats(BaseModel):
    """Statistics about candidates."""

    total: int
    by_language: dict[str, int]
    by_location: dict[str, int]
    average_confidence: float
    with_email: int
    with_phone: int


class CandidateProfile(BaseModel):
    """A candidate profile created from parsed CV."""

    id: str
    name: str
    email: Optional[str]
    phone: Optional[str]
    location: Optional[str]
    clearance_level: Optional[str]
    key_skills: list[str]
    years_of_experience: Optional[int]
    top_education: Optional[dict]
    overall_confidence_score: float
    detected_language: str
    cv_file_id: str
    created_at: str


@router.get("/stats")
async def get_candidate_stats(supabase=Depends(get_supabase_client)) -> CandidateStats:
    """Get candidate statistics and summary."""
    try:
        # Get all candidates
        response = supabase.table("candidates").select("*").is_("deleted_at", "null").execute()
        candidates = response.data or []

        if not candidates:
            return CandidateStats(
                total=0,
                by_language={},
                by_location={},
                average_confidence=0.0,
                with_email=0,
                with_phone=0,
            )

        # Calculate statistics
        by_language = {}
        by_location = {}
        total_confidence = 0
        with_email = 0
        with_phone = 0

        for candidate in candidates:
            # Language stats
            lang = candidate.get("detected_language", "unknown")
            by_language[lang] = by_language.get(lang, 0) + 1

            # Location stats
            location = candidate.get("location", "Unknown")
            by_location[location] = by_location.get(location, 0) + 1

            # Confidence
            confidence = candidate.get("overall_confidence_score", 0)
            total_confidence += confidence

            # Contact info
            if candidate.get("email"):
                with_email += 1
            if candidate.get("phone"):
                with_phone += 1

        return CandidateStats(
            total=len(candidates),
            by_language=by_language,
            by_location=by_location,
            average_confidence=total_confidence / len(candidates) if candidates else 0,
            with_email=with_email,
            with_phone=with_phone,
        )

    except Exception as e:
        logger.error(f"Failed to get candidate stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_candidates(
    language: Optional[str] = None,
    location: Optional[str] = None,
    min_confidence: float = 0.0,
    limit: int = 50,
    offset: int = 0,
    supabase=Depends(get_supabase_client),
) -> list[CandidateProfile]:
    """List candidates with optional filtering.

    Args:
        language: Filter by detected language (e.g., 'he', 'en')
        location: Filter by location
        min_confidence: Minimum overall confidence score
        limit: Number of results to return
        offset: Pagination offset
    """
    try:
        query = supabase.table("candidates").select(
            "id, name, email, phone, location, clearance_level, key_skills, "
            "years_of_experience, top_education, overall_confidence_score, "
            "detected_language, cv_file_id, created_at"
        ).is_("deleted_at", "null")

        # Apply filters
        if language:
            query = query.eq("detected_language", language)
        if location:
            query = query.eq("location", location)
        if min_confidence > 0:
            query = query.gte("overall_confidence_score", min_confidence)

        # Pagination
        response = query.order("created_at", desc=True).range(offset, offset + limit).execute()

        candidates = response.data or []
        return [CandidateProfile(**c) for c in candidates]

    except Exception as e:
        logger.error(f"Failed to list candidates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/database")
async def candidates_database(
    search: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Full candidates database view with search, paging and total count.

    Powers the admin "כל המועמדים" table. Returns the core columns for the
    table plus a total count for pagination.

    Args:
        search: Free-text match against name / email / phone
        language: Filter by detected language (e.g. 'he', 'en')
        limit: Page size
        offset: Pagination offset
    """
    try:
        columns = (
            "id, name, candidate_number, email, phone, location, "
            "clearance_level, key_skills, years_of_experience, "
            "detected_language, overall_confidence_score, "
            "skill_readiness_status, cv_file_id, "
            "source_email_from, created_at"
        )

        def _base():
            q = supabase.table("candidates").select(columns, count="exact").is_(
                "deleted_at", "null"
            )
            if language:
                q = q.eq("detected_language", language)
            if search:
                term = search.strip().replace(",", " ")
                q = q.or_(
                    f"name.ilike.%{term}%,"
                    f"email.ilike.%{term}%,"
                    f"phone.ilike.%{term}%"
                )
            return q

        response = (
            _base()
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        return {
            "data": response.data or [],
            "total": response.count or 0,
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(f"Failed to load candidates database: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{candidate_id}")
async def get_candidate(
    candidate_id: str, supabase=Depends(get_supabase_client)
) -> dict:
    """Get detailed candidate information including full extracted data."""
    try:
        response = supabase.table("candidates").select("*").eq("id", candidate_id).execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Candidate not found")

        candidate = response.data[0]

        # Get linked CV details
        cv_response = supabase.table("cv_files").select(
            "id, original_filename, source_email_from, source_email_received_at"
        ).eq("id", candidate["cv_file_id"]).execute()

        if cv_response.data:
            candidate["cv_details"] = cv_response.data[0]

        return candidate

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get candidate {candidate_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recreate-from-cv/{cv_file_id}")
async def create_candidate_from_cv(
    cv_file_id: str, supabase=Depends(get_supabase_client)
) -> dict:
    """Manually create a candidate from a specific CV file.

    Useful for re-processing failed candidates or lowconfidence results.
    """
    try:
        from pandapower.workers.candidate_creation import CandidateCreationWorker

        # Get the CV
        cv_response = supabase.table("cv_files").select("*").eq("id", cv_file_id).execute()
        if not cv_response.data:
            raise HTTPException(status_code=404, detail="CV file not found")

        cv = cv_response.data[0]

        if cv["parse_status"] != "success":
            raise HTTPException(
                status_code=400,
                detail=f"CV parse status is '{cv['parse_status']}', must be 'success'",
            )

        # Create candidate
        worker = CandidateCreationWorker(supabase)
        candidate_id = await worker._create_candidate_from_cv(cv)

        if not candidate_id:
            return {
                "status": "skipped",
                "reason": "Low confidence score",
                "cv_id": cv_file_id,
            }

        return {
            "status": "created",
            "candidate_id": candidate_id,
            "cv_id": cv_file_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create candidate from CV {cv_file_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-now")
async def trigger_candidate_creation(
    limit: int = 10, supabase=Depends(get_supabase_client)
) -> dict:
    """Manually trigger candidate creation from pending parsed CVs."""
    try:
        from pandapower.workers.candidate_creation import CandidateCreationWorker

        worker = CandidateCreationWorker(supabase)
        result = await worker.create_candidates_from_parsed_cvs(limit=limit)

        logger.info(f"Manual candidate creation triggered: {result}")
        return result

    except Exception as e:
        logger.error(f"Failed to trigger candidate creation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PHASE 11: Candidate Scoring & Readiness Classification
# ============================================================================


@router.get("/readiness/summary")
async def get_readiness_summary(
    supabase=Depends(get_supabase_client),
) -> dict:
    """Get summary of candidates by readiness status."""
    try:
        all_candidates = supabase.table("candidates").select(
            "skill_readiness_status"
        ).is_("deleted_at", "null").execute()

        summary = {"READY": 0, "REVIEW": 0, "INCOMPLETE": 0, "total": 0}

        for candidate in all_candidates.data or []:
            status = candidate.get("skill_readiness_status", "INCOMPLETE")
            if status in summary:
                summary[status] += 1
            summary["total"] += 1

        logger.info(
            f"Readiness summary",
            ready=summary["READY"],
            review=summary["REVIEW"],
            incomplete=summary["INCOMPLETE"],
        )

        return summary

    except Exception as e:
        logger.error(f"Failed to get readiness summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scoring/by-status")
async def get_candidates_by_readiness(
    status: str = "READY",
    limit: int = 50,
    supabase=Depends(get_supabase_client),
) -> list[dict]:
    """Get candidates filtered by readiness status.

    Args:
        status: READY, REVIEW, or INCOMPLETE
        limit: Maximum results to return
    """
    try:
        response = supabase.table("candidates").select(
            "id, name, detected_language, normalized_skills_count, "
            "average_skill_confidence, skill_readiness_status, recommendation_score"
        ).eq("skill_readiness_status", status).is_("deleted_at", "null").order(
            "recommendation_score", desc=True
        ).limit(limit).execute()

        return response.data or []

    except Exception as e:
        logger.error(f"Failed to get candidates by readiness: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/low-confidence/mappings")
async def get_low_confidence_mappings(
    confidence_threshold: float = 0.85,
    limit: int = 50,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Get all low-confidence skill mappings across candidates."""
    try:
        response = supabase.table("candidate_skills_detailed").select(
            "candidate_id, candidate_name, detected_language, raw_skill_text, "
            "skill_name, skill_category, confidence_score, normalization_method"
        ).lte("confidence_score", confidence_threshold).limit(limit).execute()

        skills = response.data or []

        # Group by candidate
        by_candidate = {}
        for skill in skills:
            cand_id = skill["candidate_id"]
            if cand_id not in by_candidate:
                by_candidate[cand_id] = {
                    "candidate_name": skill.get("candidate_name"),
                    "language": skill.get("detected_language"),
                    "skills": []
                }
            by_candidate[cand_id]["skills"].append({
                "raw_skill_text": skill.get("raw_skill_text"),
                "canonical_skill": skill.get("skill_name"),
                "category": skill.get("skill_category"),
                "confidence_score": skill.get("confidence_score"),
                "normalization_method": skill.get("normalization_method"),
            })

        logger.info(
            f"Found low-confidence mappings",
            threshold=confidence_threshold,
            count=len(skills),
            candidates=len(by_candidate)
        )

        return {
            "low_confidence_count": len(skills),
            "candidates_affected": len(by_candidate),
            "threshold": confidence_threshold,
            "by_candidate": by_candidate,
        }

    except Exception as e:
        logger.error(f"Failed to get low-confidence mappings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{candidate_id}/approve")
async def approve_candidate(
    candidate_id: str,
    review_notes: Optional[str] = None,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Approve a candidate for matching (set status to READY)."""
    try:
        from datetime import datetime

        update_data = {
            "skill_readiness_status": "READY",
            "manually_reviewed_at": datetime.utcnow().isoformat(),
        }

        if review_notes:
            update_data["review_notes"] = review_notes

        response = supabase.table("candidates").update(update_data).eq("id", candidate_id).execute()

        if response.data:
            logger.info(f"Approved candidate {candidate_id}")
            return {"status": "approved", "candidate_id": candidate_id}
        else:
            raise HTTPException(status_code=404, detail="Candidate not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve candidate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{candidate_id}/reject")
async def reject_candidate(
    candidate_id: str,
    reason: str,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Reject a candidate."""
    try:
        from datetime import datetime

        update_data = {
            "skill_readiness_status": "INCOMPLETE",
            "review_notes": reason,
            "manually_reviewed_at": datetime.utcnow().isoformat(),
            "deleted_at": datetime.utcnow().isoformat(),  # Soft delete
        }

        response = supabase.table("candidates").update(update_data).eq("id", candidate_id).execute()

        if response.data:
            logger.info(f"Rejected candidate {candidate_id}: {reason}")
            return {"status": "rejected", "candidate_id": candidate_id, "reason": reason}
        else:
            raise HTTPException(status_code=404, detail="Candidate not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reject candidate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-scoring")
async def trigger_candidate_scoring(
    limit: int = 50,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Manually trigger candidate scoring."""
    try:
        from pandapower.workers.candidate_scoring import CandidateScoringWorker

        worker = CandidateScoringWorker(supabase)
        result = await worker.score_candidates_by_skills(limit=limit)

        logger.info(f"Manual candidate scoring triggered: {result}")
        return result

    except Exception as e:
        logger.error(f"Failed to trigger candidate scoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))
