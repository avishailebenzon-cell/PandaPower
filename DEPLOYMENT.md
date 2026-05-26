# PandaPower Cloud Deployment Guide

## Architecture

```
┌─────────────────────────────────────┐
│    Vercel (Frontend)                │
│  - React/Vite Application           │
│  - Static + Serverless Functions    │
└─────────────┬───────────────────────┘
              │ HTTP/REST API Calls
              ↓
┌─────────────────────────────────────┐
│  Render/Railway (Backend)           │
│  - FastAPI Server (Uvicorn)         │
│  - Celery Worker                    │
│  - Celery Beat Scheduler            │
└─────────────┬───────────────────────┘
              │ Database
              ↓
┌─────────────────────────────────────┐
│  Supabase (PostgreSQL Database)     │
│  - Jobs, Candidates, Matches        │
│  - Agent Logs, Runtime State        │
└─────────────────────────────────────┘
```

## Step 1: Deploy Frontend to Vercel

### 1.1 Connect Git Repository
```bash
cd /Users/Avishai/Documents/Claude/Projects/PandaPower
git remote -v
# If not already a git repo, initialize it
git init
git add .
git commit -m "Initial commit - PandaPower system"
```

### 1.2 Deploy to Vercel
```bash
npm install -g vercel
cd /Users/Avishai/Documents/Claude/Projects/PandaPower/apps/frontend
vercel --prod
```

**During deployment, set:**
- **Project Name:** `pandapower-frontend`
- **Root Directory:** `./apps/frontend`
- **Build Command:** `npm run build`
- **Output Directory:** `dist`
- **Environment Variables:**
  ```
  VITE_API_URL=https://pandapower-backend.onrender.com
  ```

### 1.3 Save Your Vercel URL
After deployment, you'll get a URL like: `https://pandapower-frontend.vercel.app`

---

## Step 2: Deploy Backend to Render.com (Recommended for FastAPI + Celery)

### 2.1 Create Render Account
1. Go to https://render.com
2. Sign up with GitHub
3. Connect your GitHub repository

### 2.2 Create Web Service for FastAPI

1. **New → Web Service**
2. **Environment:**
   - Name: `pandapower-backend`
   - Region: `Northern Virginia (us-east-1)`
   - Branch: `main`

3. **Build & Deploy:**
   - Runtime: `Python 3.11`
   - Build Command:
     ```bash
     pip install -r requirements.txt
     ```
   - Start Command:
     ```bash
     cd apps/backend && python -m uvicorn pandapower.main:app --host 0.0.0.0 --port 8000
     ```

4. **Environment Variables:**
   ```
   PYTHONPATH=/app/apps/backend/src
   SUPABASE_URL=<from .env>
   SUPABASE_KEY=<from .env>
   SUPABASE_JWT_SECRET=<from .env>
   ANTHROPIC_API_KEY=<from .env>
   REDIS_URL=redis://<render-redis-url>
   ```

5. **Deploy!**

### 2.3 Create Background Worker for Celery Worker

1. **New → Background Worker**
2. **Environment:**
   - Name: `pandapower-worker`
   - Branch: `main`
   - Runtime: `Python 3.11`

3. **Build Command:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start Command:**
   ```bash
   cd apps/backend && celery -A pandapower.workers.celery_app worker -l info
   ```

5. **Same environment variables as Web Service**

### 2.4 Create Cron Job for Celery Beat

1. **New → Cron Job**
2. **Environment:**
   - Name: `pandapower-beat`
   - Schedule: `0 * * * *` (every hour - adjust as needed)
   - Start Command:
     ```bash
     cd apps/backend && celery -A pandapower.workers.celery_app beat -l info
     ```

3. **Same environment variables**

---

## Step 3: Alternative: Deploy to Railway.app

### 3.1 Railway Setup (Simpler than Render)

```bash
npm install -g @railway/cli
railway login

# In backend directory
cd apps/backend
railway init
railway add
# Select: PostgreSQL (if needed), Redis, Python
```

### 3.2 Configure services.json
```json
{
  "backend": {
    "build": "pip install -r requirements.txt",
    "start": "python -m uvicorn pandapower.main:app --host 0.0.0.0 --port $PORT"
  },
  "worker": {
    "build": "pip install -r requirements.txt",
    "start": "celery -A pandapower.workers.celery_app worker -l info"
  }
}
```

### 3.3 Deploy
```bash
railway up --detach
```

---

## Step 4: Post-Deployment Verification

### Check Frontend
```bash
curl https://pandapower-frontend.vercel.app
# Should return HTML
```

### Check Backend Health
```bash
curl https://pandapower-backend.onrender.com/health
# Should return: {"status":"ok","service":"pandapower-backend"}
```

### Check System Status
```bash
curl https://pandapower-backend.onrender.com/admin/agent-matching/system-status | jq .
# Should return full system status with agent data
```

---

## Step 5: Environment Variables

### Required for Backend Deployment

1. **Supabase Credentials** (from .env):
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `SUPABASE_JWT_SECRET`

2. **Anthropic API**:
   - `ANTHROPIC_API_KEY`

3. **Email Service** (Resend):
   - `RESEND_API_KEY` (for alert notifications)

4. **Celery**:
   - `REDIS_URL` (for message broker)

5. **Frontend API URL**:
   - `VITE_API_URL=https://pandapower-backend.onrender.com`

---

## Step 6: Monitoring & Logs

### Vercel
- Dashboard: https://vercel.com/dashboard
- Logs: `vercel logs <project-name> --prod`

### Render
- Dashboard: https://render.com
- Logs: Available in web interface

### Railway
- Dashboard: https://railway.app
- Logs: `railway logs`

---

## Troubleshooting

### Frontend can't reach Backend
- Check `VITE_API_URL` environment variable
- Verify backend service is running
- Check CORS settings in `pandapower/main.py`

### Celery tasks not running
- Verify Redis URL is correct
- Check worker logs in Render/Railway dashboard
- Ensure environment variables are set

### Database connection errors
- Verify `SUPABASE_URL` and `SUPABASE_KEY`
- Check network connectivity from deployed service
- Review Supabase logs

---

## Cost Estimation

| Service | Free Tier | Recommended Plan |
|---------|-----------|------------------|
| Vercel | ✅ Included | Pro: $20/mo |
| Render | ✅ 100 free hours/mo | $7/mo per service |
| Railway | ✅ $5 free credit | Pay as you go |
| Supabase | ✅ Free tier | Pro: $25/mo |
| **Total** | **Free** | **~$52-77/mo** |

---

## Next Steps

1. [ ] Prepare GitHub repository
2. [ ] Gather environment variables from .env
3. [ ] Create Vercel account and deploy frontend
4. [ ] Create Render/Railway account and deploy backend
5. [ ] Test all endpoints
6. [ ] Configure custom domain (optional)
7. [ ] Set up monitoring & alerts

