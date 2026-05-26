# PandaPower Pipedrive Integration - Comprehensive Test Guide
**Date:** May 24, 2026  
**Status:** Critical Fix #1 Implemented - Ready for Testing Phase  
**Tested By:** [Your Name]  
**Test Results:** [ ] Pass [ ] Fail  

---

## 1. Pre-Test Checklist

### 1.1 Backend Setup
- [ ] Migration 006_add_sync_schedule_timing.sql applied to Supabase
- [ ] Backend pipedrive_config.py updated with sync_days and sync_time fields
- [ ] Backend supports both POST and PUT methods on /sync-schedules/{entity_type}
- [ ] Syntax verification passed (py_compile successful)

### 1.2 Frontend Readiness
- [ ] PipedriveConfigPage.tsx can send sync_days (boolean[7]) and sync_time (HH:MM) in request
- [ ] UpdateSyncScheduleMutation uses PUT method to /admin/pipedrive/sync-schedule/{entity_type}
- [ ] UI displays day-of-week checkboxes and time picker

### 1.3 Environment Setup
- [ ] Backend development server running on localhost:8000
- [ ] Frontend development server running on localhost:5173
- [ ] Supabase project accessible with valid credentials
- [ ] Test database contains pipedrive_sync_schedule table with new columns

---

## 2. Test Suite 1: Backend Sync Schedule Endpoint

### Test 1.1: PUT Endpoint Accepts sync_days and sync_time
```bash
curl -X PUT http://localhost:8000/admin/pipedrive/sync-schedules/deals \
  -H "Content-Type: application/json" \
  -d '{
    "sync_interval_minutes": 30,
    "sync_direction": "bidirectional",
    "sync_enabled": true,
    "sync_days": [true, true, true, true, true, false, false],
    "sync_time": "02:00"
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "message": "Sync schedule for deals updated",
  "next_scheduled_sync": "2026-05-24T14:32:15.123456+00:00"
}
```

**Pass Criteria:**
- HTTP 200 response
- All fields returned correctly
- No validation errors

---

### Test 1.2: POST Endpoint Also Works (Backward Compatibility)
```bash
curl -X POST http://localhost:8000/admin/pipedrive/sync-schedules/persons \
  -H "Content-Type: application/json" \
  -d '{
    "sync_interval_minutes": 60,
    "sync_direction": "bidirectional",
    "sync_enabled": true,
    "sync_days": [true, true, true, true, true, true, true],
    "sync_time": "14:30"
  }'
```

**Expected Response:**
```json
{
  "status": "success",
  "message": "Sync schedule for persons updated",
  "next_scheduled_sync": "2026-05-24T15:32:15.123456+00:00"
}
```

**Pass Criteria:**
- HTTP 200 response
- Both POST and PUT methods work identically

---

### Test 1.3: Validation - Invalid Time Format
```bash
curl -X PUT http://localhost:8000/admin/pipedrive/sync-schedules/deals \
  -H "Content-Type: application/json" \
  -d '{
    "sync_interval_minutes": 30,
    "sync_time": "25:99"
  }'
```

**Expected Response:**
```json
{
  "detail": "Invalid time values"
}
```

**Pass Criteria:**
- HTTP 400 Bad Request
- Validation error message present

---

### Test 1.4: Validation - Wrong Number of Days
```bash
curl -X PUT http://localhost:8000/admin/pipedrive/sync-schedules/organizations \
  -H "Content-Type: application/json" \
  -d '{
    "sync_interval_minutes": 60,
    "sync_days": [true, true, true]
  }'
```

**Expected Response:**
```json
{
  "detail": "sync_days must have exactly 7 boolean values (Mon-Sun)"
}
```

**Pass Criteria:**
- HTTP 400 Bad Request
- Validation error message present

---

### Test 1.5: GET Endpoint Returns sync_days and sync_time
```bash
curl -X GET "http://localhost:8000/admin/pipedrive/sync-schedules?entity_type=deals"
```

**Expected Response:**
```json
{
  "schedules": [
    {
      "entity_type": "deals",
      "sync_interval_minutes": 30,
      "sync_direction": "bidirectional",
      "sync_enabled": true,
      "sync_days": [true, true, true, true, true, false, false],
      "sync_time": "02:00",
      "last_sync_at": null,
      "last_sync_status": null,
      "next_scheduled_sync": "2026-05-24T14:32:15.123456+00:00",
      "sync_count": 0
    }
  ],
  "count": 1
}
```

**Pass Criteria:**
- HTTP 200 response
- sync_days array returned (7 booleans)
- sync_time string returned in HH:MM format
- All other fields present

---

## 3. Test Suite 2: Database Persistence

### Test 2.1: Data Persisted to Database
```sql
SELECT entity_type, sync_days, sync_time, sync_interval_minutes
FROM pipedrive_sync_schedule
WHERE entity_type = 'deals';
```

**Expected Result:**
```
entity_type | sync_days                      | sync_time | sync_interval_minutes
deals       | {t,t,t,t,t,f,f}               | 02:00     | 30
```

**Pass Criteria:**
- Column exists and is accessible
- Boolean array stored correctly
- Time stored as string

---

### Test 2.2: Default Values Applied
```sql
SELECT entity_type, sync_days, sync_time
FROM pipedrive_sync_schedule
WHERE sync_days IS NOT NULL;
```

**Expected Result:**
- All rows have default sync_days: [true, true, true, true, true, false, false]
- All rows have default sync_time: "02:00"

**Pass Criteria:**
- No NULL values in sync_days or sync_time
- Defaults applied to existing records

---

## 4. Test Suite 3: Frontend Integration

### Test 3.1: Load Pipedrive Config Page
1. Navigate to `http://localhost:5173/admin/pipedrive/config`
2. Click "Sync Schedules" tab
3. Observe: Should see a grid of day-of-week checkboxes and time input field

**Pass Criteria:**
- Page loads without errors
- Day checkboxes visible and initialized
- Time input field visible
- Values match database (from GET endpoint)

---

### Test 3.2: Update Sync Schedule from Frontend
1. In Pipedrive Config Page, Sync Schedules tab
2. For "Deals" entity:
   - Uncheck Saturday and Sunday (should be checked from GET)
   - Set time to "15:45"
   - Click "Save Sync Schedule"
3. Observe: Loading spinner, success message

**Expected Behavior:**
- PUT request sent to `/admin/pipedrive/sync-schedules/deals`
- Payload includes:
  ```json
  {
    "sync_days": [true, true, true, true, true, false, false],
    "sync_time": "15:45",
    "sync_interval_minutes": 30,
    "sync_direction": "bidirectional"
  }
  ```
- Backend returns success
- UI updates to confirm

**Pass Criteria:**
- Network request sent with correct payload
- 200 response received
- Success message displayed
- Form values persist after refresh

---

### Test 3.3: Validation on Frontend
1. Try to set invalid time (e.g., "25:00")
2. Observe: Error message or validation prevents submission

**Pass Criteria:**
- Invalid times rejected before sending
- Error message shown to user

---

## 5. Test Suite 4: End-to-End Workflow

### Test 4.1: Complete Pipedrive Configuration Flow
1. Go to `/admin/pipedrive/config`
2. **Config Tab:**
   - Enter valid Pipedrive API token
   - Click "Save Configuration"
   - Verify success message
3. **Sync Schedules Tab:**
   - Set Deals: Every 30 minutes, Mon-Fri at 02:00
   - Set Persons: Every 60 minutes, Daily at 14:30
   - Set Organizations: Every 120 minutes, Mon-Fri at 08:00
4. **Field Mappings Tab:**
   - Verify mappings loaded
   - Add one new mapping if needed
5. **Click Save** (if applicable)
6. **Verify in Database:**
   ```sql
   SELECT entity_type, sync_days, sync_time, sync_interval_minutes
   FROM pipedrive_sync_schedule
   ORDER BY entity_type;
   ```

**Expected Result:**
```
entity_type    | sync_days              | sync_time | sync_interval_minutes
deals          | {t,t,t,t,t,f,f}      | 02:00     | 30
organizations  | {t,t,t,t,t,f,f}      | 08:00     | 120
persons        | {t,t,t,t,t,t,t}      | 14:30     | 60
```

**Pass Criteria:**
- All configuration saved correctly
- Database reflects frontend changes
- No validation errors
- UI confirms each change

---

## 6. Test Suite 5: Error Handling

### Test 5.1: Network Error Recovery
1. Stop backend server
2. Try to save sync schedule from frontend
3. Observe: Error message displayed
4. Restart backend
5. Try again - should succeed

**Pass Criteria:**
- User sees error message (not silent failure)
- Can retry after service restored

---

### Test 5.2: Invalid Data Rejection
1. Send malformed JSON to endpoint:
   ```bash
   curl -X PUT http://localhost:8000/admin/pipedrive/sync-schedules/deals \
     -H "Content-Type: application/json" \
     -d '{ "invalid": "data" }'
   ```
2. Observe: HTTP 422 Unprocessable Entity

**Pass Criteria:**
- Backend rejects invalid payloads
- Returns meaningful error message

---

## 7. Test Results Summary

| Test # | Test Name | Status | Notes |
|--------|-----------|--------|-------|
| 1.1 | PUT endpoint with sync_days/sync_time | [ ] | |
| 1.2 | POST backward compatibility | [ ] | |
| 1.3 | Invalid time validation | [ ] | |
| 1.4 | Invalid sync_days length | [ ] | |
| 1.5 | GET returns new fields | [ ] | |
| 2.1 | Database persistence | [ ] | |
| 2.2 | Default values applied | [ ] | |
| 3.1 | Frontend page loads | [ ] | |
| 3.2 | Update from frontend | [ ] | |
| 3.3 | Frontend validation | [ ] | |
| 4.1 | End-to-end workflow | [ ] | |
| 5.1 | Network error recovery | [ ] | |
| 5.2 | Invalid data rejection | [ ] | |

**Overall Result:** [ ] All Pass [ ] Some Failures [ ] Critical Failures

**Critical Blockers (if any):**
1. 
2. 
3. 

---

## 8. Next Steps After Testing

### If All Tests Pass ✓
1. Proceed to Test Suite #2: Field Mapping Validation
2. Test Suite #3: Data Sync Testing
3. Test Suite #4: Recruiter Workflow Integration
4. Full 17-test Pipedrive integration plan

### If Tests Fail ✗
1. Document failures with error messages
2. Fix issues based on error details
3. Re-run failed tests
4. Only proceed when all pass

---

## 9. Execution Notes

**Tester Name:** ________________  
**Date Tested:** ________________  
**Backend Version:** ________________  
**Frontend Version:** ________________  
**Database:** Supabase ✓ / Other: _______  
**Issues Encountered:**
```
1. [description]
2. [description]
3. [description]
```

**Fixes Applied:**
```
1. [description]
2. [description]
```

**Sign-off:** ________________  

---

**Document Version:** 1.0  
**Last Updated:** 2026-05-24  
**Status:** Ready for Testing
