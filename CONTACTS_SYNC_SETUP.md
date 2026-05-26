# Pipedrive Contacts Sync Implementation

## Overview
Complete contacts synchronization from Pipedrive with categorization into three types:
- **Employees** (עובדים) - persons linked to company organization
- **Clients** (לקוחות) - persons linked to won/completed deals
- **Potential Clients** (לקוחות פוטנציאלים) - all other persons

## Files Created/Modified

### 1. Core Sync Worker
- **File**: `apps/backend/src/pandapower/workers/pipedrive_contacts_sync.py`
- **Function**: `sync_pipedrive_contacts()`
- **Features**:
  - Fetches all persons from Pipedrive API
  - Categorizes contacts by relationship type
  - Batch processing (500 contacts per batch)
  - Update-or-insert pattern for database consistency
  - Comprehensive logging and error tracking

### 2. Database Migration
- **File**: `apps/backend/migrations/002_create_contact_tables.sql`
- **Tables Created**:
  - `public.employees` - עובדים
  - `public.clients` - לקוחות
  - `public.potential_clients` - לקוחות פוטנציאלים
- **Features**:
  - Unique constraint on `pipedrive_person_id`
  - Indexed fields: person_id, email, created_at
  - RLS enabled for security
  - All contact info fields: name, email, phone, org_id

### 3. API Endpoints
- **File**: `apps/backend/src/pandapower/routers/admin/pipedrive_sync.py`
- **Endpoints**:
  - `POST /admin/pipedrive-sync/contacts` - Manually trigger full sync
  - `GET /admin/pipedrive-sync/contacts/status` - View sync status and counts

### 4. Data Display Endpoints
- **File**: `apps/backend/src/pandapower/routers/admin/pipedrive_data.py` (Updated)
- **Endpoints**:
  - `GET /admin/pipedrive/data/employees` - List all employees
  - `GET /admin/pipedrive/data/clients` - List all clients
  - `GET /admin/pipedrive/data/potential-clients` - List potential clients
- **Features**:
  - Pagination support
  - Search filtering
  - Sorting by name, email, or date
  - Last sync timestamp

### 5. Celery Task Integration
- **Files Modified**:
  - `apps/backend/src/pandapower/workers/tasks.py` - Added `sync_pipedrive_contacts_task()`
  - `apps/backend/src/pandapower/workers/celery_app.py` - Added to beat schedule (hourly)

### 6. Application Integration
- **File**: `apps/backend/src/pandapower/main.py` (Updated)
- **Change**: Added `pipedrive_sync` router to FastAPI app

## Contact Categorization Logic

```python
1. Check for explicit contact_type field
2. If linked to won deals → client
3. If linked to organization → employee
4. Otherwise → potential_client (default)
```

## Setup Instructions

### Step 1: Run Database Migration
Execute the migration SQL against Supabase:
```bash
# Copy contents of apps/backend/migrations/002_create_contact_tables.sql
# Go to Supabase Dashboard → SQL Editor
# Create new query and paste the SQL
# Execute
```

### Step 2: Start Backend Server
```bash
cd apps/backend
python -m uvicorn src.pandapower.main:app --reload --port 8000
```

### Step 3: Trigger Manual Sync (Optional)
```bash
# Option A: Using curl
curl -X POST http://localhost:8000/admin/pipedrive-sync/contacts

# Option B: Check status
curl http://localhost:8000/admin/pipedrive-sync/contacts/status

# Option C: View employees
curl http://localhost:8000/admin/pipedrive/data/employees

# Option D: View clients
curl http://localhost:8000/admin/pipedrive/data/clients

# Option E: View potential clients
curl http://localhost:8000/admin/pipedrive/data/potential-clients
```

### Step 4: Automatic Scheduling
The sync runs automatically every hour via Celery Beat when the server is running.

## Database Schema

### employees table (עובדים)
```sql
id (UUID, PK)
pipedrive_person_id (INTEGER, UNIQUE)
name (VARCHAR)
email (VARCHAR)
phone (VARCHAR)
org_id (INTEGER) -- Company organization
contact_type (VARCHAR) = 'employee'
notes (TEXT)
created_at (TIMESTAMP)
updated_at (TIMESTAMP)
pipedrive_last_synced_at (TIMESTAMP)
```

### clients table (לקוחות)
```sql
id (UUID, PK)
pipedrive_person_id (INTEGER, UNIQUE)
name (VARCHAR)
email (VARCHAR)
phone (VARCHAR)
org_id (INTEGER)
contact_type (VARCHAR) = 'client'
revenue_potential (DECIMAL)
notes (TEXT)
created_at (TIMESTAMP)
updated_at (TIMESTAMP)
pipedrive_last_synced_at (TIMESTAMP)
```

### potential_clients table (לקוחות פוטנציאלים)
```sql
id (UUID, PK)
pipedrive_person_id (INTEGER, UNIQUE)
name (VARCHAR)
email (VARCHAR)
phone (VARCHAR)
org_id (INTEGER)
contact_type (VARCHAR) = 'potential_client'
interest_level (VARCHAR)
source (VARCHAR)
notes (TEXT)
created_at (TIMESTAMP)
updated_at (TIMESTAMP)
pipedrive_last_synced_at (TIMESTAMP)
```

## Monitoring

All sync operations are logged in `pipedrive_sync_log` table with:
- `entity_type`: "persons"
- `sync_direction`: "inbound"
- `status`: "completed" or "failed"
- `total_records`: Total persons fetched
- `created_count`: Total contacts synced
- `failed_count`: Number of errors
- `duration_ms`: Sync duration in milliseconds
- `details`: Breakdown by category (employees, clients, potential_clients)

## Testing

### Manual Full Sync
```bash
POST /admin/pipedrive-sync/contacts
```

Response:
```json
{
  "status": "success",
  "message": "Contacts sync completed",
  "timestamp": "2026-05-25T...",
  "total_fetched": 6794,
  "synced_employees": ...,
  "synced_clients": ...,
  "synced_potential_clients": ...,
  "errors": []
}
```

### View Sync Status
```bash
GET /admin/pipedrive-sync/contacts/status
```

Response:
```json
{
  "status": "success",
  "last_sync": { ... },
  "current_counts": {
    "employees": 1234,
    "clients": 567,
    "potential_clients": 4993
  },
  "timestamp": "2026-05-25T..."
}
```

## Expected Results

Based on previous analysis of Pipedrive data:
- ~6,794 total persons in Pipedrive
- Distribution depends on deal linkage and organization assignment
- Initial sync may take 30-60 seconds for large datasets

## Troubleshooting

### No data appearing?
1. Check if backend server is running
2. Verify Supabase tables were created: `SELECT * FROM employees LIMIT 1;`
3. Check logs: `docker logs backend` or check console output

### Sync taking too long?
1. Large dataset (6,794+ persons) requires patience
2. Batch processing handles this gracefully
3. Monitor via sync status endpoint

### Wrong categorization?
1. Review contact categorization logic in `pipedrive_contacts_sync.py`
2. Update `_categorize_contact()` function if needed
3. Re-run sync after changes

## Next Steps (Optional Enhancements)

1. Add custom field mapping for contact_type
2. Implement incremental sync (only recently modified persons)
3. Add contact relationship tracking
4. Implement two-way sync back to Pipedrive
5. Add contact interaction history tracking
