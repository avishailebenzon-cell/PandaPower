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
cp .env.example .env
```

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

Key variables for Phase 1:
- `CORS_ORIGINS` — Frontend URLs allowed to call the API
- `VITE_API_BASE_URL` — Backend URL for frontend

## Deployment

See [Phase 3 deployment docs](./docs/runbooks/) for instructions on deploying to Vercel (frontend) and Render (backend).

## Documentation

- **CLAUDE.md** — Complete system specification
- **docs/decisions/** — Architecture decision records
- **docs/prompts/** — LLM prompt templates
- **docs/runbooks/** — Operations & troubleshooting guides

---

Built with ❤️ for PandaTech.
