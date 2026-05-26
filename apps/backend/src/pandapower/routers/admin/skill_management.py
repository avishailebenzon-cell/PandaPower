"""
Admin API endpoints for skill management and normalization.

Phase 10: API for managing canonical skills, skill mappings, and viewing normalized skills.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pandapower.core.supabase import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/skills", tags=["admin", "skills"])


class SkillInfo(BaseModel):
    """Canonical skill information."""

    id: str
    name: str
    category: str
    description: Optional[str]
    name_he: Optional[str]
    category_he: Optional[str]
    popularity_score: int


class SkillMappingInfo(BaseModel):
    """Skill mapping information."""

    id: str
    raw_skill_text: str
    canonical_skill_id: str
    confidence_score: float
    mapping_method: str


class CandidateSkillInfo(BaseModel):
    """Normalized skill for a candidate."""

    skill_name: str
    skill_category: str
    raw_skill_text: str
    confidence_score: float
    proficiency_level: Optional[str]
    years_of_experience: Optional[float]


@router.get("/canonical")
async def list_canonical_skills(
    category: Optional[str] = None,
    limit: int = 100,
    supabase=Depends(get_supabase_client),
) -> list[SkillInfo]:
    """List canonical skills with optional filtering.

    Args:
        category: Filter by skill category (e.g., 'Programming Languages')
        limit: Maximum number of skills to return
    """
    try:
        query = supabase.table("skills").select("*").eq("is_active", True)

        if category:
            query = query.eq("category", category)

        response = await query.limit(limit).order("popularity_score", desc=True).execute()

        return [SkillInfo(**skill) for skill in response.data or []]

    except Exception as e:
        logger.error(f"Failed to list canonical skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def list_skill_categories(
    supabase=Depends(get_supabase_client),
) -> list[str]:
    """List all skill categories."""
    try:
        response = await supabase.table("skills").select("category").eq(
            "is_active", True
        ).execute()

        categories = set(skill["category"] for skill in response.data or [])
        return sorted(list(categories))

    except Exception as e:
        logger.error(f"Failed to list skill categories: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mappings")
async def list_skill_mappings(
    raw_skill_text: Optional[str] = None,
    limit: int = 100,
    supabase=Depends(get_supabase_client),
) -> list[SkillMappingInfo]:
    """List skill mappings with optional filtering.

    Args:
        raw_skill_text: Filter by raw skill text (substring match)
        limit: Maximum number of mappings to return
    """
    try:
        query = supabase.table("skill_mappings").select("*").eq("is_active", True)

        if raw_skill_text:
            query = query.ilike("raw_skill_text", f"%{raw_skill_text}%")

        response = await query.limit(limit).order("times_used", desc=True).execute()

        return [SkillMappingInfo(**mapping) for mapping in response.data or []]

    except Exception as e:
        logger.error(f"Failed to list skill mappings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candidate/{candidate_id}")
async def get_candidate_normalized_skills(
    candidate_id: str, supabase=Depends(get_supabase_client)
) -> dict:
    """Get all normalized skills for a candidate with details.

    Args:
        candidate_id: UUID of the candidate

    Returns:
        Dict with candidate info and normalized skills
    """
    try:
        # Get candidate info
        candidate_response = await supabase.table("candidates").select(
            "id, name, detected_language"
        ).eq("id", candidate_id).execute()

        if not candidate_response.data:
            raise HTTPException(status_code=404, detail="Candidate not found")

        candidate = candidate_response.data[0]

        # Get normalized skills using the detailed view
        skills_response = await supabase.table("candidate_skills_detailed").select(
            "*"
        ).eq("candidate_id", candidate_id).execute()

        skills = [CandidateSkillInfo(**skill) for skill in skills_response.data or []]

        return {
            "candidate_id": candidate["id"],
            "candidate_name": candidate["name"],
            "language": candidate["detected_language"],
            "normalized_skills": skills,
            "total_skills": len(skills),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get candidate skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_skill_statistics(supabase=Depends(get_supabase_client)) -> dict:
    """Get statistics about skills and normalization."""
    try:
        # Get canonical skills count
        skills_response = await supabase.table("skills").select(
            "id", count="exact"
        ).eq("is_active", True).execute()
        total_canonical_skills = skills_response.count or 0

        # Get total mappings
        mappings_response = await supabase.table("skill_mappings").select(
            "id", count="exact"
        ).eq("is_active", True).execute()
        total_mappings = mappings_response.count or 0

        # Get candidate skills count
        candidate_skills_response = await supabase.table("candidate_skills").select(
            "id", count="exact"
        ).execute()
        total_candidate_skills = candidate_skills_response.count or 0

        # Get candidates with normalized skills
        candidates_response = await supabase.table("candidate_skills").select(
            "candidate_id"
        ).execute()
        # Count unique candidates
        candidates_with_skills = len(set(s["candidate_id"] for s in (candidates_response.data or [])))

        return {
            "canonical_skills_count": total_canonical_skills,
            "skill_mappings_count": total_mappings,
            "candidate_skills_assigned": total_candidate_skills,
            "candidates_with_normalized_skills": candidates_with_skills,
        }

    except Exception as e:
        logger.error(f"Failed to get skill statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-now")
async def trigger_skill_normalization(
    limit: int = 30, supabase=Depends(get_supabase_client)
) -> dict:
    """Manually trigger skill normalization for pending candidates."""
    try:
        from pandapower.workers.skill_normalization import SkillNormalizationWorker
        from pandapower.integrations.claude_api import AnthropicClient
        from pandapower.core.config import settings

        # Get Claude client if available
        claude_client = None
        if settings.ANTHROPIC_API_KEY:
            claude_client = AnthropicClient(settings.ANTHROPIC_API_KEY)

        worker = SkillNormalizationWorker(supabase, claude_client)
        result = await worker.normalize_candidates_skills(limit=limit)

        if claude_client:
            await claude_client.close()

        logger.info(f"Manual skill normalization triggered: {result}")
        return result

    except Exception as e:
        logger.error(f"Failed to trigger skill normalization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BulkSkillItem(BaseModel):
    """One row for /bulk-add."""
    name: str
    category: str
    name_he: Optional[str] = None
    category_he: Optional[str] = None
    description: Optional[str] = None
    aliases: Optional[list[str]] = None
    aliases_he: Optional[list[str]] = None


class BulkSkillsRequest(BaseModel):
    skills: list[BulkSkillItem]


@router.post("/bulk-add")
async def bulk_add_skills(
    req: BulkSkillsRequest,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Add many canonical skills at once. Skips duplicates by `name` (case-insensitive).

    Used both by:
    - The skill-curation UI (admin pre-loading domain libraries)
    - The auto-learner in SkillNormalizationWorker, which discovers new skills
      during CV parsing and adds them so the next pass benefits.
    """
    try:
        # Pull existing skills once - we'll dedupe by lowercased name.
        existing_resp = await supabase.table("skills").select("name").execute()
        existing_names = {
            (row.get("name") or "").lower()
            for row in (existing_resp.data or [])
        }

        created = []
        skipped = []
        errors = []

        for item in req.skills:
            name_norm = item.name.strip()
            if not name_norm:
                continue
            if name_norm.lower() in existing_names:
                skipped.append(name_norm)
                continue

            payload = {
                "name": name_norm,
                "category": item.category,
                "name_he": item.name_he,
                "category_he": item.category_he,
                "description": item.description,
            }
            if item.aliases:
                payload["aliases"] = item.aliases
            if item.aliases_he:
                payload["aliases_he"] = item.aliases_he

            try:
                await supabase.table("skills").insert(payload).execute()
                created.append(name_norm)
                existing_names.add(name_norm.lower())  # avoid dupes within same batch
            except Exception as e:
                errors.append({"name": name_norm, "error": str(e)[:200]})

        return {
            "status": "ok",
            "submitted": len(req.skills),
            "created": len(created),
            "skipped_duplicates": len(skipped),
            "errors_count": len(errors),
            "created_names": created,
            "skipped_names": skipped,
            "errors": errors,
        }

    except Exception as e:
        logger.error(f"Bulk-add skills failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-canonical")
async def add_canonical_skill(
    skill_data: dict, supabase=Depends(get_supabase_client)
) -> dict:
    """Add a new canonical skill to the library.

    Args:
        skill_data: Dict with 'name', 'category', optionally 'name_he', 'category_he', 'description'
    """
    try:
        if not skill_data.get("name") or not skill_data.get("category"):
            raise HTTPException(
                status_code=400, detail="name and category are required"
            )

        response = await supabase.table("skills").insert({
            "name": skill_data["name"],
            "category": skill_data["category"],
            "name_he": skill_data.get("name_he"),
            "category_he": skill_data.get("category_he"),
            "description": skill_data.get("description"),
        }).execute()

        if response.data:
            return {
                "status": "created",
                "skill_id": response.data[0]["id"],
                "skill_name": response.data[0]["name"],
            }
        else:
            raise HTTPException(status_code=400, detail="Could not create skill")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add canonical skill: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-mapping")
async def update_skill_mapping(
    mapping_id: str,
    canonical_skill_id: str,
    confidence_score: float,
    supabase=Depends(get_supabase_client),
) -> dict:
    """Update a skill mapping (e.g., to correct an incorrect mapping).

    Args:
        mapping_id: ID of the mapping to update
        canonical_skill_id: New canonical skill ID
        confidence_score: New confidence score (0-1)
    """
    try:
        response = await supabase.table("skill_mappings").update({
            "canonical_skill_id": canonical_skill_id,
            "confidence_score": confidence_score,
            "mapping_method": "manual",
        }).eq("id", mapping_id).execute()

        if response.data:
            return {"status": "updated", "mapping_id": mapping_id}
        else:
            raise HTTPException(status_code=404, detail="Mapping not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update skill mapping: {e}")
        raise HTTPException(status_code=500, detail=str(e))
