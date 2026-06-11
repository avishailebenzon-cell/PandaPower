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
            # Only pick the LATEST CV per candidate that we HAVEN'T processed
            # yet. The candidate_extracted_at cursor (migration 010) is the
            # marker — without it the worker re-fetched the same 20 rows every
            # run and never advanced through the backlog. _fetch_unprocessed_cvs
            # transparently falls back to a link-based exclusion if the column
            # doesn't exist yet (i.e. migration not applied).
            parsed_cvs = await self._fetch_unprocessed_cvs(limit)
            result["total_processed"] = len(parsed_cvs)

            logger.info(f"Processing {len(parsed_cvs)} unprocessed parsed CVs for candidate creation/update")

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
                finally:
                    # ALWAYS stamp the cursor — even on skip/error — so an
                    # unparseable CV (no name, low confidence) can never block
                    # the queue behind it. No-op if the column doesn't exist.
                    await self._mark_attempted(cv["id"])

            logger.info(
                f"Candidate creation complete: total={result['total_processed']}, "
                f"created={result['created']}, updated={result['updated']}, "
                f"skipped={result['skipped_low_confidence']}, errors={len(result['errors'])}"
            )

            return result

        except Exception as e:
            logger.error(f"Candidate creation batch failed: {e}", exc_info=True)
            result["errors"].append({"error": str(e)})
            return result

    # Columns we need from cv_files for candidate creation.
    _CV_SELECT = (
        "id, original_filename, llm_analysis, source_email_from, "
        "source_email_received_at, candidate_email, is_latest, source"
    )

    async def _fetch_unprocessed_cvs(self, limit: int) -> list[dict]:
        """Return up to `limit` success+is_latest CVs not yet turned into candidates.

        Primary path uses the candidate_extracted_at cursor (migration 010):
        cheap, indexed, newest-first, and immune to unparseable CVs blocking
        the queue. If that column doesn't exist yet (migration not applied),
        falls back to excluding CVs already linked to a candidate.
        """
        # ── Primary: cursor column ────────────────────────────────────────
        try:
            r = await self.supabase.table("cv_files").select(self._CV_SELECT).eq(
                "parse_status", "success"
            ).eq("is_latest", True).is_(
                "candidate_extracted_at", "null"
            ).order("created_at", desc=True).limit(limit).execute()
            return r.data or []
        except Exception as e:
            # Column missing → migration 010 not applied yet. Fall back.
            msg = str(e).lower()
            if "candidate_extracted_at" not in msg and "column" not in msg:
                raise
            logger.warning(
                "candidate_extracted_at column not found — falling back to "
                "link-based exclusion (apply migration 010 for the fast path)"
            )

        # ── Fallback: exclude CVs already linked to a candidate ───────────
        linked = await self._load_linked_cv_ids()
        collected: list[dict] = []
        offset = 0
        page = 200
        while len(collected) < limit:
            r = await self.supabase.table("cv_files").select(self._CV_SELECT).eq(
                "parse_status", "success"
            ).eq("is_latest", True).order(
                "created_at", desc=True
            ).range(offset, offset + page - 1).execute()
            batch = r.data or []
            if not batch:
                break
            for cv in batch:
                if cv["id"] not in linked:
                    collected.append(cv)
                    if len(collected) >= limit:
                        break
            if len(batch) < page:
                break
            offset += page
        return collected

    async def _load_linked_cv_ids(self) -> set:
        """Return the set of cv_file_ids already linked to a candidate."""
        linked: set = set()
        offset = 0
        page = 1000
        while True:
            r = await self.supabase.table("candidates").select("cv_file_id").range(
                offset, offset + page - 1
            ).execute()
            batch = r.data or []
            linked.update(c["cv_file_id"] for c in batch if c.get("cv_file_id"))
            if len(batch) < page:
                break
            offset += page
        return linked

    async def _mark_attempted(self, cv_id: str) -> None:
        """Stamp candidate_extracted_at so this CV is never re-fetched.

        No-op (silently) if the column doesn't exist yet — in that case the
        link-based fallback in _fetch_unprocessed_cvs handles exclusion.
        """
        try:
            await self.supabase.table("cv_files").update(
                {"candidate_extracted_at": datetime.utcnow().isoformat()}
            ).eq("id", cv_id).execute()
        except Exception as e:
            msg = str(e).lower()
            if "candidate_extracted_at" not in msg and "column" not in msg:
                logger.debug(f"Failed to stamp candidate_extracted_at on {cv_id}: {e}")

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
                f"Skipping candidate creation - low confidence "
                f"(cv_id={cv_id}, confidence={overall_confidence:.2f}, "
                f"threshold={CONFIDENCE_THRESHOLD})"
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
        # WhatsApp CVs (Pandius intake) often don't carry a phone/email inside
        # the CV text — but we DO know the sender's WhatsApp number, which was
        # stored on the cv_files row at ingest (source_email_from / candidate_email
        # both hold the phone). Fall back to it so phone-based dedup and the
        # candidate<->contact link below have a key to work with.
        if not phone and (cv.get("source") == "whatsapp"):
            from pandapower.core.phone import to_international

            wa_phone = cv.get("source_email_from") or cv.get("candidate_email")
            phone = to_international(wa_phone) or (wa_phone or None)
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
            outcome = await self._update_existing_candidate(existing, candidate_data, cv_id, filename)
            await self._link_candidate_to_pandius_contact(cv, existing["id"])
            return outcome

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
                    outcome = await self._update_existing_candidate(existing, candidate_data, cv_id, filename)
                    await self._link_candidate_to_pandius_contact(cv, existing["id"])
                    return outcome
            raise

        if response.data:
            candidate_id = response.data[0]["id"]
            logger.info(
                f"Candidate created (NEW): {candidate_data['name']!r} "
                f"(id={candidate_id}, email={email}, cv={filename})"
            )
            await self._link_candidate_to_pandius_contact(cv, candidate_id)
            return "created"
        raise ValueError(f"Failed to insert candidate record")

    async def _link_candidate_to_pandius_contact(self, cv: dict, candidate_id: str) -> None:
        """Stamp candidates.contact_id from the Pandius intake bridge.

        For a WhatsApp CV, cv_files.pandius_client_id points at the intake row,
        which carries contact_id once Pandius's save_candidate has run. Walking
        CV -> pandius_client -> contact links the candidate to the Pandius
        contact even when the CV text held no usable email/phone. Handles the
        details-then-CV ordering (contact already exists when the CV arrives);
        the CV-then-details ordering is closed from save_candidate's side.

        Best-effort and fully back-compatible: a missing column (migration 021
        not applied) or a not-yet-identified client is a silent no-op.
        """
        try:
            # pandius_client_id lives on cv_files but isn't in the batch select
            # (kept out so the column-missing case can't break the batch fetch).
            r = await self.supabase.table("cv_files").select(
                "pandius_client_id"
            ).eq("id", cv["id"]).limit(1).execute()
            client_id = (r.data[0].get("pandius_client_id") if r.data else None)
            if not client_id:
                return

            pc = await self.supabase.table("pandius_clients").select(
                "contact_id"
            ).eq("id", client_id).limit(1).execute()
            contact_id = (pc.data[0].get("contact_id") if pc.data else None)
            if not contact_id:
                return

            await self.supabase.table("candidates").update(
                {"contact_id": contact_id}
            ).eq("id", candidate_id).execute()
            logger.info(
                f"Linked candidate {candidate_id} to Pandius contact {contact_id}"
            )
        except Exception as e:
            msg = str(e).lower()
            if "pandius_client_id" not in msg and "contact_id" not in msg and "column" not in msg:
                logger.debug(f"Pandius contact link skipped for {candidate_id}: {e}")

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
            # '+972542206805' AND '+972-52-950-7574' (separators that split the
            # local number). The ilike prefilter therefore uses only the LAST 4
            # digits — these stay contiguous in every common format — then we
            # compare the full normalized numbers in Python via phones_match().
            try:
                from pandapower.core.phone import phones_match, to_international

                intl = to_international(phone)
                if intl and len(intl) >= 7:
                    tail4 = intl[-4:]
                    r = await self.supabase.table("candidates").select("*").ilike(
                        "phone", f"%{tail4}%"
                    ).is_("deleted_at", "null").limit(50).execute()
                    for row in r.data or []:
                        if phones_match(phone, row.get("phone")):
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
