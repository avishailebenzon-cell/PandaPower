# PandaPower Session 7 - Setup Guide

## 🎯 Overview
Session 7 implements email intake pipeline from Microsoft Graph API through Supabase Storage with real-time admin monitoring dashboard.

## ⚙️ Backend Setup

### 1. Environment Variables
Copy `.env.example` to `.env` and fill in:

```bash
# Supabase (Required)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_SECRET=...

# Azure (For email integration)
AZURE_TENANT_ID=your-tenant-id
AZURE_APP_CLIENT_ID=your-app-client-id
AZURE_CLIENT_SECRET=your-client-secret
AZURE_TARGET_MAILBOX=jobs@company.com
```

### 2. Start Backend Server
```bash
cd apps/backend
PYTHONPATH=src uv run python -m uvicorn pandapower.main:app --host 0.0.0.0 --port 8000
```

### 3. Database Setup
```bash
# Run migrations via API (optional, can be manual in Supabase console)
curl -X POST http://localhost:8000/admin/setup/migrations
```

### 4. Start Celery Worker (Optional - for scheduled polling)
```bash
PYTHONPATH=src uv run celery -A pandapower.workers.celery_app worker --beat --loglevel=info
```

## 🎨 Frontend Setup

### 1. Environment Variables
```bash
# apps/frontend/.env.local
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
VITE_API_BASE=http://localhost:8000
```

### 2. Install & Start Frontend
```bash
cd apps/frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:5173

## 📚 API Endpoints

### Health Check
```bash
GET /health
GET /api/me
```

### Email Admin
```bash
POST /admin/email/test-connection
  {
    "tenant_id": "...",
    "client_id": "...",
    "client_secret": "...",
    "target_mailbox": "jobs@company.com"
  }

POST /admin/email/configure
  {
    "tenant_id": "...",
    "client_id": "...",
    "client_secret": "...",
    "target_mailbox": "..."
  }

POST /admin/email/run-now
POST /admin/email/start-backfill
  { "start_date": "2024-01-01" }

GET /admin/email/status
GET /admin/email/logs?status=success&limit=50
GET /admin/email/signed-url/{cv_file_id}
```

## 🗄️ Database Schema

Required tables (auto-created via migrations):

- `system_settings` - Configuration storage
- `email_intake_log` - Email processing history
- `cv_files` - Downloaded CV file metadata

## 🚀 Testing

```bash
cd apps/backend
PYTHONPATH=src uv run pytest tests/ -v
```

## 🔄 Workflow

1. Admin visits `/admin/integrations`
2. Enters Azure credentials → Test Connection → Configure
3. Optionally starts Backfill for historical emails
4. System fetches emails every 2 minutes (via Celery Beat)
5. For each email with CV attachments:
   - Downloads from Azure
   - SHA-256 deduplication check
   - Uploads to Supabase Storage at `cvs/outlook/{year}/{month}/{message_id}/{filename}`
   - Records in `cv_files` table with parse_status=pending
6. Admin monitors in real-time on `/admin/email-intake`
   - Live stream of processed emails
   - Historical table with pagination
   - KPI metrics updated every 5 seconds

## ⚠️ Known Limitations (Phase 7)

- Uses test/mock auth (no real session management)
- Requires manual Supabase setup (no CLI automation)
- Celery uses in-memory broker (not production-ready)
- No error recovery/retry for failed uploads
- No email parsing or CV extraction yet

## 🔐 Security Notes

- Never commit `.env` with real credentials
- Supabase RLS rules should restrict access to authenticated users
- Azure credentials rotated regularly
- CV files stored in private bucket (not public)
- Signed URLs expire after 7 days
