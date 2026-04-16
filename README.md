# Zoning Finder

A production-quality web application that lets real-estate acquisition teams find vacant parcels zoned for self-storage, mini-warehouse, light industrial, or luxury garage condominium development.

## Quick Start (local)

### Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Node.js 20+ & pnpm 9+

### 1. Clone and configure

```bash
git clone <repo>
cd zoning-finder
cp .env.example .env
# Fill in ANTHROPIC_API_KEY (required for ordinance parsing)
# Optionally fill in REGRID_API_KEY
```

### 2. Start Postgres + PostGIS

```bash
docker-compose up -d db
```

### 3. Run the backend

```bash
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 4. Run the frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Open http://localhost:3000.

---

## Phase Demo Scripts

### Phase 1 — Skeleton health check

```bash
# Backend
curl http://localhost:8000/health
# → {"status":"ok"}

# Frontend
open http://localhost:3000
# → Landing page renders
```

### Phase 2 — Draper, UT happy path

```bash
cd backend
python -m app.scripts.seed_draper
# Loads ~2,000 parcels from the Draper ArcGIS FeatureServer
# Open http://localhost:3000, select "Draper, UT" from the dropdown
```

---

## Architecture

```
zoning-finder/
├── backend/          FastAPI + PostGIS + SQLAlchemy 2.x
│   ├── app/
│   │   ├── api/      REST endpoints
│   │   ├── models/   SQLAlchemy ORM (PostGIS geometry)
│   │   ├── schemas/  Pydantic v2
│   │   ├── services/ Business logic (ArcGIS, parser, overlays)
│   │   └── prompts/  Claude system prompts
│   └── tests/
└── frontend/         Next.js 14 App Router + MapLibre GL JS
    ├── app/
    └── components/
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript strict, Tailwind CSS, shadcn/ui |
| Map | MapLibre GL JS |
| Table | TanStack Table v8 |
| Data fetching | TanStack Query v5 |
| Validation | Zod |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.x |
| Database | PostgreSQL 16 + PostGIS |
| AI | Claude Sonnet 4.6 (Anthropic SDK) |
| Vector tiles | pg_tileserv |
| Deploy | Vercel (frontend) + Fly.io (backend + pg_tileserv) |

## Environment Variables

See `.env.example` for all required and optional variables.

## Running Tests

```bash
# Backend
cd backend
pytest --cov=app -v

# Frontend
cd frontend
pnpm test
pnpm typecheck
```

## Database Migrations

```bash
cd backend
# Generate a new migration after model changes
alembic revision --autogenerate -m "description"
# Apply migrations
alembic upgrade head
# Rollback
alembic downgrade -1
```
