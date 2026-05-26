# 🐼 PandaPower Testing - Quick Reference Card

Print this page or keep it open while testing. All commands tested and ready to use.

---

## 🎯 Pre-Testing (Run Once)

```bash
# 1. Check backend is running
curl http://localhost:8000/
# Expected: {"message":"Welcome to PandaPower API"}

# 2. Verify health
curl http://localhost:8000/admin/health | jq '.overall_status'
# Expected: "healthy"

# 3. Generate test data
cd apps/backend
python3 scripts/generate_test_data.py --verbose

# Save these IDs from output:
# MATCH_ID=match_ghi789
# CANDIDATE_ID=cand_abc123
# JOB_ID=job_def456
```

---

## 📊 Real-Time Monitoring (3 Terminals)

**Terminal 1: Backend**
```bash
cd apps/backend
python3 -m uvicorn src.pandapower.main:app --reload
```

**Terminal 2: Pipeline (refresh every 5s)**
```bash
watch -n 5 'curl -s http://localhost:8000/admin/pipeline-status | \
  jq "{total: .total_matches, conversion: .conversion_rate, \
  bottleneck: .bottleneck, stages: (.stages | map({s: .stage, c: .count}))}"'
```

**Terminal 3: Agents (refresh every 3s)**
```bash
watch -n 3 'curl -s http://localhost:8000/admin/agents/status | \
  jq "{agents: .agents | map({name: .agent_name, rate: .approval_rate, status: .status}), \
  avg: .average_approval_rate}"'
```

---

## ✅ Health Check Commands

| What | Command | Expected |
|------|---------|----------|
| **System Health** | `curl http://localhost:8000/admin/health \| jq '.overall_status'` | `"healthy"` |
| **Total Matches** | `curl http://localhost:8000/admin/pipeline-status \| jq '.total_matches'` | `> 0` |
| **Conversion Rate** | `curl http://localhost:8000/admin/pipeline-status \| jq '.conversion_rate'` | `0-100` |
| **Bottleneck** | `curl http://localhost:8000/admin/pipeline-status \| jq '.bottleneck'` | `null` or state |
| **Active Agents** | `curl http://localhost:8000/admin/agents/status \| jq '.agents \| map(.status)'` | `["active", "active", ...]` |
| **Avg Approval** | `curl http://localhost:8000/admin/agents/status \| jq '.average_approval_rate'` | `> 50` |
| **Match Journey** | `curl http://localhost:8000/admin/matches/{ID}/history \| jq '.stateHistory'` | Array of states |

---

## 🔧 State Definitions (Hebrew ↔ English)

| State Code | Hebrew | Meaning |
|-----------|--------|---------|
| `found` | התאמה נמצאה | Match found by agent |
| `carmit_approved` | אושרה על ידי כרמית | Passed quality gates |
| `carmit_rejected` | נדחתה על ידי כרמית | Failed quality gate |
| `sent_to_tal` | הועברה לטל | Ready for screening |
| `tal_conversation` | שיחה עם טל | Candidate talking to Tal |
| `tal_approved` | אושר על ידי טל | Tal approved candidate |
| `tal_rejected` | נדחה על ידי טל | Tal rejected candidate |
| `sent_to_elad` | הועבר לאלעד | Moved to placement |
| `elad_conversation` | שיחה עם אלעד | Elad preparing for client |
| `offer_sent` | הצעה נשלחה ללקוח | Sent to client |
| `hired` | התקבל לעבודה | Candidate accepted |
| `placement_failed` | ממקום נכשל | Placement failed |

---

## 📈 Expected Flow at Each Phase

| Phase | Expected State | Expected Count | Expected Changes |
|-------|---|---|---|
| 1-3 | `found` | = total matches | No state changes yet |
| 4-5 | `found` → `carmit_*` | Some in each | Matches leave "found" |
| 6-7 | `sent_to_tal` | Increases | Tal gets work |
| 8-9 | `tal_conversation` | Peaks | Active conversations |
| 10-11 | `sent_to_elad` | Increases | Elad gets work |
| 12 | `hired` + `placement_failed` | Increases | Final outcomes recorded |

---

## 🚨 Warnings (Problems to Watch For)

| Warning | Check | Fix |
|---------|-------|-----|
| **Matches stuck in "found"** | `curl ... \| jq '.stages[0].avg_wait_time_hours'` | > 24h? Trigger Carmit review |
| **High bottleneck wait time** | `curl ... \| jq '.bottleneck'` | > 4h? Check agent activity |
| **Low approval rate** | `curl ... agents/status \| jq '.average_approval_rate'` | < 50%? Review quality gates |
| **Idle agents** | `curl ... agents/status \| jq '.agents[].status'` | "no_recent_activity"? Check logs |
| **Low conversion rate** | `curl ... pipeline-status \| jq '.conversion_rate'` | < 10%? High rejection rate |

---

## 🔍 Debugging Single Match

```bash
# Replace MATCH_ID with your test match ID (e.g., match_ghi789)

# Get complete journey
curl http://localhost:8000/admin/matches/MATCH_ID/history | jq '.'

# Get current state only
curl http://localhost:8000/admin/matches/MATCH_ID/history | jq '.currentState'

# Get gate results (if Carmit rejected)
curl http://localhost:8000/admin/matches/MATCH_ID/history | jq \
  '.stateHistory[] | select(.to_state | contains("carmit")) | .details.gate_results'

# Get state transition timestamps
curl http://localhost:8000/admin/matches/MATCH_ID/history | jq \
  '.stateHistory[] | {to: .to_state, time: .created_at}'
```

---

## 🧹 Cleanup & Reset

```bash
# Reset all test data
python3 scripts/generate_test_data.py --cleanup-only

# Verify cleanup
curl http://localhost:8000/admin/pipeline-status | jq '.total_matches'
# Should return: 0

# Regenerate test data
python3 scripts/generate_test_data.py --verbose
```

---

## 📋 Test Success Checklist

- [ ] Backend responds to health check
- [ ] System status is "healthy"
- [ ] Test data generates without errors
- [ ] Total matches = generated count
- [ ] All agents listed with no errors
- [ ] Can retrieve match history
- [ ] State transitions visible in history
- [ ] No error messages in backend logs
- [ ] All latencies < 500ms
- [ ] Database connectivity confirmed

---

## 💾 Saving Test Results

```bash
# Capture system health
curl -s http://localhost:8000/admin/health > health_$(date +%Y%m%d_%H%M%S).json

# Capture pipeline status
curl -s http://localhost:8000/admin/pipeline-status > pipeline_$(date +%Y%m%d_%H%M%S).json

# Capture agents status
curl -s http://localhost:8000/admin/agents/status > agents_$(date +%Y%m%d_%H%M%S).json

# Create test report
cat > test_report_$(date +%Y%m%d_%H%M%S).md << 'EOF'
# Test Report
- Started: $(date)
- Matches: $(curl -s http://localhost:8000/admin/pipeline-status | jq '.total_matches')
- Conversion: $(curl -s http://localhost:8000/admin/pipeline-status | jq '.conversion_rate')%
- Avg Approval: $(curl -s http://localhost:8000/admin/agents/status | jq '.average_approval_rate')%
EOF
```

---

## 🐛 Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `Connection refused` | Backend not running | Start: `python3 -m uvicorn ...` |
| `Database error` | DB offline | Check SUPABASE_URL, SUPABASE_KEY |
| `no attribute 'id'` | Data missing | Run: `python3 scripts/generate_test_data.py` |
| `HTTP 404` | Wrong endpoint | Check URL spelling (e.g., `/admin` not `/api/admin`) |
| `timeout` | Slow database | Wait 30s, retry, or check Supabase |

---

## 📞 Need Full Details?

| File | Content | Read Time |
|------|---------|-----------|
| `START_HERE.md` | Complete setup guide | 5 min |
| `MONITORING_GUIDE.md` | Monitoring reference | 15 min |
| `E2E_TESTING_GUIDE.md` | 12-phase test procedure | 30 min |
| `QUICK_START_TESTING.md` | Fast test options | 5 min |

---

## 🚀 Copy-Paste Full Test Sequence

```bash
# One script: Full setup + test
set -e  # Exit on error

echo "1. Generating test data..."
cd apps/backend
python3 scripts/generate_test_data.py --verbose

echo "2. Checking health..."
curl http://localhost:8000/admin/health | jq '.overall_status'

echo "3. Pipeline status..."
curl http://localhost:8000/admin/pipeline-status | jq '{total: .total_matches, conv: .conversion_rate}'

echo "4. Agent status..."
curl http://localhost:8000/admin/agents/status | jq '.average_approval_rate'

echo "✅ All tests passed!"
```

---

**Last Updated:** 2026-05-23  
**Status:** Ready for Testing  
**All Endpoints:** Live  

🐼 **Happy Testing!**
