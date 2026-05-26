# 🔬 End-to-End Testing Guide - Complete System Validation

**Version**: 1.0  
**Date**: May 23, 2026  
**Status**: Ready for Testing

---

## 📋 System Flow Overview

```
Azure Email Intake
    ↓
📥 CV Parsing & Candidate Creation
    ↓
Pipedrive Job Intake
    ↓
🎯 Carmit Routes Job to Agent
    ↓
🤖 Agent (Alik, Naama, etc.) Matches Candidates
    ↓
🔄 Matches Return to Carmit
    ↓
✅ Carmit Quality Gate Review
    ├─ Gate 1: Past Rejection Check (Pipedrive)
    ├─ Gate 2: Already Declined Check
    ├─ Gate 3: Conflict of Interest Detection
    ├─ Gate 4: Security Clearance Matching
    └─ Gate 5: Quality Score Threshold
    ↓
💬 Send to Tal (Initial Screener)
    ├─ Tal connects via WhatsApp (Green API)
    ├─ Tal conducts screening conversation
    └─ Candidate fills form
    ↓
🔄 Return to Carmit
    ↓
👤 Send to Elad (Placement Specialist)
    ├─ Elad reviews candidate profile
    └─ Elad sends to client via Email/WhatsApp
    ↓
💼 Final Outcome: HIRED ✓ or FAILED ❌
```

---

## 🧪 Testing Checklist

### **Phase 1: CV Intake from Azure** ✅

**Prerequisites:**
- Azure Storage configured
- Email account connected
- Mock CV files available

**Test Steps:**

```bash
□ Step 1.1: Upload CV to Azure
  - File: sample_candidate.pdf
  - Expected: Email triggers Azure Function
  
□ Step 1.2: CV Gets Parsed
  - Parser: Claude API CV Parser
  - Expected: Extract fields (name, email, skills, experience)
  
□ Step 1.3: Candidate Created in DB
  - Expected: New row in candidates table
  - Verify: All fields populated
  
□ Step 1.4: Check Logs
  - Expected: No errors in parsing
  - Verify: Timestamps recorded
```

**Verification:**
```sql
SELECT * FROM candidates 
WHERE created_at > NOW() - INTERVAL '10 minutes'
LIMIT 1;

-- Expected fields:
-- id, name, email, phone, key_skills[], 
-- experience_years, education, cv_text, parsed_at
```

---

### **Phase 2: Job Intake from Pipedrive** ✅

**Prerequisites:**
- Pipedrive API token configured
- Test job created in Pipedrive
- Scheduled sync working

**Test Steps:**

```bash
□ Step 2.1: Create Test Job in Pipedrive
  - Title: "Senior Backend Engineer"
  - Description: Python, PostgreSQL, AWS
  - Requirements: 5+ years experience
  
□ Step 2.2: Trigger Sync (or wait for scheduled)
  - Trigger: Manual POST /admin/sync/pipedrive-jobs
  - Expected: Job imported to PandaPower
  
□ Step 2.3: Verify Job in Database
  - Expected: New row in jobs table
  - Verify: All fields from Pipedrive
  
□ Step 2.4: Check Job Status
  - Status: 'new' (ready for routing)
  - Expected: Not assigned to agent yet
```

**Verification:**
```sql
SELECT * FROM jobs 
WHERE source = 'pipedrive' AND created_at > NOW() - INTERVAL '10 minutes'
ORDER BY created_at DESC LIMIT 1;

-- Expected fields:
-- id, title, description, required_skills[], 
-- pipedrive_deal_id, assigned_agent_code (NULL)
```

---

### **Phase 3: Carmit Routes Job to Agent** ✅

**Prerequisites:**
- Job exists in database (Phase 2 complete)
- Agent specialties configured
- Carmit worker running

**Test Steps:**

```bash
□ Step 3.1: Trigger Job Routing
  - Endpoint: POST /admin/carmit/route-job/{job_id}
  - Expected: Job assigned to appropriate agent
  
□ Step 3.2: Verify Agent Assignment
  - Expected: Naama (Python specialist) assigned
  - Field: jobs.assigned_agent_code = 'naama'
  
□ Step 3.3: Check Routing Confidence
  - Expected: High confidence (0.8+)
  - Reasoning: "Naama specializes in Python roles"
  
□ Step 3.4: Verify Agent Logs
  - Expected: Entry in agent_logs table
  - Type: 'job_routing'
  - Status: 'completed'
```

**Verification:**
```sql
SELECT * FROM jobs WHERE id = 'job_123';
-- Expected: assigned_agent_code = 'naama'

SELECT * FROM agent_logs 
WHERE job_id = 'job_123' AND type = 'job_routing'
ORDER BY created_at DESC LIMIT 1;
-- Expected: routing_confidence >= 0.8
```

---

### **Phase 4: Agent Matches Candidates** ✅

**Prerequisites:**
- Job assigned to agent (Phase 3 complete)
- Candidates exist (Phase 1 complete)
- Agent matching worker running

**Test Steps:**

```bash
□ Step 4.1: Agent Performs Matching
  - Agent: Naama (Python specialist)
  - Trigger: Automated worker every 5 minutes
  - Expected: Candidates matched against job
  
□ Step 4.2: Verify Matches Created
  - Expected: matches table has new rows
  - Status: 'found' (initial state)
  - Score: 0.0-1.0 (how good the match is)
  
□ Step 4.3: Check Match Score
  - Candidate: John (5 years Python)
  - Job: Senior Python (5+ years)
  - Expected Score: 0.85+ (good match)
  
□ Step 4.4: Verify Agent Logs
  - Type: 'matching_complete'
  - Matches Found: 1
```

**Verification:**
```sql
SELECT * FROM matches 
WHERE job_id = 'job_123' AND current_state = 'found'
ORDER BY match_score DESC;

-- Expected: At least 1 match found
-- Verify score makes sense for job/candidate pair
```

---

### **Phase 5: Matches Return to Carmit** ✅

**Prerequisites:**
- Matches created (Phase 4 complete)
- Carmit review worker running

**Test Steps:**

```bash
□ Step 5.1: Carmit Receives Matches
  - Worker: carmit_review_matches_task
  - Frequency: Every 15 minutes
  - Expected: Matches state remains 'found' for review
  
□ Step 5.2: Check Match in Queue
  - Endpoint: GET /admin/carmit/pending-review
  - Expected: Match appears in pending queue
  
□ Step 5.3: Verify Match Details
  - Expected: Score, candidate name, job title visible
  - Status: 'found' (awaiting approval)
```

**Verification:**
```sql
SELECT * FROM matches 
WHERE current_state = 'found'
LIMIT 5;

-- All matches should be in review queue
-- Ready for Carmit quality gates
```

---

### **Phase 6: Carmit Quality Gate Review** 🔥 **CRITICAL**

**Prerequisites:**
- Matches in pending queue (Phase 5 complete)
- Pipedrive integration working
- Quality gates configured

**Test Steps:**

```bash
□ Step 6.1: Trigger Carmit Review
  - Endpoint: POST /admin/carmit/review-match/{match_id}
  - Automatic: Every 15 minutes
  - Expected: All 5 gates evaluated
  
□ Step 6.2: Gate 1 - Past Rejection Check
  - Check: Has candidate been rejected for this/similar job before?
  - Source: Pipedrive deal rejection notes
  - Expected Result: PASS (if no past rejection)
  
□ Step 6.3: Gate 2 - Already Declined Check
  - Check: Did candidate decline this role/company before?
  - Source: candidates.declining_status
  - Expected Result: PASS (if not declined)
  
□ Step 6.4: Gate 3 - Conflict Detection
  - Check: No conflict of interest
  - Logic: Same company? Direct report? Competitor?
  - Expected Result: PASS (different company)
  
□ Step 6.5: Gate 4 - Clearance Matching
  - Check: candidate.clearance_level >= job.required_clearance
  - Levels: None < Secret < Top Secret
  - Expected Result: PASS (candidate Secret >= job None)
  
□ Step 6.6: Gate 5 - Quality Threshold
  - Check: match_score >= 0.70
  - Expected: Score 0.85 (PASS)
  
□ Step 6.7: Verify Match State
  - Expected: 'carmit_approved' (all gates passed)
  - Details: Gate results stored in match_state_history
  
□ Step 6.8: Check Pipedrive Note
  - Expected: No rejection note (if approved)
  - If rejected: Note explains which gate failed
```

**Verification:**
```sql
SELECT * FROM matches WHERE id = 'match_123';
-- Expected: current_state = 'carmit_approved'

SELECT * FROM match_state_history 
WHERE match_id = 'match_123' AND to_state = 'carmit_approved'
ORDER BY created_at DESC LIMIT 1;
-- Expected: details include gate_results JSON

SELECT * FROM match_state_history 
WHERE match_id = 'match_123' AND to_state LIKE '%rejected%'
-- Expected: EMPTY if approved, or contains rejection reason
```

**Gate Results JSON Example:**
```json
{
  "gate_results": {
    "past_rejection": {"passed": true},
    "already_declined": {"passed": true},
    "conflict_of_interest": {"passed": true},
    "clearance_match": {"passed": true, "score": 2},
    "quality_threshold": {"passed": true, "score": 0.85}
  },
  "decision": "approved",
  "carmit_reasoning": "All 5 gates passed. Strong match."
}
```

---

### **Phase 7: Send to Tal for Screening** ✅

**Prerequisites:**
- Match approved by Carmit (Phase 6 complete)
- Tal account configured
- Green API credentials ready

**Test Steps:**

```bash
□ Step 7.1: Transition to Tal
  - State: carmit_approved → sent_to_tal
  - Expected: Match visible in Tal's queue
  
□ Step 7.2: Check Tal Dashboard
  - Endpoint: GET /recruiting/tal
  - Expected: Match appears in "תור לטל" (Tal Queue)
  
□ Step 7.3: Tal Initiates WhatsApp
  - Method: Green API WhatsApp integration
  - Expected: Tal can send WhatsApp to candidate
  
□ Step 7.4: Verify Connection
  - Check: Candidate phone number in match
  - Expected: Valid Israeli format (+972...)
  
□ Step 7.5: Record Conversation Start
  - State: sent_to_tal → tal_conversation
  - Expected: Timestamp recorded
```

**Verification:**
```sql
SELECT * FROM matches WHERE id = 'match_123';
-- Expected: current_state = 'sent_to_tal'

SELECT * FROM match_state_history 
WHERE match_id = 'match_123' AND to_state = 'sent_to_tal'
ORDER BY created_at DESC LIMIT 1;
-- Expected: Entry exists, timestamp current
```

---

### **Phase 8: Tal WhatsApp Screening Conversation** 💬 **MANUAL TEST**

**Prerequisites:**
- Match sent to Tal (Phase 7 complete)
- Green API working
- Test phone number available

**Test Steps:**

```bash
□ Step 8.1: Tal Sends WhatsApp Message
  - Via: Green API integration
  - Message: "שלום John, יש לנו הזדמנות שחושבים שתתאים לך..."
  - Expected: Message delivered to candidate
  
□ Step 8.2: Simulate Candidate Response
  - Response: "שלום, תודה על ההזדמנות! אני מעוניין לשמוע עוד"
  - Expected: Message appears in Tal's chat interface
  
□ Step 8.3: Tal Conducts Screening
  - Topics: Technical skills, availability, salary expectations
  - Duration: 10-30 minutes of conversation
  - Expected: Full discussion recorded
  
□ Step 8.4: Tal Requests Candidate Form
  - Form: /candidate_form link sent via WhatsApp
  - Expected: Candidate fills out form with personal details
  
□ Step 8.5: Form Submission
  - Data: Name, phone, email, location, availability
  - Expected: Form saved in database
```

**Form Expected Fields:**
```json
{
  "name": "John Doe",
  "phone": "+972501234567",
  "email": "john@example.com",
  "location": "Tel Aviv",
  "availability_date": "2026-06-01",
  "expected_salary": 25000,
  "skills_summary": "Python, PostgreSQL, Docker, AWS",
  "current_employer": "Tech Corp"
}
```

---

### **Phase 9: Tal Decision & Return to Carmit** ✅

**Prerequisites:**
- Screening conversation complete (Phase 8 complete)
- Candidate form submitted
- Tal made decision

**Test Steps:**

```bash
□ Step 9.1: Tal Records Decision
  - Endpoint: POST /admin/pipedrive/recruiter-workflow/record-decision/{match_id}
  - Decision: 'accepted' or 'rejected'
  - Reason: Descriptive explanation
  
□ Step 9.2: Match State Update (if Accepted)
  - State: tal_conversation → tal_approved
  - Expected: Timestamp recorded
  
□ Step 9.3: Return to Carmit
  - State: tal_approved → sent_to_elad
  - Expected: Carmit automatically processes
  
□ Step 9.4: Check Match State History
  - Expected: 3 entries:
    1. found → carmit_approved
    2. carmit_approved → sent_to_tal
    3. tal_conversation → tal_approved
```

**Verification:**
```sql
SELECT * FROM match_state_history 
WHERE match_id = 'match_123'
ORDER BY created_at ASC;

-- Expected 3 rows showing full progression
-- Each with appropriate timestamps
```

---

### **Phase 10: Carmit Routes to Elad** ✅

**Prerequisites:**
- Tal approved match (Phase 9 complete)
- Elad account ready

**Test Steps:**

```bash
□ Step 10.1: Automatic Routing to Elad
  - Trigger: Automatic after Tal approval
  - State: tal_approved → sent_to_elad
  - Expected: Immediate transition
  
□ Step 10.2: Check Elad Dashboard
  - Endpoint: GET /recruiting/elad
  - Expected: Match appears in "תור לאלד" (Elad Queue)
  
□ Step 10.3: Verify Candidate Data
  - Expected: Full candidate profile visible
    - Skills, experience, form data
    - Job requirements visible
    - Client contact info visible
  
□ Step 10.4: Check Client Instructions
  - Expected: Job-specific client contact info
    - Client name, email, phone, WhatsApp
    - How to send candidate (email/WhatsApp)
    - Special instructions
```

**Verification:**
```sql
SELECT * FROM matches WHERE id = 'match_123';
-- Expected: current_state = 'sent_to_elad'

SELECT c.*, j.*, m.match_score 
FROM matches m
JOIN candidates c ON m.candidate_id = c.id
JOIN jobs j ON m.job_id = j.id
WHERE m.id = 'match_123';
-- Expected: All candidate and job data visible
```

---

### **Phase 11: Elad Placement - Send to Client** 🤝 **CRITICAL**

**Prerequisites:**
- Match in Elad queue (Phase 10 complete)
- Client contact info in job record
- Email/WhatsApp ready

**Test Steps:**

```bash
□ Step 11.1: Elad Reviews Candidate
  - Expected: Full candidate profile visible
  - Verify: Technical fit, soft skills, requirements
  
□ Step 11.2: Elad Initiates Placement Talk
  - State: sent_to_elad → elad_conversation
  - Method: Internal system or direct contact
  - Expected: Timestamp recorded
  
□ Step 11.3: Prepare Candidate Package
  - Content:
    - Candidate CV (PDF)
    - Candidate form data
    - Interview summary
    - Skills summary
  
□ Step 11.4: Send to Client (Email)
  - Endpoint: POST /admin/placement/send-candidate
  - Method: Email (primary)
  - Template: Professional offer letter with CV
  - Expected: Email delivered to client
  
  OR Alternative: Send via WhatsApp
  - Method: WhatsApp message with candidate link
  - Expected: Client receives message with profile link
  
□ Step 11.5: Update Match State
  - State: elad_conversation → offer_sent
  - Expected: Timestamp recorded when sent
  
□ Step 11.6: Create Pipedrive Activity
  - Expected: Activity log in Pipedrive deal
  - Content: "Candidate [Name] sent to [Client]"
  - Timestamp: When sent
```

**Email Content Example:**
```
Subject: Candidate Offer - John Doe for Senior Python Developer

Dear [Client Name],

We are pleased to present a qualified candidate for your Senior Python Developer position:

Name: John Doe
Email: john@example.com
Phone: +972501234567

Experience: 5+ years in Python, PostgreSQL, AWS
Location: Tel Aviv
Availability: June 1, 2026

CV: [Attached/Link]

Please review and let us know if you would like to proceed with an interview.

Best regards,
Elad
PandaPower Recruitment
```

**Verification:**
```sql
SELECT * FROM matches WHERE id = 'match_123';
-- Expected: current_state = 'offer_sent'

SELECT * FROM match_state_history 
WHERE match_id = 'match_123' AND to_state = 'offer_sent';
-- Expected: Timestamp shows when offer was sent

-- Check if Pipedrive activity created:
-- (Would need Pipedrive API check or manual verification)
```

---

### **Phase 12: Final Outcome - Hired or Failed** 💼 **MANUAL + SYSTEM**

**Prerequisites:**
- Offer sent to client (Phase 11 complete)
- Client response received
- Elad informed of outcome

**Test Steps - HIRED Path:**

```bash
□ Step 12.1: Client Accepts Candidate
  - Communication: Email/call/WhatsApp from client
  - Status: "We want to hire John"
  
□ Step 12.2: Elad Records Outcome
  - Endpoint: POST /admin/placement/record-outcome
  - Outcome: 'hired'
  - Notes: "Client accepted. Start date: June 1"
  
□ Step 12.3: Update Match State
  - State: offer_sent → hired
  - Expected: Final/terminal state
  
□ Step 12.4: Update Candidate Status
  - Field: candidates.placement_status = 'hired'
  - Client: Store which client hired
  
□ Step 12.5: Update Job Status
  - Field: jobs.status = 'completed'
  - Filled By: John Doe (candidate name)
  
□ Step 12.6: Record in Pipedrive
  - Deal Status: Won
  - Hired Candidate: John Doe
  - Start Date: June 1, 2026
  - Sales Commission: If applicable
  
□ Step 12.7: Verify Success
  - Expected: Timeline shows all 12 states
    - found → carmit_approved → sent_to_tal
    - → tal_conversation → tal_approved
    - → sent_to_elad → elad_conversation
    - → offer_sent → hired ✅
  - Timeline: View via Dashboard
```

**Test Steps - PLACEMENT_FAILED Path:**

```bash
□ Step 12.1: Client Rejects Candidate
  - Communication: Email/call from client
  - Status: "Not the right fit" or "Salary too high"
  
□ Step 12.2: Elad Records Outcome
  - Endpoint: POST /admin/placement/record-outcome
  - Outcome: 'placement_failed'
  - Reason: "Client salary expectations too high"
  
□ Step 12.3: Update Match State
  - State: offer_sent → placement_failed
  - Expected: Terminal/final state
  
□ Step 12.4: Record in Pipedrive
  - Deal Status: Lost
  - Reason: Rejection reason
  - Feedback: From client if available
  
□ Step 12.5: Candidate Not Marked as Hired
  - Status: remains 'available' for other opportunities
```

**Verification:**
```sql
SELECT * FROM matches WHERE id = 'match_123';
-- Expected: current_state = 'hired' or 'placement_failed'

SELECT * FROM match_state_history 
WHERE match_id = 'match_123'
ORDER BY created_at ASC;
-- Expected: All 12+ state transitions visible
-- Timeline shows complete journey

SELECT * FROM candidates WHERE id = 'candidate_123';
-- If hired: placement_status = 'hired'
-- If failed: placement_status = 'available'
```

---

## 🎯 Quick Testing Checklist

### **Automated Testing** ✅

```bash
□ CV Parsing: Test with 3 different CV formats
□ Job Routing: Verify agent assignment logic
□ Quality Gates: Test all 5 gates independently
□ State Transitions: Verify all valid paths
□ Error Handling: Test network failures
□ Database Integrity: Check constraints
□ API Response Times: Measure latency
□ Concurrent Requests: Test 10 simultaneous matches
```

### **Manual Testing** 👤

```bash
□ End-to-End Flow: Complete 1 match from start to finish
□ WhatsApp Integration: Send test messages via Green API
□ Candidate Form: Fill form and verify data saved
□ Dashboard UX: Test all UI flows
□ Error Messages: Verify user-friendly errors
□ Hebrew RTL: Check all text displays correctly
□ Mobile Responsiveness: Test on phone/tablet
```

### **Integration Testing** 🔗

```bash
□ Azure Email: Test CV intake pipeline
□ Pipedrive Sync: Verify job/deal sync
□ Green API: Test WhatsApp messaging
□ Supabase Database: Verify all CRUD operations
□ API Endpoints: Test all 50+ endpoints
□ State Machine: Test 12 state transitions
□ Notifications: Verify email/WhatsApp alerts
```

---

## 📊 Health Check Endpoints

Create these endpoints for quick system status verification:

### **1. System Health Check**
```bash
GET /admin/health
Response: {
  "status": "healthy",
  "components": {
    "database": "connected",
    "pipedrive_api": "connected",
    "green_api": "connected",
    "azure_storage": "connected",
    "redis": "connected"
  },
  "timestamp": "2026-05-23T20:30:00Z"
}
```

### **2. Pipeline Status**
```bash
GET /admin/pipeline-status
Response: {
  "pending_cvs": 5,
  "pending_jobs": 3,
  "pending_matches": 12,
  "pending_tal_review": 8,
  "pending_elad_placement": 4,
  "completed_today": 2,
  "failed_today": 1
}
```

### **3. Agent Status**
```bash
GET /admin/agents/status
Response: {
  "alik": {"status": "active", "matches_found": 15, "success_rate": 0.68},
  "naama": {"status": "active", "matches_found": 22, "success_rate": 0.75},
  "dganit": {"status": "active", "matches_found": 8, "success_rate": 0.62},
  ...
}
```

### **4. Match Journey** (NEW!)
```bash
GET /api/admin/matches/{match_id}/history
Response: {
  "matchId": "match_123",
  "candidateName": "John Doe",
  "jobTitle": "Senior Python Developer",
  "currentState": "hired",
  "stateHistory": [
    {"from_state": "found", "to_state": "carmit_approved", "created_at": "..."},
    {"from_state": "carmit_approved", "to_state": "sent_to_tal", "created_at": "..."},
    ... (all 12 states shown)
  ]
}
```

---

## 🧬 Database Verification Queries

Run these SQL queries to verify data integrity:

### **Count Active Matches by State**
```sql
SELECT 
  current_state,
  COUNT(*) as count,
  AVG(match_score) as avg_score
FROM matches
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY current_state
ORDER BY count DESC;
```

### **Verify Carmit Gate Results**
```sql
SELECT 
  m.id,
  c.name,
  j.title,
  m.match_score,
  msh.details->>'decision' as carmit_decision,
  msh.created_at
FROM matches m
JOIN match_state_history msh ON m.id = msh.match_id
JOIN candidates c ON m.candidate_id = c.id
JOIN jobs j ON m.job_id = j.id
WHERE msh.to_state IN ('carmit_approved', 'carmit_rejected')
  AND msh.created_at > NOW() - INTERVAL '24 hours'
ORDER BY msh.created_at DESC;
```

### **Check Tal Conversion Rate**
```sql
SELECT 
  COUNT(CASE WHEN to_state = 'tal_approved' THEN 1 END)::float / 
  COUNT(CASE WHEN from_state = 'sent_to_tal' THEN 1 END) as tal_approval_rate,
  COUNT(CASE WHEN from_state = 'sent_to_tal' THEN 1 END) as total_sent_to_tal
FROM match_state_history
WHERE created_at > NOW() - INTERVAL '7 days';
```

### **Verify Placement Success**
```sql
SELECT 
  COUNT(CASE WHEN to_state = 'hired' THEN 1 END) as hired_count,
  COUNT(CASE WHEN to_state = 'placement_failed' THEN 1 END) as failed_count,
  COUNT(CASE WHEN to_state IN ('hired', 'placement_failed') THEN 1 END) as completed_count,
  ROUND(
    100.0 * COUNT(CASE WHEN to_state = 'hired' THEN 1 END) / 
    NULLIF(COUNT(CASE WHEN to_state IN ('hired', 'placement_failed') THEN 1 END), 0),
    2
  ) as success_rate_percent
FROM match_state_history
WHERE created_at > NOW() - INTERVAL '7 days'
  AND to_state IN ('hired', 'placement_failed');
```

---

## 🚨 Common Issues & Solutions

### **Issue 1: CV Not Parsing**
```
Symptoms: CV uploads but no candidate created
Solution:
- Check Azure Storage connection
- Verify Claude API key in .env
- Check CV file format (PDF/DOCX supported)
- Review /api/admin/logs for parse errors
```

### **Issue 2: Job Not Routed**
```
Symptoms: Job stays "unassigned"
Solution:
- Check Pipedrive sync is running
- Verify job has required fields (title, skills, description)
- Check agent specialties configuration
- Review Carmit logs for routing errors
```

### **Issue 3: Match Stuck in State**
```
Symptoms: Match not transitioning to next state
Solution:
- Check worker is running (carmit_review_matches_task)
- Verify database permissions
- Check for validation errors
- Review match_state_history table for errors
```

### **Issue 4: WhatsApp Not Sending**
```
Symptoms: Tal can't send WhatsApp messages
Solution:
- Verify Green API credentials
- Check candidate phone number format
- Test Green API connection directly
- Review Green API logs for errors
```

### **Issue 5: Pipedrive Sync Failing**
```
Symptoms: Jobs not imported from Pipedrive
Solution:
- Verify PIPEDRIVE_API_TOKEN in .env
- Check Pipedrive API quota
- Verify deal custom field mappings
- Test Pipedrive connection via /admin/health
```

---

## 📝 Test Report Template

Save this after each test run:

```markdown
# Test Report - [Date]

## Overall Status: ✅ PASS / ⚠️ PARTIAL / ❌ FAIL

### Test Execution Summary
- Date: 2026-05-23
- Tester: [Name]
- Duration: [Time]
- Platform: [Dev/Staging/Production]

### Phase Results
- [x] Phase 1: CV Intake - ✅ PASS
- [x] Phase 2: Job Intake - ✅ PASS
- [x] Phase 3: Job Routing - ✅ PASS
- [x] Phase 4: Agent Matching - ✅ PASS
- [x] Phase 5: Match Queue - ✅ PASS
- [x] Phase 6: Quality Gates - ✅ PASS
- [x] Phase 7: Send to Tal - ✅ PASS
- [x] Phase 8: Tal Screening - ⚠️ PARTIAL (WhatsApp delayed)
- [x] Phase 9: Tal Decision - ✅ PASS
- [x] Phase 10: Send to Elad - ✅ PASS
- [x] Phase 11: Elad Placement - ✅ PASS
- [x] Phase 12: Final Outcome - ✅ PASS

### Issues Found
1. WhatsApp message delivery delayed 2 minutes
   - Severity: LOW
   - Status: Investigating Green API

2. UI RTL text slightly misaligned on mobile
   - Severity: LOW
   - Status: CSS update needed

### Performance Metrics
- Average Match Processing Time: 12 seconds
- Quality Gate Evaluation: 2 seconds
- WhatsApp Send Time: 5-8 seconds
- Database Query Performance: < 100ms

### Recommendations
1. Increase Green API timeout from 3s to 5s
2. Cache agent specialties for faster routing
3. Add WhatsApp delivery confirmation

### Sign-off
- Tested by: [Tester Name]
- Approved by: [Lead Name]
- Date: 2026-05-23
```

---

## ✅ Success Criteria

System is **READY FOR PRODUCTION** when:

- ✅ All 12 phases test successfully
- ✅ Complete match journey takes < 20 minutes
- ✅ Conversion rate (found → hired) > 10%
- ✅ No critical errors in logs
- ✅ All API endpoints respond < 1s
- ✅ Pipedrive data syncs within 5 minutes
- ✅ WhatsApp messages deliver within 10 seconds
- ✅ Database transactions complete atomically
- ✅ Error handling is user-friendly
- ✅ RTL Hebrew displays correctly
- ✅ Mobile responsive design works
- ✅ Team is trained and confident

---

**Last Updated:** May 23, 2026  
**Next Review:** June 1, 2026 (after live testing)

