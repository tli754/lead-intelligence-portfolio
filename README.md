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

### Harness design notes

Ideas worth keeping in mind when evolving the agent workflow above,
from two articles on building harnesses for long-running coding
agents:

- [Harness design for long-running agentic development](https://www.anthropic.com/engineering/harness-design-long-running-apps) (Anthropic)
  — separate the agent that does the work from the agent that judges
  it (self-evaluation is biased); turn subjective review criteria
  into concrete, gradable rubrics; prefer a clean context reset over
  compaction for long tasks; break work into explicit "contracts"
  before implementation starts; re-examine the harness whenever the
  underlying model improves, since scaffolding built around old
  limitations can become unnecessary overhead.
- [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/) (OpenAI)
  — three pillars of a harness are constraints (narrowing the
  model's output space), observability (visibility into reasoning
  and tool-call trajectories), and feedback loops (continuous
  tuning based on real traces); more constraints often make agents
  *more* reliable, not less — architectural boundaries enforced by
  linters/validators help; anything not in-context effectively
  doesn't exist to the agent, so what the repo/docs surface matters
  as much as what the model can do; the highest-leverage work shifts
  from writing code to designing the environment the agent reasons
  in.

This repo's planner/generator/evaluator split and its "Asked →
Decided → Built" artifact trail (see `CLAUDE.md`'s Task workflow)
already reflect the generator/evaluator separation and the
contracts-before-implementation idea above.
