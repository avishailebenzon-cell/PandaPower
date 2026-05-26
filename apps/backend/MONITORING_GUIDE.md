# PandaPower Monitoring & Testing Guide

## Overview

This guide explains how to monitor and test the complete PandaPower system using the health check endpoints and test data generator. The monitoring endpoints provide real-time visibility into system components, pipeline status, agent activity, and match journeys.

---

## Part 1: Quick Start Testing (5 Minutes)

### Option 1: One Command Setup & Test

```bash
# 1. Generate test data
cd apps/backend
python3 scripts/generate_test_data.py --limit 3 --verbose

# 2. Check system health (all components)
curl http://localhost:8000/admin/health | jq

# 3. Check pipeline status
curl http://localhost:8000/admin/pipeline-status | jq

# 4. Check agents status
curl http://localhost:8000/admin/agents/status | jq
```

### Option 2: Watch System in Real-Time (30 seconds)

```bash
# Terminal 1: Watch pipeline status every 2 seconds
watch -n 2 'curl -s http://localhost:8000/admin/pipeline-status | jq .'

# Terminal 2: In another terminal, watch agent status
watch -n 3 'curl -s http://localhost:8000/admin/agents/status | jq .'

# Terminal 3: Check specific match journey
MATCH_ID="<from-generated-test-data>"
curl http://localhost:8000/admin/matches/$MATCH_ID/history | jq
```

---

## Part 2: Health Check Endpoints Reference

### 1. System Health Check

**Endpoint:** `GET /admin/health`

**What it checks:**
- Database connectivity
- Match state history table
- Jobs table
- Candidates table
- Agent logs table

**Response:**
```json
{
  "overall_status": "healthy",
  "timestamp": "2026-05-23T14:30:00.000Z",
  "components": [
    {
      "name": "Database",
      "status": "healthy",
      "message": "Connected to Supabase",
      "timestamp": "2026-05-23T14:30:00.000Z",
      "latency_ms": 45.2
    },
    {
      "name": "Match State History",
      "status": "healthy",
      "message": "Found 127 state history records",
      "timestamp": "2026-05-23T14:30:00.000Z",
      "latency_ms": 23.1
    }
    // ... more components
  ],
  "summary": "All systems operational"
}
```

**Use when:**
- Starting system tests (verify all components are ready)
- Diagnosing connection issues
- Checking database latency

**Success criteria:**
- All components: `status == "healthy"`
- `overall_status == "healthy"`
- All latencies < 500ms

---

### 2. Pipeline Status

**Endpoint:** `GET /admin/pipeline-status`

**What it shows:**
- Matches in each state (found, carmit_approved, sent_to_tal, etc.)
- Percentage distribution across states
- Average wait time in each state
- Conversion rate (hired / total)
- Bottleneck identification
- Recommendations

**Response:**
```json
{
  "timestamp": "2026-05-23T14:30:00.000Z",
  "total_matches": 150,
  "stages": [
    {
      "stage": "found",
      "stage_label": "התאמה נמצאה",
      "count": 45,
      "percentage": 30.0,
      "avg_wait_time_hours": 2.3
    },
    {
      "stage": "carmit_approved",
      "stage_label": "אושרה על ידי כרמית",
      "count": 28,
      "percentage": 18.7,
      "avg_wait_time_hours": 0.5
    },
    {
      "stage": "sent_to_tal",
      "stage_label": "הועברה לטל",
      "count": 15,
      "percentage": 10.0,
      "avg_wait_time_hours": 4.2
    },
    // ... more stages
  ],
  "conversion_rate": 35.2,
  "bottleneck": "sent_to_tal",
  "recommendations": [
    "⚠️ Bottleneck at 'sent_to_tal' - 4.2 hours average wait",
    "👥 High Tal queue (15 matches) - may need additional capacity"
  ]
}
```

**Use when:**
- Checking overall system health
- Identifying bottlenecks in the workflow
- Monitoring conversion rates
- Validating state transitions are working

**Success criteria:**
- All stages have `count >= 0`
- `conversion_rate > 20%` (minimum acceptable)
- No stuck matches in "found" state >24h
- Bottleneck recommendation if any

---

### 3. Agents Status

**Endpoint:** `GET /admin/agents/status`

**What it shows:**
- Active agents with match counts
- Approval rate per agent
- Recent activity timestamps
- Agent status (active/idle/no_recent_activity)
- Most active agent
- Total matches today
- Average approval rate

**Response:**
```json
{
  "timestamp": "2026-05-23T14:30:00.000Z",
  "agents": [
    {
      "agent_code": "naama",
      "agent_name": "Naama",
      "matches_found": 45,
      "matches_approved": 32,
      "approval_rate": 71.1,
      "recent_activity": "2026-05-23T14:25:00.000Z",
      "status": "active"
    },
    {
      "agent_code": "alik",
      "agent_name": "Alik",
      "matches_found": 38,
      "matches_approved": 24,
      "approval_rate": 63.2,
      "recent_activity": "2026-05-23T14:20:00.000Z",
      "status": "active"
    }
    // ... more agents
  ],
  "most_active_agent": "naama",
  "total_matches_today": 12,
  "average_approval_rate": 67.1
}
```

**Use when:**
- Monitoring agent workload distribution
- Identifying underperforming agents
- Checking which agents are active
- Verifying agent activity log recording

**Success criteria:**
- All agents: `status in ["active", "idle"]`
- All agents: `approval_rate > 50%`
- Most active agent has recent activity
- No agent status is "no_recent_activity" during testing

---

### 4. Match History & Journey

**Endpoint:** `GET /admin/matches/{match_id}/history`

**What it shows:**
- Complete state history for a match
- Current state
- All state transitions with timestamps
- State details (gate results, reasoning, etc.)

**Response:**
```json
{
  "matchId": "match_123",
  "candidateName": "David Cohen",
  "jobTitle": "Senior Python Developer",
  "currentState": "sent_to_tal",
  "stateHistory": [
    {
      "from_state": null,
      "to_state": "found",
      "created_at": "2026-05-23T12:00:00.000Z",
      "details": {
        "agent_code": "naama",
        "match_score": 0.82,
        "reason": "Agent found this match"
      }
    },
    {
      "from_state": "found",
      "to_state": "carmit_approved",
      "created_at": "2026-05-23T12:15:00.000Z",
      "details": {
        "gate_results": {
          "past_rejection": {"passed": true},
          "already_declined": {"passed": true},
          "conflict_of_interest": {"passed": true},
          "clearance_match": {"passed": true},
          "quality_threshold": {"passed": true, "score": 0.82, "threshold": 0.70}
        },
        "decision": "approved",
        "reasoning": "All gates passed"
      }
    },
    {
      "from_state": "carmit_approved",
      "to_state": "sent_to_tal",
      "created_at": "2026-05-23T12:20:00.000Z",
      "details": {
        "recruiter": "tal",
        "reason": "Ready for candidate screening"
      }
    }
  ]
}
```

**Use when:**
- Debugging a specific match journey
- Verifying state transitions are recorded correctly
- Checking gate results and reasoning
- Validating timestamp accuracy

**Success criteria:**
- All transitions recorded with timestamps
- Gate results present for Carmit decisions
- No gaps in state history
- Timestamps increase monotonically

---

## Part 3: Using Test Data Generator

### Generate Test Data

```bash
# Basic generation (5 candidates, 5 jobs, 5 matches)
cd apps/backend
python3 scripts/generate_test_data.py

# Verbose output (helpful for debugging)
python3 scripts/generate_test_data.py --verbose

# Custom limit (e.g., 10 candidates)
python3 scripts/generate_test_data.py --limit 10

# Cleanup only (reset database)
python3 scripts/generate_test_data.py --cleanup-only
```

### Generator Output

The generator provides:
1. **Summary:** Count of created resources (candidates, jobs, matches, agents, organizations)
2. **Quick Start IDs:** First candidate, job, match IDs for manual testing
3. **Quick Test Commands:** Pre-formatted curl commands to immediately test APIs

Example output:
```
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

📋 Quick Test Commands:
1. Check match history:
   curl http://localhost:8000/api/admin/matches/match_ghi789/history

2. Check pipeline status:
   curl http://localhost:8000/admin/pipeline-status

3. Check system health:
   curl http://localhost:8000/admin/health

4. Check agents status:
   curl http://localhost:8000/admin/agents/status
```

---

## Part 4: Complete Monitoring Workflow

### Pre-Testing Checklist

```bash
# 1. Verify backend is running
curl http://localhost:8000/ | jq

# 2. Check system health
curl http://localhost:8000/admin/health | jq '.overall_status'
# Expected: "healthy"

# 3. Generate test data
python3 scripts/generate_test_data.py --verbose

# 4. Verify test data created
curl http://localhost:8000/admin/pipeline-status | jq '.total_matches'
# Expected: > 0

# 5. Check agents are loaded
curl http://localhost:8000/admin/agents/status | jq '.agents | length'
# Expected: > 0
```

### During Testing: Real-Time Monitoring

**Terminal 1: Backend logs**
```bash
cd apps/backend
python3 -m uvicorn src.pandapower.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2: Pipeline dashboard**
```bash
# Refresh every 5 seconds
watch -n 5 'echo "=== PIPELINE STATUS ===" && curl -s http://localhost:8000/admin/pipeline-status | jq "{total: .total_matches, conversion: .conversion_rate, bottleneck: .bottleneck}"'
```

**Terminal 3: Agent dashboard**
```bash
# Refresh every 3 seconds
watch -n 3 'echo "=== AGENTS STATUS ===" && curl -s http://localhost:8000/admin/agents/status | jq "{agents: (.agents | length), active: (.agents | map(select(.status == "active")) | length), avg_approval: .average_approval_rate}"'
```

**Terminal 4: Match tracking**
```bash
# Track specific match (replace MATCH_ID)
MATCH_ID="match_ghi789"
watch -n 2 "echo '=== MATCH JOURNEY ===' && curl -s http://localhost:8000/admin/matches/$MATCH_ID/history | jq '{currentState: .currentState, transitions: (.stateHistory | length)}'"
```

### Expected Changes During Testing

As you progress through the 12 testing phases:

1. **Phase 1-3: CV & Job Intake**
   - Database components: healthy ✅
   - Candidates/Jobs counts increase ✅

2. **Phase 4-5: Agent Matching**
   - Matches appear in "found" state
   - Agent activity increases
   - Agent status changes to "active"

3. **Phase 6: Carmit Review**
   - Matches transition from "found" → "carmit_approved" or "carmit_rejected"
   - Gate results appear in state history
   - Conversion rate increases

4. **Phase 7-8: Tal Screening**
   - Matches move to "sent_to_tal" → "tal_conversation"
   - Tal activity in agent logs
   - Bottleneck may appear at "tal_conversation" (normal)

5. **Phase 9-11: Elad Placement**
   - Matches move to "sent_to_elad" → "offer_sent"
   - Final outcomes recorded (hired/placement_failed)
   - Conversion rate should stabilize

---

## Part 5: Diagnostic Commands

### Database Health

```bash
# Check Supabase connection
curl -X POST https://your-supabase-project.supabase.co/rest/v1/rpc/pg_stat_activity \
  -H "Authorization: Bearer $SUPABASE_KEY"

# Check table record counts (via API)
for table in candidates jobs matches agents; do
  echo "$table: $(curl -s http://localhost:8000/admin/health | jq ".components[] | select(.name == \"${table^}\") | .message")"
done
```

### Pipeline Health

```bash
# Show stuck matches (in "found" state for >24 hours)
curl -s http://localhost:8000/admin/pipeline-status | jq '.recommendations[] | select(. | contains("stalled"))'

# Show high Tal queue
curl -s http://localhost:8000/admin/pipeline-status | jq '.recommendations[] | select(. | contains("Tal queue"))'

# Get conversion rate
curl -s http://localhost:8000/admin/pipeline-status | jq '.conversion_rate'
```

### Agent Health

```bash
# Agents sorted by approval rate (descending)
curl -s http://localhost:8000/admin/agents/status | jq '.agents | sort_by(.approval_rate) | reverse | .[] | {name, approval_rate, matches_found}'

# Find idle agents
curl -s http://localhost:8000/admin/agents/status | jq '.agents[] | select(.status == "idle")'

# Total workload
curl -s http://localhost:8000/admin/agents/status | jq '[.agents[].matches_found] | add'
```

---

## Part 6: Troubleshooting

### System Health Issues

**Problem:** Component status is "error"

```bash
# Check specific component
curl -s http://localhost:8000/admin/health | jq '.components[] | select(.status == "error")'

# Common fixes:
# 1. Database connection: Check SUPABASE_URL and SUPABASE_KEY
# 2. Tables missing: Run migrations: alembic upgrade head
# 3. Timeout: Database may be slow - increase timeout or check network
```

### Pipeline Bottlenecks

**Problem:** Matches stuck at "sent_to_tal"

```bash
# Verify Tal is receiving matches
curl -s http://localhost:8000/admin/pipeline-status | jq '.stages[] | select(.stage == "sent_to_tal")'

# Check Tal agent activity
curl -s http://localhost:8000/admin/agents/status | jq '.agents[] | select(.agent_code == "tal")'

# Possible causes:
# - Tal agent is idle (not pulling matches)
# - WhatsApp integration not working
# - Candidate not responding
```

### Test Data Issues

**Problem:** Test data generator fails

```bash
# Check database connectivity first
python3 -c "from pandapower.db.database import get_db; print('Database OK')"

# Cleanup and retry
python3 scripts/generate_test_data.py --cleanup-only
python3 scripts/generate_test_data.py --verbose

# Check logs for specific error
# Look for detailed error messages in verbose output
```

---

## Part 7: Integration with E2E Tests

### Running Tests with Monitoring

```bash
# Terminal 1: Start backend
cd apps/backend && python3 -m uvicorn src.pandapower.main:app --reload

# Terminal 2: Run E2E tests
cd ../.. && python3 -m pytest tests/e2e/test_12_phases.py --verbose

# Terminal 3: Monitor in parallel
watch -n 2 'curl -s http://localhost:8000/admin/pipeline-status | jq ".conversion_rate"'
```

### Expected Test Results

```bash
# All 12 phases should complete successfully
pytest tests/e2e/test_12_phases.py -v

# Final state: All matches in terminal states (hired, placement_failed, rejected)
curl -s http://localhost:8000/admin/pipeline-status | jq '.stages[] | select(.stage | contains("hired", "failed"))'

# Conversion rate should be measurable
curl -s http://localhost:8000/admin/pipeline-status | jq '.conversion_rate'
# Expected: 20-80% range depending on configuration
```

---

## Summary

This monitoring guide provides:

✅ **System Health Checks** - Verify all components are working  
✅ **Pipeline Visibility** - See matches flow through states  
✅ **Agent Monitoring** - Track agent activity and performance  
✅ **Match Tracking** - Follow individual match journeys  
✅ **Test Data Generation** - Create realistic test scenarios  
✅ **Diagnostic Commands** - Troubleshoot issues quickly  

Use these tools throughout testing to ensure the complete 12-phase workflow is operating correctly. The health check endpoints provide real-time visibility into system behavior as you move through each testing phase.
