import os
from celery import Celery
from pandapower.core.config import settings

app = Celery("pandapower")

# Production gate. We check BOTH env-var names because render.yaml sets
# APP_ENV=production while older deployments may have ENVIRONMENT=production.
# Either should activate Redis + non-eager mode.
_is_prod = os.getenv("ENVIRONMENT") == "production" or os.getenv("APP_ENV") == "production"

if _is_prod:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    app.conf.broker_url = redis_url
    app.conf.result_backend = redis_url
else:
    # Development: use eager mode to execute tasks synchronously
    app.conf.broker_url = "memory://"
    app.conf.result_backend = "cache+memory://"

# ---------------------------------------------------------------------------
# Celery Beat is RETIRED as of Session 36. All recurring work now runs in the
# always-on in-process scheduler inside the web service (apps/.../main.py
# _pipeline_scheduler_loop). This is the single authoritative executor — it
# removes the separate-worker single-point-of-failure that silently stopped the
# matching pipeline, and avoids double-execution of the non-idempotent matching
# tasks (carmit_route_jobs / carmit_review_matches).
#
# The schedule below is therefore gated behind ENABLE_CELERY_BEAT (default OFF).
# The task DEFINITIONS remain importable for ad-hoc/manual use (.delay() or
# direct calls). Do NOT set ENABLE_CELERY_BEAT=true while the in-process
# scheduler is running, or matching tasks will double-run.
# ---------------------------------------------------------------------------
_enable_beat = os.getenv("ENABLE_CELERY_BEAT", "false").lower() == "true"

_beat_schedule = {
    "ingest-emails-every-2-minutes": {
        "task": "pandapower.workers.tasks.ingest_emails_task",
        "schedule": 120.0,  # Run every 120 seconds
    },
    "parse-cvs-every-5-minutes": {
        "task": "pandapower.workers.tasks.parse_cv_task",
        "schedule": 300.0,  # Run every 300 seconds (5 minutes)
    },
    "create-candidates-every-10-minutes": {
        "task": "pandapower.workers.tasks.create_candidates_task",
        "schedule": 600.0,  # Run every 600 seconds (10 minutes)
    },
    "normalize-skills-every-15-minutes": {
        "task": "pandapower.workers.tasks.normalize_skills_task",
        "schedule": 900.0,  # Run every 900 seconds (15 minutes)
    },
    "score-candidates-every-hour": {
        "task": "pandapower.workers.tasks.score_candidates_task",
        "schedule": 3600.0,  # Run every 3600 seconds (1 hour)
    },
    # NOTE: Job assignment via simple keyword matching REMOVED (2026-05-25).
    # All job routing now goes through Carmit Orchestrator (carmit_route_jobs_task) which uses Claude Opus.
    # This prevents duplicate assignments and ensures intelligent routing decisions.
    #
    # REMOVED:
    # "match-jobs-every-10-minutes": check_new_jobs_for_assignment_task
    # "match-candidates-every-15-minutes": check_new_candidates_for_assignment_task
    #
    # NEW unified flow:
    # 1. Pipedrive syncs jobs (via pipedrive_sync_scheduler)
    # 2. Carmit routes jobs to agents (carmit_route_jobs_task)
    # 3. Agent performs matching (triggered by carmit or manual)
    # 4. Carmit reviews matches (carmit_review_matches_task)
    #
    "carmit-route-jobs-every-10-minutes": {
        "task": "pandapower.workers.tasks.carmit_route_jobs_task",
        "schedule": 600.0,  # Run every 10 minutes
    },
    "carmit-review-matches-every-15-minutes": {
        "task": "pandapower.workers.tasks.carmit_review_matches_task",
        "schedule": 900.0,  # Run every 15 minutes
    },
    # Carmit → Tal handoff: move carmit_approved matches into Tal's queue.
    # Cadence intentionally faster than review (10min vs 15min) so newly-
    # approved matches reach Tal within roughly one review cycle.
    "carmit-handoff-to-tal-every-10-minutes": {
        "task": "pandapower.workers.tasks.carmit_handoff_to_tal_task",
        "schedule": 600.0,
    },
    # Pipeline watchdog: re-kicks stuck matches so the pipeline self-heals
    # after worker restarts or transient crashes. See _pipeline_watchdog_async
    # for what "stuck" means.
    "pipeline-watchdog-every-30-minutes": {
        "task": "pandapower.workers.tasks.pipeline_watchdog_task",
        "schedule": 1800.0,
    },
    # NOTE: Pipedrive data sync (deals/persons/organizations) is NOT scheduled
    # at a fixed interval here. It is driven by user-defined settings in the
    # pipedrive_sync_schedule table - see "pipedrive-sync-scheduler-every-minute"
    # below.
    #
    # The following two run at fixed intervals because they handle Pipedrive
    # metadata (field definitions, historical reject reasons) - not the actual
    # entity data sync.
    "pipedrive-field-sync-every-hour": {
        "task": "pandapower.workers.tasks.pipedrive_field_sync_task",
        "schedule": 3600.0,  # Field-definition sync (custom fields, options) - 1 hour
    },
    "pipedrive-historical-import-every-4-hours": {
        "task": "pandapower.workers.tasks.pipedrive_historical_import_task",
        "schedule": 14400.0,  # Historical rejection reasons - 4 hours
    },
    # ------------------------------------------------------------------
    # User-driven Pipedrive sync scheduler:
    # Ticks every minute; consults pipedrive_sync_schedule table to decide
    # which entity sync should fire NOW based on user-defined settings
    # (sync_enabled, sync_interval_minutes, sync_days, sync_time, last_sync_at).
    # ------------------------------------------------------------------
    "pipedrive-sync-scheduler-every-minute": {
        "task": "pandapower.workers.tasks.pipedrive_sync_scheduler_task",
        "schedule": 60.0,  # Tick every minute - the task itself decides what (if anything) to run
    },
}

# Only register the beat schedule if explicitly enabled. By default it's empty,
# so a Celery worker (if ever started) acts purely as an on-demand task runner
# and does NOT compete with the in-process scheduler.
app.conf.beat_schedule = _beat_schedule if _enable_beat else {}

app.conf.timezone = "UTC"

# Task execution settings
if not _is_prod:
    # For development, execute tasks synchronously to avoid broker/worker coordination issues
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
else:
    # Production: use async workers with concurrency
    app.conf.worker_prefetch_multiplier = 4
    app.conf.worker_max_tasks_per_child = 1000
    app.conf.task_compression = "gzip"
    app.conf.result_expires = 3600  # Results expire after 1 hour

# Import tasks to register them
from pandapower.workers import tasks  # noqa: F401, E402
