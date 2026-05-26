"""
Candidate Scoring Worker - Scores candidates based on normalized skills.

Phase 11: Calculates candidate scores, readiness status, and recommendation scores
based on skill coverage, confidence, and diversity.
"""

import logging
import asyncio
from typing import Any, Optional, Callable, TypeVar
from uuid import UUID
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Type variable for retry decorator
T = TypeVar('T')


async def retry_with_backoff(
    operation: Callable[[], Any],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    operation_name: str = "database operation"
) -> Any:
    """Retry an operation with exponential backoff for transient errors.

    Args:
        operation: Callable that performs the operation
        max_retries: Maximum number of retries (default 3)
        initial_delay: Initial delay in seconds (default 1.0)
        backoff_factor: Multiplier for delay between retries (default 2.0)
        operation_name: Name for logging purposes

    Returns:
        Result of the operation

    Raises:
        Exception: If all retries fail
    """
    transient_errors = (
        ConnectionError,
        TimeoutError,
        OSError,  # Includes network errors
    )

    delay = initial_delay
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return operation()
        except transient_errors as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Transient error in {operation_name} (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                    f"Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
                delay *= backoff_factor
            else:
                logger.error(
                    f"Failed to execute {operation_name} after {max_retries + 1} attempts: {e}"
                )
                raise
        except Exception as e:
            # Non-transient errors should fail immediately
            logger.error(f"Non-transient error in {operation_name}: {e}")
            raise


class CandidateScoringWorker:
    """Worker for scoring candidates based on skills."""

    def __init__(self, supabase_client: Any):
        """Initialize candidate scoring worker.

        Args:
            supabase_client: Supabase client instance
        """
        self.supabase = supabase_client

    async def score_candidates_by_skills(self, limit: int = 20) -> dict:
        """Score all candidates based on their normalized skills.

        Args:
            limit: Maximum number of candidates to score

        Returns:
            Dict with metrics: {
                'total_processed': int,
                'candidates_scored': int,
                'ready_candidates': int,
                'review_candidates': int,
                'incomplete_candidates': int,
                'errors': list,
                'avg_score': float
            }
        """
        result = {
            "total_processed": 0,
            "candidates_scored": 0,
            "ready_candidates": 0,
            "review_candidates": 0,
            "incomplete_candidates": 0,
            "errors": [],
            "avg_score": 0.0,
            "total_score": 0.0,
        }

        try:
            # Get all candidates without deleted_at (with retry)
            def fetch_candidates():
                response = self.supabase.table("candidates").select(
                    "id, name, detected_language"
                ).is_("deleted_at", "null").limit(limit).execute()
                return response.data or []

            candidates = await retry_with_backoff(
                fetch_candidates,
                max_retries=3,
                operation_name="fetch candidates for scoring"
            )
            result["total_processed"] = len(candidates)

            logger.info(f"Scoring {len(candidates)} candidates")

            for candidate in candidates:
                try:
                    score_result = await self._score_candidate(candidate)
                    if score_result:
                        result["candidates_scored"] += 1
                        result["total_score"] += score_result["recommendation_score"]

                        # Track readiness status
                        status = score_result["skill_readiness_status"]
                        if status == "READY":
                            result["ready_candidates"] += 1
                        elif status == "REVIEW":
                            result["review_candidates"] += 1
                        else:
                            result["incomplete_candidates"] += 1

                except Exception as e:
                    error_msg = f"Failed to score candidate {candidate['id']}: {str(e)}"
                    logger.error(error_msg)
                    result["errors"].append({
                        "candidate_id": candidate["id"],
                        "error": error_msg,
                    })

            # Calculate average score
            if result["candidates_scored"] > 0:
                result["avg_score"] = result["total_score"] / result["candidates_scored"]

            logger.info(
                f"Candidate scoring complete",
                total=result["total_processed"],
                scored=result["candidates_scored"],
                ready=result["ready_candidates"],
                review=result["review_candidates"],
                incomplete=result["incomplete_candidates"],
                avg_score=result["avg_score"],
                errors=len(result["errors"]),
            )

            return result

        except Exception as e:
            logger.error(f"Candidate scoring batch failed: {e}", exc_info=True)
            result["errors"].append({"error": str(e)})
            return result

    async def _score_candidate(self, candidate: dict) -> Optional[dict]:
        """Score a single candidate.

        Args:
            candidate: Candidate record

        Returns:
            Dict with score data or None if error
        """
        candidate_id = candidate["id"]

        try:
            # Get all skills for candidate (with retry)
            def fetch_skills():
                response = self.supabase.table("candidate_skills_detailed").select(
                    "*"
                ).eq("candidate_id", candidate_id).execute()
                return response.data or []

            skills = await retry_with_backoff(
                fetch_skills,
                max_retries=3,
                operation_name=f"fetch skills for candidate {candidate_id}"
            )

            # Calculate metrics
            normalized_skills_count = len(skills)
            low_confidence_count = len([s for s in skills if s.get("confidence_score", 0) < 0.85])

            # Calculate average confidence
            if skills:
                avg_confidence = sum(s.get("confidence_score", 0) for s in skills) / len(skills)
            else:
                avg_confidence = 0.0

            # Calculate skill diversity (unique categories)
            categories = set(s.get("skill_category") for s in skills if s.get("skill_category"))
            skill_diversity_score = (len(categories) / 16) * 100  # 16 total categories

            # Calculate skill seniority (average popularity)
            if skills:
                # Try to get popularity scores from skills table (with retry)
                skill_ids = [s.get("skill_id") for s in skills if s.get("skill_id")]
                if skill_ids:
                    def fetch_skill_popularity():
                        response = self.supabase.table("skills").select(
                            "popularity_score"
                        ).in_("id", skill_ids).execute()
                        return response.data or []

                    popularity_data = await retry_with_backoff(
                        fetch_skill_popularity,
                        max_retries=2,  # Fewer retries for secondary query
                        operation_name=f"fetch skill popularity for candidate {candidate_id}"
                    )
                    popularities = [s.get("popularity_score", 0.5) for s in popularity_data]
                    skill_seniority_score = (sum(popularities) / len(popularities)) * 100 if popularities else 50.0
                else:
                    skill_seniority_score = 50.0
            else:
                skill_seniority_score = 0.0

            # Calculate recommendation score (0-100)
            # Formula: (skills_count * 2) + (avg_confidence * 50) + (diversity / 2)
            recommendation_score = min(
                100,
                (normalized_skills_count * 2) +
                (avg_confidence * 50) +
                (skill_diversity_score / 2)
            )

            # Determine readiness status
            if avg_confidence >= 0.85 and normalized_skills_count >= 3:
                readiness_status = "READY"
            elif avg_confidence >= 0.70 or normalized_skills_count >= 2:
                readiness_status = "REVIEW"
            else:
                readiness_status = "INCOMPLETE"

            # Update candidate with scores (with retry)
            update_data = {
                "normalized_skills_count": normalized_skills_count,
                "average_skill_confidence": round(avg_confidence, 2),
                "skill_readiness_status": readiness_status,
                "recommendation_score": int(recommendation_score),
                "last_skill_analysis_at": datetime.now(timezone.utc).isoformat(),
            }

            def update_candidate():
                self.supabase.table("candidates").update(update_data).eq("id", candidate_id).execute()
                return True

            await retry_with_backoff(
                update_candidate,
                max_retries=3,
                operation_name=f"update candidate scores for {candidate_id}"
            )

            logger.debug(
                f"Scored candidate",
                candidate_id=candidate_id,
                skills=normalized_skills_count,
                confidence=avg_confidence,
                recommendation=recommendation_score,
                status=readiness_status,
            )

            return {
                "candidate_id": candidate_id,
                "normalized_skills_count": normalized_skills_count,
                "average_skill_confidence": avg_confidence,
                "skill_diversity_score": skill_diversity_score,
                "skill_seniority_score": skill_seniority_score,
                "recommendation_score": int(recommendation_score),
                "skill_readiness_status": readiness_status,
                "low_confidence_mappings_count": low_confidence_count,
            }

        except Exception as e:
            logger.warning(f"Failed to score candidate {candidate_id}: {e}")
            return None

    async def get_low_confidence_mappings(self, confidence_threshold: float = 0.85, limit: int = 50) -> dict:
        """Get all low-confidence skill mappings across candidates.

        Args:
            confidence_threshold: Threshold for "low confidence" (default 0.85)
            limit: Maximum mappings to return

        Returns:
            Dict with mappings and grouping
        """
        try:
            # Get all low-confidence candidate skills (with retry)
            def fetch_low_confidence_skills():
                response = self.supabase.table("candidate_skills_detailed").select(
                    "*"
                ).lte("confidence_score", confidence_threshold).limit(limit).execute()
                return response.data or []

            skills = await retry_with_backoff(
                fetch_low_confidence_skills,
                max_retries=2,
                operation_name="fetch low-confidence skill mappings"
            )

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
                f"Found {len(skills)} low-confidence mappings",
                threshold=confidence_threshold,
                candidates=len(by_candidate)
            )

            return {
                "low_confidence_count": len(skills),
                "candidates_affected": len(by_candidate),
                "by_candidate": by_candidate,
            }

        except Exception as e:
            logger.error(f"Failed to get low-confidence mappings: {e}")
            return {
                "low_confidence_count": 0,
                "candidates_affected": 0,
                "by_candidate": {},
                "error": str(e)
            }

    async def get_readiness_summary(self) -> dict:
        """Get summary of candidate readiness statuses.

        Returns:
            Dict with counts by readiness status
        """
        try:
            # Group results
            summary = {
                "READY": 0,
                "REVIEW": 0,
                "INCOMPLETE": 0,
                "total_candidates": 0,
            }

            # Note: Supabase doesn't support COUNT in this way, so we need to fetch all (with retry)
            def fetch_all_candidates():
                response = self.supabase.table("candidates").select(
                    "skill_readiness_status"
                ).is_("deleted_at", "null").execute()
                return response.data or []

            all_candidates_data = await retry_with_backoff(
                fetch_all_candidates,
                max_retries=2,
                operation_name="fetch all candidates for readiness summary"
            )

            for candidate in all_candidates_data:
                status = candidate.get("skill_readiness_status", "INCOMPLETE")
                if status in summary:
                    summary[status] += 1
                summary["total_candidates"] += 1

            logger.info(
                f"Readiness summary",
                ready=summary["READY"],
                review=summary["REVIEW"],
                incomplete=summary["INCOMPLETE"],
                total=summary["total_candidates"],
            )

            return summary

        except Exception as e:
            logger.error(f"Failed to get readiness summary: {e}")
            return {
                "READY": 0,
                "REVIEW": 0,
                "INCOMPLETE": 0,
                "total_candidates": 0,
                "error": str(e)
            }
