from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from pandapower.core import configure_logging, settings
from pandapower.core.supabase import close_supabase, init_supabase
from pandapower.routers import health_router, webhooks
from pandapower.routers.admin import email_ingest, setup, cv_parse, cv_upload, candidate_management, candidate_recommendations, match_flow, skill_management, security_classification, agent_matching, carmit, pipedrive, pipedrive_config, pipedrive_data, pipedrive_sync, analytics, pandi, pandi_referrals, recruitment_departments, recruiter, alerts as admin_alerts, health as admin_health, whatsapp_agents, system_settings, elad_outreach, pandi_outreach, telegram_config, convertapi_config
# Note: agent_matching temporarily excluded due to missing celery tasks
# Note: match_history temporarily excluded due to import issues
from pandapower.routers import user

configure_logging()

app = FastAPI(title="PandaPower", version="0.1.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers to ensure all errors return JSON
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions and return JSON"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={"Content-Type": "application/json"},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors and return JSON"""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
        headers={"Content-Type": "application/json"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler to return JSON for unexpected errors"""
    import logging
    logging.getLogger(__name__).error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"Content-Type": "application/json"},
    )

# Routers
app.include_router(health_router)
app.include_router(user.router)
app.include_router(webhooks.router)
app.include_router(setup.router)
app.include_router(email_ingest.router)
app.include_router(cv_parse.router)
app.include_router(cv_upload.router)
app.include_router(candidate_management.router)
app.include_router(candidate_recommendations.router)
app.include_router(match_flow.router)
app.include_router(skill_management.router)
app.include_router(security_classification.router)
app.include_router(agent_matching.router)
app.include_router(carmit.router)
app.include_router(pipedrive.router)
app.include_router(pipedrive_config.router)
app.include_router(pipedrive_data.router)
app.include_router(pipedrive_sync.router)
app.include_router(analytics.router)
app.include_router(pandi.router)
app.include_router(pandi_referrals.router)
app.include_router(recruiter.router)
app.include_router(recruitment_departments.router)
app.include_router(admin_health.router)
app.include_router(admin_alerts.router)
app.include_router(whatsapp_agents.router)
app.include_router(system_settings.router)
app.include_router(elad_outreach.router)
app.include_router(pandi_outreach.router)
app.include_router(telegram_config.router)
app.include_router(convertapi_config.router)
# app.include_router(match_history.router)  # Temporarily excluded


import asyncio
import logging
import os
from datetime import datetime

_logger = logging.getLogger(__name__)

# Handles to background scheduler tasks so we can cancel them on shutdown
_pipedrive_scheduler_task: asyncio.Task | None = None
_pipeline_scheduler_task: asyncio.Task | None = None


async def _pipedrive_scheduler_loop():
    """
    Background loop that drives the user-configured Pipedrive sync schedule.

    Every minute it consults pipedrive_sync_schedule (settings managed from the
    UI) and runs the deals / persons / organizations sync that is due, honoring
    sync_enabled, sync_interval_minutes, sync_days and sync_time.
    """
    from pandapower.workers.pipedrive_sync_scheduler import run_due_syncs

    while True:
        try:
            await asyncio.sleep(60)  # Tick once per minute
            result = await run_due_syncs()
            if result.get("status") == "ran":
                _logger.info(f"Pipedrive scheduler ran: {result.get('triggered')}")
        except asyncio.CancelledError:
            _logger.info("Pipedrive scheduler loop cancelled")
            raise
        except Exception as e:
            _logger.error(f"Pipedrive scheduler tick error: {e}", exc_info=True)
            # Don't crash the loop - keep going on next tick


async def _record_heartbeat(
    task_name: str,
    status: str,
    interval: float,
    result: dict | None = None,
    error: str | None = None,
    consecutive_failures: int = 0,
) -> None:
    """Persist one task's heartbeat to scheduler_heartbeats (best-effort).

    This is the single source of truth for "is this process running?" that
    survives process restarts. Never raises — monitoring must not break the
    pipeline. Degrades silently if the table doesn't exist yet (migration
    20260601000001 not applied).
    """
    try:
        from pandapower.core.supabase import get_supabase_client
        client = await get_supabase_client()
        await client.table("scheduler_heartbeats").upsert(
            {
                "task_name": task_name,
                "last_run_at": datetime.utcnow().isoformat(),
                "last_status": status,
                "last_result": result,
                "last_error": error,
                "consecutive_failures": consecutive_failures,
                "expected_interval_seconds": int(interval),
                "updated_at": datetime.utcnow().isoformat(),
            },
            on_conflict="task_name",
        ).execute()
    except Exception as e:
        _logger.debug(f"heartbeat upsert failed for {task_name} (non-fatal): {e}")


async def _pipeline_scheduler_loop():
    """
    Background loop that runs the FULL automation pipeline autonomously.

    This is the single authoritative scheduler for ALL recurring work. It runs
    inside the always-on web service (which Render keeps alive via the health
    check), so as long as the API is up, every stage below keeps ticking. The
    separate Celery beat is intentionally retired (see celery_app.py) to avoid
    double-execution of non-idempotent matching tasks.

    Stages and intervals:
      CV intake pipeline:
        - ingest               : 120s   (poll Outlook, save CVs to storage)
        - parse                : 180s   (extract text + Claude analysis)
        - candidates           : 240s   (create candidate records)
        - skills               : 600s   (normalize raw skills → canonical)
        - score                : 3600s  (score candidate readiness)
      Matching pipeline (Carmit → Tal):
        - carmit_route_jobs    : 600s   (route open jobs to agents via Opus)
        - carmit_review_matches: 900s   (Carmit approves/rejects found matches)
        - carmit_handoff_to_tal: 600s   (move approved matches into Tal's queue)
        - pipeline_watchdog    : 1800s  (re-kick matches stuck > threshold)
      Pipedrive metadata:
        - pipedrive_field_sync       : 3600s   (custom field definitions)
        - pipedrive_historical_import: 14400s  (historical rejection reasons)

    Each stage runs independently and skips silently if its prerequisites
    (Azure creds, Anthropic key, etc.) are not configured. Failures in one
    stage don't block the others. Every run writes a heartbeat row.
    """
    from pandapower.workers.tasks import (
        _ingest_emails_async,
        _parse_cvs_async,
        _create_candidates_async,
        _normalize_skills_async,
        _score_candidates_async,
        _carmit_route_jobs_async,
        _carmit_review_matches_async,
        _carmit_handoff_to_tal_async,
        _pipeline_watchdog_async,
        _pipedrive_field_sync_async,
        _pipedrive_historical_import_async,
        _notify_telegram_async,
        _telegram_daily_summary_async,
        _reingest_missed_scheduled_async,
    )

    # Each stage: (async factory, interval seconds, initial stagger offset).
    # The stagger offset seeds last_run so heavy Opus stages (route/review)
    # don't all fire on the same tick right after boot — it spreads the first
    # firing of each stage across the first couple of minutes.
    stages: dict[str, tuple] = {
        # name                    factory                          interval  stagger
        "ingest":                (_ingest_emails_async,            120.0,    0.0),
        "parse":                 (_parse_cvs_async,                180.0,    10.0),
        "candidates":            (_create_candidates_async,        240.0,    20.0),
        "skills":                (_normalize_skills_async,         600.0,    30.0),
        "score":                 (_score_candidates_async,         3600.0,   40.0),
        "carmit_route_jobs":     (_carmit_route_jobs_async,        600.0,    50.0),
        "carmit_review_matches": (_carmit_review_matches_async,    900.0,    65.0),
        "carmit_handoff_to_tal": (_carmit_handoff_to_tal_async,    600.0,    80.0),
        "pipeline_watchdog":     (_pipeline_watchdog_async,        1800.0,   95.0),
        "pipedrive_field_sync":  (_pipedrive_field_sync_async,     3600.0,   110.0),
        "pipedrive_historical_import": (_pipedrive_historical_import_async, 14400.0, 125.0),
        # Telegram (Carmit bot): notify match→Tal / hires, and a once-a-day digest.
        "notify_telegram":       (_notify_telegram_async,          120.0,    55.0),
        "telegram_daily_summary": (_telegram_daily_summary_async,  900.0,    140.0),
        # Recover CVs the original backfill dropped (gated by reingest.enabled).
        "reingest_missed":       (_reingest_missed_scheduled_async, 120.0,   70.0),
    }

    intervals = {name: spec[1] for name, spec in stages.items()}
    # Seed last_run so the FIRST firing happens `interval - stagger` from now,
    # i.e. quickly for short-interval stages but spread out, while long-interval
    # stages still wait roughly their full interval before first run.
    loop_now = asyncio.get_event_loop().time()
    last_run: dict[str, float] = {
        name: loop_now - max(0.0, spec[1] - spec[2]) for name, spec in stages.items()
    }

    # Track consecutive failures per stage so we don't alert on every single tick,
    # but DO alert if a stage is consistently broken.
    consecutive_failures: dict[str, int] = {name: 0 for name in stages}
    FAILURE_ALERT_THRESHOLD = 3  # alert after 3 consecutive failures

    async def _run_stage(name: str, coro_factory, interval: float):
        """Run a single pipeline stage, swallowing errors so other stages keep ticking.

        Always records a heartbeat (success or failure) so the monitoring layer
        can tell the stage is alive.
        """
        from pandapower.integrations.alert_service import alert_admin

        hb_status = "completed"
        hb_error: str | None = None
        hb_result: dict | None = None
        try:
            result = await coro_factory()
            hb_result = result if isinstance(result, dict) else {"raw": str(result)}
            status = result.get("status", "unknown")
            if status == "completed" or status == "success" or status == "ok":
                consecutive_failures[name] = 0  # reset counter on success
                hb_status = "completed"
                # Only log when something actually happened
                if any(result.get(k, 0) for k in (
                    "total_processed", "success", "created", "candidates_updated",
                    "jobs_routed", "matches_reviewed", "handed_off", "candidates_scored",
                )):
                    _logger.info(f"[pipeline:{name}] {result}")
            elif status == "skipped":
                consecutive_failures[name] = 0
                hb_status = "skipped"
                hb_error = result.get("reason")
                _logger.debug(f"[pipeline:{name}] skipped - {result.get('reason')}")
            elif status == "failed":
                consecutive_failures[name] += 1
                hb_status = "failed"
                hb_error = result.get("error", "(no error message)")
                _logger.warning(f"[pipeline:{name}] failed ({consecutive_failures[name]}x consecutive): {result}")
                if consecutive_failures[name] >= FAILURE_ALERT_THRESHOLD:
                    await alert_admin(
                        key=f"pipeline-{name}-repeated-failures",
                        subject=f"Pipeline stage '{name}' failing repeatedly",
                        details=(
                            f"The '{name}' stage has failed {consecutive_failures[name]} times in a row.\n\n"
                            f"Last error:\n{result.get('error', '(no error message)')}\n\n"
                            f"Full result:\n{result}\n\n"
                            f"Check the backend logs for full tracebacks. "
                            f"The pipeline will keep retrying — fix the root cause and the alert will auto-clear."
                        ),
                        severity="error",
                    )
            else:
                # Unknown status — treat as completed-ish but record it.
                consecutive_failures[name] = 0
                hb_status = status or "unknown"
                _logger.warning(f"[pipeline:{name}] {status}: {result}")
        except Exception as e:
            consecutive_failures[name] += 1
            hb_status = "crashed"
            hb_error = f"{type(e).__name__}: {e}"
            _logger.error(f"[pipeline:{name}] crashed: {e}", exc_info=True)
            if consecutive_failures[name] >= FAILURE_ALERT_THRESHOLD:
                await alert_admin(
                    key=f"pipeline-{name}-crash",
                    subject=f"Pipeline stage '{name}' crashing repeatedly",
                    details=(
                        f"The '{name}' stage has thrown an unhandled exception "
                        f"{consecutive_failures[name]} times in a row.\n\n"
                        f"Latest exception:\n{type(e).__name__}: {e}\n\n"
                        f"This indicates a code-level bug. The pipeline will keep "
                        f"retrying every cycle, but data flow may be stalled."
                    ),
                    severity="critical",
                )
        finally:
            await _record_heartbeat(
                task_name=name,
                status=hb_status,
                interval=interval,
                result=hb_result,
                error=hb_error,
                consecutive_failures=consecutive_failures[name],
            )

    _logger.info(
        "Pipeline scheduler started: intake (ingest→parse→candidate→skills→score) + "
        "matching (route→review→handoff→watchdog) + pipedrive metadata, all running autonomously"
    )
    print(f"[PIPELINE] Loop entered, ticking every 30s, {len(stages)} stages registered", flush=True)

    while True:
        try:
            now = asyncio.get_event_loop().time()

            for name, (factory, interval, _stagger) in stages.items():
                if now - last_run[name] >= interval:
                    last_run[name] = now
                    if name == "ingest":
                        print(f"[PIPELINE] tick: triggering email ingest at t={now:.0f}", flush=True)
                    asyncio.create_task(_run_stage(name, factory, interval))

            await asyncio.sleep(30)  # Check every 30s which stages are due

        except asyncio.CancelledError:
            _logger.info("Pipeline scheduler loop cancelled")
            raise
        except Exception as e:
            _logger.error(f"Pipeline scheduler tick error: {e}", exc_info=True)
            await asyncio.sleep(30)  # Don't crash the loop


@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    global _pipedrive_scheduler_task, _pipeline_scheduler_task
    await init_supabase()

    # Singleton guard: the in-process scheduler is the ONE authoritative
    # executor for all recurring work. It must run in exactly one process.
    # The web service runs at --workers 1 (see render.yaml), so this is the
    # single process. SCHEDULER_ENABLED lets ops disable it (e.g. if ever
    # moving scheduling back to a dedicated worker). If the web service is ever
    # scaled to >1 worker, gate this with a Postgres advisory lock instead so
    # the non-idempotent matching stages (route/review) don't double-run.
    scheduler_enabled = os.getenv("SCHEDULER_ENABLED", "true").lower() != "false"
    if not scheduler_enabled:
        _logger.warning("SCHEDULER_ENABLED=false — in-process scheduler NOT started")
        return

    # Start the autonomous automation pipeline (intake + matching + pipedrive).
    # Use print so this is visible even if structlog isn't piping to stdout.
    print("[STARTUP] Starting autonomous automation pipeline scheduler", flush=True)
    _pipeline_scheduler_task = asyncio.create_task(_pipeline_scheduler_loop())
    _logger.info("Started autonomous automation pipeline scheduler")

    # Start the user-driven Pipedrive sync scheduler in the background
    if settings.PIPEDRIVE_API_TOKEN:
        _pipedrive_scheduler_task = asyncio.create_task(_pipedrive_scheduler_loop())
        _logger.info("Started Pipedrive sync scheduler loop (user-driven)")
    else:
        _logger.warning("PIPEDRIVE_API_TOKEN not set - sync scheduler disabled")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global _pipedrive_scheduler_task, _pipeline_scheduler_task

    for task_name, task in [
        ("pipeline", _pipeline_scheduler_task),
        ("pipedrive", _pipedrive_scheduler_task),
    ]:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            _logger.info(f"{task_name} scheduler stopped")

    await close_supabase()


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Welcome to PandaPower API"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("pandapower.main:app", host="0.0.0.0", port=8000, reload=True)
