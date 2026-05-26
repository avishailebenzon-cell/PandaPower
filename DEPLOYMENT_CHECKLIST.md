# Deployment Checklist - Manual Job Override Feature

## 🎯 Goal
Get the manual job override feature live and working end-to-end.

## 📋 Pre-Deployment (Code Ready)

- ✅ Frontend code complete (`CarmitPage.tsx`)
- ✅ Backend endpoint complete (`agent_matching.py`)
- ✅ Database migration ready (`20260525000004_add_override_job_assignment_rpc.sql`)
- ✅ All code syntax validated
- ✅ Documentation complete

**Status**: ✅ ALL READY

---

## ⚙️ Deployment Steps (Follow in Order)

### Step 1: Apply Database Migration ⚠️ CRITICAL
**Time**: 5 minutes  
**Difficulty**: Easy  

**Action**:
```
1. Open https://app.supabase.com
2. Select PandaPower project
3. Click SQL Editor → New Query
4. Open file: APPLY_MIGRATION_NOW.txt
5. Copy the SQL (everything in the code block)
6. Paste into Supabase SQL editor
7. Click RUN button
8. Wait for "Success" message
```

**Verify**:
```sql
-- Run this query to verify function exists:
\df override_job_assignment

-- Should show the function in the results
```

**Status**: 
- [ ] Migration applied
- [ ] Function verified exists

---

### Step 2: Restart Backend Service
**Time**: 2 minutes  
**Difficulty**: Easy  

**If using Docker Compose**:
```bash
cd /Users/Avishai/Documents/Claude/Projects/PandaPower
docker-compose restart backend
```

**If using systemd**:
```bash
sudo systemctl restart pandapower-backend
```

**If using custom setup**:
Stop and restart your backend service

**Verify**:
```bash
# Check logs for startup success
docker logs backend
# or
journalctl -u pandapower-backend -n 50

# Should see: "Application startup complete" (no errors)
```

**Status**:
- [ ] Backend restarted
- [ ] No startup errors in logs

---

### Step 3: Test Frontend Access
**Time**: 2 minutes  
**Difficulty**: Easy  

**Action**:
1. Open browser: `http://localhost:5173/admin/carmit`
2. Should load Carmit page without errors
3. Check browser console (F12) for any errors

**Verify**:
- [ ] Page loads without 404 errors
- [ ] No console errors (F12 → Console tab)
- [ ] "All Jobs" tab visible
- [ ] Jobs table populated with data

---

### Step 4: Manual Test - Override Feature
**Time**: 5 minutes  
**Difficulty**: Medium  

**Prerequisites**:
- Need at least 1 job with an assigned agent
- (Optional: Create a test job if needed)

**Test Steps**:

1. **Navigate to All Jobs Tab**
   - Click "כל המשרות" tab in Carmit page

2. **Find a Job**
   - Look for a job with assigned agent (not NULL)
   - Example: "Senior Python Dev" assigned to "Alik"

3. **Click Override Button**
   - Look for "⚙️ עדכן" button at the end of job row
   - Click it

4. **Verify Modal Opens**
   - Modal should appear with job title
   - Should show current agent
   - Should have dropdown for new agent

5. **Select New Agent**
   - Click dropdown
   - Select different agent (e.g., if "Alik", select "Naama")
   - Verify selection shows in dropdown

6. **Submit Override**
   - Click "עדכן סוכן" button
   - Should see loading spinner briefly
   - Should see success message: "Successfully reassigned job from Alik to Naama"

7. **Verify Results**
   - Modal closes
   - Jobs table updates
   - Job now shows new agent
   - Click "⚙️ עדכן" again - modal should show new agent

**Status**:
- [ ] Can open override modal
- [ ] Can select new agent
- [ ] Can submit override
- [ ] Success message appears
- [ ] Job assignment updated in table

---

### Step 5: Verify Database Changes
**Time**: 3 minutes  
**Difficulty**: Medium  

**Run these queries in Supabase SQL Editor**:

**Query 1: Check job assignment changed**
```sql
SELECT id, title, assigned_agent_code, updated_at 
FROM jobs 
WHERE assigned_agent_code = 'naama'  -- Change to your new agent
ORDER BY updated_at DESC 
LIMIT 1;
```
**Expected**: Should see your test job with new agent code and recent timestamp

**Query 2: Check old agent's matches deleted**
```sql
SELECT COUNT(*) as remaining_matches
FROM matches 
WHERE job_id = 'your-job-id'  -- Replace with your test job ID
AND matched_by_agent_code = 'alik'  -- Replace with old agent
AND current_state = 'found';
```
**Expected**: Should be 0 (all "found" matches deleted)

**Query 3: Check override logged**
```sql
SELECT agent_code, action, output_payload, created_at 
FROM agent_logs 
WHERE action = 'override_assignment' 
ORDER BY created_at DESC 
LIMIT 1;
```
**Expected**: Should see recent entry with override details

**Query 4: Check new agent notification logged**
```sql
SELECT agent_code, action, output_payload, created_at 
FROM agent_logs 
WHERE action = 'receive_job_override' 
ORDER BY created_at DESC 
LIMIT 1;
```
**Expected**: Should see recent entry with new agent code

**Status**:
- [ ] Job assignment updated in database
- [ ] Old agent's matches deleted
- [ ] Override logged to agent_logs
- [ ] New agent notification logged

---

### Step 6: Monitor Celery Task (Optional)
**Time**: 5 minutes  
**Difficulty**: Advanced  

**To verify new agent received the matching task**:

**Option A: Check Celery logs**
```bash
docker logs celery-worker
# or
journalctl -u pandapower-celery -n 50
```

Look for:
```
[match_job_candidates_task] Task queued for agent: naama
Task ID: xxxxx-xxxxx-xxxxx-xxxxx
```

**Option B: Check agent_runtime_state**
```sql
SELECT agent_code, status, current_job_id, current_task_description, last_active_at
FROM agent_runtime_state
WHERE agent_code = 'naama'
ORDER BY last_modified_at DESC
LIMIT 1;
```

**Expected**: 
- `status` = "processing" (if task running now)
- `current_job_id` = your test job ID
- `current_task_description` = something like "Matching candidates..."

**Status**:
- [ ] Celery task queued (check logs)
- [ ] Agent runtime state updated (check table)

---

## ✅ Post-Deployment Verification

### Critical Checks
- [ ] Migration applied to Supabase
- [ ] Backend restarted successfully
- [ ] Frontend loads without errors
- [ ] Override button clickable
- [ ] Can select new agent
- [ ] Can submit override
- [ ] Success message appears
- [ ] Job assignment updated in database
- [ ] Matches deleted for old agent
- [ ] Override action logged

### Optional Checks
- [ ] Celery task queued
- [ ] Agent runtime state updated
- [ ] New agent started processing

---

## 🚨 Troubleshooting

### Issue: "Could not find column 'assigned_agent_code'"
**Diagnosis**: Migration not applied  
**Solution**: Apply the SQL migration in Supabase SQL Editor (Step 1)

### Issue: Override button doesn't appear
**Diagnosis**: Frontend not reloaded, browser cache issue  
**Solution**: 
1. Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)
2. Clear browser cache
3. Restart backend and frontend

### Issue: Error when clicking override button
**Diagnosis**: Backend not restarted, or migration not applied  
**Solution**:
1. Check backend logs for errors
2. Verify migration was applied
3. Restart backend service

### Issue: "Job not found" error
**Diagnosis**: Invalid job ID  
**Solution**:
1. Verify job exists in database
2. Try with a different job
3. Check job UUID format

### Issue: Modal opens but no agents in dropdown
**Diagnosis**: AGENTS configuration issue  
**Solution**:
1. Check browser console for errors
2. Verify agents array in CarmitPage.tsx
3. Restart frontend dev server

---

## 📊 Success Metrics

After deployment, you should be able to:

✅ Open Carmit page without errors  
✅ See all jobs in "All Jobs" tab  
✅ Click "⚙️ עדכן" on any job with assigned agent  
✅ Select new agent from dropdown  
✅ Submit override and see success message  
✅ See job assignment updated immediately  
✅ Find override logged in agent_logs table  
✅ See new agent's matches deleted (if any were "found" state)  

---

## 📝 Rollback Plan

If something goes wrong, you can rollback:

**Option 1: Revert database changes**
```sql
DROP FUNCTION IF EXISTS override_job_assignment(UUID, TEXT, TIMESTAMPTZ);
```
This removes the RPC function but doesn't affect existing data.

**Option 2: Revert frontend code**
```bash
git checkout apps/frontend/src/pages/admin/CarmitPage.tsx
npm run dev
```

**Option 3: Revert backend code**
```bash
git checkout apps/backend/src/pandapower/routers/admin/agent_matching.py
docker-compose restart backend
```

---

## 📞 Support

If you encounter issues:

1. **Check documentation**:
   - `OVERRIDE_FEATURE_COMPLETE.md` - Full feature doc
   - `MIGRATION_INSTRUCTIONS.md` - Migration guide
   - `SESSION_SUMMARY.md` - Technical details

2. **Check logs**:
   - Backend logs: `docker logs backend`
   - Celery logs: `docker logs celery-worker`
   - Supabase logs: SQL Editor → View query logs
   - Browser console: F12 → Console tab

3. **Verify status**:
   - Migration applied: Run `\df override_job_assignment` in Supabase
   - Backend healthy: Check logs for startup success
   - Frontend healthy: Check browser console for errors

---

## 🎯 Final Sign-Off

When all steps are complete, you're done! 🎉

The manual job override feature is now live and ready for production use.

**Date Completed**: ________________  
**Deployed By**: ________________  
**Notes**: ________________________________________

---

## 📅 Timeline

| Task | Duration | Status |
|------|----------|--------|
| Apply migration | 5 min | [ ] |
| Restart backend | 2 min | [ ] |
| Test frontend | 2 min | [ ] |
| Manual test | 5 min | [ ] |
| Database verify | 3 min | [ ] |
| Celery verify | 5 min | [ ] |
| **Total** | **22 min** | **Ready** |

---

**Start Time**: __________  
**End Time**: __________  
**Total Duration**: __________  

---

Questions? See the documentation files or check the backend logs for details.
