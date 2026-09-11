# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**Benefits Compare** — a multi-tenant B2B backend + Next.js frontend that helps employers
compare healthcare/insurance plans from providers: deterministic eligibility + scoring
(rules engine), plus optional LLM-generated, citation-grounded narratives via RAG and a
LangGraph agentic chat. Full product context, data model, and API list live in
`PROJECT.md` — read that first for anything beyond basic orientation.

Not a git repository yet (`Is a git repository: false`) — treat any git command as
something to confirm with the user first (e.g. offer `git init`).

## Directory layout

```
backend/                 FastAPI app (Python 3.11, async SQLAlchemy)
  main.py                App entrypoint, lifespan (create_all/seed/index worker), /health
  core/                  Settings (config.py), JWT + password hashing (security.py), RBAC (policies.py)
  api/v1/                Route modules: auth, plans, comparisons, documents, rag, agents, admin
  api/deps.py            DB session + JWT auth dependencies
  domain/                Enums + domain/rules_engine (eligibility + scoring engine — the live one)
  comparison/rules_engine  Empty directory, no files — stale, safe to ignore/remove
  models/                SQLAlchemy ORM tables (base.py, entities.py)
  schemas/               Pydantic request/response models
  services/               Business logic called by routes (plan, comparison, document, rag, narrative, agent, admin)
  rag/                    Ingest pipeline: loaders, splitters, embeddings, store (Qdrant), retriever, rerank, generate, cache (Redis)
  agents/                LangGraph agentic RAG: graph.py, nodes.py, routing.py, state.py, tools.py, subgraphs/ (policy.py, compare.py)
  workers/                Background indexing queue/worker (Redis-backed)
  observability/         Structured agent tracing/logging
  db/                    session.py (async engine), seed.py (demo data)

frontend/                Next.js (App Router) UI, TypeScript
  src/app/                Routes: /login, /register, and role-aware (app)/ group:
                          /plans, /comparisons/[id], /chat, /employer, /provider, /platform
  src/components/        AppShell, AuthGuard, PlanEditorForm
  src/lib/                api.ts (backend client), auth.ts, types.ts

alembic/                 DB migrations (versions/0001..0005); alembic.ini at repo root
data/plans/               Seed policy booklet markdown files (indexed on startup)
data/uploads/             Uploaded plan documents
infra/                    docker-compose.yml (Postgres, Redis, Qdrant, + app profile), docker/api-entrypoint.sh
tests/                    pytest unit/integration tests (rules engine, RAG helpers, agent graph, API/SSE contracts)
scripts/                  One-off scripts (e.g. smoke_pec_waiting.py)
notes/                    Dated working notes (not project docs)
requirements.txt          Python deps (FastAPI, SQLAlchemy async, LangChain/LangGraph, Qdrant, etc.)
pytest.ini                Pytest config
PROJECT.md                 Full product/architecture writeup — the primary reference doc
```

## Stack

- **Backend**: FastAPI, SQLAlchemy (async, `asyncpg`), Alembic, Pydantic v2, JWT auth
  (`python-jose`), `passlib`/`bcrypt<4.1`, Redis, Qdrant, LangChain + LangGraph, BM25
  (`rank-bm25`), `pypdf`. Python 3.11 in `.venv`.
- **Frontend**: Next.js (App Router), TypeScript, calls the API via `NEXT_PUBLIC_API_URL`.
- **Infra**: Postgres 16, Redis 7, Qdrant 1.12 via Docker Compose (`infra/docker-compose.yml`).
  Ollama (external, Mac Studio) provides OpenAI-compatible chat + embeddings.

## Running things

```bash
# infra
cd infra && docker compose up -d

# API (repo root, venv already created at .venv)
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8102

# frontend
cd frontend && npm run dev   # http://localhost:3100

# tests
pytest -q
```

Local dev defaults to `AUTO_CREATE_TABLES=true` (SQLAlchemy `create_all`); Docker/prod
uses Alembic only (`alembic upgrade head`, `AUTO_CREATE_TABLES=false`). See `PROJECT.md`
"How to run" for full details, seed users, and the Phase 2 smoke path.

## Conventions / notes for future work

- Role-based access is centralized in `backend/core/policies.py` — check there before
  adding any new visibility rule (pricing hidden from employers, providers see only their
  own plans, etc.).
- The rules engine (`backend/domain/rules_engine/engine.py`) is deterministic and
  versioned (`1.0.0` in `audit_trace`); eligibility/scoring must never be inferred by the
  LLM — the `compare` LangGraph subgraph always calls `run_comparison` before generating.
- RAG-generated narratives must stay grounded in retrieved policy text and must never
  include pricing.
- `backend/comparison/rules_engine/` is an empty stale directory; the real engine is
  `backend/domain/rules_engine/engine.py`.
- Update `PROJECT.md` (not this file) when product scope, endpoints, or data model change;
  keep this file limited to orientation for coding agents.
