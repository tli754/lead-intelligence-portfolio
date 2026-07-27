# lead-intelligence

> **Note:** this is a learning project, built to explore harness
> design (planner → generator → evaluator agent workflows) rather
> than as a production lead-gen tool.

Turns pasted lead data (a plain domain list, or raw HTML copied from
storelead.app's results grid) into structured `Company` records in
MongoDB, then discovers, crawls, and extracts structured facts (with
evidence) from each company's website. Part of a larger pipeline:
Ingestion → Crawling → Interpretation → Scoring → API → Frontend — this
repo currently covers Ingestion through Interpretation:

- **companies** — the core `Company` record and its status lifecycle
- **imports** — paste-in ingestion (domain lists, StoreLeads HTML)
- **discovery** — sitemap/robots/link crawl to find candidate pages
- **crawling** — fetches and stores page content for discovered URLs
- **evidence** — source snippets backing extracted facts
- **extraction** — turns crawled content into structured facts with evidence

See `ARCHITECTURE.md` for the layering rules and `CLAUDE.md` for the
full directory layout.

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
# backend, from the repo root — two test suites under backend/tests/modules/companies
# and backend/tests/test_company_module_api.py are known-stale and abort collection,
# so ignore them explicitly until they're deleted (see CLAUDE.md's "Where tests live")
pytest --ignore=backend/tests/modules/companies --ignore=backend/tests/test_company_module_api.py

cd frontend && pnpm run test    # frontend
```

## Contributing a feature

This repository uses a planner → generator → evaluator workflow (see
`.claude/agents/`). Feature contracts live in `docs/contracts/`,
execution plans in `docs/execution-plans/`, and ADRs in
`docs/decisions/`.

The split exists for the same reason described in Anthropic's
[Harness design for long-running applications](https://www.anthropic.com/engineering/harness-design-long-running-apps)
and OpenAI's [Harness engineering](https://openai.com/index/harness-engineering/):
a single agent asked to both build and judge its own work tends to
rubber-stamp mediocre output, and a single agent given an entire
feature end-to-end loses coherence over a long context. Separating
generation from evaluation, and decomposing work into
planner-approved contracts before any code is written, keeps each
step small enough for an agent to actually get right — and gives a
human a small number of high-leverage points (the contract, the PASS/
FAIL from the evaluator) to review instead of every line of output.
