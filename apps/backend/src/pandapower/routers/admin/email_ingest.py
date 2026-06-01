import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from pandapower.core.config import Settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.azure import AzureGraphClient
from pandapower.integrations.supabase_storage import SupabaseStorageManager
from pandapower.workers.email_ingest import EmailIngestWorker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/email", tags=["admin-email"])


class TestConnectionRequest(BaseModel):
    tenant_id: str
    client_id: str
    client_secret: str
    target_mailbox: str


class TestConnectionResponse(BaseModel):
    ok: bool
    mailbox_address: str | None = None
    total_emails_count: int | None = None
    error: str | None = None


class StartBackfillRequest(BaseModel):
    start_date: str | None = None


class EmailStatusResponse(BaseModel):
    last_run_at: datetime | None = None
    last_status: str | None = None
    emails_processed_total: int = 0
    emails_processed_today: int = 0
    cv_files_extracted_total: int = 0
    cv_files_extracted_today: int = 0


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    request: TestConnectionRequest,
    settings: Settings = Depends(lambda: Settings()),
) -> TestConnectionResponse:
    """Test connection to Azure mailbox."""
    try:
        azure_client = AzureGraphClient(
            tenant_id=request.tenant_id,
            client_id=request.client_id,
            client_secret=request.client_secret,
            target_mailbox=request.target_mailbox,
        )

        # Try to fetch messages to verify connection
        await azure_client.authenticate()
        response = await azure_client.list_messages(page_size=1)

        total_count = response.get("@odata.count", 0)

        return TestConnectionResponse(
            ok=True,
            mailbox_address=request.target_mailbox,
            total_emails_count=total_count,
        )

    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return TestConnectionResponse(
            ok=False,
            error=str(e),
        )


@router.post("/start-backfill")
async def start_backfill(
    request: StartBackfillRequest,
    supabase_client=Depends(get_supabase_client),
) -> dict[str, str]:
    """Start backfill of historical emails.

    This will override the last_seen_message_received_at to start from the specified date.
    The email ingest task will then process all emails from that date forward.
    """
    try:
        start_date = request.start_date or "2021-05-01"

        # Validate date format
        try:
            datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {start_date}. Use YYYY-MM-DD")

        await supabase_client.table("system_settings").upsert(
            {
                "setting_key": "azure.backfill_start_date",
                "setting_value": f'"{start_date}"',
                "updated_at": datetime.utcnow().isoformat(),
            },
            on_conflict="setting_key",
        ).execute()

        await supabase_client.table("system_settings").upsert(
            {
                "setting_key": "azure.last_seen_message_received_at",
                "setting_value": "null",
                "updated_at": datetime.utcnow().isoformat(),
            },
            on_conflict="setting_key",
        ).execute()

        logger.info(f"Backfill started from {start_date}")

        return {
            "status": "started",
            "start_date": start_date,
            "note": "Backfill will process ~100 emails per run. Check progress in status endpoint.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Backfill start failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-now")
async def run_now(
    supabase_client=Depends(get_supabase_client),
) -> dict[str, str]:
    """Manually trigger email ingest worker."""
    try:
        # Fetch Azure settings
        settings_response = await supabase_client.table("system_settings").select(
            "setting_key,setting_value"
        ).in_("setting_key", ["azure.tenant_id", "azure.app_client_id", "azure.client_secret", "azure.target_mailbox"]).execute()

        settings_dict = {}
        for row in settings_response.data or []:
            key = row["setting_key"].split(".")[-1]
            value = row["setting_value"].strip('"') if isinstance(row["setting_value"], str) else row["setting_value"]
            settings_dict[key] = value

        if not all(k in settings_dict for k in ["tenant_id", "app_client_id", "client_secret", "target_mailbox"]):
            raise HTTPException(status_code=400, detail="Azure settings not configured")

        azure_client = AzureGraphClient(
            tenant_id=settings_dict["tenant_id"],
            client_id=settings_dict["app_client_id"],
            client_secret=settings_dict["client_secret"],
            target_mailbox=settings_dict["target_mailbox"],
        )

        storage_manager = SupabaseStorageManager(supabase_client)
        worker = EmailIngestWorker(supabase_client, azure_client, storage_manager)
        result = await worker.ingest_recent_emails()

        return {
            "status": "completed",
            "total_processed": str(result.get("total_processed", 0)),
            "cv_files_extracted": str(result.get("cv_files_extracted", 0)),
        }

    except Exception as e:
        logger.error(f"Manual ingest run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ReingestRequest(BaseModel):
    limit: int = 500


class ReingestAutoRequest(BaseModel):
    enabled: bool


@router.post("/reingest-missed")
async def reingest_missed(request: ReingestRequest) -> dict:
    """Recover CVs from emails the original backfill dropped (status partial/failed).

    Runs in the background so the HTTP call returns immediately; poll
    /admin/email/reingest-status to watch progress."""
    import asyncio as _asyncio
    from pandapower.workers.tasks import _reingest_missed_async

    limit = max(1, min(request.limit, 2000))
    _asyncio.create_task(_reingest_missed_async(limit=limit))
    return {"status": "started", "limit": limit,
            "note": "השחזור רץ ברקע — עקוב ב-/admin/email/reingest-status"}


@router.post("/reingest-auto")
async def reingest_auto(request: ReingestAutoRequest, supabase_client=Depends(get_supabase_client)) -> dict:
    """Turn the autonomous re-ingestion drain on/off (scheduler stage gate)."""
    await supabase_client.table("system_settings").upsert(
        {"setting_key": "reingest.enabled", "setting_value": "true" if request.enabled else "false",
         "updated_at": datetime.utcnow().isoformat()},
        on_conflict="setting_key",
    ).execute()
    return {"status": "ok", "enabled": request.enabled}


@router.get("/reingest-status")
async def reingest_status(supabase_client=Depends(get_supabase_client)) -> dict:
    """Counts of remaining recoverable emails + capture totals."""
    async def _count(table, **eq):
        q = supabase_client.table(table).select("id", count="exact")
        for k, v in eq.items():
            q = q.eq(k, v)
        r = await q.execute()
        return getattr(r, "count", 0) or 0

    partial = await _count("email_intake_log", status="partial")
    failed = await _count("email_intake_log", status="failed")
    cv_files = await _count("cv_files")
    candidates = await _count("candidates")
    enabled_row = await supabase_client.table("system_settings").select("setting_value").eq(
        "setting_key", "reingest.enabled"
    ).limit(1).execute()
    enabled = bool(enabled_row.data) and (enabled_row.data[0].get("setting_value") or "").strip('"') == "true"

    return {
        "auto_enabled": enabled,
        "partial_remaining": partial,
        "failed_remaining": failed,
        "recoverable_total": partial + failed,
        "cv_files_total": cv_files,
        "candidates_total": candidates,
    }


@router.get("/status", response_model=EmailStatusResponse)
async def get_status(
    supabase_client=Depends(get_supabase_client),
) -> EmailStatusResponse:
    """Get email intake status with CV counts and timing."""
    try:
        # Count CV files extracted (from cv_files table, more accurate than counting emails)
        cv_total = await supabase_client.table("cv_files").select(
            "id", count="exact"
        ).execute()
        cv_total_count = cv_total.count or 0

        # Count CVs extracted today
        today_date = datetime.utcnow().date().isoformat()
        cv_today = await supabase_client.table("cv_files").select(
            "id", count="exact"
        ).gte("created_at", today_date).execute()
        cv_today_count = cv_today.count or 0

        # Count emails processed (total success + partial statuses)
        emails_total = await supabase_client.table("email_intake_log").select(
            "id", count="exact"
        ).in_("status", ["success", "partial"]).execute()
        emails_total_count = emails_total.count or 0

        # Count emails processed today
        emails_today = await supabase_client.table("email_intake_log").select(
            "id", count="exact"
        ).in_("status", ["success", "partial"]).gte("created_at", today_date).execute()
        emails_today_count = emails_today.count or 0

        # Get last successful run time
        last_run_response = await supabase_client.table("email_intake_log").select(
            "processing_completed_at"
        ).in_("status", ["success", "partial"]).order("processing_completed_at", desc=True).limit(1).execute()

        last_run_at = None
        if last_run_response.data:
            last_run_at = datetime.fromisoformat(
                last_run_response.data[0]["processing_completed_at"].replace("Z", "+00:00")
            )

        return EmailStatusResponse(
            last_run_at=last_run_at or datetime.utcnow(),
            last_status="active" if emails_today_count > 0 else "configured",
            emails_processed_total=emails_total_count,
            emails_processed_today=emails_today_count,
            cv_files_extracted_total=cv_total_count,
            cv_files_extracted_today=cv_today_count,
        )

    except Exception as e:
        logger.error(f"Status fetch failed: {e}")
        return EmailStatusResponse()


@router.get("/backfill-progress")
async def get_backfill_progress(
    supabase_client=Depends(get_supabase_client),
) -> dict:
    """Get backfill progress."""
    try:
        # Get backfill start date (use limit(1) instead of single() to avoid error when row missing)
        backfill_response = await supabase_client.table("system_settings").select(
            "setting_value"
        ).eq("setting_key", "azure.backfill_start_date").limit(1).execute()

        backfill_start = None
        if backfill_response.data and backfill_response.data[0].get("setting_value"):
            date_str = str(backfill_response.data[0]["setting_value"]).strip('"')
            if date_str and date_str != "null":
                try:
                    backfill_start = datetime.fromisoformat(date_str)
                except ValueError:
                    pass

        # Get last processed timestamp
        last_seen_response = await supabase_client.table("system_settings").select(
            "setting_value"
        ).eq("setting_key", "azure.last_seen_message_received_at").limit(1).execute()

        last_processed = None
        if last_seen_response.data and last_seen_response.data[0].get("setting_value"):
            iso_str = str(last_seen_response.data[0]["setting_value"]).strip('"')
            if iso_str and iso_str != "null":
                try:
                    last_processed = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
                except ValueError:
                    pass

        # Calculate progress
        if backfill_start and last_processed:
            total_days = (datetime.utcnow() - backfill_start).days
            processed_days = (last_processed - backfill_start).days
            progress_percent = min(100, int((processed_days / max(total_days, 1)) * 100))
        else:
            progress_percent = 0 if backfill_start else None

        return {
            "backfill_enabled": backfill_start is not None,
            "backfill_start_date": backfill_start.isoformat() if backfill_start else None,
            "last_processed_at": last_processed.isoformat() if last_processed else None,
            "progress_percent": progress_percent,
            "days_remaining": max(0, (datetime.utcnow() - (last_processed or backfill_start)).days) if backfill_start else None,
        }

    except Exception as e:
        logger.error(f"Backfill progress fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def get_logs(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    supabase_client=Depends(get_supabase_client),
) -> dict:
    """Get email intake logs."""
    try:
        query = supabase_client.table("email_intake_log").select("*")

        if status:
            query = query.eq("status", status)

        response = await query.order("created_at", desc=True).range(offset, offset + limit).execute()

        return {
            "total": len(response.data or []),
            "data": response.data or [],
        }

    except Exception as e:
        logger.error(f"Logs fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ConfigureRequest(BaseModel):
    tenant_id: str
    client_id: str
    client_secret: str
    target_mailbox: str


@router.post("/configure")
async def configure(
    request: ConfigureRequest,
    supabase_client=Depends(get_supabase_client),
) -> dict[str, str]:
    """Save Azure email configuration."""
    try:
        settings = {
            "azure.tenant_id": request.tenant_id,
            "azure.app_client_id": request.client_id,
            "azure.client_secret": request.client_secret,
            "azure.target_mailbox": request.target_mailbox,
        }

        for key, value in settings.items():
            await supabase_client.table("system_settings").upsert(
                {
                    "setting_key": key,
                    "setting_value": f'"{value}"',
                    "updated_at": datetime.utcnow().isoformat(),
                },
                on_conflict="setting_key",
            ).execute()

        return {"status": "configured"}

    except Exception as e:
        logger.error(f"Configuration save failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cancel-backfill")
async def cancel_backfill(
    supabase_client=Depends(get_supabase_client),
) -> dict[str, str]:
    """Cancel backfill and resume normal email intake from current date."""
    try:
        await supabase_client.table("system_settings").update(
            {
                "setting_value": "null",
                "updated_at": datetime.utcnow().isoformat(),
            }
        ).eq("setting_key", "azure.backfill_start_date").execute()

        await supabase_client.table("system_settings").update(
            {
                "setting_value": f'"{datetime.utcnow().isoformat()}"',
                "updated_at": datetime.utcnow().isoformat(),
            }
        ).eq("setting_key", "azure.last_seen_message_received_at").execute()

        logger.info("Backfill cancelled, resumed normal intake from current time")

        return {"status": "cancelled", "message": "Backfill cancelled, normal intake resumed"}

    except Exception as e:
        logger.error(f"Backfill cancellation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signed-url/{cv_file_id}")
async def get_signed_url(
    cv_file_id: str,
    supabase_client=Depends(get_supabase_client),
) -> dict[str, str]:
    """Generate signed URL for downloading CV file."""
    try:
        # Fetch CV file record to get storage path
        cv_response = await supabase_client.table("cv_files").select(
            "storage_path"
        ).eq("id", cv_file_id).single().execute()

        if not cv_response.data:
            raise HTTPException(status_code=404, detail="CV file not found")

        storage_path = cv_response.data["storage_path"]

        # Generate signed URL (7 days expiry)
        storage_manager = SupabaseStorageManager(supabase_client)
        signed_url = await storage_manager.create_signed_url(storage_path, expires_in_seconds=604800)

        return {"signed_url": signed_url}

    except Exception as e:
        logger.error(f"Signed URL generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
