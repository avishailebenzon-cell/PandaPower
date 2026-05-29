# PandaPower Backend - Continuous Operation Guide

## Problem Solved ✅

The system was not running continuously because **two critical services were not active**:

1. **Uvicorn API Server** - FastAPI backend server on port 8000
2. **Celery Worker + Beat** - Background job scheduler and executor

Without these, background tasks (email processing, Pipedrive syncing, campaign outreach) would not execute.

## Services Overview

### 1. Uvicorn Server (Port 8000)
- **Purpose**: REST API endpoints for the frontend and internal services
- **Tasks**: Handles all API requests from React frontend
- **Health Check**: `curl http://localhost:8000/health`

### 2. Celery Worker + Beat
- **Purpose**: Executes scheduled background tasks continuously
- **Key Tasks**:
  - Email intake processing (every 2 minutes)
  - Pipedrive sync (hourly)
  - Campaign message sending (rate-limited)
  - Webhook processing
  - Database cleanup and maintenance
- **Broker**: Redis (localhost:6379)
- **Database**: PostgreSQL (defined in .env)

## Quick Start (Recommended: tmux version)

### Option A: Full-Featured (tmux with multiple windows)

```bash
cd /Users/Avishai/Documents/Claude/Projects/PandaPower
./start-backend.sh
```

This will:
- Create a tmux session named `pandapower`
- Start Uvicorn in window 0 (uvicorn)
- Start Celery in window 1 (celery)
- Display commands for managing the services

**To manage:**
```bash
# Attach to view logs
tmux attach-session -t pandapower

# Switch between windows
tmux select-window -t pandapower:0  # Uvicorn
tmux select-window -t pandapower:1  # Celery

# Stop everything
tmux kill-session -t pandapower
```

### Option B: Simple Background (no tmux)

```bash
cd /Users/Avishai/Documents/Claude/Projects/PandaPower
./start-backend-simple.sh
```

This starts both services in the background with logs in `apps/backend/logs/`

## Manual Start (for development)

### Terminal 1: Uvicorn Server
```bash
cd apps/backend
PYTHONPATH=src /opt/homebrew/bin/python3 -m uvicorn pandapower.main:app \
    --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2: Celery Worker + Beat
```bash
cd apps/backend
PYTHONPATH=src /opt/homebrew/bin/python3 -m celery -A pandapower.workers.celery_app \
    worker --beat --loglevel=info
```

## Verify Services Are Running

### Check API Server
```bash
curl http://localhost:8000/health
# Expected: {"status": "ok"}
```

### Check Celery Tasks
The Celery worker window should show:
- Scheduled tasks (Beat schedule output)
- Running tasks
- Task completions

### Monitor Frontend
Frontend automatically connects to `http://localhost:8000/api/*`
- Check browser console for API errors
- Admin dashboard shows realtime email processing and pipeline status

## Infrastructure Requirements

These must be running for the backend to work:

### PostgreSQL
```bash
docker run -d --name postgres \
  -e POSTGRES_PASSWORD=pandapower_dev \
  -e POSTGRES_USER=pandapower \
  -e POSTGRES_DB=pandapower \
  -p 5432:5432 \
  postgres:16-alpine
```

### Redis (Celery broker)
```bash
docker run -d --name redis \
  -p 6379:6379 \
  redis:7-alpine
```

Or use the included docker-compose:
```bash
docker-compose up -d
```

## Important Tasks Running Continuously

### Email Processing Pipeline
- **Schedule**: Every 2 minutes (via Celery Beat)
- **Task**: `pandapower.workers.tasks.process_email_intake`
- **What it does**:
  1. Fetches new emails from Azure
  2. Downloads CV attachments
  3. Deduplicates by SHA-256
  4. Uploads to Supabase Storage
  5. Records in database for admin dashboard

### Pipedrive Sync
- **Schedule**: Hourly (via Celery Beat)
- **Task**: `pandapower.workers.tasks.sync_pipedrive_data`
- **What it does**:
  1. Fetches deals, persons, organizations from Pipedrive
  2. Normalizes data
  3. Syncs to Supabase
  4. Updates job skills and candidates

### Campaign Message Sending
- **Trigger**: User clicks "Send" in admin UI
- **Task**: `pandapower.workers.tasks.send_campaign_messages`
- **Rate Limit**: 1 message every 3 seconds
- **What it does**:
  1. Fetches campaign configuration
  2. Processes messages with placeholders
  3. Sends via SMS/WhatsApp
  4. Tracks delivery status

## Troubleshooting

### Services won't start
1. Check dependencies: `pip install -r apps/backend/requirements.txt`
2. Verify Python version: `python3 --version` (should be 3.11+)
3. Check `.env` file exists in `apps/backend/`

### Email processing not working
1. Verify Celery is running: Check window 1 in tmux
2. Check Redis is running: `redis-cli ping`
3. Check logs: `tail -f apps/backend/logs/celery.log`

### API errors
1. Check Uvicorn is running: `curl http://localhost:8000/health`
2. Check logs: `tail -f apps/backend/logs/uvicorn.log`
3. Verify `.env` has all required variables

### High CPU usage from Celery
- This is normal during email backfill or campaign sending
- Celery processes multiple emails/messages in parallel
- Monitor with: `tail -f apps/backend/logs/celery.log`

## Production Deployment

For cloud deployment (Render.com, AWS, etc.):

1. **Environment Variables**: Set in platform settings
2. **Procfile** (for Render):
   ```
   web: gunicorn -w 4 -b 0.0.0.0:$PORT pandapower.main:app
   worker: celery -A pandapower.workers.celery_app worker --beat --loglevel=info
   ```
3. **Redis**: Use platform's managed Redis
4. **PostgreSQL**: Use platform's managed PostgreSQL

## Next Steps

1. **Start the backend**:
   ```bash
   cd /Users/Avishai/Documents/Claude/Projects/PandaPower
   ./start-backend.sh
   ```

2. **Verify it's working**:
   - Open http://localhost:8000/health
   - Check Celery window for scheduled tasks

3. **Monitor admin dashboard**:
   - Frontend at http://localhost:5173
   - Admin dashboard shows real-time email and campaign status

4. **Keep running**:
   - Services will continue running in tmux session
   - Close terminal without killing the session: Ctrl+B then D
   - Reconnect anytime: `tmux attach-session -t pandapower`

---

**System is now ready for continuous operation!** 🚀
