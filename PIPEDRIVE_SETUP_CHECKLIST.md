# Pipedrive Integration - Setup Checklist ✅

## Summary
The Pipedrive integration has been fully implemented in code. However, several **manual setup steps** are required in Supabase to complete the integration.

## What's Been Completed ✅

### Backend Code
- ✅ `PipedriveClient` module created (`pipedrive_client.py`)
  - Uses httpx for async HTTP requests
  - Implements retry logic with exponential backoff
  - Validates API token connectivity
  
- ✅ `pipedrive_config` router with 7 endpoints:
  - GET/POST `/admin/pipedrive/config` - Configuration management
  - GET/POST `/admin/pipedrive/field-mappings` - Field mapping management
  - POST `/admin/pipedrive/field-mappings/{entity_type}/{field_name}` - Delete mappings
  - GET/POST `/admin/pipedrive/sync-schedules/{entity_type}` - Sync schedule management
  - POST `/admin/pipedrive/sync-now/{entity_type}` - Manual sync trigger
  - GET `/admin/pipedrive/sync-history/{entity_type}` - Sync history
  - GET `/admin/pipedrive/test-connection` - Connection test

- ✅ `pipedrive_data` router with 5 data display endpoints:
  - GET `/admin/pipedrive/data/employees` - Company employees
  - GET `/admin/pipedrive/data/clients` - Active clients
  - GET `/admin/pipedrive/data/potential-clients` - Potential clients
  - GET `/admin/pipedrive/data/organizations` - Organizations
  - GET `/admin/pipedrive/data/jobs` - Job listings (with 4-digit job codes)

- ✅ Database schema migrations defined in `migrations.py`
  - pipedrive_config table definition
  - pipedrive_sync_schedule table definition
  - pipedrive_sync_log table definition

- ✅ Frontend updated to display Pipedrive IDs:
  - JobsListPage: Shows "קוד משרה" (Job Code) with 4-digit format
  - EmployeesPage: Shows "קוד איש קשר" (Contact ID)
  - ClientsPage: Shows "קוד איש קשר" (Contact ID)
  - PotentialClientsPage: Shows "קוד איש קשר" (Contact ID)
  - OrganizationsPage: Shows "קוד ארגון" (Organization ID)

### API Token Input Fixed ✅
- Changed API token input field from `type="password"` to `type="text"`
- Allows paste functionality for API tokens
- Added monospace font styling for readability

## What Needs To Be Done Manually ⚠️

### Step 1: Execute Supabase SQL (Required)
Run these SQL commands in Supabase SQL Editor (Database → SQL Editor):

```sql
-- 1. Create pipedrive_config table
CREATE TABLE IF NOT EXISTS pipedrive_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_token TEXT NOT NULL,
    api_domain TEXT DEFAULT 'https://api.pipedrive.com',
    bot_user_id TEXT,
    is_active BOOLEAN DEFAULT false,
    last_validated_at TIMESTAMPTZ,
    validation_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Create pipedrive_sync_schedule table
CREATE TABLE IF NOT EXISTS pipedrive_sync_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT UNIQUE NOT NULL,
    sync_interval_minutes INT DEFAULT 30,
    sync_direction TEXT DEFAULT 'bidirectional',
    sync_enabled BOOLEAN DEFAULT true,
    filter_by_contact_type TEXT,
    filter_by_status TEXT,
    sync_days BOOLEAN[],
    sync_time TEXT,
    last_sync_at TIMESTAMPTZ,
    last_sync_status TEXT,
    next_scheduled_sync TIMESTAMPTZ,
    sync_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Create pipedrive_sync_log table
CREATE TABLE IF NOT EXISTS pipedrive_sync_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,
    sync_direction TEXT DEFAULT 'bidirectional',
    status TEXT NOT NULL,
    records_processed INT DEFAULT 0,
    records_created INT DEFAULT 0,
    records_updated INT DEFAULT 0,
    records_failed INT DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Add missing columns to contacts table (if they don't exist)
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS pipedrive_person_id INT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS pipedrive_org_id INT;

-- 5. Add missing column to jobs table (if it doesn't exist)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS pipedrive_deal_id INT;

-- 6. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_contacts_pipedrive_person_id ON contacts(pipedrive_person_id);
CREATE INDEX IF NOT EXISTS idx_contacts_pipedrive_org_id ON contacts(pipedrive_org_id);
CREATE INDEX IF NOT EXISTS idx_jobs_pipedrive_deal_id ON jobs(pipedrive_deal_id);
CREATE INDEX IF NOT EXISTS idx_pipedrive_sync_entity ON pipedrive_sync_schedule(entity_type);
CREATE INDEX IF NOT EXISTS idx_pipedrive_sync_log_entity ON pipedrive_sync_log(entity_type);
CREATE INDEX IF NOT EXISTS idx_pipedrive_sync_log_status ON pipedrive_sync_log(status);
CREATE INDEX IF NOT EXISTS idx_pipedrive_sync_log_started ON pipedrive_sync_log(started_at DESC);
```

### Step 2: Restart Backend Server
The backend needs to be restarted to load the new PipedriveClient module:
```bash
# Kill existing backend process if running
# Then restart:
npm run dev  # or your backend start command
```

### Step 3: Test Configuration
1. Navigate to http://localhost:5173/admin/pipedrive-config
2. Paste your Pipedrive API token
3. Click "Save Configuration"
4. Verify "Connection successful" message

### Step 4: Verify Tables Created Successfully
In Supabase Console, check:
- Table `pipedrive_config` created
- Table `pipedrive_sync_schedule` created
- Table `pipedrive_sync_log` created
- Columns added to `contacts`: pipedrive_person_id, pipedrive_org_id
- Columns added to `jobs`: pipedrive_deal_id

## Testing the Integration

### Test 1: Configuration Endpoint
```bash
curl -X GET http://localhost:8000/api/admin/pipedrive/config
# Expected: Returns current config or 500 if table doesn't exist
```

### Test 2: Connection Test
```bash
curl -X GET http://localhost:8000/api/admin/pipedrive/test-connection
# Expected: "Connection to Pipedrive successful" if token is valid
```

### Test 3: Data Display Pages
1. Navigate to "Employees" page → Should load and display contacts with contact IDs
2. Navigate to "Clients" page → Should display client contacts with IDs
3. Navigate to "Organizations" page → Should display org IDs (קוד ארגון)
4. Navigate to "Jobs" page → Should display job codes (קוד משרה) in blue #0001 format

## Expected Results After Setup ✅

### Configuration Page Working
- API token can be pasted into field
- "Save Configuration" submits token and validates with Pipedrive API
- "Test Connection" verifies stored token works
- Configuration stored in `pipedrive_config` table

### Data Display Pages
- All 5 pages load without errors
- Each shows Pipedrive sync status (last synced time)
- ID columns display in blue monospace format:
  - Jobs: #0001 format (4-digit deal ID)
  - Employees/Clients: 4-digit person IDs
  - Organizations: 4-digit organization IDs

### Sync Schedule
- `/admin/pipedrive/sync-schedules` endpoint returns entity sync settings
- Can customize sync intervals (hourly, daily, weekly)
- Sync history tracked in `pipedrive_sync_log` table

## File Changes Summary

| File | Changes |
|------|---------|
| `pipedrive_client.py` | NEW - Pipedrive API client |
| `db/migrations.py` | +3 new table definitions |
| `routers/admin/pipedrive_config.py` | +7 endpoints (already existed) |
| `routers/admin/pipedrive_data.py` | +5 endpoints (already existed) |
| `pages/admin/PipedriveConfigPage.tsx` | Input type password→text |
| `pages/admin/JobsListPage.tsx` | +Job Code column |
| `pages/admin/EmployeesPage.tsx` | +Contact ID column |
| `pages/admin/ClientsPage.tsx` | +Contact ID column |
| `pages/admin/PotentialClientsPage.tsx` | +Contact ID column |
| `pages/admin/OrganizationsPage.tsx` | +Organization ID column |

## Important Notes

1. **API Token Security**: The token is stored in plaintext in Supabase. Consider:
   - Using Supabase Vault for encryption (premium feature)
   - Limiting database access via RLS policies
   - Using environment variables for token (currently only supports DB storage)

2. **Sync Operations**: Manual sync endpoints are available but actual sync workers (Celery tasks) need to be implemented separately in Phase 7.

3. **Field Mappings**: The `pipedrive_field_mappings` table is already created but fields need to be mapped for deals, persons, and organizations.

4. **Bidirectional Sync**: Read operations implemented (data display). Write operations (sync back to Pipedrive) need implementation in Phase 7.

## Next Steps

After manual Supabase setup is complete:
1. ✅ Configuration page works → API token saved
2. ✅ Data display pages load → Shows synced data with IDs
3. ⏳ Phase 7: Implement actual data sync workers (Celery tasks)
4. ⏳ Phase 7: Implement field mapping validation
5. ⏳ Phase 7: Implement deal/person update operations

## Support

If you encounter issues:
1. Check Supabase console for table creation status
2. Verify `contacts` table has the new columns
3. Check backend logs for import errors
4. Ensure API token is valid (test with `curl`)

---
**Last Updated**: 2026-05-24
**Status**: Code Complete - Awaiting Manual Supabase Setup
