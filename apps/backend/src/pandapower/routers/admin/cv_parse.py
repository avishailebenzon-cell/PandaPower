import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from pandapower.core.config import settings
from pandapower.core.supabase import get_supabase_client
from pandapower.integrations.claude_api import AnthropicClient
from pandapower.integrations.supabase_storage import SupabaseStorageManager
from pandapower.workers.cv_parse import CVParseWorker

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/cv", tags=["admin", "cv-parsing"])


# Pydantic models for responses
from pydantic import BaseModel


class CVParseStatusResponse(BaseModel):
    """Response for CV parsing status."""
    pending: int
    parsing: int
    success: int
    failed: int


class CVParseMetrics(BaseModel):
    """Response for CV parsing metrics."""
    total_processed: int
    success: int
    failed: int
    tokens_used: int
    errors: list[dict[str, Any]]


class CVParseLog(BaseModel):
    """Single CV parse log entry."""
    cv_file_id: str
    original_filename: str
    parse_status: str
    parse_duration_ms: int | None
    detected_language: str | None
    llm_tokens_used: int | None
    parse_error: str | None


class CVParseResult(BaseModel):
    """Detailed parse result."""
    cv_file_id: str
    original_filename: str
    parse_status: str
    detected_language: str | None
    extraction_method: str | None
    raw_text_length: int | None
    llm_tokens_used: int | None
    parse_duration_ms: int | None
    extracted_fields: dict[str, Any] | None
    confidence_scores: dict[str, float] | None
    extraction_notes: str | None


@router.get("/status", response_model=CVParseStatusResponse)
async def get_cv_parse_status() -> CVParseStatusResponse:
    """Get current CV parsing status."""
    try:
        supabase = await get_supabase_client()

        # Count CVs by status (use count="exact" for efficiency)
        pending = await supabase.table("cv_files").select("id", count="exact").eq("parse_status", "pending").execute()
        parsing = await supabase.table("cv_files").select("id", count="exact").eq("parse_status", "parsing").execute()
        success = await supabase.table("cv_files").select("id", count="exact").eq("parse_status", "success").execute()
        failed = await supabase.table("cv_files").select("id", count="exact").eq("parse_status", "failed").execute()

        return CVParseStatusResponse(
            pending=pending.count or 0,
            parsing=parsing.count or 0,
            success=success.count or 0,
            failed=failed.count or 0,
        )

    except Exception as e:
        logger.error(f"Failed to get CV parse status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-now", response_model=CVParseMetrics)
async def trigger_cv_parse_now() -> CVParseMetrics:
    """Manually trigger CV parsing."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="ANTHROPIC_API_KEY not configured",
        )

    try:
        supabase = await get_supabase_client()
        claude = AnthropicClient(settings.ANTHROPIC_API_KEY)
        storage = SupabaseStorageManager(supabase)

        worker = CVParseWorker(
            supabase,
            storage,
            claude,
            batch_size=settings.CV_PARSE_BATCH_SIZE,
            parse_timeout=settings.CV_PARSE_TIMEOUT_SECONDS,
        )

        result = await worker.parse_pending_cvs()
        await claude.close()

        return CVParseMetrics(
            total_processed=result.get("total_processed", 0),
            success=result.get("success", 0),
            failed=result.get("failed", 0),
            tokens_used=result.get("tokens_used", 0),
            errors=result.get("errors", []),
        )

    except Exception as e:
        logger.error(f"Failed to trigger CV parsing: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs", response_model=list[CVParseLog])
async def get_cv_parse_logs(limit: int = 50, status: str | None = None) -> list[CVParseLog]:
    """Get CV parsing logs."""
    if limit < 1 or limit > 500:
        limit = 50

    try:
        supabase = await get_supabase_client()

        query = (
            supabase.table("cv_files")
            .select(
                "id,"
                "original_filename,"
                "parse_status,"
                "parse_duration_ms,"
                "detected_language,"
                "llm_tokens_used,"
                "parse_error"
            )
            .order("processing_completed_at", desc=True)
            .limit(limit)
        )

        if status:
            query = query.eq("parse_status", status)

        result = await query.execute()

        logs = [
            CVParseLog(
                cv_file_id=row["id"],
                original_filename=row.get("original_filename", ""),
                parse_status=row.get("parse_status", "unknown"),
                parse_duration_ms=row.get("parse_duration_ms"),
                detected_language=row.get("detected_language"),
                llm_tokens_used=row.get("llm_tokens_used"),
                parse_error=row.get("parse_error"),
            )
            for row in (result.data or [])
        ]

        return logs

    except Exception as e:
        logger.error(f"Failed to get CV parse logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ReparseAllRequest(BaseModel):
    """Filter for bulk re-parse."""
    only_failed: bool = False  # if True, only failed CVs; else also re-parse successful ones
    confirm: bool = False  # safety: must be True to actually run


class ReparseAllResponse(BaseModel):
    status: str
    marked_pending: int
    previous_status_breakdown: dict[str, int]
    note: str


@router.post("/reparse-all", response_model=ReparseAllResponse)
async def reparse_all_cvs(req: ReparseAllRequest) -> ReparseAllResponse:
    """Mark every CV as pending so the autonomous CV-parse worker picks them
    up again — useful when the extraction prompt changes and we want to
    re-extract richer data from CVs we already processed.

    Pass {"confirm": true} to actually run. Without confirm, returns a dry-run
    preview so the user can see how many CVs would be affected.

    With only_failed=true, only CVs in 'failed' state are reset (much cheaper).
    """
    try:
        supabase = await get_supabase_client()

        # Build a per-status count so the UI can warn about Claude API cost.
        status_breakdown = {}
        for status_name in ("pending", "parsing", "success", "failed"):
            r = await supabase.table("cv_files").select(
                "id", count="exact"
            ).eq("parse_status", status_name).execute()
            status_breakdown[status_name] = r.count or 0

        # Decide which statuses to reset
        statuses_to_reset = ["failed"] if req.only_failed else ["success", "failed"]

        will_reset = sum(status_breakdown[s] for s in statuses_to_reset)

        if not req.confirm:
            return ReparseAllResponse(
                status="dry_run",
                marked_pending=0,
                previous_status_breakdown=status_breakdown,
                note=(
                    f"Dry run: would mark {will_reset} CVs as pending "
                    f"(statuses: {', '.join(statuses_to_reset)}). "
                    f"Re-call with confirm=true to execute."
                ),
            )

        if will_reset == 0:
            return ReparseAllResponse(
                status="nothing_to_do",
                marked_pending=0,
                previous_status_breakdown=status_breakdown,
                note="No CVs match the requested statuses.",
            )

        # Reset the chosen statuses to pending, clearing prior parse artifacts so
        # they don't bleed into the next run.
        await supabase.table("cv_files").update({
            "parse_status": "pending",
            "parse_error": None,
            "parse_duration_ms": None,
            "processing_completed_at": None,
            "llm_tokens_used": None,
            # NOTE: we intentionally keep llm_analysis around as a historical
            # snapshot; the worker will overwrite it on the next successful parse.
        }).in_("parse_status", statuses_to_reset).execute()

        return ReparseAllResponse(
            status="queued",
            marked_pending=will_reset,
            previous_status_breakdown=status_breakdown,
            note=(
                f"Marked {will_reset} CVs as pending. The autonomous parser "
                f"will pick them up over the next few minutes "
                f"(batch size {settings.CV_PARSE_BATCH_SIZE} every 3 min)."
            ),
        )

    except Exception as e:
        logger.error(f"Failed to reparse all CVs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retry/{cv_file_id}", response_model=CVParseMetrics)
async def retry_failed_cv(cv_file_id: str) -> CVParseMetrics:
    """Retry parsing a single failed CV."""
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="ANTHROPIC_API_KEY not configured",
        )

    try:
        supabase = await get_supabase_client()

        # Verify CV exists
        cv_query = await supabase.table("cv_files").select("*").eq("id", cv_file_id).execute()
        if not cv_query.data:
            raise HTTPException(status_code=404, detail="CV not found")

        # Mark as pending again
        await supabase.table("cv_files").update({"parse_status": "pending"}).eq(
            "id", cv_file_id
        ).execute()

        # Parse it
        claude = AnthropicClient(settings.ANTHROPIC_API_KEY)
        storage = SupabaseStorageManager(supabase)

        worker = CVParseWorker(
            supabase,
            storage,
            claude,
            batch_size=1,
            parse_timeout=settings.CV_PARSE_TIMEOUT_SECONDS,
        )

        # Manually parse this one CV
        cv_file = cv_query.data[0]
        parsed = await worker._parse_single_cv(cv_file)
        await claude.close()

        return CVParseMetrics(
            total_processed=1,
            success=1 if parsed.get("success") else 0,
            failed=0 if parsed.get("success") else 1,
            tokens_used=parsed.get("tokens_used", 0),
            errors=[],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry CV {cv_file_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results/{cv_file_id}", response_model=CVParseResult)
async def get_cv_parse_result(cv_file_id: str) -> CVParseResult:
    """Get detailed parse result for a CV."""
    try:
        supabase = await get_supabase_client()

        result = await (
            supabase.table("cv_files")
            .select("*")
            .eq("id", cv_file_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=404, detail="CV not found")

        cv = result.data[0]
        llm_analysis = cv.get("llm_analysis") or {}

        return CVParseResult(
            cv_file_id=cv["id"],
            original_filename=cv.get("original_filename", ""),
            parse_status=cv.get("parse_status", "unknown"),
            detected_language=cv.get("detected_language"),
            extraction_method=llm_analysis.get("extraction_method"),
            raw_text_length=llm_analysis.get("raw_text_length"),
            llm_tokens_used=cv.get("llm_tokens_used"),
            parse_duration_ms=cv.get("parse_duration_ms"),
            extracted_fields=llm_analysis.get("extracted_fields"),
            confidence_scores=llm_analysis.get("confidence_scores"),
            extraction_notes=llm_analysis.get("extraction_notes"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get CV parse result {cv_file_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
