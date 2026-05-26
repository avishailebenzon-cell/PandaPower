# Phase 4: Sub-Agent Matching Implementation

## Overview

Phase 4 creates the infrastructure for candidate-job matching using 7 specialized agents. Each agent focuses on a specific technical domain and uses Claude Sonnet for scoring matches.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Admin API Endpoints                         │
│  /admin/agent-matching/*                                        │
│  - Trigger matching for jobs/candidates                         │
│  - View agent statistics                                        │
│  - Monitor recent matches                                       │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              AgentMatchingWorker (Core Logic)                   │
│  - find_matches_for_job(job_id, agent_code)                    │
│  - find_matches_for_candidate(candidate_id, agent_code)        │
│  - _score_candidate_job_pair() → Claude Sonnet                 │
└─────────────────────────────────────────────────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
        ┌─────────────────────┐  ┌──────────────────┐
        │  Supabase Database  │  │  Claude API      │
        │  - matches          │  │  (Claude Sonnet) │
        │  - agent_logs       │  │  Score: 0-100    │
        │  - candidates       │  │  JSON parsing    │
        │  - jobs             │  └──────────────────┘
        └─────────────────────┘
```

## Key Components

### 1. Core Worker: `agent_matching.py`

**Class:** `AgentMatchingWorker`

#### Entry Point 1: Job → Candidates
```python
async def find_matches_for_job(job_id, agent_code) -> dict:
    """Find candidates matching a job assigned to agent."""
    - Fetches job details from DB
    - Loads all active candidates (100 limit per run)
    - Scores each candidate against job using Claude
    - Creates matches with score >= 70
    - Logs all activity to agent_logs table
```

#### Entry Point 2: Candidate → Jobs
```python
async def find_matches_for_candidate(candidate_id, agent_code) -> dict:
    """Find jobs matching a candidate assigned to agent."""
    - Fetches candidate details from DB
    - Loads open jobs from DB
    - Scores candidate against each job
    - Creates matches with score >= 70
    - Logs all activity
```

#### Scoring Method
```python
async def _score_candidate_job_pair(candidate, job, agent_code, config):
    """Use Claude Sonnet to score a match."""
    - Builds context-aware prompt
    - Calls Claude Sonnet model
    - Returns: {
        score: 0-100,
        reasoning: str,
        strengths: [str],
        gaps: [str],
        tokens_used: int,
        duration_ms: float
      }
```

### 2. Celery Tasks: `tasks.py` Updates

Two new async tasks added:

```python
@app.task
def match_job_candidates_task(job_id: str, agent_code: str):
    """Trigger matching for a job via Celery."""
    # Async wrapper for AgentMatchingWorker.find_matches_for_job()

@app.task
def match_candidate_jobs_task(candidate_id: str, agent_code: str):
    """Trigger matching for a candidate via Celery."""
    # Async wrapper for AgentMatchingWorker.find_matches_for_candidate()
```

### 3. Admin API Endpoints: `admin/agent_matching.py`

**Router Prefix:** `/admin/agent-matching`

#### Agent Configuration Endpoints
- `GET /agents` → List all 7 agents
- `GET /agents/{code}` → Get agent details

#### Matching Control Endpoints
- `POST /match-job` → Trigger matching for a job
  - Input: `{job_id, agent_code}`
  - Output: Matches found, tokens used, errors
  
- `POST /match-candidate` → Trigger matching for a candidate
  - Input: `{candidate_id, agent_code}`
  - Output: Matches found, tokens used, errors

#### Monitoring Endpoints
- `GET /agents/{code}/stats?days=7` → Agent statistics
  - Total logs, success rate, tokens used, matches created
  
- `GET /matches/recent?limit=50` → Recent matches from all agents
  
- `GET /matches/by-agent/{code}?limit=20` → Matches by specific agent

### 4. Claude API Extension: `claude_api.py`

New method added:
```python
async def match_score_with_json(prompt: str, model: str = "claude-sonnet-4"):
    """Score a candidate-job match and return JSON."""
    - Calls Claude with JSON response format
    - Parses JSON response
    - Returns: {parsed: {...}, tokens_used: int}
```

## Agent Configurations

Each agent specializes in a domain and has curated keywords:

| Code    | Name    | Domain                | Keywords                                    |
|---------|---------|----------------------|---------------------------------------------|
| alik    | Alik    | Electronics          | Verilog, VHDL, FPGA, PCB, RF, Analog       |
| naama   | Naama   | Software & Cloud     | Python, Java, C++, Cloud, Microservices    |
| dganit  | Dganit  | QA & Testing         | Testing, Selenium, LoadRunner, Automation  |
| ofir    | Ofir    | Systems & DevOps     | Linux, Networking, DevOps, Container       |
| itai    | Itai    | IT & Infrastructure  | Infrastructure, Windows, Helpdesk, Networks|
| lior    | Lior    | Mechanical Engineering| CAD, SOLIDWORKS, FEA, Manufacturing         |
| gc      | GC      | General/Catch-all    | Any domain not covered by specialists      |

## Database Integration

### Tables Used
- **matches**: Stores candidate-job pairs with scores
  - `match_score`: 0.0-1.0 (normalized)
  - `match_reasoning`: LLM reasoning
  - `matched_by_agent_code`: Which agent created
  - `current_state`: Finite state (found → reviewed → proposed → etc)

- **agent_logs**: Audit trail for all agent actions
  - `action`: find_match, find_matches_for_job, etc
  - `input_payload`: Job/candidate IDs
  - `output_payload`: Score, reasoning, strengths/gaps
  - `tokens_used`: Claude API token count
  - `duration_ms`: Wall clock time
  - `status`: success/failed

## Scoring Process

When evaluating a candidate-job pair, Claude Sonnet:

1. **Extracts candidate profile:**
   - Skills (top 15)
   - Years of experience
   - Location, clearance level
   - Language

2. **Extracts job requirements:**
   - Title, domain
   - **Qualifications** (weighted more heavily)
   - Description
   - Security clearance requirement

3. **Evaluates match quality:**
   - How well do skills match qualifications?
   - Is there a clearance gap?
   - What are critical skill gaps?
   - What unique strengths does candidate bring?

4. **Returns JSON:**
```json
{
  "score": 75,
  "reasoning": "Strong Python background with cloud experience, but lacking specific Kubernetes expertise.",
  "strengths": ["5+ years Python", "AWS/Azure experience"],
  "gaps": ["No Kubernetes", "No Docker"]
}
```

## Threshold

- **Match created if:** Score >= 70
- **Optimization:** Each run processes up to 100 candidates/jobs
- **Token budgeting:** Logs all tokens for monitoring

## Integration Points

### Automatic Triggering (Future Phases)
1. When a new job is created: Trigger `match_job_candidates_task`
2. When a candidate is ready: Trigger `match_candidate_jobs_task`

### Manual Triggering (Current)
Admin endpoints allow operators to:
- Manually trigger matching for a specific job/candidate
- View what matches were created
- Monitor agent performance

## Logging & Monitoring

All operations are logged to `agent_logs`:
```python
{
  agent_code: "alik",
  action: "find_match",
  related_match_id: "uuid",
  related_job_id: "uuid",
  related_candidate_id: "uuid",
  input_payload: {job_id, candidate_id},
  output_payload: {score, reasoning, strengths, gaps},
  llm_model: "claude-sonnet-4",
  tokens_used: 1234,
  duration_ms: 2543,
  status: "success"
}
```

## API Usage Examples

### Trigger Job Matching
```bash
curl -X POST http://localhost:8000/admin/agent-matching/match-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "agent_code": "naama"
  }'

# Response:
{
  "status": "completed",
  "total_evaluated": 45,
  "matches_found": 7,
  "tokens_used": 3456,
  "duration_ms": 12543.0,
  "errors": []
}
```

### Get Agent Statistics
```bash
curl http://localhost:8000/admin/agent-matching/agents/naama/stats?days=7

# Response:
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

### View Recent Matches
```bash
curl http://localhost:8000/admin/agent-matching/matches/recent?limit=10

# Response:
{
  "total": 10,
  "by_agent": {
    "naama": 4,
    "alik": 3,
    "dganit": 2,
    "ofir": 1
  },
  "recent": [
    {
      "id": "...",
      "candidate_name": "John Doe",
      "job_title": "Senior Python Developer",
      "match_score": 0.85,
      "matched_by_agent_code": "naama",
      "created_at": "2026-05-22T16:45:00Z"
    }
  ]
}
```

## Testing

To test Phase 4 implementation:

1. **Unit Tests** (TODO: Phase 4.5)
   - Test scoring prompt building
   - Test JSON parsing from Claude
   - Test threshold logic

2. **Integration Tests** (TODO: Phase 4.5)
   - End-to-end job matching
   - End-to-end candidate matching
   - Verify agent_logs created

3. **Load Tests** (TODO: Phase 4.5)
   - 100 candidates → 1 job
   - Token usage monitoring
   - Duration benchmarks

## Next Phases

### Phase 4.3: Agent Triggers & Orchestration
- Automatically trigger matching when job is assigned
- Automatically trigger matching when candidate is ready
- Implement agent assignment logic (which agent owns which job/candidate)

### Phase 4.4: Admin Dashboard UI
- React components for agent monitoring
- Match review interface for Carmit
- Agent performance charts

### Phase 4.5: Testing & Validation
- Golden dataset of known matches
- Benchmark against human decisions
- Optimize scoring prompts per agent

## Files Created/Modified

### New Files
- `/apps/backend/src/pandapower/workers/agent_matching.py` (400+ lines)
- `/apps/backend/src/pandapower/routers/admin/agent_matching.py` (400+ lines)

### Modified Files
- `/apps/backend/src/pandapower/workers/tasks.py` (added 2 Celery tasks)
- `/apps/backend/src/pandapower/integrations/claude_api.py` (added match_score_with_json method)
- `/apps/backend/src/pandapower/main.py` (registered router)

## Configuration & Secrets

Required environment variables:
```
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://...
SUPABASE_SERVICE_ROLE_KEY=...
```

No additional configuration needed—agents are defined in code with AGENT_CONFIGS dict.

## Performance Considerations

1. **Token Usage:** Each match scores ~500 tokens. Budget ~5M tokens/month for moderate load.
2. **Latency:** Single match scores in ~2-3 seconds. 100 candidates ≈ 4-5 minutes.
3. **Concurrency:** Can run multiple agents in parallel via Celery.
4. **Caching:** Future optimization: cache job descriptions to reduce input tokens.

## Known Limitations & TODOs

1. **Candidate Filtering:** Currently scores all candidates. Phase 4.3 will add keyword filtering.
2. **Agent Assignment:** Jobs are manually assigned to agents. Phase 4.3 will automate.
3. **Prompt Optimization:** Agent-specific prompts can be tuned per domain.
4. **Skill Categorization:** Rely on normalized skills; can improve with skill category joins.
5. **Error Recovery:** No retry logic for failed scores; add in Phase 4.5.

## Rollback

If issues arise:
1. Revert code changes to previous commit
2. Existing matches in DB are not affected (immutable append-only design)
3. Agent logs provide full audit trail

---

**Implementation Date:** 2026-05-22
**Status:** Phase 4.2 Complete ✓
**Next Milestone:** Phase 4.3 (Agent Triggers & Orchestration)
