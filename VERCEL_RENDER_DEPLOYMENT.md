# Vercel + Render Deployment Checklist

## ✅ Pre-Deployment Checklist

### Environment Variables Ready
From your `.env` file, collect:

- [ ] `SUPABASE_URL` - Your Supabase project URL
- [ ] `SUPABASE_KEY` - Supabase service role key
- [ ] `SUPABASE_JWT_SECRET` - JWT secret from Supabase
- [ ] `ANTHROPIC_API_KEY` - Claude API key
- [ ] `RESEND_API_KEY` - Email service (from resend.com)
- [ ] GitHub account created (https://github.com)

---

## 🚀 STEP 1: Deploy Frontend to Vercel (10 minutes)

### 1.1 Connect to GitHub (Do this first!)

Before anything, push code to GitHub:

```bash
# If you created a new GitHub repo, run:
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/pandapower.git
git push -u origin main

# Or if the remote already exists:
git push -u origin main
```

**Verify:** Go to https://github.com/YOUR-USERNAME/pandapower and confirm code is there.

### 1.2 Deploy Frontend to Vercel

```bash
# Install Vercel CLI
npm install -g vercel

# Login to Vercel
vercel login

# Deploy from frontend directory
cd /Users/Avishai/Documents/Claude/Projects/PandaPower/apps/frontend
vercel --prod
```

**During the deployment, Vercel will ask:**

| Question | Answer |
|----------|--------|
| Set up and deploy? | `Y` |
| Which scope? | Your Vercel account |
| Link to existing project? | `N` |
| Project name | `pandapower-frontend` |
| Directory | `./` (current) |
| Want to override? | `Y` |

### 1.3 Add Environment Variables to Vercel

After deployment:

1. Go to https://vercel.com/dashboard
2. Click on `pandapower-frontend` project
3. Settings → Environment Variables
4. Add:
   ```
   VITE_API_URL=https://pandapower-backend.onrender.com
   ```
5. Save and redeploy

**You'll get a URL like:** `https://pandapower-frontend-abc123.vercel.app`

✅ **Vercel deployment complete!**

---

## 🎯 STEP 2: Deploy Backend to Render (20 minutes)

### 2.1 Create Render Account

1. Go to https://render.com
2. Click "Sign up"
3. Connect with GitHub
4. Authorize Render to access your GitHub repositories

### 2.2 Deploy FastAPI Web Service

1. In Render dashboard: **New → Web Service**

2. **Connect Repository:**
   - Search for: `pandapower`
   - Select your repository
   - Branch: `main`

3. **Configure Service:**
   - Name: `pandapower-backend`
   - Root Directory: `apps/backend`
   - Runtime: `Python 3.11`
   - Build Command:
     ```
     pip install -r requirements.txt
     ```
   - Start Command:
     ```
     python -m uvicorn pandapower.main:app --host 0.0.0.0 --port $PORT
     ```

4. **Environment Variables** (Add each):
   ```
   PYTHONPATH=/opt/render/project/apps/backend/src
   SUPABASE_URL=<paste from .env>
   SUPABASE_KEY=<paste from .env>
   SUPABASE_JWT_SECRET=<paste from .env>
   ANTHROPIC_API_KEY=<paste from .env>
   RESEND_API_KEY=<paste from .env>
   REDIS_URL=redis://default:@redis:6379
   ```

5. **Plan:** Free tier for now (can upgrade later)
6. Click **Create Web Service**

⏳ **Wait 10 minutes for deployment**

**Get your backend URL:** `https://pandapower-backend.onrender.com`

### 2.3 Create Celery Worker Service

1. In Render: **New → Background Worker**

2. **Configure:**
   - Name: `pandapower-worker`
   - Root Directory: `apps/backend`
   - Runtime: `Python 3.11`
   - Build Command:
     ```
     pip install -r requirements.txt
     ```
   - Start Command:
     ```
     celery -A pandapower.workers.celery_app worker -l info
     ```

3. **Environment Variables:** (Same as Web Service above)

4. Click **Create Background Worker**

⏳ **Wait 5 minutes for startup**

### 2.4 Create Celery Beat Cron Service

1. In Render: **New → Cron Job**

2. **Configure:**
   - Name: `pandapower-beat`
   - Schedule: `0 * * * *` (hourly)
   - Root Directory: `apps/backend`
   - Runtime: `Python 3.11`
   - Build Command:
     ```
     pip install -r requirements.txt
     ```
   - Start Command:
     ```
     celery -A pandapower.workers.celery_app beat -l info
     ```

3. **Environment Variables:** (Same as above)

4. Click **Create Cron Job**

✅ **Render deployment complete!**

---

## 🧪 STEP 3: Verify Deployment (5 minutes)

### Test Frontend
```bash
curl -I https://pandapower-frontend-abc123.vercel.app
# Should return: HTTP/2 200
```

### Test Backend Health
```bash
curl https://pandapower-backend.onrender.com/health
# Should return: {"status":"ok","service":"pandapower-backend"}
```

### Test System Status
```bash
curl https://pandapower-backend.onrender.com/admin/agent-matching/system-status | jq .
# Should return full system status with agent data
```

### Update Frontend API URL (if needed)
If your backend URL is different, update Vercel:

1. Vercel Dashboard → Settings → Environment Variables
2. Edit `VITE_API_URL`
3. Redeploy: Click "Deployments" → Last deployment → "Redeploy"

---

## 📋 Deployment Status Checklist

| Component | Service | Status | URL |
|-----------|---------|--------|-----|
| Frontend | Vercel | ⏳ Pending | https://pandapower-frontend-xxx.vercel.app |
| Backend API | Render Web | ⏳ Pending | https://pandapower-backend.onrender.com |
| Celery Worker | Render Background | ⏳ Pending | N/A (no URL) |
| Celery Beat | Render Cron | ⏳ Pending | N/A (no URL) |

---

## 🔧 Troubleshooting

### Frontend shows blank page
- Check browser console (F12) for errors
- Verify `VITE_API_URL` is set correctly
- Check that backend is running

### Backend returns 503 Service Unavailable
- Wait 2-3 minutes for full startup
- Check Render logs: Click service → Logs
- Verify environment variables are set

### Celery tasks not running
- Check Render Worker service logs
- Verify `REDIS_URL` is correct
- Ensure Beat service is running

### Can't connect to Supabase
- Verify `SUPABASE_URL` and `SUPABASE_KEY` are correct
- Check network firewall isn't blocking Supabase
- Test locally first: `curl https://<your-supabase-url>/rest/v1/`

---

## 💰 Costs

| Service | Free | Recommended | Cost/mo |
|---------|------|-------------|---------|
| Vercel | ✅ | Hobby | Free |
| Render | 750 hrs/mo | Pay-as-you-go | $7-15 |
| Supabase | 2GB storage | Pro | $25 |
| **Total** | | | **~$32-40** |

---

## 🎉 Success Indicators

- ✅ Frontend loads at https://pandapower-frontend-xxx.vercel.app
- ✅ Backend responds to /health check
- ✅ System status endpoint returns real data
- ✅ Agent screens show live data
- ✅ Carmit dashboard displays job assignments
- ✅ Celery tasks execute automatically

---

## 📞 Next Steps

1. [ ] Create GitHub repository
2. [ ] Push code to GitHub
3. [ ] Deploy frontend to Vercel
4. [ ] Deploy backend to Render (Web Service)
5. [ ] Deploy Celery Worker to Render
6. [ ] Deploy Celery Beat to Render
7. [ ] Test all endpoints
8. [ ] Share deployed URLs with team

**Ready?** Start with GitHub setup above! 🚀

