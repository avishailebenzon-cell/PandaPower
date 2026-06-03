import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Optional

from langdetect import detect as detect_language
from langdetect import LangDetectException

from pandapower.integrations.claude_api import AnthropicClient
from pandapower.integrations.supabase_storage import SupabaseStorageManager
from pandapower.workers.file_extractors import (
    ExtractorError,
    ExtractorTimeoutError,
    extract_text,
)
from pandapower.workers.sender_blocklist import is_likely_candidate_email

logger = logging.getLogger(__name__)


class CVParseWorker:
    """Orchestrates CV parsing: extraction → language detection → Claude API → storage."""

    def __init__(
        self,
        supabase_client: Any,
        storage_manager: SupabaseStorageManager,
        claude_client: AnthropicClient,
        batch_size: int = 10,
        parse_timeout: int = 300,
    ):
        self.supabase = supabase_client
        self.storage = storage_manager
        self.claude = claude_client
        self.batch_size = batch_size
        self.parse_timeout = parse_timeout

    async def parse_pending_cvs(self) -> dict[str, Any]:
        """
        Main entry point: fetch pending CVs and parse them.

        Returns:
            Metrics dict with total, success, failed, tokens_used
        """
        result = {
            "total_processed": 0,
            "success": 0,
            "failed": 0,
            "tokens_used": 0,
            "errors": [],
        }

        try:
            # Query pending CVs with limit
            logger.info(f"Querying pending CVs with batch size {self.batch_size}")
            query = (
                self.supabase.table("cv_files")
                .select("*")
                .eq("parse_status", "pending")
                .limit(self.batch_size)
                .execute()
            )

            if not query.data:
                logger.info("No pending CVs to process")
                return result

            pending_cvs = query.data
            logger.info(f"Found {len(pending_cvs)} pending CVs to process")

            # Mark all as parsing to prevent duplicate processing
            cv_ids = [cv["id"] for cv in pending_cvs]
            try:
                self.supabase.table("cv_files").update(
                    {
                        "parse_status": "parsing",
                        "processing_started_at": datetime.utcnow().isoformat(),
                    }
                ).in_("id", cv_ids).execute()
                logger.debug(f"Marked {len(cv_ids)} CVs as parsing")
            except Exception as e:
                logger.error(f"Failed to mark CVs as parsing: {e}")

            # Process each CV
            for cv_file in pending_cvs:
                try:
                    parsed = await self._parse_single_cv(cv_file)
                    result["total_processed"] += 1

                    if parsed.get("success"):
                        result["success"] += 1
                        result["tokens_used"] += parsed.get("tokens_used", 0)
                    else:
                        result["failed"] += 1
                        if parsed.get("error"):
                            result["errors"].append(
                                {
                                    "cv_id": cv_file["id"],
                                    "error": parsed["error"],
                                }
                            )

                except Exception as e:
                    logger.error(f"Unexpected error processing CV {cv_file['id']}: {e}")
                    result["total_processed"] += 1
                    result["failed"] += 1
                    result["errors"].append(
                        {
                            "cv_id": cv_file["id"],
                            "error": f"Unexpected error: {str(e)}",
                        }
                    )

            logger.info(
                f"CV parsing batch completed",
                total=result["total_processed"],
                success=result["success"],
                failed=result["failed"],
                tokens_used=result["tokens_used"],
            )
            return result

        except Exception as e:
            logger.error(f"CV parsing batch failed: {e}")
            result["errors"].append({"batch": str(e)})
            return result

    async def _parse_single_cv(self, cv_file: dict[str, Any]) -> dict[str, Any]:
        """
        Parse a single CV: download → extract → detect lang → Claude API → update DB.

        Returns:
            Dict with success flag, error message, tokens_used
        """
        cv_id = cv_file["id"]
        storage_path = cv_file.get("storage_path")
        original_filename = cv_file.get("original_filename", "unknown")

        result = {
            "success": False,
            "error": None,
            "tokens_used": 0,
        }

        start_time = time.time()

        try:
            logger.info(f"Starting parse for CV {cv_id}: {original_filename}")

            # Step 1: Download from storage
            logger.debug(f"Downloading from storage: {storage_path}")
            file_content = await self._download_cv_file(storage_path)
            logger.debug(f"Downloaded {len(file_content)} bytes")

            # Step 2: Extract text
            logger.debug(f"Extracting text from {original_filename}")
            try:
                raw_text, extraction_method = await extract_text(
                    original_filename, file_content
                )
            except ExtractorTimeoutError as e:
                error_msg = f"Text extraction timeout: {str(e)}"
                logger.warning(error_msg)
                await self._update_cv_record(
                    cv_id,
                    {
                        "parse_status": "failed",
                        "parse_error": error_msg,
                        "processing_completed_at": datetime.utcnow().isoformat(),
                        "parse_duration_ms": int((time.time() - start_time) * 1000),
                    },
                )
                result["error"] = error_msg
                return result

            except ExtractorError as e:
                error_msg = f"Text extraction failed: {str(e)}"
                logger.warning(error_msg)
                await self._update_cv_record(
                    cv_id,
                    {
                        "parse_status": "failed",
                        "parse_error": error_msg,
                        "processing_completed_at": datetime.utcnow().isoformat(),
                        "parse_duration_ms": int((time.time() - start_time) * 1000),
                    },
                )
                result["error"] = error_msg
                return result

            logger.info(
                f"Text extracted",
                cv_id=cv_id,
                method=extraction_method,
                length=len(raw_text),
            )

            # Step 3: Detect language
            detected_language = await self._detect_language(raw_text)
            logger.debug(f"Detected language: {detected_language}")

            # Step 4: Load security keywords for classification
            logger.debug(f"Loading security keywords for classification")
            security_keywords = await self._load_security_keywords()

            # Step 5: Parse with Claude (includes security clearance detection)
            logger.debug(f"Calling Claude API for CV {cv_id}")
            try:
                parsed = await asyncio.wait_for(
                    self.claude.parse_cv_structured(raw_text, detected_language, security_keywords),
                    timeout=self.parse_timeout,
                )
            except asyncio.TimeoutError:
                error_msg = f"Claude API call timed out after {self.parse_timeout}s"
                logger.error(error_msg)
                await self._update_cv_record(
                    cv_id,
                    {
                        "parse_status": "failed",
                        "parse_error": error_msg,
                        "processing_completed_at": datetime.utcnow().isoformat(),
                        "parse_duration_ms": int((time.time() - start_time) * 1000),
                    },
                )
                result["error"] = error_msg
                return result

            logger.info(f"Claude API parsing completed for CV {cv_id}")

            # Step 6: Prepare JSONB data with security clearance info
            tokens_used = parsed.get("api_response_tokens", {}).get("total_tokens", 0)
            llm_analysis = {
                "extracted_fields": parsed.get("extracted_fields", {}),
                "confidence_scores": parsed.get("confidence_scores", {}),
                "raw_text_length": len(raw_text),
                "detected_language": detected_language,
                "extraction_method": extraction_method,
                "extraction_notes": parsed.get("extraction_notes", ""),
                "api_response_tokens": parsed.get("api_response_tokens", {}),
            }

            # Step 7: Update database with parsed results
            logger.debug(f"Updating database record for CV {cv_id}")
            duration_ms = int((time.time() - start_time) * 1000)

            # Extract the candidate's ACTUAL email from Claude's analysis.
            # CRITICAL: the email_from header is usually a job-board middleman
            # (info@jobnet.co.il, AllJobs, drushim, etc) — the candidate's real
            # email lives only inside the CV file. Two-layer defense:
            #   (1) Claude extracts what it thinks is the candidate's email
            #   (2) We REJECT it via sender_blocklist if it's a known intermediary
            # If both layers fail, we leave candidate_email as the sender (with a
            # warning) — that lets the deduplicator skip this row instead of
            # gluing many people together under one mailbox.
            extracted_fields = parsed.get("extracted_fields", {}) or {}
            raw_email = (extracted_fields.get("email") or "").strip().lower() or None
            candidate_real_phone = (extracted_fields.get("phone") or "").strip() or None

            candidate_real_email: Optional[str] = None
            if raw_email:
                if is_likely_candidate_email(raw_email):
                    candidate_real_email = raw_email
                else:
                    logger.warning(
                        f"[blocklist] Refusing to use '{raw_email}' as "
                        f"candidate_email — it's an intermediary/sender mailbox. "
                        f"Probably extracted from CV footer/signature, not the "
                        f"candidate themselves. cv_id={cv_id}"
                    )

            cv_update = {
                "raw_text": raw_text,
                "llm_analysis": llm_analysis,
                "parse_status": "success",
                "parse_error": None,
                "llm_tokens_used": tokens_used,
                "processing_completed_at": datetime.utcnow().isoformat(),
                "parse_duration_ms": duration_ms,
                "detected_language": detected_language,
            }
            # Only overwrite candidate_email when we got a REAL candidate address.
            # If Claude returned something blocklisted, leave the existing value
            # (the sender) untouched - downstream dedup will treat it as "no
            # canonical identity" and skip glueing multiple candidates together.
            if candidate_real_email:
                cv_update["candidate_email"] = candidate_real_email

            await self._update_cv_record(cv_id, cv_update)

            # Step 8: Mark older CVs of the SAME candidate as not-latest, and
            # ensure this one is is_latest=True. Identification by Claude-extracted
            # email is far more reliable than sender — same person can upload
            # via 5 different job boards using their personal email.
            if candidate_real_email:
                await self._mark_as_latest_for_candidate(
                    cv_id, candidate_real_email, candidate_real_phone
                )

            logger.info(
                f"CV parsed successfully",
                cv_id=cv_id,
                duration_ms=duration_ms,
                tokens_used=tokens_used,
                language=detected_language,
                candidate_email=candidate_real_email,
            )

            result["success"] = True
            result["tokens_used"] = tokens_used
            return result

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Failed to parse CV {cv_id}: {error_msg}")

            try:
                await self._update_cv_record(
                    cv_id,
                    {
                        "parse_status": "failed",
                        "parse_error": error_msg,
                        "processing_completed_at": datetime.utcnow().isoformat(),
                        "parse_duration_ms": int((time.time() - start_time) * 1000),
                    },
                )
            except Exception as db_error:
                logger.error(f"Failed to update CV record: {db_error}")

            result["error"] = error_msg
            return result

    async def _mark_as_latest_for_candidate(
        self,
        new_cv_id: str,
        candidate_email: str,
        candidate_phone: Optional[str] = None,
    ) -> None:
        """Ensure exactly ONE cv_files row per candidate has is_latest=True.

        Called after a CV is parsed successfully. We:
        1. Find all OTHER CVs with the same candidate_email (or phone fallback).
        2. Mark all of them is_latest=False, and link them to this new CV via
           superseded_by so the audit trail is preserved.
        3. Mark THIS CV as is_latest=True.

        This handles the common case of:
        - Same person uploads CV via 3 job boards over 2 weeks.
        - Same person sends an updated CV directly to recruitment@.
        - Same person re-applies a year later with a refreshed CV.

        Identification priority: email > phone. Email is what Claude pulled
        from inside the CV, so it's the candidate's real address, not the
        middleman job-board's sender address.
        """
        try:
            # Find sibling CVs by email
            siblings = self.supabase.table("cv_files").select(
                "id, version_number"
            ).eq("candidate_email", candidate_email).neq("id", new_cv_id).execute()

            sibling_rows = siblings.data or []

            # Compute next version number
            max_version = 0
            for s in sibling_rows:
                v = s.get("version_number") or 0
                if v > max_version:
                    max_version = v
            new_version = max_version + 1

            # Mark all siblings as not-latest and superseded by us
            if sibling_rows:
                self.supabase.table("cv_files").update({
                    "is_latest": False,
                    "superseded_by": new_cv_id,
                }).eq("candidate_email", candidate_email).neq("id", new_cv_id).execute()
                logger.info(
                    f"[dedup] Marked {len(sibling_rows)} previous CV(s) as "
                    f"superseded for candidate_email={candidate_email}"
                )

            # Mark THIS CV as the latest, with the right version number
            self.supabase.table("cv_files").update({
                "is_latest": True,
                "superseded_by": None,
                "version_number": new_version,
            }).eq("id", new_cv_id).execute()

        except Exception as e:
            # Non-fatal — the CV parse itself succeeded, this is just
            # the dedup bookkeeping. Log and move on.
            logger.warning(
                f"[dedup] Could not update is_latest flags for "
                f"{candidate_email} (cv {new_cv_id}): {e}"
            )

    async def _download_cv_file(self, storage_path: str) -> bytes:
        """Download CV file from Supabase Storage."""
        try:
            return await self.storage.download_file(storage_path)
        except Exception as e:
            logger.error(f"Failed to download {storage_path}: {e}")
            raise

    async def _detect_language(self, text: str) -> str:
        """
        Detect language using langdetect.

        Returns:
            'he' for Hebrew, 'en' for English, 'mixed' if unclear
        """
        if not text or len(text.strip()) < 50:
            logger.warning("Text too short for reliable language detection")
            return "en"  # Default to English

        try:
            lang = detect_language(text)
            logger.debug(f"Detected language: {lang}")

            # Map to our standard codes
            if lang == "he":
                return "he"
            elif lang == "en":
                return "en"
            else:
                # Any other language detected
                logger.warning(f"Unexpected language detected: {lang}, defaulting to en")
                return "en"

        except LangDetectException as e:
            logger.warning(f"Language detection failed: {e}, defaulting to en")
            return "en"

    async def _load_security_keywords(self) -> dict[int, list[str]]:
        """
        Load security classification keywords from the database.

        These keywords are passed to Claude so it can identify clearance levels
        in the CV text. Users can edit them via /admin/security UI.

        Falls back to the DEFAULT_SECURITY_LEVELS list if the table is empty
        or unreachable — this guarantees the CV parser always has something
        to match against, even on a fresh install.

        Returns:
            Dict mapping level numbers (int) to lists of keyword strings.
        """
        try:
            response = self.supabase.table("security_levels").select(
                "level, keywords"
            ).execute()
            security_keywords = {}

            for level_data in response.data or []:
                level = level_data.get("level")
                keywords = level_data.get("keywords", [])
                if level is not None and keywords:
                    security_keywords[level] = keywords

            if security_keywords:
                total = sum(len(v) for v in security_keywords.values())
                logger.info(
                    f"Loaded {total} security keywords across "
                    f"{len(security_keywords)} levels from DB"
                )
                return security_keywords

            # DB empty — use defaults so Claude still gets a useful guide.
            logger.warning(
                "security_levels DB table is empty; using built-in defaults. "
                "Visit /admin/security and click 'אפס לברירות מחדל' to seed."
            )
        except Exception as e:
            logger.warning(f"Failed to load security keywords from DB: {e}; using defaults")

        # Fallback to defaults defined in the router (single source of truth)
        try:
            from pandapower.routers.admin.security_classification import (
                DEFAULT_SECURITY_LEVELS,
            )
            return {lv["level"]: lv["keywords"] for lv in DEFAULT_SECURITY_LEVELS}
        except Exception as e:
            logger.error(f"Could not load even default security keywords: {e}")
            return {}

    async def _update_cv_record(self, cv_id: str, updates: dict[str, Any]) -> None:
        """Update CV record in database with error handling."""
        try:
            # Ensure JSONB fields are properly serialized
            if "llm_analysis" in updates and isinstance(updates["llm_analysis"], dict):
                # Supabase expects JSONB as JSON string or dict, usually dict works
                pass

            self.supabase.table("cv_files").update(updates).eq("id", cv_id).execute()
            logger.debug(f"Updated CV record {cv_id}")

        except Exception as e:
            logger.error(f"Failed to update CV record {cv_id}: {e}")
            # Don't re-raise - we want to continue processing other CVs
