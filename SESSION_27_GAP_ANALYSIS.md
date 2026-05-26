# Session 27: Pandi Infrastructure + Onboarding Flow — Gap Analysis

**Status:** Complete audit of existing codebase  
**Date:** May 23, 2026  
**Scope:** Phase 10, Session 27 kickoff  

---

## Executive Summary

**Current State:** Zero Pandi code exists. The system has foundational infrastructure (Celery, Supabase, FastAPI, React) but no Pandi-specific layers.

**Build Path:** 4 distinct components must be created in this session:
1. **Database migrations** (4 migrations: candidate_number, pandi_tables, pandi_views, pandi_settings)
2. **Green API integration** (extend existing integration for 3rd instance)
3. **Celery workers** (pandi message receiver, onboarding flow, quota init)
4. **FastAPI routers** (admin endpoints, webhook receiver)
5. **Frontend foundation** (Pandi agent tab skeleton, candidate_number display refactor)

---

## 1. Database Layer — Gaps & Requirements

### 1.1 Existing Migration Files

The codebase has 13 migration files (numbered by date):
- `20240521000001` through `20240521000010` — Core schema (candidates, matches, whatsapp, etc.)
- `20240522000001` — Update candidates
- `20240522000002` — Skill tables
- `20240523000001` — Enhance candidates (scoring fields)

**Gap:** NO migrations for Pandi-specific tables.

### 1.2 Required Migrations for Session 27

| Migration File | Purpose | Key Tables | Status |
|---|---|---|---|
| `0011_add_candidate_number.sql` | Add candidate_number system with auto-generation | candidates (new column), candidate_number_seq, trigger | ⚠️ **MISSING** |
| `0012_create_pandi_tables.sql` | All Pandi tables | pandi_clients, pandi_conversations, pandi_messages, candidate_referrals, candidate_referral_history, pandi_message_quotas | ⚠️ **MISSING** |
| `0013_create_pandi_views.sql` | Helper views for Pandi dashboards | v_referrals_with_context, v_pandi_active_conversations, v_pandi_quota_status | ⚠️ **MISSING** |
| `0014_add_pandi_settings.sql` | System settings for Pandi config | system_settings inserts (pandi.default_monthly_limit, pandi.instance_id, pandi.token, pandi.whatsapp_number) | ⚠️ **MISSING** |

### 1.3 Critical Table Definitions Needed

**pandi_clients:**
- contact_id (FK to contacts)
- phone (E.164, unique)
- whatsapp_chat_id
- identified_at, identification_method
- initial_invite_sent_at, initial_invite_sent_by_user_id
- is_active, first_message_at, last_message_at
- intake_status ('not_started' | 'in_progress' | 'completed' | 'failed_no_response')
- intake_collected_data (JSONB)

**pandi_conversations:**
- pandi_client_id (FK)
- status ('open' | 'awaiting_job_definition' | 'presenting_candidates' | 'awaiting_selection' | 'transferred_to_recruitment' | 'closed_idle' | 'closed_by_quota' | 'closed_by_admin')
- job_context (JSONB: {title, qualifications, location, security_clearance, must_have, nice_to_have, notes})
- matched_job_id (FK to jobs, nullable)
- summary, started_at, last_activity_at, closed_at

**pandi_messages:**
- conversation_id, pandi_client_id
- direction ('inbound' | 'outbound')
- message_type ('text' | 'document' | 'image' | 'system')
- green_api_message_id
- text, document_url, document_filename
- llm_invoked, llm_model, llm_input_tokens, llm_output_tokens, llm_tools_called (JSONB)
- was_quota_blocked, inappropriate_flag, flag_reason
- sent_at (indexed)

**candidate_referrals:**
- candidate_id, candidate_number (snapshot), pandi_client_id
- conversation_id, job_context (JSONB), matched_job_id
- presented_at, presented_payload (JSONB - anonymized), llm_match_reasoning
- status state machine (11 states: presented → hired)
- full_cv_approval_requested_at, full_cv_approved_by_user_id, full_cv_approved_at
- full_cv_sent_at, full_cv_pandi_message_id (FK to pandi_messages)

**candidate_referral_history:**
- referral_id, from_status, to_status
- triggered_by_user_id, triggered_by_pandi_client_id
- reasoning, metadata (JSONB)

**pandi_message_quotas:**
- pandi_client_id, month (DATE)
- monthly_limit, messages_used
- increase_requested_at, increase_requested_amount
- increase_approved_at, increase_approved_by_user_id, increase_approved_amount

**Views to create:**
- `v_referrals_with_context` — joins referrals with candidate, client, contact, job details
- `v_pandi_active_conversations` — active conversations per client
- `v_pandi_quota_status` — quota usage % and state (ok/warning/exhausted/pending_approval)

---

## 2. Integrations Layer — Gaps & Requirements

### 2.1 Existing Integration Structure

```
/integrations/
├── __init__.py
├── azure/          ← Azure AD for email polling (exists)
├── claude_api.py   ← CV parsing (exists)
├── pipedrive.py    ← CRM sync (exists)
└── supabase_storage.py ← File storage (exists)
```

**Gap:** NO Green API integration yet.

### 2.2 Green API Setup Needed

**Current State:**
- Tal and Elad agents use WhatsApp via Green API (Phase 6)
- Only instances 1 & 2 are currently registered

**Required for Pandi:**
1. **Create Green API instance #3** in Green API portal
   - New WhatsApp number (separate from Tal/Elad instances)
   - Instance ID + API token (store in system_settings or .env)

2. **Extend green_api client** to support 3 agents:
   ```python
   # Location: apps/backend/src/pandapower/integrations/green_api/client.py
   
   def get_green_api_client(agent_code: Literal['tal', 'elad', 'pandi']) -> GreenAPIClient:
       """Factory function to get the correct Green API client instance."""
       if agent_code == 'pandi':
           return GreenAPIClient(
               instance_id=settings.pandi.instance_id,
               token=settings.pandi.token
           )
       # ... tal and elad cases
   ```

3. **Webhook receiver at separate endpoint:**
   ```python
   # Location: apps/backend/src/pandapower/integrations/green_api/webhooks.py
   
   @router.post("/webhooks/whatsapp/pandi")
   async def receive_pandi_webhook(payload: dict):
       """Receive incoming Pandi messages from Green API."""
       # 1. Validate webhook secret
       # 2. Return 200 OK immediately
       # 3. Queue task: process_pandi_incoming_message(payload)
   ```

---

## 3. Workers Layer — Gaps & Requirements

### 3.1 Existing Celery Structure

```
/workers/
├── celery_app.py       ← Celery + Redis config (EXISTS)
├── tasks.py            ← Task routing (EXISTS)
├── agent_matching.py   ← Agent worker base (EXISTS)
├── candidate_creation.py
├── candidate_scoring.py
├── carmit.py           ← Orchestrator worker
├── cv_parse.py
├── email_ingest.py
├── file_extractors.py
├── pipedrive_*.py      ← Various sync tasks
├── skill_normalization.py
└── ... (total 19 files)
```

**Gap:** NO Pandi workers exist.

### 3.2 Required Pandi Workers for Session 27

**New directory structure:**
```
/workers/
├── pandi/
│   ├── __init__.py
│   ├── onboarding.py       ← Handle intake flow
│   ├── message_handler.py  ← Route incoming messages
│   ├── quota_manager.py    ← Initialize/check quotas
│   └── identification.py   ← Auto-identify by phone
```

**Worker 1: `process_pandi_incoming_message(payload)`**
- Extract phone from Green API payload
- Look up in pandi_clients
- If exists: route to appropriate handler (intake vs conversation)
- If not exists: start intake or auto-identify
- Save incoming message to pandi_messages
- **Idempotent:** Use green_api_message_id as dedup key

**Worker 2: `pandi_intake_continue(client_id, response_text)`**
- Advance through intake questionnaire (4 steps)
- Save responses to pandi_clients.intake_collected_data
- When complete: create Contact + Organization, notify admin via Telegram
- Set identification_method='manual_intake_via_bot'

**Worker 3: `pandi_initialize_quota(client_id, month=today)`**
- Create pandi_message_quotas record
- monthly_limit from settings (default 100)
- messages_used = 0

**Worker 4: `pandi_send_message(client_id, message_text, conversation_id=None)`**
- Check quota (is_active, haven't exceeded limit)
- If quota exceeded: queue rejection message, set was_quota_blocked=True
- Send via Green API
- Save outbound message to pandi_messages

---

## 4. API Routes Layer — Gaps & Requirements

### 4.1 Existing Router Structure

```
/routers/
├── health.py
├── user.py
└── admin/
    ├── agent_matching.py
    ├── analytics.py
    ├── candidate_management.py
    ├── carmit.py
    ├── cv_parse.py
    ├── email_ingest.py
    ├── pipedrive.py
    ├── security_classification.py
    ├── skill_management.py
    └── setup.py
```

**Gap:** NO Pandi-specific routers exist.

### 4.2 Required Endpoints for Session 27

**New file: `apps/backend/src/pandapower/routers/admin/pandi.py`**

1. **POST /admin/pandi/generate-invite**
   - Body: `{contact_id: UUID}`
   - Returns: `{invite_url, prefilled_message, instructions_for_admin}`
   - Creates/updates pandi_client with initial_invite_sent_at, initial_invite_sent_by_user_id

2. **POST /webhooks/whatsapp/pandi** *(in integrations/green_api/webhooks.py)*
   - Receives Green API webhook
   - Validates secret
   - Queues task

3. **GET /admin/pandi/clients**
   - Returns paginated list of pandi_clients with related data
   - Filters: is_active, identification_method, intake_status

4. **GET /admin/pandi/clients/{client_id}**
   - Returns full client profile + conversation history

---

## 5. Frontend Layer — Gaps & Requirements

### 5.1 Existing Frontend Structure

```
/src/pages/
├── admin/
│   ├── AgentManagementPage.tsx
│   ├── AnalyticsDashboard.tsx
│   ├── CVParsingPage.tsx
│   ├── CandidateManagementPage.tsx
│   ├── CarmitPage.tsx
│   ├── EmailIntakePage.tsx
│   ├── IntegrationsPage.tsx          ← Update for Green API Pandi section
│   ├── RecruiterDashboard.tsx
│   ├── SecurityClassificationPage.tsx
│   └── SkillManagementPage.tsx
└── (no agents/ subdirectory yet)
```

**Gap:** 
- No `/agents/pandi` page
- No agents subdirectory structure
- candidate_number not displayed anywhere

### 5.2 Required Frontend Changes for Session 27

**1. Create agents page structure:**
```
/src/pages/agents/
├── AgentPage.tsx           ← Router wrapper (handles ?agent=tal|elad|pandi)
└── agents/
    ├── TalAgent.tsx        ← Candidate outreach (exists in concept)
    ├── EladAgent.tsx       ← Client outreach (exists in concept)
    └── PandiAgent.tsx      ← 🐼 New!
```

**2. PandiAgent tab structure:**
```
PandiAgent.tsx (skeleton, non-functional in Session 27)
├── Tab 1: "לקוחות פעילים" (Active Clients)
│   ├── DataTable: phone | contact name | organization | identification_method | intake_status | first_message_at | last_message_at | is_active
│   ├── Row actions: "צפה בשיחה" (disabled), "השעה לקוח"
│   └── Top action: "+ הוסף לקוח חדש" → Modal with contact autocomplete
├── Tab 2: "הצעות מועמדים" (Candidate Referrals) — placeholder for Session 28
├── Tab 3: "דוחות ודרישות" (Reports & Quotas) — placeholder for Session 28
```

**3. Display candidate_number everywhere:**
- **Candidates list page:** Add column "מס' מועמד" with badge
- **Candidates/:id profile:** Add prominent badge with candidate_number
- **Matches list & detail:** Display candidate_number next to candidate name
- **Admin pages:** Update all candidate displays

**4. Update IntegrationsPage:**
- Add Green API section (similar to existing integrations)
- Show Pandi instance_id (masked token)
- "Test connection" button
- Display WhatsApp number

---

## 6. Implementation Order (Session 27)

### Phase 1: Database (foundation)
1. Create `0011_add_candidate_number.sql`
   - Add sequence + trigger
   - Backfill existing candidates
2. Create `0012_create_pandi_tables.sql`
   - All 6 Pandi tables + indexes
3. Create `0013_create_pandi_views.sql`
   - 3 views
4. Create `0014_add_pandi_settings.sql`
   - Insert system_settings rows

### Phase 2: Backend Integration (plumbing)
1. Extend green_api client factory
2. Create webhook receiver endpoint
3. Create admin Pandi router with invite generation

### Phase 3: Backend Workers (logic)
1. Create pandi_workers module structure
2. Implement message receiver task
3. Implement intake flow task
4. Implement quota initialization task
5. Hook tasks into Celery

### Phase 4: Frontend Foundation (UI shell)
1. Create agents page routing structure
2. Create PandiAgent skeleton with DataTable
3. Add candidate_number display refactor across all pages
4. Update IntegrationsPage for Green API Pandi section

### Phase 5: Manual Setup (external)
1. Create Green API instance #3 (manual, outside code)
2. Update system_settings in Supabase with Pandi credentials
3. Choose Pandi WhatsApp number
4. Select 3 pilot clients

### Phase 6: Manual Testing (security checkpoint)
1. Test invite URL generation
2. Test webhook receiver
3. Test intake flow end-to-end
4. Verify anonymization (candidate_number only in UI, no full_name)

---

## 7. Security Checklist for Session 27

**Privacy by Default — Anonymization Verification:**

| Data | Allowed in UI? | Allowed in Webhook? | Notes |
|---|---|---|---|
| candidate_number | ✅ Yes | ✅ Yes | Only identifier sent to clients |
| full_name | ❌ No | ❌ No | Never expose to Pandi |
| email | ❌ No | ❌ No | Never expose |
| phone | ❌ No | ❌ No | Never expose |
| years_experience | ✅ Yes | ✅ Yes | Allowed (granular) |
| primary_domain | ✅ Yes | ✅ Yes | Allowed |
| security_clearance | ✅ Yes | ✅ Yes | Allowed |
| region | ✅ Yes (if available) | ✅ Yes | Allowed |
| languages | ✅ Yes | ✅ Yes | Allowed |
| skills (normalized) | ✅ Yes | ✅ Yes | Allowed |

**Before marking Session 27 complete:**
- [ ] Manually test: send anonymized candidate_number via Pandi webhook
- [ ] Verify: full_name never appears in pandi_messages
- [ ] Verify: email never appears in presented_payload
- [ ] Verify: phone (candidate phone) never appears in Pandi data
- [ ] Verify: Green API logs don't contain PII beyond phone (which is required for routing)

---

## 8. Known Blockers & Assumptions

1. **Green API instance #3:** Not yet created. Requires manual portal access. Assume instance_id + token will be provided before Phase 2.

2. **system_settings table:** Assume it already exists with key-value storage. ✅ Verified in CLAUDE.md section 5.

3. **Telegram bot:** Assume admin notifications route works. Will verify during onboarding intake test.

4. **Contacts table:** Assume `contacts` table exists (verified in migrations). Pandi client creation requires a contact_id.

5. **Users table:** Assume exists for audit fields (initial_invite_sent_by_user_id, etc.).

---

## 9. Files to Create/Modify Summary

### New Files (17 total)
**Migrations:**
1. `infra/supabase/migrations/0011_add_candidate_number.sql`
2. `infra/supabase/migrations/0012_create_pandi_tables.sql`
3. `infra/supabase/migrations/0013_create_pandi_views.sql`
4. `infra/supabase/migrations/0014_add_pandi_settings.sql`

**Backend:**
5. `apps/backend/src/pandapower/integrations/green_api/__init__.py` (new dir)
6. `apps/backend/src/pandapower/integrations/green_api/client.py` (extend)
7. `apps/backend/src/pandapower/integrations/green_api/webhooks.py` (new)
8. `apps/backend/src/pandapower/routers/admin/pandi.py` (new)
9. `apps/backend/src/pandapower/workers/pandi/__init__.py` (new dir)
10. `apps/backend/src/pandapower/workers/pandi/onboarding.py`
11. `apps/backend/src/pandapower/workers/pandi/message_handler.py`
12. `apps/backend/src/pandapower/workers/pandi/quota_manager.py`
13. `apps/backend/src/pandapower/workers/pandi/identification.py`

**Frontend:**
14. `apps/frontend/src/pages/agents/AgentPage.tsx` (new)
15. `apps/frontend/src/pages/agents/PandiAgent.tsx` (new)
16. `apps/frontend/src/pages/agents/TalAgent.tsx` (skeleton)
17. `apps/frontend/src/pages/agents/EladAgent.tsx` (skeleton)

### Modified Files (6 total)
1. `apps/backend/src/pandapower/integrations/green_api/client.py` — Add 'pandi' factory case
2. `apps/backend/src/pandapower/workers/tasks.py` — Register Pandi tasks
3. `apps/backend/src/pandapower/workers/celery_app.py` — Add Pandi tasks to Celery
4. `apps/backend/src/pandapower/core/config.py` — Add pandi config section
5. `apps/frontend/src/pages/admin/IntegrationsPage.tsx` — Add Pandi Green API section
6. All `/candidates` and `/matches` related components — Add candidate_number display

---

## Next Steps

With this gap analysis, Session 27 is ready to begin. The implementation path is clear:

1. **Database first** — Migrations create the schema foundation
2. **Green API extension** — Enable Pandi to send/receive messages
3. **Workers** — Implement business logic (intake, routing, quotas)
4. **API routes** — Expose admin endpoints
5. **Frontend** — UI for client management + candidate_number everywhere
6. **Manual testing** — Security checkpoint before handoff

**Estimated effort:** 8-10 hours for a solid, security-tested implementation.

---

**Compiled by:** Claude Code  
**Based on:** Phase10-Pandi-ClaudeCode-Prompts.md, CLAUDE.md sections 5.1, 9.8, 11.3, 15.6
