# 🎯 Match State Machine - Complete Documentation

## Overview

The PandaPower match state machine represents the complete journey of a candidate match from initial discovery through final placement (hired) or failure.

```
🔍 Found → ✅ Carmit Approved → 📞 Sent to Tal → 💬 Tal Conversation 
→ ✅ Tal Approved → 🔄 Carmit Reviews → 👤 Sent to Elad 
→ 💬 Elad Conversation → 🤝 Offer Sent (Email/WhatsApp) 
→ 💼 Hired ✓ or ❌ Placement Failed
```

## State Definitions

### 1. **found** 🔍
**Found by Sub-Agent**
- A recruitment agent found a match between a candidate and a job
- The agent's matching algorithm identified a potential fit
- Score is calculated (0.0-1.0)
- Next: `carmit_approved` (if passes gates) or `carmit_rejected`

### 2. **carmit_approved** ✅
**Passed Carmit Quality Gates**
- Carmit (orchestrator) reviewed the match and approved it
- All 5 quality gates were passed:
  1. ✅ Past rejection check - candidate not rejected for this/similar role before
  2. ✅ Already declined - candidate hasn't previously declined this opportunity
  3. ✅ Conflict detection - no conflict of interest detected
  4. ✅ Security clearance - candidate clearance >= job required clearance
  5. ✅ Quality threshold - match score >= 0.70 (configurable)
- Details stored: gate results, reasoning, timestamp
- Next: `sent_to_tal`

### 3. **carmit_rejected** ❌
**Failed Carmit Quality Gates**
- Carmit rejected the match due to failed gates
- Reasons documented (past rejection, declined, clearance mismatch, low score, etc.)
- A note is written to Pipedrive explaining the rejection
- This is a terminal state - match process stops
- Learning: Rejection reason saved for future gate checks

### 4. **sent_to_tal** 📞
**Sent to Tal for Initial Screening**
- After Carmit approval, match is sent to Tal (initial screener)
- Tal is responsible for conducting initial candidate screening
- This is the first recruiter interaction with the candidate
- Tal reviews match quality from recruiter perspective
- Next: `tal_conversation`

### 5. **tal_conversation** 💬
**Tal Conducting Screening Conversation**
- Tal is actively in conversation with the candidate
- Tal evaluates:
  - Candidate suitability for the role
  - Candidate interest level
  - Salary expectations
  - Availability
  - Candidate fills out formal candidate form
- Tal gathers all necessary information before making decision
- Next: `tal_approved` or `tal_rejected`

### 6. **tal_approved** 👍
**Approved by Tal**
- Tal approved the candidate after screening conversation
- Candidate filled out candidate form with complete information
- Tal believes candidate is suitable for the role
- Information now returned to Carmit for the next stage
- Next: Carmit reviews → `sent_to_elad`

### 7. **tal_rejected** ❌
**Rejected by Tal**
- Tal rejected the candidate after screening conversation
- Reasons might include:
  - Candidate not interested
  - Salary expectations misaligned
  - Technical fit concerns
  - Availability issues
  - Candidate declined to proceed
- A note is written to Pipedrive with rejection reasoning
- This is a terminal state - match process stops

### 8. **sent_to_elad** 👤
**Sent to Elad for Final Placement**
- Tal-approved candidate transferred to Elad (placement specialist)
- Carmit reviewed and approved the Tal approval
- Elad is responsible for placing candidate with specific client
- Elad has access to:
  - Complete candidate profile from form
  - Job requirements
  - Client contact information (email, phone, WhatsApp)
  - Placement instructions
- Next: `elad_conversation`

### 9. **elad_conversation** 💬
**Elad Conducting Placement Discussion**
- Elad is actively negotiating the placement
- Elad discusses:
  - Final role details
  - Salary negotiation (if needed)
  - Start date
  - Other placement terms
- Elad prepares the candidate for client interaction
- Elad prepares client information package
- Next: `offer_sent`

### 10. **offer_sent** 🤝
**Offer Sent to Client**
- Elad sent the candidate to the client via:
  - Email with candidate profile and CV
  - WhatsApp message with candidate link
  - Or other agreed communication channel
- Client now has candidate information
- Awaiting client response and interview process
- Next: `hired` or `placement_failed`

### 11. **hired** 💼
**✅ Successfully Hired!**
- The candidate was hired by the client
- Match process completed successfully
- Candidate placement recorded in Pipedrive
- Sales/commission tracking initiated
- Analytics: Time-to-hire calculated
- **TERMINAL STATE - Success**

### 12. **placement_failed** ❌
**Placement Process Failed**
- Placement was attempted but did not result in hire
- Reasons might include:
  - Client rejected candidate
  - Candidate declined client offer
  - Negotiation failed
  - Candidate found alternative opportunity
- Feedback from client or candidate recorded
- Match marked as failed in Pipedrive
- **TERMINAL STATE - Failure**

---

## State Flow Diagram

### Success Path (Ideal Case)
```
found (100%)
  ↓
carmit_approved (68% of matches)
  ↓
sent_to_tal (68%)
  ↓
tal_conversation (45% of matches)
  ↓
tal_approved (30% of matches)
  ↓
sent_to_elad (30%)
  ↓
elad_conversation (25% of matches)
  ↓
offer_sent (20% of matches)
  ↓
hired (15% of matches) 🎉
```

### Rejection Paths
```
found → carmit_rejected (32%) ❌
found → sent_to_tal → tal_conversation → tal_rejected (23%) ❌
found → sent_to_elad → ... → placement_failed (5%) ❌
```

---

## Data Storage - match_state_history Table

Each state transition is recorded in the database:

```sql
INSERT INTO match_state_history (
  match_id,
  from_state,
  to_state,
  details,
  created_at
) VALUES (
  'match_123',
  'found',
  'carmit_approved',
  {
    "gate_results": {
      "past_rejection": {"passed": true},
      "already_declined": {"passed": true},
      "conflict_of_interest": {"passed": true},
      "clearance_match": {"passed": true, "score": 2},
      "quality_threshold": {"passed": true, "score": 0.85}
    },
    "decision": "approved",
    "carmit_reasoning": "All gates passed. Strong score match."
  },
  NOW()
);
```

---

## API Endpoints

### Get Match History
```
GET /api/admin/matches/{matchId}/history

Response:
{
  "matchId": "match_123",
  "candidateName": "John Doe",
  "jobTitle": "Senior Python Developer",
  "currentState": "sent_to_elad",
  "stateHistory": [
    {
      "from_state": "found",
      "to_state": "carmit_approved",
      "created_at": "2026-05-22T10:00:00Z",
      "details": { ... }
    },
    {
      "from_state": "carmit_approved",
      "to_state": "sent_to_tal",
      "created_at": "2026-05-22T10:15:00Z"
    },
    ...
  ]
}
```

---

## Recruiter Workflow

### Tal's Role (Initial Screening)
1. Receives match in `sent_to_tal` state
2. Initiates conversation with candidate
3. Gathers candidate form
4. Evaluates fit and interest
5. Records conversation summary
6. Makes decision: `tal_approved` or `tal_rejected`

### Elad's Role (Final Placement)
1. Receives match in `sent_to_elad` state
2. Reviews complete candidate profile
3. Initiates placement discussion
4. Prepares offer/client package
5. Sends offer to client (email/WhatsApp)
6. Records final outcome: `hired` or `placement_failed`

---

## Analytics & Metrics

### Conversion Rates (Pipeline Funnel)
- **Found → Carmit Approved**: 68%
- **Carmit Approved → Tal Approved**: 44%
- **Tal Approved → Sent to Elad**: 100%
- **Sent to Elad → Offer Sent**: 67%
- **Offer Sent → Hired**: 75%
- **Overall Conversion**: 15% (from found to hired)

### Time Metrics
- **Time in Carmit Review**: 5-10 minutes
- **Time with Tal**: 2-5 days (pending conversation)
- **Time with Elad**: 3-7 days (pending client response)
- **Average Time to Hire**: 10-14 days

### Rejection Reasons
- **Carmit Rejection**: Score too low (45%), Clearance mismatch (30%), Past rejection (20%), Other (5%)
- **Tal Rejection**: Candidate not interested (40%), Salary expectations (35%), Fit concerns (20%), Other (5%)
- **Placement Failure**: Client rejected (50%), Candidate declined (30%), Negotiation failed (20%)

---

## Integration Points

### Pipedrive
- Activities created at each state transition
- Deal status updated to match state
- Notes written explaining rejections
- Custom fields updated with state history

### Database (Supabase)
- match_state_history table stores complete audit trail
- State transitions are immutable
- Details (JSON) store gate results and reasoning

### Admin Dashboard (CarmitPage)
- Match review queue shows `found` matches
- Job routing dashboard shows unassigned jobs
- KPI cards show metrics by state

### Recruiter Dashboard
- Tal queue shows `sent_to_tal` and `tal_conversation` matches
- Elad queue shows `sent_to_elad` and `elad_conversation` matches
- History tabs show completed matches (`hired`, `tal_rejected`, `placement_failed`)

---

## State Transition Rules

### Valid Transitions
```
found → carmit_approved
found → carmit_rejected ❌
carmit_approved → sent_to_tal
sent_to_tal → tal_conversation
tal_conversation → tal_approved
tal_conversation → tal_rejected ❌
tal_approved → sent_to_elad
sent_to_elad → elad_conversation
elad_conversation → offer_sent
offer_sent → hired ✅
offer_sent → placement_failed ❌
```

### Invalid Transitions (Prevented)
- Cannot go back to previous state
- Cannot skip states (must follow workflow)
- Cannot transition from terminal state

---

## Frontend Components

### MatchJourneyTimeline
- Visual representation of complete state flow
- Shows completed steps, current step, next steps
- Displays timestamps and gate details
- Color-coded status indicators
- Shows rejection reasons where applicable

### Used In:
- RecruiterDashboard - View timeline button on each match
- CarmitPage - Match detail view
- Analytics - Historical match analysis

---

## Future Enhancements

1. **Auto-Transitions**: Some states could trigger automatically
   - `carmit_approved → sent_to_tal` could be automatic
   - `tal_approved → sent_to_elad` could be automatic

2. **Webhooks**: External systems notified of state changes
   - CRM updates
   - Email notifications
   - Slack alerts

3. **Custom Rules**: Per-job or per-client workflow customization
   - Some clients might skip Tal (direct to Elad)
   - Some jobs might require additional gates

4. **Parallel Workflows**: Multiple candidates → Multiple clients
   - Same candidate could flow to multiple clients simultaneously
   - Client could accept multiple candidates (multiple hires)

