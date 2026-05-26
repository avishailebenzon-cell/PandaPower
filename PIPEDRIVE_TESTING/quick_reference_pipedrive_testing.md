# PandaPower Pipedrive Integration - Quick Reference Guide
**Fast copy-paste commands for testing**

---

## 🔧 1. Database Migration (Run in Supabase SQL Editor)

**Copy and paste this entire SQL block:**

```sql
-- Migration: Add Sync Schedule Timing Fields
-- Add columns to pipedrive_sync_schedule table
ALTER TABLE IF EXISTS pipedrive_sync_schedule
ADD COLUMN IF NOT EXISTS sync_days BOOLEAN[] DEFAULT ARRAY[true, true, true, true, true, false, false]::BOOLEAN[],
ADD COLUMN IF NOT EXISTS sync_time TEXT DEFAULT '02:00';

-- Update existing schedules with default values
UPDATE pipedrive_sync_schedule
SET sync_days = ARRAY[true, true, true, true, true, false, false]::BOOLEAN[],
    sync_time = '02:00'
WHERE sync_days IS NULL OR sync_time IS NULL;

-- Verify migration
SELECT entity_type, sync_days, sync_time, sync_interval_minutes 
FROM pipedrive_sync_schedule 
ORDER BY entity_type;
```

**Expected Output:**
```
entity_type    | sync_days              | sync_time | sync_interval_minutes
deals          | {t,t,t,t,t,f,f}      | 02:00     | 30
organizations  | {t,t,t,t,t,f,f}      | 02:00     | 60
persons        | {t,t,t,t,t,f,f}      | 02:00     | 60
```

---

## 🧪 2. Backend Tests (Run in Terminal)

### Test 1: PUT with valid data
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
**Expected:** `"status": "success"`

---

### Test 2: POST backward compatibility
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
**Expected:** `"status": "success"`

---

### Test 3: GET returns new fields
```bash
curl -X GET "http://localhost:8000/admin/pipedrive/sync-schedules/deals" \
  -H "Accept: application/json"
```
**Expected:** Response includes `sync_days` and `sync_time` arrays

---

### Test 4: Validation - invalid time
```bash
curl -X PUT http://localhost:8000/admin/pipedrive/sync-schedules/deals \
  -H "Content-Type: application/json" \
  -d '{
    "sync_interval_minutes": 30,
    "sync_time": "25:99"
  }'
```
**Expected:** HTTP 400 with error message

---

### Test 5: Validation - wrong day count
```bash
curl -X PUT http://localhost:8000/admin/pipedrive/sync-schedules/deals \
  -H "Content-Type: application/json" \
  -d '{
    "sync_interval_minutes": 30,
    "sync_days": [true, false, true]
  }'
```
**Expected:** HTTP 400 with error message about 7 values

---

### Test 6: All entities configured
```bash
curl -X GET "http://localhost:8000/admin/pipedrive/sync-schedules" \
  -H "Accept: application/json"
```
**Expected:** 3 schedules returned (deals, persons, organizations)

---

## 🌐 3. Frontend UI Tests

### Step 1: Load config page
```
Open: http://localhost:5173/admin/pipedrive/config
```

### Step 2: Navigate to Sync Schedules tab
- Click on "Sync Schedules" tab
- Should show form for deals, persons, organizations

### Step 3: Update Deals entity
```
Changes:
- Days: Mon-Fri (default is already correct)
- Time: Change from 02:00 to 15:45
- Interval: Keep at 30 minutes
```

### Step 4: Click Save
- Should show loading indicator
- Should show success message
- Button text should return to normal

### Step 5: Refresh page
```
Press: Ctrl + R (or Cmd + R on Mac)
```
- Time field should show "15:45"
- Days should show Mon-Fri selected
- Values should persist

### Step 6: Check Network Request (DevTools)
```
Press: F12 (Open DevTools)
Go to: Network tab
Filter: XHR/Fetch
Save button again
```

**Verify request:**
- Method: PUT
- URL: `/admin/pipedrive/sync-schedules/deals`
- Payload includes sync_days array
- Payload includes sync_time string
- Response status: 200

---

## 🔍 4. Database Verification (Supabase SQL)

### Check columns exist
```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'pipedrive_sync_schedule' 
AND column_name IN ('sync_days', 'sync_time')
ORDER BY column_name;
```

---

### Check current values
```sql
SELECT 
  entity_type, 
  sync_days, 
  sync_time, 
  sync_interval_minutes,
  sync_direction
FROM pipedrive_sync_schedule 
ORDER BY entity_type;
```

---

### Check recent updates
```sql
SELECT 
  entity_type, 
  sync_days, 
  sync_time, 
  updated_at 
FROM pipedrive_sync_schedule 
WHERE updated_at > NOW() - INTERVAL '1 hour'
ORDER BY updated_at DESC;
```

---

## ✅ 5. Test Completion Checklist

### Backend Tests
- [ ] Test 1 passed (PUT with valid data)
- [ ] Test 2 passed (POST backward compat)
- [ ] Test 3 passed (GET returns fields)
- [ ] Test 4 passed (time validation)
- [ ] Test 5 passed (day count validation)
- [ ] Test 6 passed (all entities exist)

### Database Tests
- [ ] Columns exist with correct types
- [ ] Default values applied
- [ ] All entities have data
- [ ] Recent updates match PUT requests

### Frontend Tests
- [ ] Page loads (no console errors)
- [ ] Day checkboxes visible
- [ ] Time input visible
- [ ] Values load from DB
- [ ] Save button works
- [ ] Success message appears
- [ ] Values persist on refresh
- [ ] Network request correct

### Overall
- [ ] All tests passed
- [ ] No regressions
- [ ] Ready for next suite

---

## 🐛 6. Troubleshooting Quick Fixes

### Backend returns 404 on PUT
```bash
# Check if server is running
curl http://localhost:8000/docs

# If offline, restart backend
cd /Users/Avishai/Documents/Claude/Projects/PandaPower/apps/backend
source .venv/bin/activate
python src/pandapower/main.py
```

### Frontend shows old data
```bash
# Hard refresh (clear cache)
# Windows/Linux: Ctrl + Shift + R
# Mac: Cmd + Shift + R

# Or clear cache entirely:
# DevTools → Application → Storage → Clear site data
```

### Migration fails in Supabase
```sql
-- Check if table exists
SELECT EXISTS(
  SELECT FROM information_schema.tables 
  WHERE table_name = 'pipedrive_sync_schedule'
);

-- Check columns
SELECT column_name 
FROM information_schema.columns 
WHERE table_name = 'pipedrive_sync_schedule';
```

### Time validation error
```
Valid format: HH:MM (24-hour)
❌ 25:99 (invalid hour and minute)
❌ 14:30:00 (seconds not allowed)
✅ 14:30 (correct)
✅ 02:00 (correct)
```

---

## 📊 7. Expected Results Summary

| Component | Expected | Status |
|-----------|----------|--------|
| Database columns | 2 new columns added | ⏳ |
| Default values | All rows have defaults | ⏳ |
| PUT endpoint | Accepts sync_days/time | ⏳ |
| POST endpoint | Still works (backward compat) | ⏳ |
| GET endpoint | Returns sync_days/time | ⏳ |
| Time validation | Rejects invalid times | ⏳ |
| Day count validation | Rejects wrong count | ⏳ |
| Frontend form | Shows checkboxes + time input | ⏳ |
| Frontend save | Sends PUT request | ⏳ |
| Data persistence | Values save and load | ⏳ |

---

## 🎯 7. How to Proceed After This Passes

Once all tests ✅ pass:

1. **Document Results**
   - Screenshot or note each test result
   - Any issues found and how you fixed them

2. **Next Test Suite**
   - Move to Field Mapping Validation
   - Or Recruiter Workflow Integration tests

3. **Full Integration Testing**
   - Then proceed to 17-test comprehensive Pipedrive suite

---

**Status:** Ready to execute tests  
**Time Estimate:** 1-2 hours for full test suite  
**Next Step:** Run migration in Supabase SQL Editor

