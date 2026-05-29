from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pandapower.core import configure_logging, settings
from pandapower.core.supabase import close_supabase, init_supabase
from pandapower.routers import health_router, webhooks
from pandapower.routers.admin import email_ingest, setup, cv_parse, cv_upload, candidate_management, candidate_recommendations, match_flow, skill_management, security_classification, agent_matching, carmit, pipedrive, pipedrive_config, pipedrive_data, pipedrive_sync, analytics, pandi, pandi_referrals, recruitment_departments, recruiter, alerts as admin_alerts, health as admin_health, whatsapp_agents, system_settings, elad_outreach, pandi_outreach
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
# app.include_router(match_history.router)  # Temporarily excluded


import asyncio
import logging

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


async def _pipeline_scheduler_loop():
    """
    Background loop that runs the full CV processing pipeline autonomously.

    Stages and intervals:
      - Email ingest         : every 120s  (poll Outlook, save CVs to storage)
      - CV parsing           : every 180s  (extract text + Claude analysis)
      - Candidate creation   : every 240s  (create candidate records from parsed CVs)
      - Skill normalization  : every 600s  (map raw skills to canonical skills)

    Each stage runs independently and skips silently if its prerequisites
    (Azure creds, Anthropic key, etc.) are not configured. Failures in one
    stage don't block the others.
    """
    from pandapower.workers.tasks import (
        _ingest_emails_async,
        _parse_cvs_async,
        _create_candidates_async,
        _normalize_skills_async,
    )

    # Track when each stage last ran so we can pace them independently.
    last_run: dict[str, float] = {
        "ingest": 0.0,
        "parse": 0.0,
        "candidates": 0.0,
        "skills": 0.0,
    }
    intervals = {
        "ingest": 120.0,
        "parse": 180.0,
        "candidates": 240.0,
        "skills": 600.0,
    }

    # Track consecutive failures per stage so we don't alert on every single tick,
    # but DO alert if a stage is consistently broken.
    consecutive_failures: dict[str, int] = {"ingest": 0, "parse": 0, "candidates": 0, "skills": 0}
    FAILURE_ALERT_THRESHOLD = 3  # alert after 3 consecutive failures

    async def _run_stage(name: str, coro_factory):
        """Run a single pipeline stage, swallowing errors so other stages keep ticking."""
        from pandapower.integrations.alert_service import alert_admin

        try:
            result = await coro_factory()
            status = result.get("status", "unknown")
            if status == "completed":
                consecutive_failures[name] = 0  # reset counter on success
                # Only log when something actually happened
                if any(result.get(k, 0) for k in ("total_processed", "success", "created", "candidates_updated")):
                    _logger.info(f"[pipeline:{name}] {result}")
            elif status == "skipped":
                _logger.debug(f"[pipeline:{name}] skipped - {result.get('reason')}")
            elif status == "failed":
                consecutive_failures[name] += 1
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
                _logger.warning(f"[pipeline:{name}] {status}: {result}")
        except Exception as e:
            consecutive_failures[name] += 1
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

    _logger.info("Pipeline scheduler started: email→parse→candidate→skills running autonomously")
    print("[PIPELINE] Loop entered, ticking every 30s", flush=True)

    while True:
        try:
            now = asyncio.get_event_loop().time()

            if now - last_run["ingest"] >= intervals["ingest"]:
                last_run["ingest"] = now
                print(f"[PIPELINE] tick: triggering email ingest at t={now:.0f}", flush=True)
                asyncio.create_task(_run_stage("ingest", _ingest_emails_async))

            if now - last_run["parse"] >= intervals["parse"]:
                last_run["parse"] = now
                asyncio.create_task(_run_stage("parse", _parse_cvs_async))

            if now - last_run["candidates"] >= intervals["candidates"]:
                last_run["candidates"] = now
                asyncio.create_task(_run_stage("candidates", _create_candidates_async))

            if now - last_run["skills"] >= intervals["skills"]:
                last_run["skills"] = now
                asyncio.create_task(_run_stage("skills", _normalize_skills_async))

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

    # Start the autonomous CV processing pipeline (email → parse → candidate → skills)
    # Use print so this is visible even if structlog isn't piping to stdout.
    print("[STARTUP] Starting autonomous CV processing pipeline scheduler", flush=True)
    _pipeline_scheduler_task = asyncio.create_task(_pipeline_scheduler_loop())
    _logger.info("Started autonomous CV processing pipeline scheduler")

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
