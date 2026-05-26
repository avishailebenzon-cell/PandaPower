# PandaPower Phase 3 Session 7 - Complete Setup Checklist

## ✅ Completed: Code & Infrastructure

- [x] Backend FastAPI server with async support
- [x] Frontend React 18 with React Router v7
- [x] Celery worker with Beat scheduler (2-minute polling)
- [x] Database migrations schema (system_settings, email_intake_log, cv_files)
- [x] Email ingest worker with Azure Graph integration
- [x] Supabase storage manager with signed URL support
- [x] Admin dashboard with real-time email monitoring
- [x] Integrations configuration page
- [x] Mock authentication for development
- [x] React Query with server state management
- [x] TypeScript compilation ✓
- [x] Python syntax checks ✓
- [x] Frontend build verification ✓

---

## ⚙️ MANUAL SETUP REQUIRED (External Services)

### Phase 1: Supabase Project Creation (5-10 minutes)

These steps MUST be done in the Supabase web console at https://supabase.com

1. **Create Supabase Account**
   - Go to https://supabase.com
   - Sign up with email or GitHub
   - Verify email

2. **Create New Project**
   - Click "New Project"
   - Choose organization (or create one)
   - Enter project name: `pandapower-session7`
   - Choose password for database
   - Select region closest to you
   - Click "Create new project"
   - Wait for project to initialize (2-3 minutes)

3. **Get API Keys**
   - Go to Project Settings → API
   - Copy these 4 values:
     - **Project URL** → SUPABASE_URL
     - **anon public** → SUPABASE_ANON_KEY
     - **service_role** → SUPABASE_SERVICE_ROLE_KEY
     - Go to JWT Settings → copy JWT Secret → SUPABASE_JWT_SECRET

4. **Update Environment Files**

   **Backend** (`apps/backend/.env`):
   ```bash
   SUPABASE_URL=https://your-project-id.supabase.co
   SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   SUPABASE_JWT_SECRET=your-secret-here
   ```

   **Frontend** (`apps/frontend/.env.local`):
   ```bash
   VITE_SUPABASE_URL=https://your-project-id.supabase.co
   VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   VITE_API_BASE=http://localhost:8000
   ```

5. **Create Storage Bucket**
   - In Supabase Console, go to Storage
   - Click "New bucket"
   - Name: `cvs`
   - Make it Private
   - Click Create

6. **Run Database Migrations**
   
   Option A (Recommended - via API):
   ```bash
   cd apps/backend
   PYTHONPATH=src uv run python -m uvicorn pandapower.main:app --host 0.0.0.0 --port 8000 &
   sleep 2
   curl -X POST http://localhost:8000/admin/setup/migrations
   # Should see: {"system_settings":"success","email_intake_log":"success","cv_files":"success"}
   ```

   Option B (Manual SQL):
   - In Supabase Console, go to SQL Editor
   - Create new query
   - Copy the SQL from `apps/backend/src/pandapower/db/migrations.py` → SCHEMA_MIGRATIONS
   - Paste each table creation SQL and execute

7. **Initialize System Settings**
   ```bash
   curl -X POST http://localhost:8000/admin/setup/init-settings
   # Response: {"status":"success","settings_initialized":6}
   ```

---

### Phase 2: Azure Application Registration (10-15 minutes)

These steps MUST be done in Azure Portal: https://portal.azure.com

1. **Register Application**
   - Go to https://portal.azure.com
   - Search for "Azure Active Directory"
   - Go to App Registrations
   - Click "New registration"
   - Name: `PandaPower-EmailIntake`
   - Supported account types: "Single tenant" (your org only)
   - Redirect URI: (leave blank for now - we're using client credentials flow)
   - Click Register

2. **Create Client Secret**
   - In app registration, go to "Certificates & secrets"
   - Click "New client secret"
   - Description: `Email intake pipeline`
   - Expires: 24 months
   - Click Add
   - **Copy the secret value immediately** (won't show again)
   - **Copy the Secret ID** for reference

3. **Get Application IDs**
   - In app registration, go to "Overview"
   - Copy:
     - **Application (client) ID** → AZURE_APP_CLIENT_ID
     - **Directory (tenant) ID** → AZURE_TENANT_ID

4. **Grant API Permissions**
   - In app registration, go to "API permissions"
   - Click "Add a permission"
   - Select "Microsoft Graph"
   - Choose "Application permissions" (not Delegated)
   - Search and add:
     - `Mail.Read` (read all mailboxes)
     - `Files.Read` (read attachments)
     - `User.Read.All` (read user info)
   - Click "Grant admin consent for [Org]"

5. **Update Environment File**
   
   Update `apps/backend/.env`:
   ```bash
   AZURE_TENANT_ID=your-tenant-id-here
   AZURE_APP_CLIENT_ID=your-app-id-here
   AZURE_CLIENT_SECRET=your-client-secret-here
   AZURE_TARGET_MAILBOX=jobs@yourdomain.com
   ```

---

## 🚀 Starting the Services

Once Supabase and Azure are configured:

### Terminal 1: Backend Server
```bash
cd apps/backend
PYTHONPATH=src uv run python -m uvicorn pandapower.main:app --host 0.0.0.0 --port 8000
# Should see: "Uvicorn running on http://0.0.0.0:8000"
```

### Terminal 2: Celery Worker (for background email polling)
```bash
cd apps/backend
PYTHONPATH=src uv run celery -A pandapower.workers.celery_app worker --beat --loglevel=info
# Should see: "ready to accept tasks"
```

### Terminal 3: Frontend Dev Server
```bash
cd apps/frontend
npm run dev
# Should see: "Local:   http://localhost:5173/"
```

---

## ✅ Verification Steps

### 1. Health Check
```bash
curl http://localhost:8000/health
# Response: {"status":"ok"}
```

### 2. API Authentication
```bash
curl http://localhost:8000/api/me
# Response: {"email":"admin@test.com","role":"admin"}
```

### 3. Frontend Access
- Open http://localhost:5173
- Should see: PandaPower header + sidebar + Dashboard
- No login required (development mock auth)

### 4. Admin Dashboard
- Navigate to `/admin/integrations`
- Should see: Connection Settings block + Backfill Control + Live Status
- Fill in Azure credentials and click "Test Connection"
- Should see: "✓ Connection successful"

### 5. Email Intake Monitoring
- Navigate to `/admin/email-intake`
- Should see: KPI cards + Live Stream timeline + History table
- After configuring, emails arrive every 2 minutes via Celery Beat

---

## 🔧 Troubleshooting

### "Connection refused" on backend
- Ensure backend is running on port 8000
- Check: `lsof -i :8000`

### "SUPABASE_URL not set" error
- Verify `.env` file has SUPABASE_URL
- Restart backend after changing .env

### "Azure credentials invalid"
- Verify tenant_id, client_id, client_secret in .env are correct
- Check that app registration has Email permissions
- Ensure AZURE_TARGET_MAILBOX is a valid mailbox (e.g., jobs@domain.com)

### Celery task not running
- Verify celery worker is running (Terminal 2)
- Check logs for errors
- Ensure system_settings table is populated with Azure config

### Frontend showing "Unauthorized"
- This shouldn't happen in dev (mock auth is enabled)
- If it does: clear localStorage and refresh
- Check useAuth.ts - should return mock user in dev

---

## 📋 Quick Reference: File Locations

- Backend config: `apps/backend/.env`
- Frontend config: `apps/frontend/.env.local`
- Backend startup: `apps/backend/src/pandapower/main.py`
- Workers: `apps/backend/src/pandapower/workers/`
- Migrations: `apps/backend/src/pandapower/db/migrations.py`
- Admin UI: `apps/frontend/src/pages/admin/`
- API docs: http://localhost:8000/docs (Swagger)

---

## 🎯 Next Steps After Setup

1. **Test Email Intake Loop**
   - Send test email to AZURE_TARGET_MAILBOX with PDF attachment
   - Wait 2 minutes for polling (or click "Run Now" in UI)
   - Should appear in `/admin/email-intake` dashboard

2. **Monitor Storage**
   - Files stored at: `cvs/outlook/{year}/{month}/{message_id}/{filename}`
   - View in Supabase Storage bucket `cvs`

3. **Phase 8: Email Parsing**
   - Add PDF extraction library
   - Parse CV content
   - Update `parse_status` from "pending" to "extracted"

4. **Production Deployment**
   - Use real Supabase account (not free tier for production)
   - Set up proper error logging and monitoring
   - Configure RLS policies on Supabase tables
   - Use Redis instead of memory:// for Celery broker
   - Deploy with Docker/K8s

---

## 📊 Project Structure

```
PandaPower/
├── apps/
│   ├── backend/
│   │   ├── src/pandapower/
│   │   │   ├── main.py (FastAPI app)
│   │   │   ├── workers/ (Celery tasks)
│   │   │   ├── integrations/ (Azure, Supabase)
│   │   │   ├── routers/ (API endpoints)
│   │   │   └── db/ (Migrations)
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── frontend/
│       ├── src/
│       │   ├── pages/admin/ (Dashboard pages)
│       │   ├── hooks/ (useAuth, useMe)
│       │   ├── lib/ (Supabase, React Query)
│       │   └── components/ (Layout, Routes)
│       └── package.json
└── SETUP_CHECKLIST.md (this file)
```

---

## ✨ What's Working Now

✅ Backend API with async/await  
✅ Frontend React UI with routing  
✅ Celery background workers  
✅ Database schema design  
✅ Azure Graph integration code  
✅ Real-time email monitoring UI  
✅ Admin configuration interface  
✅ Supabase Storage with signed URLs  

## ⏳ What's Next

⏳ Supabase project creation  
⏳ Azure app registration  
⏳ Running migrations  
⏳ Testing end-to-end email intake  
⏳ Phase 8: CV parsing & extraction  

---

**Status: Phase 7 Backend/Frontend Complete | Awaiting External Service Setup**
