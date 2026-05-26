# 🚀 Deployment Checklist - ALWAYS DO THIS AT END OF SESSION

## Before Closing Session

### 1. ✅ Commit & Push to GitHub
```bash
git status                    # Verify all changes
git add .                     # Stage changes
git commit -m "Your message"  # Commit
git push origin main          # Push to GitHub
```

### 2. ✅ Verify GitHub Push
```bash
git log -1 --oneline         # Confirm last commit
git remote -v               # Verify remote is set
```

### 3. ✅ Check Vercel Build
- Go to: https://vercel.com/dashboard/projects
- Look for "PandaPower" project
- Status should be **READY** (green)
- Click to see build logs if needed

### 4. ✅ Check Render Backend
- Endpoint: https://pandapower-backend.onrender.com/health
- Should return: `{"status":"ok","service":"pandapower-backend"}`

### 5. ✅ Test Live URLs
- Frontend: https://pandapower.vercel.app (or your Vercel domain)
- Backend: https://pandapower-backend.onrender.com

### 6. ✅ Stop Local Servers (if running)
```bash
pkill -f "uvicorn"   # Stop backend
pkill -f "node"      # Stop frontend
pkill -f "npm"       # Stop npm servers
```

## If Deployment Fails

### Vercel Issues
- Check build logs: https://vercel.com/dashboard
- Common issues:
  - Wrong Node version → Fix in vercel.json
  - Missing env vars → Add to Vercel dashboard
  - Port conflicts → Check `.vercelignore`

### Render Issues
- Check deployment logs: https://dashboard.render.com
- Common issues:
  - Missing dependencies → Update requirements.txt
  - Environment variables → Add to Render dashboard
  - Port binding → Should be 8000

## Quick Deployment via CLI (Alternative)

```bash
# Install Vercel CLI (one time)
npm install -g vercel

# Deploy frontend
cd apps/frontend
vercel --prod

# Deploy backend (manual)
cd ../backend
# Push to GitHub, let Render auto-deploy
```

---
**⚠️ IMPORTANT: No work session is complete without deploying to cloud!**
