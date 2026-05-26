# 🚀 PandaPower - Access Information

## System Status: ✅ READY

Both backend and frontend are running and ready to use.

---

## Access URLs

### Frontend (React Dashboard)
```
http://localhost:5173
```
- Real-time admin dashboard
- Integrations configuration
- Email intake monitoring
- Pipedrive sync monitoring

### Backend API
```
http://localhost:8000
```
- Health check: `GET /`
- API documentation: `/docs` (Swagger UI)

---

## Key Endpoints

### Pipedrive Sync Management
```bash
# Get sync history
GET http://localhost:8000/admin/pipedrive/sync-history/persons?limit=5

# Check current config
GET http://localhost:8000/admin/pipedrive/config

# Trigger incremental sync (manual)
POST http://localhost:8000/admin/pipedrive/sync-incremental/persons?minutes_back=60

# Trigger full sync (manual)
POST http://localhost:8000/admin/pipedrive/sync-now/persons
```

### Test Connection
```bash
# Verify Pipedrive API is working
GET http://localhost:8000/admin/pipedrive/test-connection
```

---

## Running Services

### Frontend Dev Server
- **Port**: 5173
- **Status**: Running
- **Command**: `npm run dev`
- **Location**: `/Users/Avishai/Documents/Claude/Projects/PandaPower/apps/frontend`

### Backend API Server
- **Port**: 8000
- **Status**: Running
- **Command**: `python3 -m uvicorn pandapower.main:app --host 0.0.0.0 --port 8000`
- **Location**: `/Users/Avishai/Documents/Claude/Projects/PandaPower/apps/backend`

---

## Stop Services

```bash
# Kill frontend
pkill -f "npm run dev" || lsof -ti:5173 | xargs kill -9

# Kill backend
pkill -f "uvicorn pandapower.main" || lsof -ti:8000 | xargs kill -9
```

---

## Restart Services

```bash
# Kill all
pkill -f "npm run dev"
pkill -f "uvicorn"
sleep 2

# Restart backend
export PYTHONPATH=/Users/Avishai/Documents/Claude/Projects/PandaPower/apps/backend/src:$PYTHONPATH
cd /Users/Avishai/Documents/Claude/Projects/PandaPower/apps/backend
python3 -m uvicorn pandapower.main:app --host 0.0.0.0 --port 8000 > /tmp/backend.log 2>&1 &

# Restart frontend
cd /Users/Avishai/Documents/Claude/Projects/PandaPower/apps/frontend
npm run dev > /tmp/frontend.log 2>&1 &
```

---

## Features Available

### ✅ Pipedrive Sync (COMPLETE)
- Full sync: Batches 6,792 contacts (no timeouts)
- Incremental sync: Syncs recent changes in < 2 seconds
- Hourly automation: Scheduled at :07 every hour
- Non-blocking: System stays responsive
- Monitoring: Full audit trail in database

### ✅ Email Intake (Phase 7)
- Azure Graph integration
- Celery background processing
- Supabase file storage
- Admin dashboard monitoring

### ✅ CV Parsing (Phase 8)
- Claude API parsing
- 10 structured fields extracted
- Bilingual support (EN + HE)
- Confidence scoring

### ✅ Candidate Management (Phase 9)
- Skill normalization
- Candidate database
- API endpoints for search/filtering

---

## Development

### Frontend Logs
```bash
tail -f /tmp/frontend.log
```

### Backend Logs
```bash
tail -f /tmp/backend.log
```

### Check Ports
```bash
lsof -i :5173    # Frontend
lsof -i :8000    # Backend
```

---

## Next Steps

1. **Open Frontend**: http://localhost:5173
2. **Check Sync Status**: View sync history in dashboard
3. **Monitor**: Watch for hourly incremental syncs
4. **Deploy**: Ready for production after any additional setup

---

**Status**: ✅ All systems operational  
**Last Updated**: 2026-05-24  
**Services**: Both frontend and backend running
