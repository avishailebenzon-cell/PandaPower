"""Feed a CV a candidate sent over WhatsApp into the normal scan pipeline.

We download the file from Green API's downloadUrl, store it in the same 'cvs'
bucket the email intake uses, and insert a cv_files row with parse_status
'pending'. The existing parse → candidate-creation pipeline picks it up exactly
like an emailed CV (source='whatsapp')."""

import hashlib
import logging
from datetime import datetime
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


async def ingest_whatsapp_cv(
    supabase,
    download_url: str,
    filename: str,
    mime_type: str,
    phone: str,
    green_api_message_id: Optional[str] = None,
    pandius_client_id: Optional[str] = None,
) -> Optional[str]:
    """Download + store a WhatsApp CV and queue it for parsing.

    Returns the created cv_files id, or None on failure (best-effort; never
    raises so the conversation keeps flowing)."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as resp:
                if resp.status != 200:
                    logger.warning(f"Pandius CV download failed: HTTP {resp.status}")
                    return None
                content = await resp.read()

        if not content:
            return None

        file_hash = hashlib.sha256(content).hexdigest()
        safe_filename = (filename or "cv.pdf").replace("/", "_").strip() or "cv.pdf"
        now = datetime.utcnow()
        storage_path = (
            f"cvs/whatsapp/{now.year}/{now.month:02d}/{file_hash}/{safe_filename}"
        )

        # De-dupe: if we already have this exact file, don't re-ingest.
        existing = await supabase.table("cv_files").select("id").eq(
            "file_hash", file_hash
        ).limit(1).execute()
        if existing.data:
            return existing.data[0]["id"]

        # Upload to Supabase storage.
        try:
            from pandapower.integrations.supabase_storage import SupabaseStorageManager

            storage = SupabaseStorageManager(supabase)
            await storage.upload_file(storage_path, content, mime_type or "application/pdf")
        except Exception as e:
            logger.warning(f"Pandius CV storage upload failed: {e}")

        cv_row = {
            "file_hash": file_hash,
            "original_filename": safe_filename,
            "storage_path": storage_path,
            "mime_type": mime_type or "application/pdf",
            "file_size_bytes": len(content),
            "source": "whatsapp",
            "source_email_id": green_api_message_id,
            "source_email_from": phone,
            "source_email_received_at": now.isoformat(),
            "candidate_email": phone,  # no email yet — phone is the identifier
            # Stable bridge back to the intake row (and from there the contact),
            # so candidate-creation can link the candidate to the Pandius contact
            # even before the real email is collected. NULL for emailed CVs.
            "pandius_client_id": pandius_client_id,
            "version_number": 1,
            "is_latest": True,
            "parse_status": "pending",
        }
        try:
            row = await supabase.table("cv_files").insert(cv_row).execute()
        except Exception as e:
            # Column missing → migration 021 not applied yet. Don't let that
            # block CV ingestion entirely; retry without the bridge column.
            msg = str(e).lower()
            if "pandius_client_id" not in msg and "column" not in msg:
                raise
            logger.warning(
                "cv_files.pandius_client_id not found — ingesting without the "
                "bridge column (apply migration 021 for direct contact linkage)"
            )
            cv_row.pop("pandius_client_id", None)
            row = await supabase.table("cv_files").insert(cv_row).execute()

        cv_id = row.data[0]["id"] if row.data else None
        logger.info(f"Pandius CV ingested: cv_id={cv_id} phone={phone}")
        return cv_id
    except Exception as e:
        logger.error(f"Pandius CV ingest failed: {e}", exc_info=True)
        return None
