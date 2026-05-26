# Migration Instructions for Job Assignment Override

## Problem Solved
The manual job override feature had a Supabase schema cache issue preventing the direct UPDATE operation on the `assigned_agent_code` column. This has been resolved by creating an RPC (Remote Procedure Call) function that performs the update directly in SQL, completely bypassing the schema cache validation issue.

## What's New
1. **New RPC Function**: `override_job_assignment()` - A PostgreSQL stored procedure that safely updates job assignments
2. **Updated Backend Endpoint**: `/admin/agent-matching/override-job-assignment` now uses the RPC function
3. **Migration File**: `infra/supabase/migrations/20260525000004_add_override_job_assignment_rpc.sql`

## How to Apply the Migration

### Option 1: Via Supabase SQL Editor (Recommended - Easiest)

1. Go to [Supabase Console](https://app.supabase.com)
2. Select your PandaPower project
3. Go to **SQL Editor** in the left sidebar
4. Click **New Query**
5. Copy the SQL from `infra/supabase/migrations/20260525000004_add_override_job_assignment_rpc.sql`
6. Paste it into the SQL editor
7. Click **Run** button

The migration will be applied immediately.

### Option 2: Via psycopg2 Script (Command Line)

If you have the database password:

```bash
cd /Users/Avishai/Documents/Claude/Projects/PandaPower/apps/backend
python scripts/apply_single_migration.py ../../../infra/supabase/migrations/20260525000004_add_override_job_assignment_rpc.sql
```

### Option 3: Via Environment Variable

If you want to set the database password in your environment:

```bash
# First, get your Supabase postgres password from:
# 1. Go to Supabase Console > Project Settings > Database
# 2. Click "Reveal" next to password field
# 3. Copy the password

export SUPABASE_DB_PASSWORD="your_postgres_password_here"

# Then apply the migration:
cd /Users/Avishai/Documents/Claude/Projects/PandaPower
python apply_migrations.py
```

## What the Migration Does

The migration creates a PostgreSQL function with the following signature:

```sql
CREATE OR REPLACE FUNCTION override_job_assignment(
    p_job_id UUID,
    p_new_agent_code TEXT,
    p_updated_at TIMESTAMPTZ DEFAULT NOW()
) RETURNS TABLE (
    success BOOLEAN,
    message TEXT,
    old_agent_code TEXT,
    new_agent_code TEXT
)
```

This function:
- Takes a job ID and new agent code as input
- Updates the job's `assigned_agent_code` to the new agent
- Returns success status and the old/new agent codes
- Completely bypasses Supabase's schema cache validation issues

## Testing the Feature After Migration

Once the migration is applied:

1. **Backend API**: POST `/admin/agent-matching/override-job-assignment`
   ```json
   {
     "job_id": "uuid-of-job",
     "new_agent_code": "naama",
     "override_reason": "manual_override",
     "override_user_id": "user@example.com"
   }
   ```

2. **Frontend**: Use the Carmit Page → Click "⚙️ עדכן" button on any job → Select new agent → Confirm

3. **Expected Result**:
   - Job's `assigned_agent_code` updated to new agent ✓
   - All "found" state matches from old agent deleted ✓
   - New agent receives Celery task to match candidates ✓
   - Override action logged to `agent_logs` table ✓

## Troubleshooting

### If you see "PGRST204: Could not find column" error:
- The migration hasn't been applied yet
- Apply the migration using one of the options above
- Restart the backend after applying the migration

### If RPC call returns "Job not found":
- Verify the job_id exists in the database
- Check that you're using the correct UUID format

### If match deletion doesn't work:
- Check that there are actually "found" state matches to delete
- The system only deletes matches with `current_state = 'found'`
- Already-approved matches ("carmit_approved", "sent_to_tal", etc.) are protected and not deleted

## Code Changes Summary

### Frontend (`/apps/frontend/src/pages/admin/CarmitPage.tsx`)
- Added override modal UI ✓
- Added agent selection dropdown ✓
- Added POST request to override endpoint ✓
- Added error handling and success message ✓

### Backend (`/apps/backend/src/pandapower/routers/admin/agent_matching.py`)
- Updated endpoint to use RPC function instead of REST API ✓
- Added comprehensive logging ✓
- Added match deletion for old agent ✓
- Added task queueing for new agent ✓

### Database (`infra/supabase/migrations/20260525000004_add_override_job_assignment_rpc.sql`)
- Created `override_job_assignment()` RPC function ✓

## Next Steps

After applying the migration:

1. Restart the backend server to load the updated endpoint code
2. Test the override feature through the Carmit page UI
3. Verify that matches are deleted and new agent receives the job
4. Monitor `agent_logs` table for audit trail of overrides

## Questions?

If you encounter any issues:
1. Check the backend logs: `docker logs backend` (or equivalent)
2. Check the Supabase logs: SQL Editor → View query logs
3. Verify the RPC function exists: Supabase → SQL Editor → Run `\df override_job_assignment`
