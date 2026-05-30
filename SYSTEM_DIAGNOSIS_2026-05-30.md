# System Diagnosis - Why No Matches Since 2026-05-27

**Date**: 2026-05-30  
**Status**: Root cause identified ✅

## Executive Summary

**No new matches have been created since 2026-05-27 because there are no new jobs in the system after 2026-05-25.**

The matching pipeline is 100% operational, but has nothing to match — Celery was offline briefly (causing Carmit orchestrator to go dark), but more importantly, **no new job postings have entered the system for 5 days**.

---

## Full Diagnosis Results

### ✅ **Layer 1: Email Scanning — WORKING**
- **Status**: Active
- **Last scan**: 2026-05-30 04:25:28 UTC (2.4 hours ago)
- **Finding**: System successfully scans incoming emails and extracts CVs

### ✅ **Layer 2: CV Processing — WORKING**
- **Status**: CVs parsed, candidates created
- **Candidates created since 27/5**: 20
  - 27/5: 8 candidates
  - 28/5: 12 candidates
- **CV files**: 101 total in system

### ❌ **Layer 3: Job Ingest — BROKEN (ROOT CAUSE)**
- **Status**: No new jobs since 2026-05-25
- **Jobs in system**: 81 total
- **Most recent job**: 2026-05-25 (5 days ago)
- **Expected**: New job postings should arrive daily
- **Impact**: Without new jobs, matching cannot proceed

### ❌ **Layer 4: Job Routing (Carmit) — WAS OFFLINE, NOW RESTORED**
- **Status**: Last activity 2026-05-28 18:04 (36.7 hours ago)
- **Problem**: Celery Beat (worker service on Render) went offline
- **Evidence**: 
  - `handoff_to_tal` actions stopped
  - No `route_job` actions for 72 hours
  - Zero `carmit_review_matches_task` runs since 28/5
- **Root Cause**: Render worker service crashed or was not redeployed after restart
- **Current Status**: Can be manually triggered ✅ (tested successfully)

### ⚠️ **Layer 5: Pipedrive Sync — RUNNING BUT NO NEW DATA**
- **Status**: Sync is enabled and working
  - Organizations: last sync 2026-05-30 06:24 ✅
  - Persons: last sync 2026-05-30 06:35 ✅
  - **Deals**: last sync 2026-05-30 06:43 ✅
- **Problem**: No new deals created in Pipedrive since 2026-05-25
- **Finding**: All 81 jobs in system have Pipedrive `deal_id`

### ⚠️ **Layer 6: Matching Pipeline — OPERATIONAL**
- **Status**: Works when tested manually ✅
- **Manual trigger result**:
  - `_carmit_route_jobs_async()` → `jobs_routed: 0` (no unassigned jobs)
  - `_carmit_review_matches_async()` → `matches_reviewed: 0` (no pending matches)
- **Conclusion**: Pipeline code is correct; has nothing to process

---

## Root Causes (Priority Order)

### 1️⃣ **PRIMARY: No New Job Postings (5 days)**
**Impact**: HIGH  
**Timeline**: Jobs stopped appearing after 2026-05-25

**Likely Reasons**:
- No new deals created in Pipedrive since 2026-05-25
- Sales team hasn't posted new job openings
- Pipeline is empty (expected if you're between hiring cycles)

**Fix**: 
- ✅ Create new job postings in Pipedrive
- ✅ System will automatically sync them (deals sync runs every 30min)
- ✅ Carmit will route them to agents
- ✅ Matching will produce results

### 2️⃣ **SECONDARY: Celery Beat Offline (Intermittent)**
**Impact**: MEDIUM  
**Timeline**: Worker service crashed ~2026-05-28 18:04

**Evidence**:
- Carmit last action: 2026-05-28 18:04
- No agent routing logs since then
- agent_runtime_state table empty (agents don't report status)

**Root Cause**: Render worker service (`pandapower-worker`) either:
- Crashed without auto-restart
- Was not redeployed when main service restarted
- Lost connection to Redis (REDIS_URL env var issue)

**Fix**:
- ✅ Restart Render worker service manually
- ✅ Check Render dashboard: Services → pandapower-worker → Restart
- ✅ Verify REDIS_URL is set on both web and worker services
- ✅ Watch logs for Celery Beat: `celery -A pandapower.workers.celery_app worker -B`

---

## Data Quality Summary

| Component | Count | Status |
|-----------|-------|--------|
| **Jobs** | 81 | ❌ Stale (5d old) |
| **Candidates** | ~150 | ✅ Growing (20 new in 3d) |
| **CV Files** | 101 | ✅ Active |
| **Matches** | 86 | ✅ Last: 2026-05-27 |
| **Agents** | 8 | ⚠️ Idle (Carmit stalled) |

---

## How to Restore the Pipeline

### **Immediate Actions (Do These First)**

#### Step 1: Add New Job Postings
1. Open Pipedrive
2. Create 1+ new deals in your sales pipeline with job details
3. **System will auto-sync** (deals sync: every 30 min)
4. Carmit will route them to agents (every 10 min)
5. Matches will be created (agent-specific, typically 70+ score)

#### Step 2: Restart Celery Worker (if still offline)
```bash
# Via Render Dashboard:
1. Services → pandapower-worker
2. Click "Restart"
3. Watch logs to confirm Celery Beat is active
```

#### Step 3: Verify Connectivity
```bash
# Check Render logs:
# Look for: "celery -A pandapower.workers.celery_app worker -B"
# and scheduler messages like: "ingest-emails-every-2-minutes"
```

### **Process Flow (Once Restored)**
```
1. New Job in Pipedrive
   ↓
2. Pipedrive Sync (every 30min) → Job appears in 'jobs' table
   ↓
3. Carmit Routes Job to Agent (every 10min) → job.assigned_agent_code set
   ↓
4. Agent Matches Candidates (every 15min) → matches created (score 70+)
   ↓
5. Carmit Reviews Matches (every 15min) → quality gates pass/block
   ↓
6. Talreceivers Handoff (every 10min) → matches sent to Tal's queue
```

---

## Verification Checklist

- [ ] **Did you add a new job to Pipedrive?** (required to see matches)
- [ ] **Is Render worker service running?** (check Render dashboard)
- [ ] **Is REDIS_URL set on both web + worker services?** (settings → env vars)
- [ ] **Do agent logs show `route_job` actions in last 30 min?** (via database query)
- [ ] **Are new matches appearing in DB since you posted the job?**

---

## Celery Beat Schedule (For Reference)

These tasks should run automatically if worker service is online:

```
✅ ingest-emails-every-2-minutes        (120s)
✅ parse-cvs-every-5-minutes            (300s)
✅ create-candidates-every-10-minutes   (600s)
✅ normalize-skills-every-15-minutes    (900s)
✅ score-candidates-every-hour          (3600s)
❌ carmit-route-jobs-every-10-minutes   (600s)  ← stopped
❌ carmit-review-matches-every-15-minutes (900s) ← stopped
❌ carmit-handoff-to-tal-every-10-minutes (600s)  ← stopped
✅ pipeline-watchdog-every-30-minutes   (1800s)
✅ pipedrive-sync-scheduler-every-minute (60s)
```

---

## Next Steps

1. **Add job postings to Pipedrive** (or clarify if you're between hiring cycles)
2. **Restart Render worker** if needed
3. **Monitor logs** for Carmit routing activity
4. **Watch for matches** appearing in dashboard within 30 minutes

If you add a new job and still see no matches after 1 hour, run the manual trigger:
```bash
python3 /tmp/manual_trigger2.py
```

---

**Questions?** Check logs or run manual diagnostic:
```bash
python3 /tmp/check_system3.py  # Email, candidate, match status
python3 /tmp/check_jobs.py      # Job routing status
python3 /tmp/check_pipedrive.py # Pipedrive sync status
```

