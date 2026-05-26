"""
Candidate creation worker - converts parsed CV data to candidate records.

Phase 9: Creates structured candidate profiles from successfully parsed CVs
with high confidence scores (>0.85 average confidence).
"""

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pandapower.workers.sender_blocklist import is_likely_candidate_email

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.85  # Only create candidates for high-confidence parses


class CandidateCreationWorker:
    """Worker for creating candidates from parsed CV data."""

    def __init__(self, supabase_client: Any):
        """Initialize the candidate creation worker.

        Args:
            supabase_client: Supabase client instance
        """
        self.supabase = supabase_client

    async def create_candidates_from_parsed_cvs(self, limit: int = 10) -> dict:
        """Create or UPDATE candidates from successfully parsed CVs.

        For each parsed CV:
        1. Try to find an existing candidate by extracted email (or phone).
        2. If found → UPDATE that candidate with the newest analysis (history
           is preserved in cv_files; old analyses are kept under is_latest=False).
        3. If not found → INSERT a new candidate.

        This is the "same candidate sent CV multiple times" path. The cv_parse
        worker has already marked the older CVs of this candidate as
        is_latest=False, so we just trust extracted_fields.email here.

        Args:
            limit: Maximum number of CVs to process in one batch
        """
        result = {
            "total_processed": 0,
            "created": 0,
            "updated": 0,
            "skipped_low_confidence": 0,
            "errors": [],
        }

        try:
            # Only pick the LATEST CV per candidate. If a candidate uploaded 5
            # times, we want to run candidate creation only on the most recent
            # analysis - not all five (which would just re-update with the
            # same data 5 times in random order).
            response = await self.supabase.table("cv_files").select(
                "id, original_filename, llm_analysis, source_email_from, "
                "source_email_received_at, candidate_email, is_latest"
            ).eq("parse_status", "success").eq("is_latest", True).limit(limit).execute()

            parsed_cvs = response.data or []
            result["total_processed"] = len(parsed_cvs)

            logger.info(f"Processing {len(parsed_cvs)} latest parsed CVs for candidate creation/update")

            for cv in parsed_cvs:
                try:
                    outcome = await self._create_or_update_candidate_from_cv(cv)
                    if outcome == "created":
                        result["created"] += 1
                    elif outcome == "updated":
                        result["updated"] += 1
                    elif outcome == "skipped_low_confidence":
                        result["skipped_low_confidence"] += 1
                except Exception as e:
                    error_msg = f"Failed to create/update candidate from CV {cv['id']}: {str(e)}"
                    logger.error(error_msg)
                    result["errors"].append({
                        "cv_id": cv["id"],
                        "filename": cv["original_filename"],
                        "error": error_msg,
                    })

            logger.info(
                f"Candidate creation complete",
                total=result["total_processed"],
                created=result["created"],
                skipped=result["skipped_low_confidence"],
                errors=len(result["errors"]),
            )

            return result

        except Exception as e:
            logger.error(f"Candidate creation batch failed: {e}", exc_info=True)
            result["errors"].append({"error": str(e)})
            return result

    async def _create_or_update_candidate_from_cv(self, cv: dict) -> str:
        """Create new OR update existing candidate from a parsed CV.

        Returns one of: "created" | "updated" | "skipped_low_confidence".

        Dedup priority:
        1. Match by candidate_email on cv_files (already linked to a candidate via cv_file_id history)
        2. Match by extracted_fields.email
        3. Match by extracted_fields.phone (E.164 normalized)
        Falls back to creating a new candidate if no match.
        """
        cv_id = cv["id"]
        filename = cv["original_filename"]

        analysis = cv.get("llm_analysis", {}) or {}
        if not analysis:
            raise ValueError(f"No analysis found for CV {cv_id}")

        extracted_fields = analysis.get("extracted_fields", {}) or {}
        confidence_scores = analysis.get("confidence_scores", {}) or {}

        overall_confidence = self._calculate_confidence(confidence_scores)
        if overall_confidence < CONFIDENCE_THRESHOLD:
            logger.warning(
                f"Skipping candidate creation - low confidence",
                cv_id=cv_id,
                confidence=overall_confidence,
                threshold=CONFIDENCE_THRESHOLD,
            )
            return "skipped_low_confidence"

        # Build the payload — same shape whether we INSERT or UPDATE.
        # CRITICAL: refuse to store an intermediary/sender mailbox as the
        # candidate's email. Better NULL than wrong, because a wrong email
        # would let the next CV merge two unrelated people.
        raw_email = (extracted_fields.get("email") or "").strip().lower() or None
        email = raw_email if (raw_email and is_likely_candidate_email(raw_email)) else None
        if raw_email and not email:
            logger.info(
                f"[blocklist] Rejecting '{raw_email}' as candidate email "
                f"(it's an intermediary mailbox). Will store NULL instead."
            )
        phone = (extracted_fields.get("phone") or "").strip() or None
        candidate_data = {
            "name": extracted_fields.get("name"),
            "email": email,
            "phone": phone,
            "location": extracted_fields.get("geographical_location") or extracted_fields.get("location"),
            "clearance_level": extracted_fields.get("clearance_level"),
            "key_skills": self._extract_top_skills(extracted_fields.get("skills", [])),
            "years_of_experience": (
                extracted_fields.get("years_of_experience")
                or self._calculate_experience_years(extracted_fields.get("experience", []))
            ),
            "top_education": self._extract_top_education(
                extracted_fields.get("education", []),
                extracted_fields.get("university_1st_degree"),
            ),
            "experiences": extracted_fields.get("experience", []),
            "cv_file_id": cv_id,  # Always point to the LATEST CV
            "overall_confidence_score": overall_confidence,
            "field_confidence_scores": confidence_scores,
            "extracted_from_cv": analysis,
            "extraction_notes": analysis.get("extraction_notes"),
            "detected_language": analysis.get("detected_language"),
            "source_email_from": cv.get("source_email_from"),
            "source_email_received_at": cv.get("source_email_received_at"),
            "last_updated_at": datetime.utcnow().isoformat(),
        }

        if not candidate_data.get("name"):
            raise ValueError(f"Candidate name is required but missing")

        # ── Find existing candidate ───────────────────────────────────────
        existing = await self._find_existing_candidate(email=email, phone=phone)
        if existing:
            return await self._update_existing_candidate(existing, candidate_data, cv_id, filename)

        # ── No match → INSERT new ─────────────────────────────────────────
        logger.debug(f"Creating new candidate from CV {cv_id}: {filename}")
        try:
            response = await self.supabase.table("candidates").insert(candidate_data).execute()
        except Exception as e:
            # Race: another worker may have just inserted the same candidate.
            # Retry as UPDATE.
            msg = str(e).lower()
            if "duplicate" in msg or "unique" in msg or "conflict" in msg:
                logger.info(f"INSERT raced; retrying as UPDATE for CV {cv_id}")
                existing = await self._find_existing_candidate(email=email, phone=phone)
                if existing:
                    return await self._update_existing_candidate(existing, candidate_data, cv_id, filename)
            raise

        if response.data:
            candidate_id = response.data[0]["id"]
            logger.info(
                f"Candidate created (NEW): {candidate_data['name']!r} "
                f"(id={candidate_id}, email={email}, cv={filename})"
            )
            return "created"
        raise ValueError(f"Failed to insert candidate record")

    async def _find_existing_candidate(
        self, email: Optional[str], phone: Optional[str]
    ) -> Optional[dict]:
        """Return the existing candidate row (or None) matching this person.

        Lookup order:
        1. email (case-insensitive) — but ONLY if it passes the sender blocklist.
           A platform/intermediary email like info@jobnet.co.il is shared by
           THOUSANDS of CVs, so matching by it would merge every jobnet
           candidate into one record. We hard-skip this lookup in that case.
        2. phone (normalized: digits only after the country code)
        """
        if email and is_likely_candidate_email(email):
            try:
                r = await self.supabase.table("candidates").select("*").eq(
                    "email", email
                ).is_("deleted_at", "null").limit(1).execute()
                if r.data:
                    return r.data[0]
            except Exception as e:
                logger.debug(f"Email lookup failed for {email}: {e}")
        elif email:
            # Don't even try to dedupe by intermediary/sender mailboxes.
            logger.debug(
                f"Skipping email-based candidate lookup — '{email}' is a "
                f"sender/intermediary mailbox, not a personal address."
            )

        if phone:
            # Try exact match first
            try:
                r = await self.supabase.table("candidates").select("*").eq(
                    "phone", phone
                ).is_("deleted_at", "null").limit(1).execute()
                if r.data:
                    return r.data[0]
            except Exception as e:
                logger.debug(f"Phone lookup failed for {phone}: {e}")

            # Fall back to digits-only comparison: '+972-54-220-6805' should match
            # '+972542206805'. Pull a small batch and compare client-side.
            try:
                digits = "".join(ch for ch in phone if ch.isdigit())
                if len(digits) >= 7:
                    # Last 7 digits are typically the local number
                    tail = digits[-7:]
                    r = await self.supabase.table("candidates").select("*").ilike(
                        "phone", f"%{tail}%"
                    ).is_("deleted_at", "null").limit(5).execute()
                    for row in r.data or []:
                        row_digits = "".join(ch for ch in (row.get("phone") or "") if ch.isdigit())
                        if row_digits.endswith(tail):
                            return row
            except Exception as e:
                logger.debug(f"Fuzzy phone lookup failed for {phone}: {e}")

        return None

    async def _update_existing_candidate(
        self,
        existing: dict,
        candidate_data: dict,
        cv_id: str,
        filename: str,
    ) -> str:
        """Update a known candidate with the newest CV analysis.

        Preserves what shouldn't be overwritten (manual review notes, etc.)
        and keeps cv_file_id pointing at the most recent CV.
        """
        existing_id = existing["id"]

        # Fields we never want to overwrite (manual curation)
        do_not_overwrite = {
            "id", "created_at", "candidate_number",
            "manually_reviewed_at", "reviewed_by_user_id", "review_notes",
        }
        update_payload = {k: v for k, v in candidate_data.items() if k not in do_not_overwrite}

        await self.supabase.table("candidates").update(update_payload).eq(
            "id", existing_id
        ).execute()

        logger.info(
            f"Candidate UPDATED (existing): {candidate_data.get('name')!r} "
            f"(id={existing_id}, cv={filename}, prior_name={existing.get('name')!r})"
        )
        return "updated"

    @staticmethod
    def _calculate_confidence(confidence_scores: dict) -> float:
        """Calculate overall confidence score as average of all fields.

        Args:
            confidence_scores: Dict mapping field names to confidence values (0-1)

        Returns:
            Average confidence score (0-1)
        """
        if not confidence_scores:
            return 0.0

        # Filter out fields with 0 confidence (not found)
        valid_scores = [
            score for score in confidence_scores.values() if score > 0
        ]

        if not valid_scores:
            return 0.0

        return sum(valid_scores) / len(valid_scores)

    @staticmethod
    def _extract_top_skills(skills: list, limit: int = 10) -> list:
        """Extract top skills from the skills list.

        Args:
            skills: List of skill strings
            limit: Maximum number of skills to return

        Returns:
            List of top skills
        """
        if not skills:
            return []

        # Return first N skills (already ordered by importance in parsed data)
        return skills[:limit]

    @staticmethod
    def _calculate_experience_years(experiences: list) -> Optional[int]:
        """Calculate total years of experience from experience array.

        Args:
            experiences: List of dicts with 'duration' field (e.g., "2020-2023")

        Returns:
            Estimated years of experience or None if cannot calculate
        """
        if not experiences:
            return None

        from datetime import datetime
        from dateutil import parser as dateutil_parser

        years = 0

        for exp in experiences:
            duration = exp.get("duration", "")
            if not duration:
                continue

            try:
                # Parse duration like "2020-2023" or "2020-היום" (Hebrew for "today")
                if "היום" in duration or "today" in duration.lower() or duration.endswith("-"):
                    # Still ongoing
                    parts = duration.split("-")
                    if parts[0].isdigit():
                        start_year = int(parts[0])
                        end_year = datetime.now().year
                        years += (end_year - start_year)
                else:
                    # Parse range like "2020-2023"
                    parts = [p.strip() for p in duration.split("-")]
                    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                        start_year = int(parts[0])
                        end_year = int(parts[1])
                        years += (end_year - start_year)
            except Exception as e:
                logger.warning(f"Failed to parse duration '{duration}': {e}")
                continue

        return years if years > 0 else None

    @staticmethod
    def _extract_top_education(
        education_list: list, first_degree: Optional[dict]
    ) -> Optional[dict]:
        """Extract top education from education arrays.

        Prioritizes first_degree if available, otherwise uses first education item.

        Args:
            education_list: List of education dicts
            first_degree: Optional dict with name and field

        Returns:
            Top education dict or None
        """
        if first_degree and first_degree.get("name"):
            return {
                "institution": first_degree.get("name"),
                "field": first_degree.get("field"),
                "degree": "First Degree",
            }

        if education_list:
            return education_list[0]

        return None
