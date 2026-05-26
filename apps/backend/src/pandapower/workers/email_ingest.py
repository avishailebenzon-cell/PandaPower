import asyncio
import hashlib
import logging
import unicodedata
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

from pandapower.integrations.azure import AzureGraphClient
from pandapower.integrations.supabase_storage import SupabaseStorageManager

logger = logging.getLogger(__name__)

# Concurrent limits for API calls
MAX_CONCURRENT_DOWNLOADS = 3
MAX_CONCURRENT_UPLOADS = 3
MAX_ATTACHMENT_SIZE_MB = 50


class EmailIngestWorker:
    def __init__(
        self,
        supabase_client: Any,
        azure_client: AzureGraphClient,
        storage_manager: SupabaseStorageManager,
    ):
        self.supabase = supabase_client
        self.azure = azure_client
        self.storage = storage_manager

    async def ingest_recent_emails(self, batch_size: int = 20) -> dict[str, Any]:
        """Poll and ingest recent emails from target mailbox.

        Args:
            batch_size: Number of messages to process per batch (optimal for backfill)
        """
        result = {
            "total_processed": 0,
            "cv_files_extracted": 0,
            "duplicates_found": 0,
            "errors": [],
            "backfill_progress": None,
        }

        try:
            # Fetch last processed timestamp
            last_seen = None
            backfill_start = None
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
                logger.debug(f"last_seen lookup failed (treating as cold start): {e}")

            # If no last_seen (backfill mode), check for backfill_start_date
            if last_seen is None:
                try:
                    backfill_response = await self.supabase.table("system_settings").select(
                        "setting_value"
                    ).eq("setting_key", "azure.backfill_start_date").limit(1).execute()
                    if backfill_response.data and backfill_response.data[0].get("setting_value"):
                        date_str = str(backfill_response.data[0]["setting_value"]).strip('"')
                        if date_str and date_str != "null":
                            backfill_start = datetime.fromisoformat(date_str)
                            last_seen = backfill_start
                            logger.info(f"Starting backfill from date: {last_seen}")
                except Exception as e:
                    logger.debug(f"Backfill date lookup failed: {e}")

            next_link = None
            max_received = last_seen
            processed_batch = 0

            logger.info(f"Email ingest: last_seen = {last_seen}, will fetch emails since this timestamp")

            while True:
                logger.debug(f"Fetching messages with since={last_seen}, next_link={next_link is not None}")
                response = await self.azure.list_messages(since=last_seen, next_link=next_link, page_size=batch_size)
                messages = response.get("value", [])
                logger.info(f"Azure returned {len(messages)} messages in this batch")

                if not messages:
                    break

                # Process messages concurrently with semaphore to limit parallelism
                tasks = []
                for msg_data in messages:
                    tasks.append(self._process_message(msg_data))

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

                    if processed["received_at"] and (max_received is None or processed["received_at"] > max_received):
                        max_received = processed["received_at"]

                # Update progress for backfill
                if backfill_start:
                    days_processed = (max_received - backfill_start).days if max_received else 0
                    result["backfill_progress"] = f"Processing {max_received.date() if max_received else 'recent'}"
                    logger.info(f"Backfill progress: {days_processed} days processed, {result['total_processed']} emails, {result['cv_files_extracted']} CVs")

                next_link = response.get("@odata.nextLink")
                if not next_link:
                    logger.info(f"Completed batch of {processed_batch} messages, no more pages")
                    break

                # Limit batch size to avoid memory issues
                if processed_batch >= batch_size * 5:  # Stop after ~100 messages per run
                    logger.info(f"Reached batch limit ({processed_batch} messages), will continue in next run")
                    break

            # Update last seen timestamp
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

            logger.info(f"Email ingest completed: {result}")
            return result

        except Exception as e:
            logger.error(f"Email ingest failed: {e}", exc_info=True)
            result["errors"].append(str(e))
            return result

    async def _process_message(self, msg_data: dict[str, Any]) -> dict[str, Any]:
        """Process a single email message and extract CV attachments."""
        result = {
            "cv_count": 0,
            "duplicates": 0,
            "received_at": None,
            "error": None,
        }

        try:
            message_id = msg_data.get("id")
            subject = msg_data.get("subject", "")
            email_from = msg_data.get("from", {}).get("emailAddress", {}).get("address", "")
            received_datetime = msg_data.get("receivedDateTime")

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

            # Process attachments
            attachments = msg_data.get("attachments", [])
            logger.debug(f"Message {message_id} has {len(attachments)} attachments")

            cv_attachments = [
                a for a in attachments
                if self._is_cv_file(a.get("name", ""), a.get("contentType", ""))
            ]

            logger.debug(f"Message {subject}: {len(attachments)} attachments, {len(cv_attachments)} CV files")
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

            # Process attachments concurrently with limited concurrency
            attachment_tasks = []
            for attachment in cv_attachments:
                attachment_tasks.append(
                    self._process_attachment_with_retry(
                        message_id, email_from, received_datetime, attachment
                    )
                )

            processed_attachments = await asyncio.gather(*attachment_tasks, return_exceptions=True)

            for processed in processed_attachments:
                if isinstance(processed, Exception):
                    logger.error(f"Error processing attachment: {processed}")
                    continue
                result["cv_count"] += processed["created"]
                result["duplicates"] += processed["duplicates"]

            # Update email_intake_log
            await self.supabase.table("email_intake_log").update(
                {
                    "status": "success" if result["cv_count"] > 0 else "partial",
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
    ) -> dict[str, int]:
        """Process attachment with automatic retry on failure."""
        for attempt in range(max_retries):
            try:
                return await self._process_attachment(message_id, email_from, received_datetime, attachment)
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

            # Download file
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
                await self.storage.upload_file(storage_path, file_content, content_type)
                logger.debug(f"Upload completed")
            except Exception as e:
                # If file already exists in storage (409 Duplicate), that's OK - we'll still create the DB record
                if "409" in str(e) or "duplicate" in str(e).lower():
                    logger.debug(f"File already exists in storage: {storage_path}")
                else:
                    # For other upload errors, re-raise
                    raise

            # Provisional candidate_email = sender (alljobs, jobnet, recruiter, etc).
            # This is OFTEN the middleman, not the real candidate. cv_parse_worker
            # will OVERWRITE this field after Claude extracts the candidate's
            # real email from inside the CV.
            candidate_email = email_from.lower() if email_from else None

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

    # Supported CV file extensions
    CV_EXTENSIONS = (
        ".pdf",
        ".doc",
        ".docx",
        ".rtf",
        ".odt",
        ".txt",
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

    # Extensions that should NEVER be treated as a CV even if MIME looks OK
    # (prevents false positives on signature images, calendar invites, etc.)
    NON_CV_EXTENSIONS = (
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".tif", ".tiff",
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
