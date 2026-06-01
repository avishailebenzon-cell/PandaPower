# PandaPower — AI-Powered Recruitment System

An intelligent recruitment platform for PandaTech that automates candidate matching, CV analysis, and job placements using AI agents.

## System Requirements

- Python 3.12+
- Node.js 20+
- Docker & Docker Compose
- uv (Python package manager)

## Quick Start

### 1. Clone and Setup Environment

```bash
# Root .env for backend services
cp .env.example .env

# Frontend .env (CRITICAL: must have VITE_API_URL, not VITE_API_BASE!)
cd apps/frontend
cp ../.env.example .env
# Edit .env and ensure: VITE_API_URL=http://localhost:8000
# Or run the setup script:
bash setup-env.sh
```

⚠️ **IMPORTANT**: The frontend requires `VITE_API_URL` (not `VITE_API_BASE` or `VITE_API_BASE_URL`) to communicate with the backend.

### 2. Start Database & Cache

```bash
docker compose up -d
```

Verify services are healthy:
```bash
docker compose ps
```

### 3. Backend Setup

```bash
cd apps/backend
uv sync
uv run uvicorn pandapower.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

Test the health endpoint:
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "service": "pandapower-backend"
}
```

### 4. Frontend Setup

```bash
cd apps/frontend
npm install
npm run dev
```

The UI will be available at `http://localhost:5173`

## Project Structure

```
pandapower/
├── apps/
│   ├── backend/          # FastAPI application
│   │   ├── src/pandapower/
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── frontend/         # React + TypeScript application
│       ├── src/
│       └── package.json
├── infra/
│   └── supabase/         # Database migrations (Phase 2)
├── docs/
│   ├── decisions/        # Architecture Decision Records
│   ├── prompts/          # LLM prompts
│   └── runbooks/         # Operations guides
└── docker-compose.yml    # Local development environment
```

## Architecture

For complete system architecture and design decisions, see [CLAUDE.md](./CLAUDE.md).

### Phases

- **Phase 1** — Foundation (current)
  - Monorepo setup
  - Basic backend & frontend
  - CI/CD pipelines

- **Phase 2** — Supabase Schema
  - Database migrations
  - RLS policies
  - Seed data

- **Phase 3** — Walking Skeleton
  - Authentication
  - Layout & routing
  - Cloud deployment (Vercel + Render)

## Development

### Running Tests

**Backend:**
```bash
cd apps/backend
uv run pytest
```

**Frontend:**
```bash
cd apps/frontend
npm test
```

### Code Quality

**Backend:**
```bash
cd apps/backend
uv run ruff check .    # Linting
uv run mypy src        # Type checking
```

**Frontend:**
```bash
cd apps/frontend
npx tsc --noEmit       # Type checking
```

## CI/CD

GitHub Actions workflows run automatically on:
- Push to `main`
- Pull requests

Workflows validate:
- Backend: ruff (linting), mypy (types), pytest (tests)
- Frontend: tsc (types), vite build

## Environment Variables

See `.env.example` for a complete list of all environment variables used by the system.

### Critical Frontend Variables
⚠️ **IMPORTANT**: These must be set correctly or the frontend cannot communicate with the API:

- `VITE_API_URL` — Backend API URL (default: `http://localhost:8000`)
  - ❌ NOT `VITE_API_BASE` or `VITE_API_BASE_URL`
  - This is used by the Vite proxy to route API requests
  
- `VITE_SUPABASE_URL` — Supabase project URL
- `VITE_SUPABASE_ANON_KEY` — Supabase anonymous key

### Backend Variables

- `CORS_ORIGINS` — Frontend URLs allowed to call the API (default: `http://localhost:5173`)
- Database/Cache variables (see `.env.example` for full list)

## Troubleshooting

### Frontend Error: "Failed to fetch [endpoint]: Response is not JSON (received text/html)"

**Cause:** The `VITE_API_URL` environment variable is not set correctly in `apps/frontend/.env`

**Fix:**
1. Check `apps/frontend/.env` has: `VITE_API_URL=http://localhost:8000`
2. NOT `VITE_API_BASE` or `VITE_API_BASE_URL`
3. Restart the frontend dev server: `npm run dev`
4. Hard refresh the browser: `Cmd+Shift+R` (Mac) or `Ctrl+Shift+R` (Windows)

### Employee/Contact Data Pages Show Error

**Cause:** API endpoint variables not configured or proxy misconfigured

**Fix:**
1. Verify backend is running: `curl http://localhost:8000/health`
2. Check `VITE_API_URL` in frontend `.env`
3. Check `CORS_ORIGINS` in root `.env` includes `http://localhost:5173`
4. Restart both backend and frontend

## Deployment

See [Phase 3 deployment docs](./docs/runbooks/) for instructions on deploying to Vercel (frontend) and Render (backend).

## Documentation

- **CLAUDE.md** — Complete system specification
- **FRONTEND_SETUP.md** — Frontend setup guide with automation scripts
- **FRONTEND_API_VALIDATION.md** — API configuration & troubleshooting
- **EMAIL_BACKFILL_GUIDE.md** — Historical email scanning with 5-10x performance boost
- **docs/decisions/** — Architecture decision records
- **docs/prompts/** — LLM prompt templates
- **docs/runbooks/** — Operations & troubleshooting guides

---

Built with ❤️ for PandaTech.
