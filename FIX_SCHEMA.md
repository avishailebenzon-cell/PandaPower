# Fix Contacts Table Schema

## Problem
The `contacts` table has the wrong schema. It's missing the `contact_status` column and other required fields needed for Pipedrive sync.

## Current Schema (in database)
- id
- name
- email
- phone
- organization_id
- created_at
- pipedrive_person_id
- pipedrive_org_id

## Required Schema (for Pipedrive sync)
- id
- pipedrive_person_id
- **full_name** (currently named 'name')
- email
- phone
- organization_id
- **contact_status** ← MISSING - this is causing the sync to fail
- **professional_domain** ← MISSING
- **security_clearance_level** ← MISSING
- **pipedrive_last_synced_at** ← MISSING
- created_at
- **updated_at** ← MISSING

## How to Fix

### Option 1: Manual SQL Execution (Recommended)

1. Go to https://app.supabase.com
2. Log in and select the **PandaPower** project
3. Go to **SQL Editor** → Click **+ New Query**
4. Copy and paste the SQL below:

```sql
-- Fix contacts table schema
ALTER TABLE contacts RENAME COLUMN IF EXISTS name TO full_name;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS contact_status TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS professional_domain TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS security_clearance_level TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS pipedrive_last_synced_at TIMESTAMPTZ;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Add indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(contact_status);
CREATE INDEX IF NOT EXISTS idx_contacts_domain ON contacts(professional_domain);
CREATE INDEX IF NOT EXISTS idx_contacts_synced ON contacts(pipedrive_last_synced_at);
```

5. Click **Run** to execute the SQL
6. Verify the schema was updated successfully

### Option 2: Automatic Execution (via Python)

If you have the Supabase database password:

```bash
python3 << 'EOF'
import os
import sys
sys.path.insert(0, "apps/backend/src")

import psycopg2

# Set your database password
DB_PASSWORD = input("Enter Supabase database password: ")
PROJECT_ID = "xknzpurparakylocrnld"

conn_str = f"host=db.{PROJECT_ID}.supabase.co user=postgres password={DB_PASSWORD} dbname=postgres port=5432"

try:
    conn = psycopg2.connect(conn_str)
    conn.autocommit = True
    cursor = conn.cursor()
    
    migration = """
    ALTER TABLE contacts RENAME COLUMN IF EXISTS name TO full_name;
    ALTER TABLE contacts ADD COLUMN IF NOT EXISTS contact_status TEXT;
    ALTER TABLE contacts ADD COLUMN IF NOT EXISTS professional_domain TEXT;
    ALTER TABLE contacts ADD COLUMN IF NOT EXISTS security_clearance_level TEXT;
    ALTER TABLE contacts ADD COLUMN IF NOT EXISTS pipedrive_last_synced_at TIMESTAMPTZ;
    ALTER TABLE contacts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
    CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(contact_status);
    CREATE INDEX IF NOT EXISTS idx_contacts_domain ON contacts(professional_domain);
    CREATE INDEX IF NOT EXISTS idx_contacts_synced ON contacts(pipedrive_last_synced_at);
    """
    
    for stmt in migration.split(';'):
        stmt = stmt.strip()
        if stmt:
            cursor.execute(stmt)
            print(f"✓ Executed: {stmt[:70]}...")
    
    cursor.close()
    conn.close()
    print("\n✓ Schema migration completed!")
    
except Exception as e:
    print(f"✗ Error: {e}")
EOF
```

## After Fixing the Schema

Once the schema is fixed:

1. The Pipedrive sync will be able to write to all required columns
2. The backend sync worker should complete successfully
3. Contacts will be synced from Pipedrive with the correct data structure

To test the sync:

```bash
# Start the backend server
cd apps/backend
PYTHONPATH=src uv run python -m uvicorn pandapower.main:app --host 0.0.0.0 --port 8000

# In another terminal, run the sync
curl -X POST http://localhost:8000/admin/pipedrive/sync-now/persons
```

The sync should now complete successfully and sync all contacts from Pipedrive.
