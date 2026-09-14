# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**Benefits Compare** — a multi-tenant B2B backend + Next.js frontend that helps employers
compare healthcare/insurance plans from providers: deterministic eligibility + scoring
(rules engine), plus optional LLM-generated, citation-grounded narratives via RAG and a
LangGraph agentic chat. This file is the sole standing reference doc for the repo (there
used to be a separate `PROJECT.md`; it was deliberately removed as redundant with this
file — don't recreate it).

## Stack

Ollama (chat + embeddings, OpenAI-compatible API) runs externally on a Mac Studio — not
discoverable from any manifest in this repo. Everything else (FastAPI/SQLAlchemy on the
backend, Next.js on the frontend, Postgres/Redis/Qdrant in `infra/docker-compose.yml`) is
standard and listed in `requirements.txt`/`package.json`.

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
uses Alembic only (`alembic upgrade head`, `AUTO_CREATE_TABLES=false`).

Demo accounts seeded by `backend/db/seed.py` (password `password123` for all):
`employer@acme.com` (employer_admin), `admin@healthfirst.com` / `admin@medicare.com`
(healthcare_org_admin), `platform@benefits.com` (platform_admin).

## Architectural boundaries

- **Protocol**: REST under `/api/v1` (one resource collection per aggregate: `plans`,
  `comparisons`, `documents`, `organizations`, `users`) + **SSE** for the two streaming
  routes (`/rag/query`, `/agents/chat`). No GraphQL — the domain is a small, clearly
  bounded set of resources; SSE streaming would only be complicated by a subscriptions
  layer on top of it. Revisit only if the frontend needs arbitrary cross-resource nested
  queries.
- **Frontend ↔ backend**: Next.js is a pure API client — no BFF business logic, no direct
  DB/Qdrant/Redis access from `frontend/`. All domain and RBAC logic stays server-side in
  `backend/`.
- **RBAC boundary**: `backend/core/policies.py` is the single source of truth for who can
  see what (pricing visibility, own-org scoping, comparison access). Frontend role-based
  routing (`src/lib/auth.ts` → `homeForRole`) is UX convenience only, never a security
  boundary — never gate a sensitive field on the client alone.
- **Rules engine vs LLM boundary**: eligibility/scoring is deterministic and must never be
  inferred by an LLM (see `backend/domain/rules_engine/engine.py`, versioned in
  `audit_trace`). The `compare` LangGraph subgraph always calls `run_comparison` before
  generating any narrative. RAG narratives must stay grounded in retrieved policy text and
  must never surface pricing.
- **State on the frontend** (target shape — the current client in `src/lib/api.ts` is
  plain `fetch` with no cache/invalidation layer yet): server state (plans, comparisons,
  org profile) via a query/cache layer (e.g. TanStack Query) wrapping the existing typed
  fetch functions; auth/session state via a small React context, not ad-hoc
  `localStorage` reads scattered across components; local UI state via plain
  `useState`/`useReducer`. Don't reach for a global store (Redux/Zustand) at this scale.
- **Auth**: short-lived (15 min) JWT access token + rotating, revocable refresh token
  (30 day, hashed server-side in `refresh_tokens`, single-use with reuse detection),
  delivered as httpOnly cookies (`backend/api/v1/auth.py`); no token is ever stored in
  browser `localStorage` or JS-readable. `get_security_context`
  (`backend/api/deps.py`) also still accepts a plain `Authorization: Bearer` header, so
  non-browser clients (`scripts/smoke_pec_waiting.py`, Swagger UI) are unaffected.
  Dev gotcha: `SameSite=Lax` cookies only flow between frontend and backend when both are
  addressed via `localhost` (not `127.0.0.1` — browsers treat those as different sites).
- **Versioning**: API versioned by path (`/api/v1`); bump the path segment for breaking
  changes rather than content negotiation.

## Known gaps (productionization, not comparison logic)

The rules engine, RAG pipeline, and agentic chat already work end-to-end. What's missing
is SaaS hardening:

- Tenancy/billing: no subscription tiers, no Stripe, no per-org usage limits (careful:
  "plans" in a billing sense would collide in naming with insurance `plans` — pick a
  distinct term, e.g. `subscription_tiers`).
- Auth hardening is done (see "Auth" above); still missing: email verification,
  password reset, invite-based provider onboarding.
- No CI (lint/type-check/test) wired up for this repo.
- No rate limiting on auth or the LLM-backed routes (`/rag/query`, `/agents/chat`) — the
  most expensive endpoints to leave unprotected.
- No generated TypeScript client from the FastAPI OpenAPI schema — `frontend/src/lib/types.ts`
  is hand-maintained and can drift from `backend/schemas/`.
- Seed data (`backend/db/seed.py`) is a single hardcoded demo tenant, not a factory for
  varied demo/load-test tenants.

## Conventions / notes for future work

- Role-based access is centralized in `backend/core/policies.py` — check there before
  adding any new visibility rule (pricing hidden from employers, providers see only their
  own plans, etc.).
- `backend/comparison/rules_engine/` is an empty stale directory; the real engine is
  `backend/domain/rules_engine/engine.py` (see "Rules engine vs LLM boundary" above).
- Keep this file updated as product scope, endpoints, or the data model change — it's the
  only standing reference doc for this repo now.
