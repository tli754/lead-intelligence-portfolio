# lead-intelligence

Turns pasted lead data (a plain domain list, or raw HTML copied from
storelead.app's results grid) into structured `Company` records in
MongoDB. First stage of a larger pipeline: Ingestion → Crawling →
Interpretation → Scoring → API → Frontend. See `ARCHITECTURE.md` for
the layering rules and `CLAUDE.md` for the directory layout.

## Prerequisites

- Python 3.11+
- Node.js (for the frontend)
- MongoDB reachable at `localhost:27017`

## MongoDB

If you already have a MongoDB instance running locally on `27017`
(e.g. a shared dev-infra stack), use that — nothing else to do.

Otherwise, start the one this project provides:

```bash
docker-compose up -d mongo
```

Don't run both — they'll conflict on port `27017`.

## Backend

```bash
export MONGODB_URI=mongodb://localhost:27017
export MONGODB_DB_NAME=lead_intelligence
export CORS_ALLOWED_ORIGINS=http://localhost:5173
.venv/bin/uvicorn backend.app.main:app --reload --port 8000
```

(Or copy `.env.example` to `.env` to avoid exporting these each time.)

Verify it's up:

```bash
curl http://localhost:8000/api/health
# {"status":"ok"}
```

## Frontend

```bash
cd frontend
pnpm install   # first time only
pnpm run dev
```

Open http://localhost:5173 — the import screen talks to the backend
at `http://localhost:8000` (set via `VITE_API_BASE_URL`).

## Tests

```bash
pytest                          # backend, from the repo root
cd frontend && pnpm run test    # frontend
```

## Contributing a feature

This repository uses a planner → generator → evaluator workflow (see
`.claude/agents/`). Feature contracts live in `docs/contracts/`,
execution plans in `docs/execution-plans/`, and ADRs in
`docs/decisions/`.
