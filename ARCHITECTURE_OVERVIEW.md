# PandaPower - System Architecture Overview
**Date:** 2026-05-23  
**Version:** 2.0

---

## 🏗️ High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React + Vite)                   │
│  - WorkLayout (Recruiting operations)                        │
│  - AdminLayout (System administration)                       │
│  - Dashboards: Work, Recruiter, Pandi, Analytics, Carmit    │
│  - Components: Modals, Cards, Tables, Charts                │
│  - State: React Query + useState                             │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP/REST
                             │ (Fetch API + React Query)
                             ↓
┌─────────────────────────────────────────────────────────────┐
│               Backend (FastAPI + Python)                     │
│  - Routers: Admin, Email, CV, Candidates, Skills, etc.      │
│  - Models: Pydantic for request/response validation         │
│  - Services: Pipedrive, Claude API, Celery tasks            │
│  - Database: Supabase (PostgreSQL)                           │
│  - CORS enabled for frontend communication                   │
└────────────────────────────┬────────────────────────────────┘
                             │ SQL
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                 Supabase (PostgreSQL)                        │
│  - Tables: agents, matches, candidates, jobs, skills        │
│  - Auth: Supabase Auth                                       │
│  - Real-time: Subscriptions for live updates                │
└─────────────────────────────────────────────────────────────┘
```

---

## 📂 Directory Structure

### Frontend (`apps/frontend/src/`)

```
├── pages/
│   ├── work/
│   │   └── WorkDashboard.tsx          # Main recruitment dashboard
│   └── admin/
│       ├── AdminDashboard.tsx         # Admin overview
│       ├── PandiPage.tsx              # Pandi WhatsApp management
│       ├── RecruiterDashboard.tsx     # Recruiter queue management
│       ├── AnalyticsDashboard.tsx     # Analytics & reports
│       ├── CarmitPage.tsx             # Carmit job routing
│       ├── RecruitmentDepartment.tsx  # Agent department view
│       └── (other admin pages)
│
├── components/
│   ├── WorkLayout.tsx                 # Layout for work area
│   ├── AdminLayout.tsx                # Layout for admin area
│   ├── ProtectedRoute.tsx             # Route guard
│   ├── PandiClientTable.tsx           # Pandi clients table
│   ├── ClientDetailModal.tsx          # Pandi client details
│   ├── InviteGeneratorModal.tsx       # Pandi invite generator
│   ├── MatchCard.tsx                  # Match card component
│   ├── KPICard.tsx                    # Key metric card
│   ├── AnalyticsChart.tsx             # Chart wrapper
│   └── (other components)
│
├── api/
│   ├── pandi.ts                       # Pandi API client
│   ├── recruiter.ts                   # Recruiter API client
│   ├── recruitment-departments.ts     # Departments API client
│   └── (other API clients)
│
├── hooks/
│   ├── useAuth.ts                     # Authentication hook
│   └── (other custom hooks)
│
├── data/
│   └── agents.ts                      # Agent profiles & data
│
├── main.tsx                           # App entry point
├── index.css                          # Global styles
└── App.tsx                            # Root component
```

### Backend (`apps/backend/src/pandapower/`)

```
├── main.py                            # FastAPI app & router registration
│
├── core/
│   ├── config.py                      # Settings & environment vars
│   ├── supabase.py                    # Database client
│   └── logging.py                     # Logging setup
│
├── routers/
│   ├── admin/
│   │   ├── pandi.py                   # Pandi WhatsApp endpoints
│   │   ├── recruiter.py               # Recruiter dashboard endpoints
│   │   ├── analytics.py               # Analytics endpoints
│   │   ├── carmit.py                  # Carmit orchestrator endpoints
│   │   ├── pipedrive.py               # Pipedrive integration endpoints
│   │   ├── email_ingest.py            # Email intake endpoints
│   │   ├── cv_parse.py                # CV parsing endpoints
│   │   ├── candidate_management.py    # Candidate endpoints
│   │   ├── skill_management.py        # Skill endpoints
│   │   ├── security_classification.py # Security clearance endpoints
│   │   ├── recruitment_departments.py # Department endpoints
│   │   └── setup.py                   # Setup/config endpoints
│   ├── webhooks.py                    # Webhook handlers
│   ├── user.py                        # User management
│   └── health.py                      # Health check
│
├── workers/
│   ├── celery_app.py                  # Celery task scheduler
│   ├── tasks.py                       # Scheduled tasks
│   ├── carmit.py                      # Carmit orchestrator worker
│   ├── pandi.py                       # Pandi bot worker
│   └── pipedrive_recruiter_workflow.py # Recruiter workflow manager
│
├── integrations/
│   ├── pipedrive.py                   # Pipedrive API client
│   ├── azure.py                       # Azure email API client
│   ├── anthropic.py                   # Claude API client
│   └── (other integrations)
│
└── models/
    └── (Pydantic models for validation)
```

---

## 🔄 Key Data Flows

### 1. Recruitment Pipeline

```
Job Created
  ↓
Carmit Routes Job to Agent (Claude Opus decides best agent)
  ↓
Agent Finds Matches (candidate pool search)
  ↓
Carmit Reviews Match (5 quality gates)
  ├─ Gate 1: Past rejection check (Pipedrive)
  ├─ Gate 2: Already declined check
  ├─ Gate 3: Conflict detection
  ├─ Gate 4: Clearance level match
  └─ Gate 5: Quality score threshold (0.70+)
  ↓
Match Approved → Sent to Tal (Recruiter 1)
  ↓
Tal Records Conversation
  ↓
Tal Makes Decision: Accept or Reject
  ├─ Reject → Match ends
  └─ Accept → Sent to Elad (Recruiter 2)
  ↓
Elad Negotiates Placement
  ↓
Final Outcome: Hired or Placement Failed
```

### 2. Admin Dashboard Access

```
User logs in
  ↓
/ (root) → Navigate to /recruiting (WorkLayout)
  ↓
User clicks ⚙️ Settings button
  ↓
Navigate to /admin (AdminLayout)
  ↓
Choose admin function from sidebar:
  ├─ Integrations (Azure, Pipedrive config)
  ├─ Email Intake (manage email pipeline)
  ├─ CV Parsing (configure Claude CV parser)
  ├─ Candidates (view/manage candidate pool)
  ├─ Skills (normalization & validation)
  ├─ Security (clearance levels)
  ├─ Agents (AI agent configuration)
  ├─ Carmit (job routing & match review)
  ├─ Pandi (WhatsApp bot management)
  └─ Analytics (reports & metrics)
  ↓
User clicks ↪ Return to Work
  ↓
Navigate back to /recruiting (WorkLayout)
```

### 3. Pandi WhatsApp Bot Flow

```
Admin goes to /admin/pandi
  ↓
Views active Pandi clients
  ↓
Selects client and clicks "Generate Invite"
  ↓
System creates pandi_client record
  ↓
Generates WhatsApp invite URL (wa.me link)
  ↓
Returns: invite_url, prefilled_message, instructions
  ↓
Admin copies URL or message to send to client
  ↓
Client clicks/scans → Opens WhatsApp chat with Pandi bot
  ↓
Pandi bot receives message → Stores as pandi_conversation
  ↓
Claude processes message → Generates response
  ↓
Pandi sends response back to client on WhatsApp
  ↓
Admin can view conversation history in dashboard
```

---

## 🛠️ Technology Stack

### Frontend
- **Framework:** React 18+ with TypeScript
- **Build Tool:** Vite
- **HTTP Client:** Fetch API + React Query (@tanstack/react-query)
- **Routing:** React Router v6
- **State Management:** React Query (server state) + useState (UI state)
- **Styling:** Tailwind CSS with RTL support
- **Charts:** Recharts (for analytics)
- **Auth:** Supabase Auth + Custom useAuth hook

### Backend
- **Framework:** FastAPI (Python 3.10+)
- **Database:** PostgreSQL (via Supabase)
- **Database Client:** Supabase Python SDK + SQLAlchemy
- **Validation:** Pydantic v2
- **Task Queue:** Celery with Redis
- **Async:** asyncio for concurrent operations
- **API Clients:**
  - Anthropic SDK (Claude API)
  - Pipedrive SDK
  - Azure communication SDK (email)
  - Green API SDK (WhatsApp)

### DevOps / Deployment
- **Package Manager (Frontend):** npm
- **Package Manager (Backend):** pip
- **Version Control:** Git
- **Container:** Docker (optional)

---

## 🔐 Security & Authentication

### Frontend
```
ProtectedRoute Component
  ↓
Checks useAuth() hook
  ├─ If authenticated: Show component
  └─ If not: Redirect to login
```

### Backend
```
Dependency Injection Pattern
  ↓
get_supabase_client() dependency
  ↓
Supabase auth session verification
  ├─ Valid session: Process request
  └─ Invalid: Return 401 Unauthorized
```

### Environment Variables

**Frontend (.env.local):**
```
VITE_API_BASE=http://localhost:8000
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_KEY=your-anon-key
```

**Backend (.env):**
```
DATABASE_URL=postgresql://...
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-key
ANTHROPIC_API_KEY=sk-...
PIPEDRIVE_API_TOKEN=...
AZURE_TENANT_ID=...
PANDI_WHATSAPP_NUMBER=+972...
```

---

## 📊 Database Schema (Key Tables)

```sql
-- Agents and organizations
TABLE agents (id, name, department, specialization, avatar_url)
TABLE organizations (id, name, domain, pipedrive_org_id)

-- Recruiting pipeline
TABLE jobs (id, title, organization_id, status, agent_assigned)
TABLE candidates (id, name, skills, cv_data, phone, email)
TABLE matches (
  id, candidate_id, job_id, agent_code, 
  current_state, match_score, created_at, updated_at
)
TABLE match_state_history (
  match_id, from_state, to_state, details (JSONB), created_at
)

-- Recruiter workflow
TABLE recruiter_conversations (
  id, match_id, recruiter_name, 
  conversation_text, recorded_at
)

-- Pandi WhatsApp bot
TABLE pandi_clients (
  id, contact_id, phone, intake_status, 
  initial_invite_sent_at, is_active
)
TABLE pandi_conversations (
  id, pandi_client_id, message_text, 
  direction (incoming/outgoing), created_at
)

-- Skills normalization
TABLE skills (id, name, category)
TABLE candidate_skills (candidate_id, skill_id, confidence)
TABLE normalized_skills (original, normalized_to)

-- System configuration
TABLE pipedrive_field_mappings (field_name, pipedrive_id, data_type)
TABLE security_clearances (id, name, level)
TABLE job_locations (job_id, location, address)
```

---

## 🚀 Deployment Considerations

### Local Development
```bash
# Terminal 1: Backend
cd apps/backend
source .venv/bin/activate
python src/pandapower/main.py
# Runs on http://localhost:8000

# Terminal 2: Frontend
cd apps/frontend
npm run dev
# Runs on http://localhost:5173
```

### Production (Docker)
```dockerfile
# Backend
FROM python:3.11-slim
WORKDIR /app
COPY apps/backend/requirements.txt .
RUN pip install -r requirements.txt
COPY apps/backend/src ./src
CMD ["python", "src/pandapower/main.py"]

# Frontend
FROM node:18-alpine
WORKDIR /app
COPY apps/frontend/package*.json .
RUN npm install
COPY apps/frontend . 
RUN npm run build
CMD ["npm", "run", "preview"]
```

### Environment Considerations
- **Development:** Hot reload, detailed logging, CORS permissive
- **Staging:** Real database, API validation, email test mode
- **Production:** Optimized builds, rate limiting, security headers

---

## 📈 Performance Optimization

### Frontend
- **Code Splitting:** Lazy load admin pages
- **React Query:** Caching & background refetch
- **Memoization:** useMemo for expensive calculations
- **Image Optimization:** DiceBear avatars as SVG (lightweight)

### Backend
- **Database Indexing:** On state, created_at, candidate_id
- **Caching:** Redis for match scores, agent stats
- **Async/Await:** Non-blocking I/O operations
- **Connection Pooling:** Supabase client pooling

---

## 🔄 Data Sync & Real-Time

### WebSocket (Optional Future Enhancement)
```
Supabase Real-time subscriptions could push:
- Match state changes
- New candidates
- Pandi messages
- Recruiter decisions
```

### Current Implementation
```
React Query refetchInterval: 10-30 seconds
- recruiter-status: Every 10s
- recruiter-matches: Every 10s
- pandi-clients: Every 30s
- analytics-kpi: Every 30s
```

---

## 📚 Related Documentation

- **SETUP_AND_TESTING_GUIDE.md** - Development setup and testing procedures
- **IMPLEMENTATION_SUMMARY_2026-05-23.md** - Phase completion details
- **SEPARATION_DOCUMENTATION.md** - Work/Admin separation details
- **תיעוד_ההפרדה_בעברית.md** - Hebrew user guide

---

**Version:** 2.0  
**Last Updated:** 2026-05-23  
**Status:** Production-Ready (with testing)
