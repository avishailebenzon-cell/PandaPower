"""
Session 30: Real candidate matching and scoring for Pandi
Implements candidate database queries and match score calculation
"""

import logging
from typing import Optional
from uuid import UUID

from pandapower.core.supabase import get_supabase_client

import structlog as _structlog
logger = _structlog.get_logger(__name__)


class CandidateMatchingEngine:
    """Match candidates to job contexts based on skills, experience, and requirements."""

    def __init__(self):
        self._supabase = None

    async def _get_supabase(self):
        """Get Supabase client lazily."""
        if self._supabase is None:
            self._supabase = await get_supabase_client()
        return self._supabase

    async def search_matching_candidates(
        self,
        job_context: dict,
        limit: int = 3,
    ) -> list[dict]:
        """
        Search for candidates matching job context from database.

        Args:
            job_context: Dict with title, qualifications, must_have, nice_to_have,
                        security_clearance, location, years_experience_min, notes
            limit: Max candidates to return (default 3)

        Returns:
            List of matched candidates with scores and reasoning
        """
        try:
            supabase = await self._get_supabase()

            # Extract requirements from job context
            must_have_skills = job_context.get("must_have", [])
            nice_to_have_skills = job_context.get("nice_to_have", [])
            required_clearance = job_context.get("security_clearance", "none")
            location_preference = job_context.get("location", "")
            min_years_experience = self._extract_min_years(
                job_context.get("qualifications", "")
            )

            logger.info(
                "searching_candidates",
                must_have_count=len(must_have_skills),
                nice_to_have_count=len(nice_to_have_skills),
                required_clearance=required_clearance,
            )

            # Query active candidates from database
            candidates_result = await supabase.table("candidates").select(
                """
                id, name, years_of_experience,
                clearance_level,
                location, primary_domain, languages
                """
            ).eq("is_active", True).limit(100).execute()  # Fetch batch for scoring

            candidates = candidates_result.data if candidates_result else []

            if not candidates:
                logger.warning("no_active_candidates_found")
                return []

            # For each candidate, fetch their skills
            scored_candidates = []
            for candidate in candidates:
                score_data = await self._calculate_match_score(
                    candidate,
                    supabase,
                    must_have_skills,
                    nice_to_have_skills,
                    required_clearance,
                    min_years_experience,
                    location_preference,
                )
                scored_candidates.append(score_data)

            # Sort by score descending and return top N
            scored_candidates.sort(key=lambda x: x["match_score"], reverse=True)
            top_candidates = scored_candidates[:limit]

            logger.info(
                "candidates_matched",
                count=len(top_candidates),
                top_score=top_candidates[0]["match_score"] if top_candidates else 0,
            )

            return top_candidates

        except Exception as e:
            logger.error(f"search_matching_candidates failed: {e}", exc_info=True)
            return []

    async def _calculate_match_score(
        self,
        candidate: dict,
        supabase,
        must_have_skills: list,
        nice_to_have_skills: list,
        required_clearance: str,
        min_years_experience: float,
        location_preference: str,
    ) -> dict:
        """Calculate match score for a single candidate."""

        candidate_id = candidate["id"]

        # Fetch candidate skills
        skills_result = await supabase.table("candidate_skills").select(
            "skill_name, years_in_skill, proficiency"
        ).eq("candidate_id", str(candidate_id)).execute()

        candidate_skills = skills_result.data if skills_result else []
        candidate_skill_names = {skill["skill_name"].lower() for skill in candidate_skills}

        # Calculate skill match scores
        must_have_matched = sum(
            1 for skill in must_have_skills
            if skill.lower() in candidate_skill_names
        )
        must_have_total = len(must_have_skills) if must_have_skills else 1
        must_have_score = (must_have_matched / must_have_total * 100) if must_have_total > 0 else 50

        nice_to_have_matched = sum(
            1 for skill in nice_to_have_skills
            if skill.lower() in candidate_skill_names
        )
        nice_to_have_total = len(nice_to_have_skills) if nice_to_have_skills else 0
        nice_to_have_score = (
            (nice_to_have_matched / nice_to_have_total * 100)
            if nice_to_have_total > 0
            else 50
        )

        # Experience match
        candidate_years = candidate.get("years_of_experience") or 0
        experience_score = min(
            100,
            (candidate_years / max(min_years_experience, 1) * 100)
            if min_years_experience > 0
            else 100,
        )

        # Security clearance match
        clearance_score = self._calculate_clearance_score(
            candidate.get("clearance_level"),
            None,
            required_clearance,
        )

        # Location match (simple string comparison)
        location_score = 100 if self._location_matches(
            candidate.get("location", ""), location_preference
        ) else 70

        # Composite score: weight the components
        # Must-have skills: 40%, experience: 25%, clearance: 20%, location: 15%
        composite_score = (
            must_have_score * 0.40
            + experience_score * 0.25
            + clearance_score * 0.20
            + location_score * 0.10
            + nice_to_have_score * 0.05
        )

        # Generate reasoning
        reasoning = self._generate_reasoning(
            must_have_matched,
            must_have_total,
            nice_to_have_matched,
            nice_to_have_total,
            candidate_years,
            min_years_experience,
            candidate.get("clearance_level"),
            required_clearance,
            location_preference,
            candidate.get("location"),
        )

        return {
            "candidate_number": candidate.get("id"),
            "match_score": round(composite_score, 1),
            "years_experience": float(candidate_years),
            "security_clearance": candidate.get("clearance_level", "unknown"),
            "location": candidate.get("location", ""),
            "languages": candidate.get("languages", []),
            "top_skills": self._get_top_skills(candidate_skills, 4),
            "summary": candidate.get("cv_summary", "")[:200],  # Truncate for readability
            "reasoning": reasoning,
        }

    def _extract_min_years(self, qualifications: str) -> float:
        """Extract minimum years of experience from qualifications text."""
        if not qualifications:
            return 3.0

        # Look for patterns like "5+ years", "5 years", "5-10 years"
        import re

        patterns = [
            r"(\d+)\+?\s*years?",
            r"(\d+)\-\d+\s*years?",
        ]

        for pattern in patterns:
            match = re.search(pattern, qualifications, re.IGNORECASE)
            if match:
                return float(match.group(1))

        return 3.0  # Default to 3 years if not found

    def _calculate_clearance_score(
        self,
        candidate_clearance: Optional[str],
        clearance_confidence: Optional[float],
        required_clearance: str,
    ) -> float:
        """Calculate security clearance match score."""

        clearance_hierarchy = {
            "none": 0,
            "confidential": 1,
            "secret": 2,
            "top_secret": 3,
            "highest": 4,
            "unknown": -1,
        }

        required_level = clearance_hierarchy.get(required_clearance.lower(), 0)
        candidate_level = clearance_hierarchy.get(
            (candidate_clearance or "unknown").lower(), -1
        )

        # If required is "none", any clearance is fine
        if required_level == 0:
            return 100

        # If unknown, give benefit of doubt but lower score
        if candidate_level == -1:
            return 60

        # If candidate has same or higher clearance, full marks
        if candidate_level >= required_level:
            confidence = clearance_confidence or 0.8
            return 100 * confidence

        # If candidate has lower clearance, penalize
        return max(30, 60 - (required_level - candidate_level) * 15)

    def _location_matches(self, candidate_city: str, location_preference: str) -> bool:
        """Check if candidate location matches requirement (fuzzy)."""
        if not location_preference or location_preference.lower() == "any":
            return True

        if not candidate_city:
            return True  # Unknown location gives benefit of doubt

        # Simple substring match (case-insensitive)
        return location_preference.lower() in candidate_city.lower() or \
               candidate_city.lower() in location_preference.lower()

    def _get_top_skills(self, candidate_skills: list, count: int = 4) -> list[str]:
        """Get top N skills from candidate."""
        if not candidate_skills:
            return []

        # Sort by years (if available) or by proficiency level
        proficiency_order = {"expert": 4, "advanced": 3, "intermediate": 2, "beginner": 1}

        sorted_skills = sorted(
            candidate_skills,
            key=lambda x: (
                x.get("years_in_skill") or 0,
                proficiency_order.get(x.get("proficiency", ""), 0),
            ),
            reverse=True,
        )

        return [
            f"{skill['skill_name']} ({skill.get('years_in_skill', 1):.0f}y)"
            if skill.get("years_in_skill")
            else skill["skill_name"]
            for skill in sorted_skills[:count]
        ]

    def _generate_reasoning(
        self,
        must_have_matched: int,
        must_have_total: int,
        nice_to_have_matched: int,
        nice_to_have_total: int,
        candidate_years: float,
        required_years: float,
        candidate_clearance: Optional[str],
        required_clearance: str,
        location_preference: str,
        candidate_city: str,
    ) -> str:
        """Generate human-readable reasoning for the match."""

        reasons = []

        # Skills match
        if must_have_matched == must_have_total and must_have_total > 0:
            reasons.append(f"✓ כל {must_have_total} כישורי החובה קיימים")
        elif must_have_matched > 0:
            reasons.append(f"✓ {must_have_matched}/{must_have_total} כישורי חובה קיימים")
        else:
            reasons.append(f"✗ חסרים כישורי חובה ({must_have_total} נדרשים)")

        if nice_to_have_matched > 0:
            reasons.append(f"✓ {nice_to_have_matched} כישורים מועדפים קיימים")

        # Experience
        if candidate_years >= required_years:
            reasons.append(f"✓ {candidate_years:.0f} שנות ניסיון (≥ {required_years:.0f} נדרשות)")
        else:
            reasons.append(
                f"~ {candidate_years:.0f} שנות ניסיון (נדרשו {required_years:.0f}, פער קל)"
            )

        # Clearance
        clearance_hierarchy = ["none", "confidential", "secret", "top_secret", "highest"]
        if required_clearance.lower() != "none":
            if candidate_clearance and candidate_clearance.lower() in clearance_hierarchy:
                if clearance_hierarchy.index(candidate_clearance.lower()) >= \
                   clearance_hierarchy.index(required_clearance.lower()):
                    reasons.append(f"✓ בעל סיווג ביטחוני נדרש ({candidate_clearance})")
                else:
                    reasons.append(f"⚠ סיווג ביטחוני מתחת לנדרש ({candidate_clearance})")
            else:
                reasons.append("⚠ סטטוס סיווג ביטחוני לא ברור")

        # Location
        if location_preference and location_preference.lower() != "any":
            if self._location_matches(candidate_city, location_preference):
                reasons.append(f"✓ מיקום תואם ({candidate_city})")
            else:
                reasons.append(f"⚠ מיקום שונה ({candidate_city})")

        return " ".join(reasons)


async def search_candidates_real(
    context_summary: str, limit: int = 3
) -> dict:
    """
    Real candidate search implementation (Session 30).

    Replaces the mock implementation from Session 28.
    Uses the CandidateMatchingEngine to find real matches.
    """
    try:
        # Parse context summary to extract job requirements
        # In real use, this would be called from handle_search_candidates
        # which has access to the actual job_context dict
        # For now, we create a basic context for testing

        engine = CandidateMatchingEngine()

        # This is a simplified extraction - in practice, the handler
        # will pass the full job_context dict
        job_context = _parse_context_summary(context_summary)

        # Search matching candidates
        matched = await engine.search_matching_candidates(job_context, limit)

        if not matched:
            return {
                "status": "success",
                "candidates": [],
                "total_found": 0,
                "message": "No suitable candidates found in database",
            }

        return {
            "status": "success",
            "candidates": matched,
            "total_found": len(matched),
        }

    except Exception as e:
        logger.error(f"search_candidates_real failed: {e}", exc_info=True)
        return {
            "status": "error",
            "candidates": [],
            "total_found": 0,
            "error": str(e),
        }


async def search_candidates_for_context(
    job_context: dict, limit: int = 3
) -> dict:
    """
    Real candidate search using actual job_context dict (Session 30).

    This is the preferred method when full context is available.

    Args:
        job_context: Dict with title, qualifications, must_have, nice_to_have, etc.
        limit: Max candidates to return

    Returns:
        Result dict with candidates and total found
    """
    try:
        engine = CandidateMatchingEngine()
        matched = await engine.search_matching_candidates(job_context, limit)

        return {
            "status": "success",
            "candidates": matched,
            "total_found": len(matched),
        }

    except Exception as e:
        logger.error(f"search_candidates_for_context failed: {e}", exc_info=True)
        return {
            "status": "error",
            "candidates": [],
            "total_found": 0,
            "error": str(e),
        }


def _parse_context_summary(summary: str) -> dict:
    """
    Parse context summary string to extract job requirements.

    This is a fallback for when we only have a text summary.
    In practice, we use the full job_context dict instead.
    """
    # Basic extraction from text
    import re

    context = {
        "must_have": [],
        "nice_to_have": [],
        "security_clearance": "none",
        "location": "",
        "years_experience_min": 3,
    }

    # Look for clearance mentions
    if any(word in summary.lower() for word in ["secret", "סודי"]):
        context["security_clearance"] = "secret"
    elif any(word in summary.lower() for word in ["top secret", "top_secret", "סודי מאוד"]):
        context["security_clearance"] = "top_secret"

    return context
