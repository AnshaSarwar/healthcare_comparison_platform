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
  - **Email verification**: `POST /auth/register` creates the user with
    `email_verified=false` and fires a verification email (see below); confirm via
    `POST /auth/email/verify {token}`, resend via
    `POST /auth/email/resend-verification {email}` (always 202, no user enumeration).
    Verification is advisory, not a login gate — `/auth/me` exposes `email_verified` for
    the frontend to nag on, but an unverified user can still sign in. Seeded demo users
    (`backend/db/seed.py`) are pre-verified.
  - **Password reset**: `POST /auth/password-reset/request {email}` (always 202) emails a
    short-lived (30 min) single-use token; `POST /auth/password-reset/confirm {token,
    new_password}` sets the new password and revokes every existing refresh token for
    that user (forces re-login everywhere, treating a reset as compromise recovery).
  - **Invite-based provider onboarding**: healthcare providers can no longer
    self-register — `POST /auth/register` now only accepts `org_type=employer`
    (`backend/services/admin.py::register_tenant` rejects `healthcare_provider`). A
    platform admin creates an invite (`POST /invites`, platform-admin only) which emails
    a link; the invitee previews it via `GET /auth/invites/{token}` and accepts via
    `POST /auth/invites/{token}/accept {password}`, which creates the org +
    `HealthcareProvider` profile + a pre-verified `healthcare_org_admin` user and logs
    them in. Manage invites via `GET /invites` / `POST /invites/{id}/revoke`. Token
    issuance/consumption for all three flows lives in `backend/services/auth_flows.py`
    (kept separate from `backend/services/admin.py`'s tenant CRUD).
  - **Email delivery**: `backend/core/email.py`. No SMTP provider is wired up in
    `infra/docker-compose.yml`, so the default `EMAIL_BACKEND=console` just logs the
    message (the token is visible in API logs for local dev). Set `EMAIL_BACKEND=smtp`
    plus the `SMTP_*` settings for a real provider — it uses stdlib `smtplib`, not a
    vendor SDK, so any standard SMTP endpoint works. Links are built from
    `FRONTEND_BASE_URL` (e.g. `{FRONTEND_BASE_URL}/verify-email?token=...`); the
    corresponding pages (`frontend/src/app/{verify-email,forgot-password,reset-password,
    accept-invite}/`) consume them, plus an unverified-email nudge banner in `AppShell`
    (resend button) and a provider-invite management panel on the platform admin page.
- **Versioning**: API versioned by path (`/api/v1`); bump the path segment for breaking
  changes rather than content negotiation.

## Known gaps (productionization, not comparison logic)

The rules engine, RAG pipeline, and agentic chat already work end-to-end. What's missing
is SaaS hardening:

- Tenancy/billing: no subscription tiers, no Stripe, no per-org usage limits (careful:
  "plans" in a billing sense would collide in naming with insurance `plans` — pick a
  distinct term, e.g. `subscription_tiers`).
- Auth hardening, email verification, password reset, and invite-based provider
  onboarding are done end-to-end (backend + frontend, see "Auth" above). Still missing: a
  real transactional-email provider wired into `infra/docker-compose.yml` (currently just
  console-logs in dev; `EMAIL_BACKEND=smtp` works but nothing runs an SMTP server
  locally).
- CI is done: `.github/workflows/ci.yml` runs ruff + pytest (backend) and
  eslint + `tsc --noEmit` (frontend) on every push/PR. Ruff config lives in the root
  `pyproject.toml`.
- Rate limiting is done: `backend/core/rate_limit.py` (Redis-backed slowapi `Limiter`,
  reusing `Settings.redis_url`) protects `/auth/login`, `/auth/register`,
  `/auth/refresh`, `/auth/logout` (per-IP) and `/rag/query`, `/agents/chat` (per
  authenticated user). Thresholds are tunable via `Settings.rate_limit_*`, not
  hardcoded in route files.
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
