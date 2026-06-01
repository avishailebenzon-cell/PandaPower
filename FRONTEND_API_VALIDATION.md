# Frontend API Configuration Validation Guide

## The Problem: "Response is not JSON" Errors

When you see this error:
```
Failed to fetch employees: Response is not JSON (received text/html)
```

It means your API requests are hitting the Vite dev server's fallback error page instead of being routed to the backend.

## Root Cause

All fetch calls in the frontend must use the `API_BASE` constant which is built from the `VITE_API_URL` environment variable:

```typescript
// CRITICAL: Get API base URL from environment - MUST use VITE_API_URL (not VITE_API_BASE)
const API_BASE = import.meta.env.VITE_API_URL || '';

// ✅ CORRECT
const response = await fetch(`${API_BASE}/admin/pipedrive/data/employees`);

// ❌ WRONG - will cause "Response is not JSON" error
const response = await fetch(`/admin/pipedrive/data/employees`);
```

## Validation Checklist

### 1. Environment Variable Setup

```bash
# Check your .env file exists
ls -la apps/frontend/.env

# Verify VITE_API_URL is set (NOT VITE_API_BASE or VITE_API_BASE_URL!)
grep "VITE_API_URL" apps/frontend/.env
# Expected output:
# VITE_API_URL=http://localhost:8000
```

### 2. Verify Backend is Running

```bash
# Check backend health
curl http://localhost:8000/health
# Expected response:
# {"status":"ok","service":"pandapower-backend"}
```

### 3. Check Browser Console

Open the browser developer tools (F12) and:
1. Go to Network tab
2. Filter for `/admin/` or `/api/` requests
3. Look at the request URL - it should be:
   - ✅ `http://localhost:8000/admin/...` OR
   - ✅ `http://localhost:5173` with proxy working
   - ❌ NOT pointing to wrong origin

### 4. Verify TypeScript Compilation

```bash
cd apps/frontend
npx tsc --noEmit
# Should complete without errors
```

## Files That Use API_BASE

All the following files properly use `API_BASE` for API calls:

- ✅ `src/api/pipedrive-data.ts` - 5 endpoints (employees, clients, potential-clients, organizations, jobs)
- ✅ `src/api/matches.ts` - 2 endpoints (fetch history, update status)
- ✅ `src/pages/admin/CarmitPage.tsx` - 6 endpoints
- ✅ `src/pages/admin/PandiReferralsPage.tsx` - 3 endpoints
- ✅ `src/pages/admin/PandiOutreachPage.tsx` - Outreach endpoints
- ✅ `src/pages/admin/CVAnalysisPage.tsx` - CV analysis endpoints

## Automated Validation

Run this script to check your setup:

```bash
cd apps/frontend
bash validate-api-setup.sh
```

## Manual Testing

After setup, test the API connection:

```bash
# In the browser console, run:
const API_BASE = localStorage.getItem('api_base') || 'http://localhost:8000';
fetch(`${API_BASE}/admin/pipedrive/data/employees`)
  .then(r => r.json())
  .then(data => console.log('✅ API working:', data))
  .catch(e => console.error('❌ API error:', e));
```

## Troubleshooting Steps

### Still seeing "Response is not JSON"?

1. **Restart frontend dev server:**
   ```bash
   npm run dev
   ```

2. **Hard refresh browser:**
   - Mac: `Cmd+Shift+R`
   - Windows/Linux: `Ctrl+Shift+R`

3. **Clear browser cache:**
   - Chrome/Edge: Settings → Privacy → Clear browsing data → check "Cached images and files" → Clear data

4. **Verify environment variable is loaded:**
   ```bash
   # Check .env file directly
   cat apps/frontend/.env | grep VITE_API_URL
   
   # Check Vite resolved it (in browser console)
   console.log(import.meta.env.VITE_API_URL)
   ```

5. **Check CORS settings in backend:**
   ```bash
   # Verify root .env has correct CORS_ORIGINS
   grep "CORS_ORIGINS" .env
   # Should include: http://localhost:5173
   ```

## Common Mistakes

| Mistake | ❌ Wrong | ✅ Right |
|---------|---------|---------|
| Variable name | `VITE_API_BASE` | `VITE_API_URL` |
| Variable name | `VITE_API_BASE_URL` | `VITE_API_URL` |
| No API prefix | `fetch('/admin/...')` | `fetch(\`${API_BASE}/admin/...\`)` |
| Wrong endpoint | `fetch('http://wrong-url/...')` | Use environment variable |

## Development Best Practices

1. **Always declare API_BASE at the top of files:**
   ```typescript
   // CRITICAL: Get API base URL from environment - MUST use VITE_API_URL (not VITE_API_BASE)
   const API_BASE = import.meta.env.VITE_API_URL || '';
   ```

2. **Use it consistently for all API calls:**
   ```typescript
   fetch(`${API_BASE}/admin/...`)
   fetch(`${API_BASE}/api/...`)
   ```

3. **Never hardcode URLs:**
   ```typescript
   // ❌ Bad
   const API_BASE = 'http://localhost:8000';
   
   // ✅ Good
   const API_BASE = import.meta.env.VITE_API_URL || '';
   ```

## See Also

- [FRONTEND_SETUP.md](./FRONTEND_SETUP.md) - Complete setup guide
- [README.md](./README.md) - Quick start & troubleshooting
- `.env.example` - Environment variable reference
