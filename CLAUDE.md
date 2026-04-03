# Lockpick — Claude Code Guide

## What this project is

SSH pivot tracker for red teams. Ingests raw evidence (private keys, `authorized_keys`, `auth.log`, `known_hosts`, bash history) and builds a relationship graph showing lateral movement paths across an engagement. Runs as a shared web server — single `docker compose up -d`, no external dependencies.

## Working Style

- **Do not survey the codebase before starting.** Read AGENT.md for architecture context, then begin implementing. Do not open files to "understand the project" — AGENT.md describes everything you need to know upfront.
- **Read files on-demand only.** Open a source file only when you are about to edit it or need to understand a specific function/interface it provides. Never read a file "just in case."

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy ORM, Alembic, uv
- **Database**: SQLite at `./data/tracker.db`
- **Frontend**: React 18, Vite, TypeScript, cytoscape.js (for graph)
- **Tests**: pytest + httpx (integration tests against real in-memory DB)
- **Deploy**: Docker Compose (backend + nginx-served frontend)

## Running Things

```bash
# Docker (production-like)
docker compose up -d --build
# Frontend: http://localhost:3000 | Backend API: http://localhost:8000

# Local dev
make dev-backend    # uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
make dev-frontend   # npm run dev  (dev server: http://localhost:5173)

# Tests
make test           # cd backend && uv run pytest ../tests/ -v
```

**Always use `uv run` for Python — never `python` directly.**

## Repository Layout

```
backend/
├── main.py          # App entry point, CORS, lifespan (runs Alembic on startup)
├── config.py        # Settings via env vars (pydantic-settings)
├── database.py      # SQLAlchemy engine, session factory, Base
├── models.py        # ORM models
├── schemas.py       # Pydantic request/response models
├── routers/         # operations.py, hosts.py, credentials.py, connections.py
├── parsers/         # File parsers implementing BaseParser
├── services/        # Graph builder, IP resolver, pivot analysis
│   ├── graph_builder.py   # Aggregate CredentialLinks + ConnectionRecords → edge objects
│   ├── ip_resolver.py     # Match IPs/hostnames to known hosts (best-effort)
│   ├── key_matcher.py     # Cross-reference fingerprints across an op
│   └── pivot_analysis.py  # BFS path finding between hosts (Phase 7)
└── alembic/         # Migrations

frontend/src/
├── App.tsx          # Root component + page routing
├── theme.ts         # Dark theme color constants (source of truth)
├── index.css        # Global styles + CSS custom properties
├── types/           # TypeScript interfaces matching backend schemas
├── api/             # Typed API client functions
└── pages/           # Top-level page components

tests/
├── conftest.py      # Shared fixtures (in-memory DB, TestClient)
└── test_api/        # API integration tests
```

## Data Model Rules

- **All IDs** are UUIDs stored as strings in SQLite
- **All timestamps** are timezone-aware UTC (ISO 8601)
- **No authentication** — trusted network tool, no login screen
- **All persistent state** lives in `./data/` — only thing to backup
- **`CredentialLink.username`** (plain string) is the authoritative field for pivot path queries — `host_user_id` is optional enrichment only
- **Edges between hosts are not stored** — the backend computes them by aggregating evidence (key matches, connection logs, known_hosts, bash_history) and returns `{"confidence": "confirmed|observed|indicator", "evidence": [...]}`

## Adding a New Endpoint

1. ORM model in `backend/models.py` (if new table)
2. Pydantic schemas in `backend/schemas.py` (Create / Update / Read variants)
3. Router function in `backend/routers/` (or new file)
4. Register router in `backend/main.py`
5. Alembic migration if schema changed: `cd backend && uv run alembic revision --autogenerate -m "describe"`
6. Tests in `tests/test_api/`
7. TypeScript types in `frontend/src/types/index.ts`
8. API client functions in `frontend/src/api/`

## SQLite Migration Rules

- **Always use `batch_alter_table`** — SQLite does not support `ALTER COLUMN`
- **Never drop constraints by name** — SQLite does not store named FK constraints; dropping by name raises `ValueError`; dropping the column alone is sufficient

## Parser Pattern

All parsers in `backend/parsers/` implement `BaseParser` (defined in `parsers/__init__.py`):

```python
class ParseResult:
    hosts_found: list[HostData]
    credentials_found: list[CredentialData]
    connections_found: list[ConnectionData]
    warnings: list[str]
    stats: dict

class BaseParser:
    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult: ...
```

Parsers **must never crash** on bad input — catch exceptions, append to `warnings`, and continue. Fixture files for parser tests live in `tests/fixtures/`.

## Key Architecture Rules

- **Edges are not stored** — computed on demand by `services/graph_builder.py` from CredentialLinks + ConnectionRecords
- **IP resolution is best-effort** — create an unresolved host if no existing host matches; user merges later
- **Frontend never touches the DB** — all data flows through the REST API
- **No authentication** — trusted network tool; see AGENT.md for full architecture rules

## Frontend Conventions

### Dark Theme

Use only CSS custom properties — never hardcode colors:

```css
/* Good */
color: var(--text-primary);
background: var(--bg-surface);
border: 1px solid var(--border);

/* Bad */
color: #c9d1d9;
```

Key variables: `--text-primary`, `--text-muted`, `--bg-surface`, `--bg-surface-2`, `--border`, `--accent`, `--success` (confirmed), `--warning` (observed).

Use CSS modules (`.module.css` alongside the component) — not global styles.

## Git Commit Format

```
type(scope): short description

types: feat, fix, refactor, test, docs, chore
scopes: backend, frontend, parsers, docker, schema
```

**Before committing:** `make test` + `cd frontend && npm run build`. Stage specific files — avoid `git add .`.

## Environment Variables (backend)

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `../data/tracker.db` | SQLite database path |
| `UPLOAD_PATH` | `../data/uploads` | Uploaded raw files directory |

Frontend uses `/api` prefix proxied by nginx (production) or `vite.config.ts` (dev). No frontend env vars needed.
