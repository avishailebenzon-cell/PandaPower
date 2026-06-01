# System Reliability — How the automation stays running 24/7

This document explains how PandaPower guarantees that **all** automated processes
run continuously, and how to confirm at a glance that they are.

## The model: one always-on scheduler

Every recurring process runs inside a **single in-process scheduler** that lives
in the always-on web service:

`apps/backend/src/pandapower/main.py` → `_pipeline_scheduler_loop()`

Render keeps the web service alive via the `/health` check, so **as long as the
API is up, the automation is running**. There is no separate worker that can
silently die.

### Why we did this

Previously the **matching pipeline** (Carmit → Tal) ran only in a separate
Celery Beat worker. If that worker crashed, or `REDIS_URL` was missing, the
matching side stopped **silently** while email intake kept going — so jobs
stopped being routed and matches stopped being handled, and nobody noticed for
hours. Two of those tasks (`carmit_route_jobs`, `carmit_review_matches`) are not
idempotent, so we also couldn't safely run them in two places at once.

**Fix:** consolidate everything onto the always-on web-service scheduler and
retire the Celery beat (see `render.yaml` and `workers/celery_app.py`, now gated
behind `ENABLE_CELERY_BEAT`, default off).

## The processes and their cadence

| Stage | Interval | What it does |
|---|---|---|
| `ingest` | 2 min | Poll Outlook, save CV attachments |
| `parse` | 3 min | Extract text + Claude CV analysis |
| `candidates` | 4 min | Create candidate records |
| `skills` | 10 min | Normalize raw skills → canonical |
| `score` | 1 h | Score candidate readiness |
| `carmit_route_jobs` | 10 min | Route open jobs to agents (Opus) |
| `carmit_review_matches` | 15 min | Carmit approves/rejects found matches |
| `carmit_handoff_to_tal` | 10 min | Move approved matches into Tal's queue |
| `pipeline_watchdog` | 30 min | Re-kick matches stuck past threshold (self-healing) |
| `pipedrive_field_sync` | 1 h | Sync custom-field definitions |
| `pipedrive_historical_import` | 4 h | Import historical rejection reasons |
| Pipedrive entity sync | 1 min tick | User-configured deals/persons/orgs sync |

Each stage runs independently, skips silently if its prerequisites aren't
configured, and a failure in one never blocks the others.

## How you SEE that everything works

### Dashboard
Admin sidebar → **🩺 ניטור מערכת** (`/admin/system-health`).
Shows every process with: last-run time, status badge (פעיל / תקוע / כשל),
expected interval, and consecutive-failure count. Auto-refreshes every 15s.

### API
`GET /admin/system/heartbeat` returns real per-task health. A task is flagged
`is_stalled: true` when its last run is older than **2× its expected interval**.

### Persistence
Every run writes a row to the `scheduler_heartbeats` table (migration
`20260601000001`). This survives restarts, so a stall is detectable after the
fact — not just lost in memory.

### Alerts
If a stage fails/crashes **3 times in a row**, an email goes to the admin
(`avishai.lebenzon@gmail.com`) via the existing `alert_admin` service (Resend),
with a 30-min cooldown per stage. The alert auto-clears when the stage recovers.

## Operational notes

- **Keep the web service at `--workers 1`** (it already is in `render.yaml`).
  The scheduler must run in exactly one process. If you ever scale web workers
  up, gate the loop with a Postgres advisory lock so the non-idempotent matching
  stages don't double-run. `SCHEDULER_ENABLED=false` disables the loop entirely.
- **Do NOT set `ENABLE_CELERY_BEAT=true`** while the in-process scheduler runs —
  that would double-run matching tasks.
- The `scheduler_heartbeats` migration must be applied once
  (`apps/backend/scripts/apply_single_migration.py`). Until then the dashboard
  shows every task as "stalled / never run" (it degrades gracefully, no errors).

## Quick verification checklist

1. `curl https://pandapower-backend.onrender.com/health` → `{"status":"ok"}`
2. `curl https://pandapower-backend.onrender.com/admin/system/heartbeat` → every
   task present, recent `last_run_at`, `is_stalled:false`, `overall_status:"healthy"`.
3. Open **🩺 ניטור מערכת** in the admin UI → all rows green.
4. `curl .../admin/pipeline-status` → real match-state counts (no mock text).
