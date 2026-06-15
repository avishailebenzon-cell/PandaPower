import asyncio
import hashlib
import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import quote

from pandapower.integrations.azure import AzureGraphClient
from pandapower.integrations.supabase_storage import SupabaseStorageManager
from pandapower.workers.sender_blocklist import is_likely_candidate_email
from pandapower.workers.placement_jobs import (
    create_placement_job_from_email,
    is_placement_sender,
)

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Israeli mobile/landline shapes: 05x-xxxxxxx, 0x-xxxxxxx, +9725xxxxxxxx, etc.
_PHONE_RE = re.compile(r"(?:\+972[\-\s]?|0)(?:5\d|[2-49])[\-\s]?\d{3}[\-\s]?\d{4}")


def _normalize_phone(raw: str) -> Optional[str]:
    """Return digits-only national form (drops +972 → leading 0), or None."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("972"):
        digits = "0" + digits[3:]
    return digits if len(digits) >= 9 else None


def extract_candidate_identity(subject: str, body: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Cheaply pull the candidate's (email, phone, name) from a job-board email,
    WITHOUT calling Claude. Used to skip duplicate people before parsing.

    - email: first address in the body that passes is_likely_candidate_email
      (so shared mailboxes like info@jobnet.co.il are ignored).
    - phone: first Israeli-looking number, normalized to national digits.
    - name : subject tail after "–"/" - " (Jobnet/Drushim), else body "שם: <name>".
    Returns (None, None, None) for any part that can't be determined.
    """
    text = body or ""
    # email
    cand_email = None
    for m in _EMAIL_RE.findall(text):
        e = m.strip().lower()
        if is_likely_candidate_email(e):
            cand_email = e
            break
    # phone
    cand_phone = None
    pm = _PHONE_RE.search(text)
    if pm:
        cand_phone = _normalize_phone(pm.group(0))
    # name
    cand_name = None
    subj = subject or ""
    for sep in ("–", " - ", " — "):
        if sep in subj:
            tail = subj.split(sep)[-1].strip()
            if tail and len(tail) <= 60:
                cand_name = tail
            break
    if not cand_name:
        nm = re.search(r"שם\s*[:：]\s*([^\n\r]{2,60})", text)
        if nm:
            cand_name = nm.group(1).strip()
    return cand_email, cand_phone, cand_name

# Concurrent limits for API calls.
# Memory-bounded: each concurrent download/upload holds an attachment's bytes
# (up to MAX_ATTACHMENT_SIZE_MB) in RAM. On a 512MB instance, 30×N MB caused
# OOM restarts — keep concurrency modest. Throughput stays high because the
# scheduler runs ingest every 60s.
MAX_CONCURRENT_DOWNLOADS_INCREMENTAL = 5
MAX_CONCURRENT_DOWNLOADS_BACKFILL = 8
MAX_CONCURRENT_UPLOADS_INCREMENTAL = 5
MAX_CONCURRENT_UPLOADS_BACKFILL = 8
MAX_ATTACHMENT_SIZE_MB = 50

# Batch processing limits. Smaller backfill batch = lower peak memory (the run
# holds message metadata + in-flight attachments). 400/run × 60s ≈ 24k/hr —
# plenty for the ~15-20k 24-month backlog, without OOM.
MAX_EMAILS_PER_RUN_INCREMENTAL = 100
MAX_EMAILS_PER_RUN_BACKFILL = 400


class EmailIngestWorker:
    def __init__(
        self,
        supabase_client: Any,
        azure_client: AzureGraphClient,
        storage_manager: SupabaseStorageManager,
        is_backfill: bool = False,
    ):
        self.supabase = supabase_client
        self.azure = azure_client
        self.storage = storage_manager
        self.is_backfill = is_backfill
        # Throttle the cosmetic "currently scanning: <file>" UI write so it
        # fires at most once every few seconds instead of once per message.
        # That write was hitting system_settings ~130K times and was a top-10
        # DB-CPU consumer for a label nobody needs sub-second.
        self._last_current_file_write = 0.0

        # Set concurrency limits based on backfill mode
        if is_backfill:
            self.max_concurrent_downloads = MAX_CONCURRENT_DOWNLOADS_BACKFILL
            self.max_concurrent_uploads = MAX_CONCURRENT_UPLOADS_BACKFILL
            self.max_emails_per_run = MAX_EMAILS_PER_RUN_BACKFILL
        else:
            self.max_concurrent_downloads = MAX_CONCURRENT_DOWNLOADS_INCREMENTAL
            self.max_concurrent_uploads = MAX_CONCURRENT_UPLOADS_INCREMENTAL
            self.max_emails_per_run = MAX_EMAILS_PER_RUN_INCREMENTAL

    async def ingest_incremental_emails(self, batch_size: int = 20) -> dict[str, Any]:
        """Scan recent emails forward in time (daily incoming emails).

        Process new emails that arrive today, keeping track of the latest timestamp
        so we don't reprocess the same emails.
        """
        self.download_semaphore = asyncio.Semaphore(self.max_concurrent_downloads)
        self.upload_semaphore = asyncio.Semaphore(self.max_concurrent_uploads)

        result = {
            "total_processed": 0,
            "cv_files_extracted": 0,
            "duplicates_found": 0,
            "errors": [],
            "type": "incremental",
        }

        try:
            # Fetch last_seen for incremental scan
            last_seen = None
            try:
                settings_response = await self.supabase.table("system_settings").select(
                    "setting_value"
                ).eq("setting_key", "azure.last_seen_message_received_at").limit(1).execute()
                if settings_response.data and settings_response.data[0].get("setting_value"):
                    iso_str = str(settings_response.data[0]["setting_value"])
                    if iso_str.strip('"') and iso_str.strip('"') != "null":
                        iso_cleaned = iso_str.strip('"').replace('Z', '+00:00')
                        last_seen = datetime.fromisoformat(iso_cleaned)
            except Exception as e:
                logger.debug(f"last_seen lookup failed: {e}")

            if last_seen is None:
                from datetime import timezone as _tz
                last_seen = datetime.now(_tz.utc) - timedelta(hours=1)
                logger.info(f"Starting incremental scan from 1 hour ago: {last_seen}")

            # Ensure tz-aware
            if last_seen.tzinfo is None:
                from datetime import timezone as _tz
                last_seen = last_seen.replace(tzinfo=_tz.utc)

            next_link = None
            max_received = last_seen
            processed_batch = 0

            logger.info(f"Email ingest (incremental): fetching new emails since {last_seen}")

            while True:
                # Forward scan: fetch emails newer than last_seen
                logger.debug(f"Fetching new emails since={last_seen}, next_link={next_link is not None}")
                response = await self.azure.list_messages(since=last_seen, next_link=next_link, page_size=batch_size)
                messages = response.get("value", [])
                logger.info(f"Azure returned {len(messages)} new messages in this batch")

                if not messages:
                    logger.info("No new messages")
                    break

                # Process messages (no dedup - we want to capture all recent emails)
                tasks = []
                for msg_data in messages:
                    tasks.append(self._process_message(msg_data, dedup_identity=False))

                processed_messages = await asyncio.gather(*tasks, return_exceptions=True)

                for processed in processed_messages:
                    if isinstance(processed, Exception):
                        logger.error(f"Error processing message: {processed}")
                        result["errors"].append(str(processed))
                        continue

                    result["total_processed"] += 1
                    result["cv_files_extracted"] += processed["cv_count"]
                    result["duplicates_found"] += processed["duplicates"]
                    processed_batch += 1

                    recv = processed.get("received_at")
                    if recv is not None and getattr(recv, "tzinfo", None) is None:
                        from datetime import timezone as _tz
                        recv = recv.replace(tzinfo=_tz.utc)
                    if recv and (max_received is None or recv > max_received):
                        max_received = recv

                result["progress"] = f"Processed up to {max_received.date() if max_received else 'recent'}"
                logger.info(f"Incremental scan progress: {result['total_processed']} emails, {result['cv_files_extracted']} CVs")

                next_link = response.get("@odata.nextLink")
                if not next_link:
                    logger.info("Completed batch, no more pages")
                    break

                if processed_batch >= self.max_emails_per_run:
                    logger.info(f"Reached max emails per run ({processed_batch}/{self.max_emails_per_run})")
                    break

            # Update last_seen timestamp
            if max_received:
                await self.supabase.table("system_settings").upsert(
                    {
                        "setting_key": "azure.last_seen_message_received_at",
                        "setting_value": f'"{max_received.isoformat()}"',
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                    on_conflict="setting_key",
                ).execute()
                logger.info(f"Updated last_seen to: {max_received.isoformat()}")

            logger.info(f"Incremental ingest completed: {result}")
            return result

        except Exception as e:
            logger.error(f"Incremental email ingest failed: {e}", exc_info=True)
            result["errors"].append(str(e))
            return result

    async def ingest_recent_emails(self, batch_size: int = 20) -> dict[str, Any]:
        """Scan emails backward in time, starting from today until backfill_start_date.

        The backward scan strategy:
        1. Start from today (or last_processed if resuming)
        2. Fetch emails older than that date
        3. Skip candidates that already exist in the system
        4. Ingest new candidates
        5. Continue until backfill_start_date is reached
        6. Track last_processed as the oldest date we've seen
        """
        self.download_semaphore = asyncio.Semaphore(self.max_concurrent_downloads)
        self.upload_semaphore = asyncio.Semaphore(self.max_concurrent_uploads)

        result = {
            "total_processed": 0,
            "cv_files_extracted": 0,
            "duplicates_found": 0,
            "errors": [],
            "backfill_progress": None,
        }

        try:
            # Fetch the starting point for backward scan (today or resume point)
            last_processed = None
            backfill_start = None
            try:
                settings_response = await self.supabase.table("system_settings").select(
                    "setting_value"
                ).eq("setting_key", "azure.last_processed_message_received_at").limit(1).execute()
                if settings_response.data and settings_response.data[0].get("setting_value"):
                    iso_str = str(settings_response.data[0]["setting_value"])
                    if iso_str.strip('"') and iso_str.strip('"') != "null":
                        iso_cleaned = iso_str.strip('"').replace('Z', '+00:00')
                        last_processed = datetime.fromisoformat(iso_cleaned)
            except Exception as e:
                logger.debug(f"last_processed lookup failed: {e}")

            # Get backfill_start_date (when to stop going backward)
            try:
                backfill_response = await self.supabase.table("system_settings").select(
                    "setting_value"
                ).eq("setting_key", "azure.backfill_start_date").limit(1).execute()
                if backfill_response.data and backfill_response.data[0].get("setting_value"):
                    date_str = str(backfill_response.data[0]["setting_value"]).strip('"')
                    if date_str and date_str != "null":
                        backfill_start = datetime.fromisoformat(date_str)
                        from datetime import timezone as _tz
                        if backfill_start.tzinfo is None:
                            backfill_start = backfill_start.replace(tzinfo=_tz.utc)
                        logger.info(f"Backward scan: will stop at {backfill_start}")
            except Exception as e:
                logger.debug(f"Backfill date lookup failed: {e}")

            # If no last_processed, start from today
            if last_processed is None:
                from datetime import timezone as _tz
                last_processed = datetime.now(_tz.utc)
                logger.info(f"Starting backward scan from today: {last_processed}")

            # Ensure tz-aware
            if last_processed and last_processed.tzinfo is None:
                from datetime import timezone as _tz
                last_processed = last_processed.replace(tzinfo=_tz.utc)

            next_link = None
            min_received = last_processed  # Track oldest date we've seen
            processed_batch = 0

            logger.info(f"Email ingest (backward): scanning until {last_processed}, stop at {backfill_start}")

            while True:
                # Backward scan: fetch emails older than last_processed
                # Ensure last_processed is a datetime object before passing to list_messages
                if not isinstance(last_processed, datetime):
                    logger.error(f"last_processed is not a datetime: {type(last_processed)} = {last_processed}")
                    result["errors"].append(f"Invalid type for last_processed: {type(last_processed)}")
                    break

                logger.info(f"[BACKFILL] Fetching emails until={last_processed}, next_link={next_link is not None}")
                try:
                    response = await self.azure.list_messages(until=last_processed, next_link=next_link, page_size=batch_size)
                    messages = response.get("value", [])
                    logger.info(f"[BACKFILL] Azure returned {len(messages)} messages in this batch")
                except Exception as e:
                    logger.error(f"[BACKFILL] Azure query failed: {e}", exc_info=True)
                    result["errors"].append(f"Azure query error: {str(e)}")
                    break

                if not messages:
                    logger.info(f"[BACKFILL] No more messages returned from Azure, backfill complete!")
                    break

                # Process with dedup_identity=True to skip existing candidates
                tasks = []
                for msg_data in messages:
                    tasks.append(self._process_message(msg_data, dedup_identity=True))

                processed_messages = await asyncio.gather(*tasks, return_exceptions=True)

                for processed in processed_messages:
                    if isinstance(processed, Exception):
                        logger.error(f"Error processing message: {processed}")
                        result["errors"].append(str(processed))
                        continue

                    result["total_processed"] += 1
                    result["cv_files_extracted"] += processed["cv_count"]
                    result["duplicates_found"] += processed["duplicates"]
                    processed_batch += 1

                    # Track the oldest date we've seen
                    recv = processed.get("received_at")
                    if recv is not None and getattr(recv, "tzinfo", None) is None:
                        from datetime import timezone as _tz
                        recv = recv.replace(tzinfo=_tz.utc)
                    if recv and (min_received is None or recv < min_received):
                        min_received = recv

                # Check if we've reached the backfill start date
                if min_received and backfill_start and min_received <= backfill_start:
                    logger.info(f"Reached backfill start date ({backfill_start}), stopping backward scan")
                    break

                # Update progress
                if min_received:
                    result["backfill_progress"] = f"Scanned back to {min_received.date()}"
                    logger.info(f"Backward scan progress: {result['total_processed']} emails, {result['cv_files_extracted']} CVs, oldest: {min_received.date()}")

                next_link = response.get("@odata.nextLink")
                if not next_link:
                    logger.info("Completed batch, no more pagination links")
                    break

                # Limit per run
                if processed_batch >= self.max_emails_per_run:
                    logger.info(f"Reached max emails per run ({processed_batch}/{self.max_emails_per_run}), will resume in next run")
                    break

            # Update last_processed to the oldest date we've seen
            if min_received:
                await self.supabase.table("system_settings").upsert(
                    {
                        "setting_key": "azure.last_processed_message_received_at",
                        "setting_value": f'"{min_received.isoformat()}"',
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                    on_conflict="setting_key",
                ).execute()
                logger.info(f"Updated last_processed to: {min_received.isoformat()}")

            logger.info(f"Email ingest completed: {result}")
            return result

        except Exception as e:
            logger.error(f"Email ingest failed: {e}", exc_info=True)
            result["errors"].append(str(e))
            return result

    async def _process_message(
        self,
        msg_data: dict[str, Any],
        dedup_identity: bool = False,
        email_body: Optional[str] = None,
    ) -> dict[str, Any]:
        """Process a single email message and extract CV attachments.

        When dedup_identity=True (used by the newest-first recovery drain), the
        candidate's email is extracted from the body and, if a CV for that same
        person from a NEWER-OR-EQUAL email already exists, this email is skipped
        (status 'skipped_duplicate_person') WITHOUT downloading/parsing — so we
        keep each person's newest CV and don't waste parsing on older repeats.
        """
        result = {
            "cv_count": 0,
            "duplicates": 0,
            "received_at": None,
            "error": None,
            "skipped_duplicate": False,
        }

        try:
            message_id = msg_data.get("id")
            subject = msg_data.get("subject", "")
            email_from = msg_data.get("from", {}).get("emailAddress", {}).get("address", "")
            received_datetime = msg_data.get("receivedDateTime")
            body_text = email_body or (msg_data.get("body") or {}).get("content") or msg_data.get("bodyPreview") or ""

            # Pre-parse person dedup (cheap, no Claude): find the candidate's real
            # email from the body and resolve it once for reuse below.
            candidate_real_email = None
            if dedup_identity:
                candidate_real_email, _phone, _name = extract_candidate_identity(subject, body_text)

            if received_datetime:
                result["received_at"] = datetime.fromisoformat(received_datetime.replace("Z", "+00:00"))

            # Upsert email_intake_log entry
            email_exists = False
            try:
                await self.supabase.table("email_intake_log").insert(
                    {
                        "outlook_message_id": message_id,
                        "email_subject": subject,
                        "email_from": email_from,
                        "email_received_at": received_datetime,
                        "status": "processing",
                        "processing_started_at": datetime.utcnow().isoformat(),
                    }
                ).execute()
            except Exception as e:
                # Email already exists - update status to processing and continue
                if "duplicate key" in str(e).lower():
                    logger.debug(f"Email already exists, updating to processing status: {message_id}")
                    email_exists = True
                    await self.supabase.table("email_intake_log").update(
                        {
                            "status": "processing",
                            "processing_started_at": datetime.utcnow().isoformat(),
                        }
                    ).eq("outlook_message_id", message_id).execute()
                else:
                    # If different error, re-raise
                    raise

            # Placement-job emails (recruitment agencies, e.g. @adamtotal.co.il):
            # these describe a vacancy at a CLIENT, not a candidate CV. Parse the
            # body into an internal job and skip the CV pipeline entirely.
            if is_placement_sender(email_from):
                placement = await create_placement_job_from_email(
                    self.supabase,
                    message_id=message_id,
                    email_from=email_from,
                    subject=subject,
                    body=body_text,
                    received_at=received_datetime,
                )
                await self.supabase.table("email_intake_log").update(
                    {
                        "status": "placement_job"
                        if placement["created"]
                        else f"placement_{placement['reason']}",
                        "cv_files_extracted": 0,
                        "processing_completed_at": datetime.utcnow().isoformat(),
                    }
                ).eq("outlook_message_id", message_id).execute()
                return result

            # Process attachments
            attachments = msg_data.get("attachments", [])
            logger.debug(f"Message {message_id} has {len(attachments)} attachments")

            cv_attachments = [
                a for a in attachments
                if self._is_cv_file(a.get("name", ""), a.get("contentType", ""))
            ]

            logger.debug(f"Message {subject}: {len(attachments)} attachments, {len(cv_attachments)} CV files")

            # Update current scanning status for UI — throttled to ≤1 write per
            # 5s, and skipped entirely during backfill (the label is meaningless
            # while bulk-draining history). Saves ~130K system_settings writes.
            if cv_attachments and not self.is_backfill:
                now = time.monotonic()
                if now - self._last_current_file_write >= 5.0:
                    self._last_current_file_write = now
                    current_file = cv_attachments[0].get("name", "Unknown")
                    await self.supabase.table("system_settings").upsert(
                        {
                            "setting_key": "email.current_file_scanning",
                            "setting_value": f'"{current_file}"',
                            "updated_at": datetime.utcnow().isoformat(),
                        },
                        on_conflict="setting_key",
                    ).execute()
            if len(attachments) > 0:
                for a in attachments:
                    name = a.get('name', 'unknown')
                    mime = a.get('contentType', 'unknown')
                    is_cv = self._is_cv_file(name, mime)
                    logger.debug(f"  - {name} ({mime}) - is_cv={is_cv}")

            if len(attachments) > 0 and len(cv_attachments) == 0:
                logger.info(f"No CV files found in {len(attachments)} attachments for {subject}:")
                for a in attachments[:3]:
                    logger.info(f"  - {a.get('name', 'unknown')} (type: {a.get('contentType', 'unknown')})")

            if not cv_attachments:
                await self.supabase.table("email_intake_log").update(
                    {
                        "status": "skipped_no_cv",
                        "cv_files_extracted": 0,
                        "processing_completed_at": datetime.utcnow().isoformat(),
                        "processing_duration_ms": 0,
                    }
                ).eq("outlook_message_id", message_id).execute()
                return result

            # Person-level dedup (newest-first recovery): if we already captured a
            # CV for this candidate from a NEWER-OR-EQUAL email, skip this older
            # one entirely — don't download or parse. Order-independent: we compare
            # source_email_received_at, so "keep newest" holds regardless of the
            # processing order.
            if dedup_identity and candidate_real_email and received_datetime:
                try:
                    seen = await (
                        self.supabase.table("cv_files")
                        .select("id")
                        .eq("candidate_email", candidate_real_email)
                        .gte("source_email_received_at", received_datetime)
                        .limit(1)
                        .execute()
                    )
                    if seen.data:
                        logger.info(f"Skipping older duplicate of {candidate_real_email} ({subject[:40]})")
                        result["skipped_duplicate"] = True
                        await self.supabase.table("email_intake_log").update(
                            {
                                "status": "skipped_duplicate_person",
                                "cv_files_extracted": 0,
                                "processing_completed_at": datetime.utcnow().isoformat(),
                            }
                        ).eq("outlook_message_id", message_id).execute()
                        return result
                except Exception as e:
                    logger.debug(f"identity dedup check failed (proceeding): {e}")

            # Process attachments concurrently with limited concurrency
            attachment_tasks = []
            for attachment in cv_attachments:
                attachment_tasks.append(
                    self._process_attachment_with_retry(
                        message_id, email_from, received_datetime, attachment,
                        candidate_email_override=candidate_real_email,
                    )
                )

            processed_attachments = await asyncio.gather(*attachment_tasks, return_exceptions=True)

            attachment_errors = 0
            for processed in processed_attachments:
                if isinstance(processed, Exception):
                    logger.error(f"Error processing attachment: {processed}")
                    attachment_errors += 1
                    continue
                result["cv_count"] += processed["created"]
                result["duplicates"] += processed["duplicates"]

            # Status semantics (made trustworthy + retryable):
            #   success – a CV file was stored, or it was a known duplicate
            #             (already captured earlier) → nothing more to do.
            #   failed  – we had CV attachments but stored none AND hit errors →
            #             RETRYABLE: the reingest drain re-attempts 'failed' rows.
            #             (Previously this was silently marked 'partial' and the
            #             CV was lost forever — the root cause of ~31K dropped CVs.)
            if result["cv_count"] > 0 or result["duplicates"] > 0:
                new_status = "success"
            elif attachment_errors > 0:
                new_status = "failed"
            else:
                new_status = "partial"

            await self.supabase.table("email_intake_log").update(
                {
                    "status": new_status,
                    "cv_files_extracted": result["cv_count"],
                    "processing_completed_at": datetime.utcnow().isoformat(),
                }
            ).eq("outlook_message_id", message_id).execute()

        except Exception as e:
            logger.error(f"Failed to process message {msg_data.get('id')}: {e}", exc_info=True)
            result["error"] = str(e)
            try:
                await self.supabase.table("email_intake_log").update(
                    {
                        "status": "failed",
                        "error_message": str(e)[:500],
                        "processing_completed_at": datetime.utcnow().isoformat(),
                    }
                ).eq("outlook_message_id", msg_data.get("id")).execute()
            except Exception as log_err:
                logger.error(f"Could not log failure to email_intake_log: {log_err}")

        return result

    async def _process_attachment_with_retry(
        self,
        message_id: str,
        email_from: str,
        received_datetime: str,
        attachment: dict[str, Any],
        max_retries: int = 3,
        candidate_email_override: Optional[str] = None,
    ) -> dict[str, int]:
        """Process attachment with automatic retry on failure."""
        for attempt in range(max_retries):
            try:
                return await self._process_attachment(
                    message_id, email_from, received_datetime, attachment,
                    candidate_email_override=candidate_email_override,
                )
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Attachment processing failed (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Attachment processing failed after {max_retries} attempts: {e}")
                    return {"created": 0, "duplicates": 0}

    async def _process_attachment(
        self,
        message_id: str,
        email_from: str,
        received_datetime: str,
        attachment: dict[str, Any],
        candidate_email_override: Optional[str] = None,
    ) -> dict[str, int]:
        """Download and store a single attachment."""
        result = {"created": 0, "duplicates": 0}

        try:
            attachment_id = attachment.get("id")
            filename = attachment.get("name", "unknown")
            content_type = attachment.get("contentType", "")
            size_bytes = attachment.get("size", 0)

            # Skip oversized files
            if size_bytes > MAX_ATTACHMENT_SIZE_MB * 1024 * 1024:
                logger.warning(f"Skipping oversized attachment: {filename} ({size_bytes / 1024 / 1024:.1f} MB)")
                return result

            logger.debug(f"Processing attachment: {filename} ({content_type}, {size_bytes} bytes)")

            # Download file with concurrency control
            async with self.download_semaphore:
                file_content = await self.azure.download_attachment(message_id, attachment_id)
                logger.debug(f"Downloaded {len(file_content)} bytes")

            # Calculate SHA-256
            file_hash = hashlib.sha256(file_content).hexdigest()
            logger.debug(f"File hash: {file_hash}")

            # Check for duplicates
            existing = await self.supabase.table("cv_files").select("id").eq("file_hash", file_hash).execute()
            logger.debug(f"Duplicate check: {len(existing.data or [])} existing records")

            if existing.data:
                logger.info(f"Duplicate CV file detected: {filename} (hash: {file_hash})")
                result["duplicates"] += 1
                return result

            # Sanitize filename for storage
            # Supabase Storage doesn't allow non-ASCII characters even if URL-encoded
            # So we use a hash-based filename for files with non-ASCII characters
            logger.debug(f"Original filename: {filename}")

            # Check if filename has non-ASCII characters
            try:
                filename.encode('ascii')
                # If we get here, filename is ASCII-safe, use it (with .pdf extension preserved)
                safe_filename = filename
                logger.debug(f"ASCII-safe filename: {safe_filename}")
            except UnicodeEncodeError:
                # Filename has non-ASCII characters, use hash-based name
                safe_filename = f"cv_{file_hash[:8]}.pdf"
                logger.debug(f"Non-ASCII filename detected, using hash-based: {safe_filename}")

            # Upload to storage with sanitized filename
            # Include file hash in path to ensure uniqueness (same file from different messages/times won't conflict)
            storage_path = f"cvs/outlook/{datetime.now().year}/{datetime.now().month:02d}/{file_hash}/{safe_filename}"
            logger.debug(f"Uploading to storage: {storage_path}")
            try:
                async with self.upload_semaphore:
                    await self.storage.upload_file(storage_path, file_content, content_type)
                    logger.debug(f"Upload completed")
            except Exception as e:
                # A "409/duplicate" means the object key already exists. Previously
                # we blindly created the DB record on 409 — but if that prior
                # object was never really written, we ended up with cv_files rows
                # pointing at missing files ("Object not found" at parse time).
                # Verify the object actually exists; if not, re-raise so the
                # retry wrapper re-uploads it.
                if "409" in str(e) or "duplicate" in str(e).lower():
                    exists = False
                    try:
                        await self.storage.download_file(storage_path)
                        exists = True
                    except Exception:
                        exists = False
                    if not exists:
                        logger.warning(f"Storage 409 but object missing, re-raising to retry: {storage_path}")
                        raise
                    logger.debug(f"File already exists in storage: {storage_path}")
                else:
                    # For other upload errors, re-raise
                    raise

            # candidate_email: prefer the REAL candidate email parsed from the
            # email body (override) when available — this lets person-level dedup
            # work pre-parse and gives downstream the right identity immediately.
            # Otherwise fall back to the sender (often the job-board middleman);
            # cv_parse_worker overwrites it later from inside the CV.
            candidate_email = (candidate_email_override or (email_from.lower() if email_from else None))

            # Check if this candidate has existing CV files
            latest_cv = None
            if candidate_email:
                try:
                    existing_cvs = await self.supabase.table("cv_files").select(
                        "id, version_number"
                    ).eq("candidate_email", candidate_email).eq("is_latest", True).execute()

                    if existing_cvs.data:
                        latest_cv = existing_cvs.data[0]
                        # Mark old CV as superseded
                        await self.supabase.table("cv_files").update(
                            {"is_latest": False}
                        ).eq("id", latest_cv["id"]).execute()
                        logger.info(f"Marked previous CV as old for {candidate_email}")
                except Exception as e:
                    logger.warning(f"Failed to check for existing CVs: {e}")

            # Create cv_files record with versioning
            new_version_number = (latest_cv.get("version_number", 0) + 1) if latest_cv else 1

            logger.debug(f"Inserting cv_files record with version {new_version_number}")
            new_cv = await self.supabase.table("cv_files").insert(
                {
                    "file_hash": file_hash,
                    "original_filename": filename,
                    "storage_path": storage_path,
                    "mime_type": content_type,
                    "file_size_bytes": len(file_content),
                    "source": "outlook",
                    "source_email_id": message_id,
                    "source_email_from": email_from,
                    "source_email_received_at": received_datetime,
                    "candidate_email": candidate_email,
                    "version_number": new_version_number,
                    "is_latest": True,
                    "superseded_by": None,
                    "parse_status": "pending",
                }
            ).execute()
            logger.debug(f"Insert result: {len(new_cv.data) if new_cv.data else 0} records")

            # Link old CV to new one if exists
            if latest_cv and new_cv.data:
                try:
                    new_cv_id = new_cv.data[0]["id"]
                    await self.supabase.table("cv_files").update(
                        {"superseded_by": new_cv_id}
                    ).eq("id", latest_cv["id"]).execute()
                    logger.info(f"Linked old CV to new version for {candidate_email}")
                except Exception as e:
                    logger.warning(f"Failed to link old CV to new: {e}")

            result["created"] += 1
            logger.info(f"Created cv_files record for: {filename} (version {new_version_number})")

        except Exception as e:
            logger.error(f"Failed to process attachment: {e}", exc_info=True)
            result["error"] = str(e)
            raise  # Let _process_attachment_with_retry handle retries

        return result

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Sanitize filename to be storage-safe (ASCII only)."""
        # URL encode the filename to handle special characters (including Hebrew)
        # This converts "קורות חיים.pdf" to "%D7%A7%D7%95%D7%A8%D7%95%D7%AA%20%D7%97%D7%99%D7%99%D7%9D.pdf"
        return quote(filename, safe='.')

    # Supported CV file extensions. Images are now accepted because CV text
    # extraction runs through ConvertAPI OCR (see integrations/convertapi_client.py),
    # so photographed / scanned-image résumés are recoverable.
    CV_EXTENSIONS = (
        ".pdf",
        ".doc",
        ".docx",
        ".rtf",
        ".odt",
        ".txt",
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
    )

    # MIME types that indicate a CV-compatible document.
    # Includes common variants seen from Outlook, Gmail, mobile clients, and zip-wrapped DOCX.
    CV_MIME_TYPES = (
        # PDF
        "application/pdf",
        "application/x-pdf",
        "application/acrobat",
        "applications/vnd.pdf",
        # Word DOC (binary, Office 97-2003)
        "application/msword",
        "application/doc",
        "application/ms-doc",
        "application/x-msword",
        # Word DOCX (OOXML)
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-word.document.macroenabled.12",
        # RTF
        "application/rtf",
        "text/rtf",
        "application/x-rtf",
        "text/richtext",
        # OpenDocument
        "application/vnd.oasis.opendocument.text",
        # Plain text
        "text/plain",
        # Generic binary - many email clients (including Outlook mobile) send
        # attachments as octet-stream; fall back to extension check below.
        "application/octet-stream",
        # DOCX is technically a ZIP archive; some scanners report it that way.
        "application/zip",
        "application/x-zip-compressed",
    )

    # Extensions that should NEVER be treated as a CV even if MIME looks OK.
    # NOTE: common résumé image formats (jpg/png/tiff/webp) were removed here and
    # added to CV_EXTENSIONS — ConvertAPI OCR can read them. We still reject
    # tiny/non-document images like gif/bmp/svg and all clearly-non-CV types.
    NON_CV_EXTENSIONS = (
        ".gif", ".bmp", ".svg",
        ".ics", ".vcf", ".eml", ".msg",
        ".xls", ".xlsx", ".csv",
        ".ppt", ".pptx",
        ".zip", ".rar", ".7z", ".tar", ".gz",
        ".mp3", ".mp4", ".mov", ".wav", ".avi",
        ".exe", ".dll", ".bat",
    )

    @classmethod
    def _is_cv_file(cls, filename: str, content_type: str) -> bool:
        """Check if file is a valid CV format.

        Accepts a file if EITHER the extension OR the MIME type indicates it
        is a supported document format. Explicitly rejects known non-CV
        extensions (images, spreadsheets, calendars, etc.) even when the
        MIME type is generic (application/octet-stream).
        """
        filename_lower = (filename or "").lower().strip()
        content_type_lower = (content_type or "").lower().strip()

        # Hard reject known non-CV extensions regardless of MIME
        if any(filename_lower.endswith(ext) for ext in cls.NON_CV_EXTENSIONS):
            return False

        has_valid_ext = any(filename_lower.endswith(ext) for ext in cls.CV_EXTENSIONS)
        has_valid_type = content_type_lower in cls.CV_MIME_TYPES

        # For ambiguous MIME types (octet-stream, zip), require valid extension
        ambiguous_mimes = ("application/octet-stream", "application/zip", "application/x-zip-compressed")
        if content_type_lower in ambiguous_mimes:
            return has_valid_ext

        return has_valid_ext or has_valid_type
