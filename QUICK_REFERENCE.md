# PandaPower - Quick Reference Guide

## 🚀 Common Tasks

### Running the Application

**Start Backend**
```bash
cd apps/backend
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
python src/pandapower/main.py
```
→ Backend runs on `http://localhost:8000`

**Start Frontend**
```bash
cd apps/frontend
npm run dev
```
→ Frontend runs on `http://localhost:5173`

**Check Code Quality**
```bash
# Frontend
npm run lint

# Backend
python -m py_compile src/pandapower/**/*.py
```

### API Endpoint Cheat Sheet

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/admin/recruiter/status` | GET | Get recruiter queue metrics |
| `/admin/recruiter/matches` | GET | Get matches by queue tab |
| `/admin/pandi/clients` | GET | List Pandi clients |
| `/admin/pandi/generate-invite` | POST | Create WhatsApp invite |
| `/admin/analytics/kpi-summary` | GET | Get KPI metrics |
| `/admin/analytics/recruiter-performance` | GET | Get recruiter stats |
| `/admin/carmit/pending-review` | GET | Get matches pending review |
| `/admin/pipedrive/recruiter-workflow/record-conversation/{id}` | POST | Record recruiter conversation |
| `/admin/pipedrive/recruiter-workflow/record-decision/{id}` | POST | Record recruiter decision |

### Frontend Navigation Routes

```
/                                  → Redirects to /recruiting
/recruiting                        → WorkDashboard (main recruitment view)
/recruiting/departments/:code      → Agent department view
/recruiting/tal                    → Tal (screener) dashboard
/recruiting/elad                   → Elad (placement) dashboard

/admin                             → AdminDashboard (system overview)
/admin/pandi                       → Pandi WhatsApp management
/admin/recruiter                   → Recruiter queue management
/admin/analytics                   → Analytics & reports
/admin/carmit                      → Carmit job routing
/admin/candidates                  → Candidate management
/admin/cv-parsing                  → CV parsing
/admin/email-intake                → Email intake
/admin/skills                      → Skill management
/admin/security                    → Security classification
/admin/agents                      → AI agent config
/admin/integrations                → External integrations
```

### Environment Variables Checklist

**Required for Backend (.env)**
- ✅ `DATABASE_URL` - PostgreSQL connection string
- ✅ `SUPABASE_URL` - Supabase project URL
- ✅ `SUPABASE_KEY` - Supabase service key
- ✅ `ANTHROPIC_API_KEY` - Claude API key
- 📍 `PIPEDRIVE_API_TOKEN` - For Pipedrive integration
- 📍 `PANDI_WHATSAPP_NUMBER` - For Pandi WhatsApp
- 📍 `AZURE_TENANT_ID` - For Azure email integration

**Optional for Frontend (.env.local)**
- `VITE_API_BASE` - API URL (default: http://localhost:8000)

---

## 🔍 Debugging Tips

### Frontend Debugging

**Check React Query state**
```javascript
// In browser console
import { queryClient } from '@/lib/queryClient'
queryClient.getQueryData(['recruiter-status'])  // View cached data
queryClient.invalidateQueries({ queryKey: ['recruiter-status'] })  // Force refetch
```

**View network requests**
- Open DevTools → Network tab
- Look for XHR/Fetch requests
- Check Response tab for API responses

**Common Frontend Issues**
| Problem | Solution |
|---------|----------|
| "Cannot find module" | Run `npm install` |
| TypeScript errors | Run `npm run lint` and fix them |
| Blank page | Check browser console for errors |
| API calls fail | Check backend is running on correct port |
| CORS error | Verify backend CORS config |

### Backend Debugging

**Check endpoint availability**
```bash
curl http://localhost:8000/  # Should return {"message": "Welcome"}
curl http://localhost:8000/admin/recruiter/status  # Should return JSON
```

**View database queries**
```bash
# Enable SQLAlchemy logging in config.py
echo "echo=True" >> src/pandapower/core/config.py
```

**Common Backend Issues**
| Problem | Solution |
|---------|----------|
| "Module not found" | Check PYTHONPATH includes `src/` |
| 500 errors | Check backend logs for traceback |
| Database connection fails | Verify DATABASE_URL is correct |
| Auth failures | Check Supabase credentials |

---

## 📁 File Organization Tips

### When adding a new API client
1. Create file: `apps/frontend/src/api/module-name.ts`
2. Define interfaces for request/response types
3. Export async functions for each endpoint
4. Example: `src/api/recruiter.ts`, `src/api/pandi.ts`

### When adding a new page
1. Create file: `apps/frontend/src/pages/{section}/{PageName}.tsx`
2. Use layout components (WorkLayout or AdminLayout)
3. Import React Query hooks and API clients
4. Add route to `main.tsx`
5. Add navigation link to sidebar

### When adding a new backend endpoint
1. Create/edit router: `apps/backend/src/pandapower/routers/admin/feature.py`
2. Define Pydantic models for request/response
3. Implement endpoint function with FastAPI decorator
4. Import and register router in `main.py`
5. Test with curl or Postman

---

## 🧪 Testing Workflow

### Frontend Component Testing

```bash
# 1. Start dev server
npm run dev

# 2. Go to specific route in browser
# 3. Open DevTools (F12)
# 4. Check Console tab for errors
# 5. Check Network tab for API calls
# 6. Interact with component
# 7. Verify expected behavior
```

### Backend Endpoint Testing

```bash
# Test endpoint with curl
curl -X GET http://localhost:8000/admin/recruiter/status

# Test with data
curl -X POST http://localhost:8000/admin/pandi/generate-invite \
  -H "Content-Type: application/json" \
  -d '{"contact_id": "550e8400-e29b-41d4-a716-446655440000"}'

# Test with authentication (if needed)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/admin/recruiter/matches?tab=tal-queue
```

---

## 🔄 Git Workflow

```bash
# Create feature branch
git checkout -b feature/component-name

# Make changes and commit
git add apps/frontend/src/pages/MyPage.tsx
git commit -m "Add MyPage component"

# Push branch
git push origin feature/component-name

# Create pull request on GitHub
# After review and approval, merge to main
```

---

## 📊 Data Model Reference

### Match States
```
found
  ↓
carmit_approved / carmit_rejected
  ↓ (if approved)
sent_to_tal
  ↓
tal_conversation
  ↓
tal_approved → sent_to_elad / tal_rejected → (end)
  ↓
elad_conversation
  ↓
hired / placement_failed (end)
```

### Pandi Client States
```
not_started
  ↓
in_progress
  ↓
completed
```

### Candidate Skill Matching
```
Candidate has skills: [Python, JavaScript, React]
Job requires: [JavaScript, React, Node.js]
Match score = (matching skills / total job skills) * 100
= (2 / 3) * 100 = 66.7%
```

---

## 🎨 Design System Reference

### Color Palette

| Component | Colors | Hex |
|-----------|--------|-----|
| Work Area | Indigo, Blue, Purple, Green | #4F46E5, #3B82F6, #9333EA, #22C55E |
| Admin Area | Slate, Indigo, Cyan | #0F172A, #4F46E5, #06B6D4 |
| Status - Success | Green | #22C55E |
| Status - Warning | Yellow | #EAB308 |
| Status - Error | Red | #EF4444 |
| Status - Info | Blue | #3B82F6 |

### Component Sizes

| Type | Size |
|------|------|
| Large Button | `px-6 py-3 text-base` |
| Medium Button | `px-4 py-2 text-sm` |
| Small Button | `px-3 py-1 text-xs` |
| Avatar | `w-12 h-12` or `w-8 h-8` |
| Card Padding | `p-4` or `p-6` |
| Modal Max Width | `max-w-md` or `max-w-2xl` |

### RTL Considerations

```css
/* When using Tailwind with RTL */
dir="rtl"                    /* Set on root element */
text-right                   /* For body text */
justify-start / justify-end  /* Reversed in RTL */
gap-{size}                   /* Works both directions */
border-l / border-r          /* Watch these in RTL */
```

---

## 🚨 Common Mistakes to Avoid

### Frontend
- ❌ Forgetting `dir="rtl"` on RTL pages
- ❌ Not wrapping with `ProtectedRoute`
- ❌ Forgetting to add routes to `main.tsx`
- ❌ Using relative imports instead of `@/` alias
- ❌ Not calling `queryClient.invalidateQueries()` after mutations

### Backend
- ❌ Forgetting to import router in `main.py`
- ❌ Not defining Pydantic models for request/response
- ❌ Using `response_model` without proper types
- ❌ Forgetting to add route to database when needed
- ❌ Not handling potential None values from database

### General
- ❌ Committing `.env` files with credentials
- ❌ Not testing before pushing
- ❌ Leaving `console.log()` in production code
- ❌ Using hardcoded URLs instead of env vars
- ❌ Not updating documentation when changing APIs

---

## 📞 Getting Help

**Error in Frontend?**
1. Check browser console (F12)
2. Run `npm run lint`
3. Check that API base URL is correct
4. Verify backend is running

**Error in Backend?**
1. Check backend logs in terminal
2. Verify database connection
3. Test endpoint directly with curl
4. Check Supabase credentials

**Database issue?**
1. Verify connection string
2. Check Supabase dashboard
3. Verify credentials have proper permissions
4. Test with psql CLI if available

---

**Last Updated:** 2026-05-23  
**Quick Reference Version:** 1.0
