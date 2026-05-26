# 🐼 PandaPower Testing - START HERE

This document is your entry point for testing the complete PandaPower system. Follow the steps below to verify everything works correctly.

---

## What You're Testing

PandaPower is a complex recruitment system with 12 distinct phases:

```
CV Intake (Azure)
    ↓
Job Intake (Pipedrive)
    ↓
Agent Routing (Carmit)
    ↓
Agent Matching (7 agents)
    ↓
Carmit Review (5 quality gates)
    ↓
Tal Screening (WhatsApp)
    ↓
Elad Placement (Client outreach)
    ↓
Final Outcome (Hired or Failed)
```

We've built **4 health check endpoints** and a **test data generator** to monitor this entire flow.

---

## 5-Minute Quick Start

### Step 1: Verify Backend is Running

```bash
# Check if backend responds
curl http://localhost:8000/

# Expected response:
# {"message":"Welcome to PandaPower API"}
```

❌ **Backend not running?**
```bash
cd apps/backend
python3 -m uvicorn src.pandapower.main:app --reload
```

---

### Step 2: Check System Health

```bash
curl http://localhost:8000/admin/health | jq '.'
```

**What to look for:**
- `overall_status: "healthy"` ✅
- All components: `status: "healthy"` ✅
- All latencies < 500ms ✅

❌ **Health check failing?** See Troubleshooting section below.

---

### Step 3: Generate Test Data

```bash
cd apps/backend
python3 scripts/generate_test_data.py --verbose
```

**What you'll see:**
```
============================================================
✅ Test Data Generated Successfully!
============================================================

Created:
  - 5 Candidates
  - 5 Jobs
  - 5 Matches (in 'found' state)
  - 3 Organizations
  - 3 Agents

📊 Test Data Summary:
  Agent Code: naama
  First Candidate: מועמד 1 - David Cohen (ID: cand_abc123)
  First Job: Senior Python Developer (ID: job_def456)
  First Match: David Cohen → Senior Python Developer (ID: match_ghi789)
```

**Copy down these IDs** - you'll use them for testing!

---

### Step 4: Monitor the Pipeline

```bash
curl http://localhost:8000/admin/pipeline-status | jq '.'
```

**What you should see:**
- `total_matches: 5` (or your custom limit)
- Matches in "found" state
- `conversion_rate: 0` (not yet approved by Carmit)

---

### Step 5: Check Agents

```bash
curl http://localhost:8000/admin/agents/status | jq '.'
```

**What you should see:**
- 3 agents listed (naama, alik, dganit)
- `status: "idle"` (waiting for work)
- `matches_found > 0` for each agent

---

## 30-Minute Guided Testing

For more comprehensive testing, follow the **MONITORING_GUIDE.md**:

```bash
cat apps/backend/MONITORING_GUIDE.md
```

This guide shows you:
- ✅ Real-time monitoring with `watch` commands
- ✅ Multi-terminal setup for simultaneous visibility
- ✅ Diagnostic commands for troubleshooting
- ✅ Expected changes at each testing phase
- ✅ How to detect bottlenecks and issues

---

## The 4 Health Check Endpoints

### 1. System Health: `/admin/health`

```bash
curl http://localhost:8000/admin/health | jq '.overall_status'
```

**What it does:** Checks database connectivity and all system components.

**When to use:** Starting testing, diagnosing connection issues.

---

### 2. Pipeline Status: `/admin/pipeline-status`

```bash
curl http://localhost:8000/admin/pipeline-status | jq '{total: .total_matches, conversion: .conversion_rate, bottleneck: .bottleneck}'
```

**What it does:** Shows matches in each state, identifies bottlenecks, recommends next steps.

**When to use:** Monitoring workflow progress, identifying stuck matches.

---

### 3. Agents Status: `/admin/agents/status`

```bash
curl http://localhost:8000/admin/agents/status | jq '.agents[] | {name: .agent_name, approval_rate: .approval_rate, status: .status}'
```

**What it does:** Shows which agents are active, their approval rates, workload.

**When to use:** Monitoring agent activity, checking workload balance.

---

### 4. Match Journey: `/admin/matches/{id}/history`

```bash
# Replace with your match ID
curl http://localhost:8000/admin/matches/match_ghi789/history | jq '.stateHistory'
```

**What it does:** Shows complete journey of a single match through all states.

**When to use:** Debugging a specific match, verifying state transitions.

---

## Troubleshooting

### Problem: Backend not responding

```bash
# Check if backend is running
lsof -i :8000

# If nothing, start backend
cd apps/backend
python3 -m uvicorn src.pandapower.main:app --reload

# Check for Python errors
python3 -c "from pandapower.main import app; print('Backend OK')"
```

---

### Problem: Health check returns errors

```bash
# Check component details
curl http://localhost:8000/admin/health | jq '.components[] | select(.status == "error")'

# Common issues:
# 1. Database offline → Check SUPABASE_URL and SUPABASE_KEY in .env
# 2. Table doesn't exist → Run migrations: alembic upgrade head
# 3. Timeout → Database may be slow, try again
```

---

### Problem: Test data generator fails

```bash
# Check database connectivity
python3 -c "from pandapower.db.database import get_db; print('DB OK')"

# Try cleanup first
python3 scripts/generate_test_data.py --cleanup-only

# Then regenerate
python3 scripts/generate_test_data.py --verbose

# Check detailed error output
python3 scripts/generate_test_data.py --verbose 2>&1 | tail -20
```

---

### Problem: No matches in pipeline

```bash
# Check total matches
curl http://localhost:8000/admin/pipeline-status | jq '.total_matches'

# If 0:
# 1. Generate test data: python3 scripts/generate_test_data.py
# 2. Check if database was populated: SELECT COUNT(*) FROM matches;
# 3. Verify agent code is correct

# Check database directly
# SELECT count(*) FROM matches WHERE current_state = 'found';
```

---

## Next Steps After Quick Start

### Option 1: Run Full E2E Tests (1 hour)

```bash
# Read the complete testing guide
cat apps/backend/E2E_TESTING_GUIDE.md

# Run tests (if available)
python3 -m pytest tests/e2e/test_12_phases.py --verbose

# Monitor with dashboard
watch -n 2 'curl -s http://localhost:8000/admin/pipeline-status | jq "{total: .total_matches, conversion: .conversion_rate}"'
```

---

### Option 2: Manual Testing of Each Phase (2-3 hours)

```bash
# Phase 1: CV Intake
# Upload CV to Azure, verify it appears in candidates table

# Phase 2: Job Intake
# Upload job to Pipedrive, verify it appears in jobs table

# Phase 3: Agent Matching
# Check agents find matches:
curl http://localhost:8000/admin/pipeline-status | jq '.stages[] | select(.stage == "found")'

# Phase 4: Carmit Review
# Simulate Carmit approval (move matches to "carmit_approved" state)

# Phase 5: Tal Screening
# Simulate Tal conversation (move matches to "tal_conversation")

# And so on...
```

---

### Option 3: Continuous Monitoring (Real-time)

```bash
# Terminal 1: Start backend
cd apps/backend
python3 -m uvicorn src.pandapower.main:app --reload

# Terminal 2: Watch pipeline every 5 seconds
watch -n 5 'curl -s http://localhost:8000/admin/pipeline-status | jq .'

# Terminal 3: Watch agents every 3 seconds
watch -n 3 'curl -s http://localhost:8000/admin/agents/status | jq ".agents"'

# Terminal 4: Watch specific match
MATCH_ID="match_ghi789"
watch -n 2 "curl -s http://localhost:8000/admin/matches/$MATCH_ID/history | jq '.currentState'"
```

---

## Important Files

| File | Purpose | Read Time |
|------|---------|-----------|
| `MONITORING_GUIDE.md` | Complete monitoring reference with examples | 15 min |
| `E2E_TESTING_GUIDE.md` | 12-phase testing procedure with SQL queries | 30 min |
| `QUICK_START_TESTING.md` | Fast-track testing options | 5 min |
| `scripts/generate_test_data.py` | Test data generator script | N/A |
| `src/pandapower/routers/admin/health.py` | Health check endpoint code | N/A |

---

## Success Criteria

**After quick start (5 min), you should have:**
- ✅ Backend responding to health check
- ✅ Test data created (5+ matches)
- ✅ Pipeline status showing matches in "found" state
- ✅ Agents listed with activity

**After full testing (1-3 hours), you should have:**
- ✅ All 12 phases validated
- ✅ Matches flowing through complete state machine
- ✅ Final outcomes recorded (hired/failed)
- ✅ Conversion rate calculated and logged
- ✅ No bottlenecks or stuck matches

---

## Quick Reference: Key Metrics

### System Health
```bash
curl http://localhost:8000/admin/health | jq '.overall_status'
# Expected: "healthy"
```

### Total Matches
```bash
curl http://localhost:8000/admin/pipeline-status | jq '.total_matches'
# Expected: > 0
```

### Conversion Rate
```bash
curl http://localhost:8000/admin/pipeline-status | jq '.conversion_rate'
# Expected: 20-80% (depends on test configuration)
```

### Agent Approval Rate
```bash
curl http://localhost:8000/admin/agents/status | jq '.average_approval_rate'
# Expected: > 50%
```

### Bottleneck
```bash
curl http://localhost:8000/admin/pipeline-status | jq '.bottleneck'
# Expected: null or specific state name if slow
```

---

## Need Help?

### Check the logs:
```bash
# Backend logs (Terminal 1)
# Look for errors like "Database connection failed" or "Agent not found"

# Database logs:
# Check Supabase dashboard for query errors
```

### Run diagnostics:
```bash
# Health check with details
curl http://localhost:8000/admin/health | jq '.'

# Pipeline with recommendations
curl http://localhost:8000/admin/pipeline-status | jq '.recommendations'

# Specific agent details
curl http://localhost:8000/admin/agents/status | jq '.agents[0]'
```

### Read detailed guides:
- Pipeline bottlenecks → See MONITORING_GUIDE.md "Troubleshooting" section
- State transitions → See STATE_MACHINE.md
- Full test procedure → See E2E_TESTING_GUIDE.md

---

## Summary

🚀 **You're ready to test PandaPower!**

1. **5 minutes:** Run quick start steps above
2. **15 minutes:** Review MONITORING_GUIDE.md
3. **30+ minutes:** Run full E2E tests or manual testing
4. **Ongoing:** Use health check endpoints to monitor progress

The health check endpoints provide complete visibility into system behavior. Use them throughout testing to ensure everything flows smoothly from CV intake through final placement.

**Good luck! 🐼**
