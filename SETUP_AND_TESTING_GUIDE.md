# PandaPower - Setup & Testing Guide
**Created:** 2026-05-23  
**Status:** Ready for Development Testing

---

## 🚀 Quick Start

### Prerequisites
- Node.js 18+ (for frontend)
- Python 3.10+ (for backend)
- PostgreSQL with Supabase client (for database)
- Git

### Backend Setup

```bash
# Navigate to backend directory
cd apps/backend

# Create virtual environment (if not already done)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file with credentials
# REQUIRED:
# - SUPABASE_URL=https://your-project.supabase.co
# - SUPABASE_KEY=your-anon-key
# - DATABASE_URL=postgresql://user:password@host/dbname
# - ANTHROPIC_API_KEY=sk-...
# - PIPEDRIVE_API_TOKEN=... (for Pipedrive integration)
# - PANDI_WHATSAPP_NUMBER=+972... (for Pandi WhatsApp)

# Run backend (development)
python src/pandapower/main.py
# Backend will run on http://localhost:8000
```

### Frontend Setup

```bash
# Navigate to frontend directory
cd apps/frontend

# Install dependencies
npm install

# Create .env.local (if needed for API base URL)
# VITE_API_BASE=http://localhost:8000

# Run frontend (development)
npm run dev
# Frontend will run on http://localhost:5173
```

---

## 📋 Testing Checklist

### 1. Layout & Navigation Separation ✅

**Purpose:** Verify Work and Admin layouts are properly separated

```
□ Navigate to http://localhost:5173/recruiting
  - Should see WorkLayout (warm blue/purple theme)
  - See 7 recruitment department agents with avatars
  - See 2 recruiters (Tal, Elad) with avatars
  - Sidebar shows: Main Dashboard, Departments, Recruiters, Quick Links

□ From WorkLayout, click ⚙️ button
  - Should navigate to /admin
  - Should see AdminLayout (dark slate theme)

□ From AdminLayout, click ↪ "Return to Work" link
  - Should navigate back to /recruiting
  - Should see WorkLayout again

□ Verify RTL (Right-to-Left) text alignment
  - Hebrew text should align right
  - Buttons should be on left side
  - Navigation items should flow right-to-left
```

### 2. Pandi Admin Dashboard (Phase 9) ✅

**Purpose:** Test Pandi WhatsApp client management

```
□ Navigate to /admin/pandi
  - Should see header "ניהול Pandi"
  - Should see 4 KPI cards:
    * שיחות פעילות (Active Conversations)
    * סך הכל לקוחות (Total Clients)
    * שיחות השבוע (This Week)
    * הודעות לקוח (Avg Messages)

□ Test tab navigation
  - Click "קליינטים פעילים" (Active Clients)
  - Click "היסטוריה" (History)
  - Should show different client lists

□ Test client table
  - Should display: Name, Organization, Phone, Status, Last Activity
  - Status badge should be color-coded
  - Should have 3 action buttons per row:
    * 📋 פרטים (View Details)
    * 🔗 הזמנה (Generate Invite)
    * 👁️ הצג (View Invite)

□ Test search & filter
  - Type in search box (search by name, org, phone)
  - Should filter client list in real-time
  - Sort dropdown should work (Newest, Oldest, Name)

□ Test "View Details" modal
  - Click 📋 button on a client
  - Should open modal with client info
  - Should show: Phone, Organization, Intake Status
  - Should list recent conversations (up to 10)
  - Should have close button

□ Test "Generate Invite" flow
  - Click 🔗 button on a client
  - Should show confirmation modal
  - Confirm → Should show invite modal with:
    * Invite URL (with WhatsApp link)
    * Prefilled message for client
    * Admin instructions for copy-paste
    * Copy button functionality
```

### 3. Recruiter Dashboard (Phase 3) ✅

**Purpose:** Test recruiter queue management

```
□ Navigate to /admin/recruiter
  - Should see header "מנהל מגייסים"
  - Should see 6 status cards:
    * Pending Tal, In Conversation Tal
    * Awaiting Elad, In Conversation Elad
    * Hired, Failed

□ Test tab navigation
  - 4 tabs: תור לטל, היסטוריית טל, תור לאלד, היסטוריית אלד
  - Each tab should show different match queues
  - Switching tabs should update the match list

□ Test matches display
  - Each match should show:
    * Candidate name & job title
    * Company name
    * Match score (0-100 scale)
    * Status badge
    * Days in current stage
    * Last activity timestamp
    * Action buttons: Conversation, Decision, (Placement for Elad)

□ Test "Record Conversation" modal
  - Click "Conversation" button on a match
  - Should show modal with:
    * Text area for conversation summary
    * Optional date picker
    * Submit button
  - Submit → Should update match state to "In Conversation"
  - Should invalidate React Query to refetch data

□ Test "Record Decision" modal
  - Click "Decision" button on a match
  - Should show modal with:
    * Radio buttons: Accepted / Rejected
    * Text area for decision reason
  - Select decision → Submit
  - Should update match state and show in new queue

□ Test "Record Placement" modal (Elad only)
  - Click "Placement" button for Elad matches
  - Should show modal with:
    * Radio buttons: Hired / Placement Failed
    * Notes field
  - Submit → Should finalize match state
```

### 4. Analytics Dashboard (Phase 8) ✅

**Purpose:** Test analytics and reporting

```
□ Navigate to /admin/analytics
  - Should see header "דוחות ואנליטיקה"
  - Should see period selector buttons:
    * Week, Month, Quarter, Year

□ Test KPI cards
  - Should display 6 metrics:
    * Total Hired (green)
    * Placement Rate % (blue)
    * Pending Matches (yellow)
    * Avg Time-to-Hire Days (purple)
    * Failed Matches (red)
    * Active Conversations (cyan)

□ Test charts (if Recharts library works)
  - Funnel chart: Shows match drop-off at each stage
  - Line chart: Time-to-placement trend
  - Bar chart: Recruiter comparison (Tal vs Elad)

□ Test recruiter performance table
  - Should show metrics for both recruiters
  - Columns: Name, Conversations, Approvals, Approval Rate, Hires, etc.

□ Test rejection reasons breakdown
  - Should show pie/bar chart of why matches failed
  - Reasons should be categorized by stage
```

### 5. API Integration Testing

**Purpose:** Verify backend endpoints respond correctly

```bash
# Test Recruiter endpoints
curl http://localhost:8000/admin/recruiter/status
  → Should return: {pending_tal, in_conversation_tal, awaiting_elad, etc.}

curl "http://localhost:8000/admin/recruiter/matches?tab=tal-queue&limit=50&page=1"
  → Should return: {matches: [...], total, page, limit}

# Test Pandi endpoints
curl http://localhost:8000/admin/pandi/clients?is_active=true&limit=50
  → Should return list of pandi_clients

curl -X POST http://localhost:8000/admin/pandi/generate-invite \
  -H "Content-Type: application/json" \
  -d '{"contact_id": "uuid"}'
  → Should return: {invite_url, prefilled_message, instructions}

# Test Analytics endpoints
curl http://localhost:8000/admin/analytics/kpi-summary
  → Should return: {total_hired, placement_rate, pending_matches, etc.}

curl "http://localhost:8000/admin/analytics/recruiter-performance?recruiter=tal"
  → Should return recruiter metrics
```

---

## 🐛 Troubleshooting

### Frontend Issues

**"Module not found" errors**
- Ensure you've run `npm install` in the frontend directory
- Check that all import paths match actual file locations
- Verify `tsconfig.json` path aliases are correct (@ = src/)

**TypeScript compilation errors**
- Run `npm run lint` to see all errors
- Common issues: type mismatches, missing imports
- Check that `src/api/*.ts` files export proper types

**API calls failing (404, 500)**
- Ensure backend is running on http://localhost:8000
- Check backend logs for detailed error messages
- Verify API endpoint URLs in src/api/*.ts match backend routes

**CORS errors**
- Backend should have CORS middleware enabled
- Check `CORS_ORIGINS` in backend config includes `http://localhost:5173`

### Backend Issues

**Import errors**
- Ensure you're in the correct virtual environment
- Run `pip install -r requirements.txt` again
- Check that all routers are properly imported in `main.py`

**Database connection errors**
- Verify `DATABASE_URL` and `SUPABASE_*` env vars are set
- Test connection: `psql $DATABASE_URL` (if PostgreSQL CLI installed)
- Check Supabase project is active and accessible

**Endpoint not found (404)**
- Verify router is imported and registered in `main.py`
- Check route path matches exactly (e.g., `/admin/recruiter` vs `/admin/recruiters`)
- Confirm function parameters match query/path params

---

## 📊 Expected Data Flow

### User Registration & Login
```
Frontend (login form)
  ↓
Backend (auth endpoint)
  ↓
Supabase auth
  ↓
User session → React Query → Frontend state
```

### Dashboard Data Loading
```
Frontend mounts RecruiterDashboard
  ↓
useQuery(['recruiter-status']) fires
  ↓
GET /admin/recruiter/status
  ↓
Queries matches table by state
  ↓
Returns StatusMetrics
  ↓
React Query caches → Component renders
  ↓
Auto-refetch every 10 seconds (refetchInterval: 10000)
```

### Recording Recruiter Action
```
User clicks "Record Conversation" button
  ↓
Opens ConversationModal
  ↓
User fills summary + date, clicks submit
  ↓
useMutation fires recordConversation()
  ↓
POST /admin/pipedrive/recruiter-workflow/record-conversation/{matchId}
  ↓
Backend updates match state in database
  ↓
Returns success response
  ↓
useMutation onSuccess hook:
  - Invalidates ['recruiter-matches'] query key
  - Invalidates ['recruiter-status'] query key
  ↓
React Query auto-refetches
  ↓
Components re-render with updated data
```

---

## ✅ Sign-Off Checklist

When all tests pass, confirm:

- [ ] All layouts render without errors
- [ ] RTL text alignment works for Hebrew
- [ ] Avatars load correctly
- [ ] Tab navigation switches content properly
- [ ] API endpoints return correct data
- [ ] React Query refetch works
- [ ] Modal forms submit and update state
- [ ] Search/filter/sort functionality works
- [ ] No console errors in browser DevTools
- [ ] No TypeScript compilation errors
- [ ] Backend logs show no errors
- [ ] Database queries succeed
- [ ] Responsive design works (test mobile view)

---

## 📞 Support

If you encounter issues:

1. **Check the browser console** (F12) for JavaScript errors
2. **Check the backend logs** for detailed error messages
3. **Run `npm run lint`** for TypeScript errors
4. **Verify environment variables** are set correctly
5. **Test API endpoints directly** with curl to isolate issues
6. **Check database connection** with psql or Supabase dashboard

---

**Last Updated:** 2026-05-23  
**Status:** Ready for Testing Phase
