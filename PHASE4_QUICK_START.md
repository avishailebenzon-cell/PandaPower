# Phase 4 Quick Start Guide

## What Was Built

Phase 4.2 creates the **sub-agent matching infrastructure** — the core matching logic that powers PandaPower's 7-agent system.

## Three Main Components

### 1. Agent Matching Worker
**File:** `/apps/backend/src/pandapower/workers/agent_matching.py`

The core business logic class that:
- Scores candidate-job pairs using Claude Sonnet
- Creates match records in the database
- Logs all agent activity for monitoring
- Returns match statistics and token usage

```python
worker = AgentMatchingWorker(supabase_client, claude_client)

# Entry point 1: Find candidates for a job
result = await worker.find_matches_for_job(job_id, "naama")
# Returns: {matches_found: 7, tokens_used: 3400, errors: []}

# Entry point 2: Find jobs for a candidate
result = await worker.find_matches_for_candidate(candidate_id, "alik")
# Returns: {matches_found: 2, tokens_used: 1200, errors: []}
```

### 2. Celery Tasks
**File:** `/apps/backend/src/pandapower/workers/tasks.py` (updated)

Two new async tasks for background job execution:

```python
# Trigger from code or admin interface
match_job_candidates_task.delay(job_id="abc-123", agent_code="naama")
match_candidate_jobs_task.delay(candidate_id="xyz-789", agent_code="alik")
```

### 3. Admin API Endpoints
**File:** `/apps/backend/src/pandapower/routers/admin/agent_matching.py`

REST API for:
- **Triggering matches** (POST /admin/agent-matching/match-job)
- **Viewing statistics** (GET /admin/agent-matching/agents/{code}/stats)
- **Monitoring matches** (GET /admin/agent-matching/matches/recent)
- **Agent configuration** (GET /admin/agent-matching/agents)

## How It Works

```
┌─────────────────┐
│  Admin triggers │
│  matching via   │
│  API endpoint   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│  AgentMatchingWorker:           │
│  find_matches_for_job()         │
│                                 │
│  1. Fetch job details           │
│  2. Load 100 candidates         │
│  3. For each candidate:         │
│     - Build scoring prompt      │
│     - Call Claude Sonnet        │
│     - Parse JSON response       │
│     - If score >= 70:           │
│       * Create match record     │
│       * Log to agent_logs       │
└────────┬────────────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
Supabase   Claude API
Database   (Scoring)
```

## Scoring Example

**Claude evaluates each pair:**

```
CANDIDATE: Alice Chen
- Skills: Python, AWS, Kubernetes, Docker
- Experience: 5 years backend engineer
- Clearance: None

JOB: Senior Python Developer
- Required Skills: Python, FastAPI, PostgreSQL, AWS
- Clearance: None

CLAUDE SONNET RESPONSE:
{
  "score": 82,
  "reasoning": "Strong Python & AWS background, but needs PostgreSQL and FastAPI skills",
  "strengths": ["5+ years Python", "AWS expert"],
  "gaps": ["No FastAPI", "No PostgreSQL"]
}
```

Score >= 70 → Match created!

## Key Features

### 1. Seven Specialized Agents
Each with curated domain keywords:

| Agent  | Domain             | Example Keywords |
|--------|-------------------|------------------|
| alik   | Electronics       | FPGA, VHDL, PCB  |
| naama  | Software & Cloud  | Python, K8s      |
| dganit | QA & Testing      | Selenium, pytest |
| ofir   | DevOps & Systems  | Linux, Docker    |
| itai   | IT & Infra        | Windows, AD      |
| lior   | Mechanical Eng    | CAD, FEA         |
| gc     | General/Catch-all | Any domain       |

### 2. Audit Logging
Every match creation logged to `agent_logs`:
```json
{
  "agent_code": "naama",
  "action": "find_match",
  "related_match_id": "uuid",
  "llm_model": "claude-sonnet-4",
  "tokens_used": 1234,
  "duration_ms": 2543,
  "status": "success"
}
```

### 3. Performance Monitoring
Admin can view:
- Total matches created per agent (7 days)
- Success rate (% successful runs)
- Token consumption (for cost tracking)
- Recent matches across all agents

## Testing the Implementation

### 1. Manually Trigger Job Matching
```bash
curl -X POST http://localhost:8000/admin/agent-matching/match-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "agent_code": "naama"
  }'
```

Expected response:
```json
{
  "status": "completed",
  "total_evaluated": 45,
  "matches_found": 7,
  "tokens_used": 3456,
  "duration_ms": 12543.0,
  "errors": []
}
```

### 2. View Agent Statistics
```bash
curl http://localhost:8000/admin/agent-matching/agents/naama/stats?days=7
```

Expected response:
```json
{
  "agent_code": "naama",
  "period_days": 7,
  "total_logs": 12,
  "successful_runs": 11,
  "failed_runs": 1,
  "total_tokens_used": 18234,
  "matches_created": 45,
  "success_rate": 0.917
}
```

### 3. List All Agents
```bash
curl http://localhost:8000/admin/agent-matching/agents
```

## Database Schema (Phase 4.1)

Two key tables:

### matches
```
id, candidate_id, job_id, match_score (0.0-1.0), 
match_reasoning, matched_by_agent_code, current_state, ...
```

### agent_logs
```
id, agent_code, action, related_match_id, 
input_payload (JSON), output_payload (JSON),
tokens_used, duration_ms, status, ...
```

## Integration with Existing Pipelines

Phase 4 **reuses** infrastructure from earlier phases:

- **Phase 8 (CV Parsing):** Provides candidate.key_skills via Claude API
- **Phase 9 (Candidate Creation):** Creates initial candidate records
- **Phase 10 (Skill Normalization):** Normalizes skill names for better matching
- **Pipedrive Sync:** Jobs come from Pipedrive deals

Phase 4 **adds:**
- Matching logic (this implementation)
- Match state machine (found → reviewed → proposed → hired)
- Agent activity audit trail

## Files Changed

### New Files
- `workers/agent_matching.py` (400+ lines) — Core matching worker
- `routers/admin/agent_matching.py` (400+ lines) — Admin API

### Modified Files
- `workers/tasks.py` — Added 2 Celery task wrappers
- `integrations/claude_api.py` — Added match_score_with_json() method
- `main.py` — Registered new router

### All files compile successfully ✓

## What's Next (Phase 4.3)

**Agent Triggers & Orchestration:**
- Automatically trigger matching when job assigned
- Automatically trigger matching when candidate ready
- Implement intelligent agent assignment (which agent owns which job/candidate)

This will move from manual admin-triggered matching to fully automated background processing.

## Configuration

No special configuration needed! Everything is built-in:
- Agent configs are in `AGENT_CONFIGS` dict in agent_matching.py
- Scoring thresholds are hardcoded (70 minimum)
- Token budgets are logged for monitoring

Just needs:
```
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

## Known Limitations

1. **Manual Triggering Only:** Admin must manually call /match-job endpoint
2. **No Skill Filtering:** Scores all candidates (optimization TBD)
3. **No Prompt Optimization:** Generic prompt used for all agents
4. **No Error Recovery:** Failed scores not automatically retried

All of these will be addressed in Phase 4.3 and 4.5.

---

**Ready to move to Phase 4.3 (Agent Triggers & Orchestration)**
