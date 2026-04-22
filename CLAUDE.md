# Lockpick — Claude Code Guide

## What this project is

SSH pivot tracker for red teams. Ingests raw evidence (private keys, `authorized_keys`, `auth.log`, `known_hosts`, bash history, `/etc/passwd`, `/etc/shadow`, `/etc/ssh/sshd_config`, nmap XML) and builds a relationship graph showing lateral movement paths across an engagement. Runs as a shared web server — single `docker compose up -d`, no external dependencies.

@AGENT.md

## Working Style

- **Do not survey the codebase before starting.** Do not open files to "understand the project" — AGENT.md describes everything you need to know upfront.
- **Read files on-demand only.** Open a source file only when you are about to edit it or need to understand a specific function/interface it provides. Never read a file "just in case."

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy ORM, Alembic, uv
- **Database**: SQLite at `./data/tracker.db`
- **Frontend**: React 18, Vite, TypeScript, react-force-graph-2d + d3-force (for graph)
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
├── routers/         # One file per resource group (operations, hosts, credentials, connections, graph, upload, search, stats, export_import, activity)
├── parsers/         # File parsers implementing BaseParser; registry.py maps file_type → class
├── services/        # Graph builder, IP resolver, pivot analysis
│   ├── graph_builder.py   # Aggregate CredentialLinks + ConnectionRecords → edge objects
│   ├── ip_resolver.py     # Match IPs/hostnames to known hosts (best-effort)
│   ├── key_utils.py       # Cross-reference fingerprints across an op
│   ├── pivot_analysis.py  # BFS path finding between hosts
│   └── activity.py        # log_activity() — call before db.commit() in all write endpoints
└── alembic/         # Migrations

frontend/src/
├── App.tsx          # Root component + page routing
├── theme.ts         # Dark theme color constants (source of truth)
├── index.css        # Global styles + CSS custom properties
├── types/           # TypeScript interfaces matching backend schemas
├── api/             # Typed API client functions
├── components/      # Shared UI components
├── utils/           # Shared utility functions
└── pages/           # Top-level page components

tests/
├── conftest.py      # Shared fixtures (in-memory DB, TestClient)
├── fixtures/        # Sample files for parser tests
├── test_api/        # API integration tests
├── test_parsers/    # Parser unit tests
└── test_services/   # Service layer tests
```

## Adding a New Endpoint

1. ORM model in `backend/models.py` (if new table)
2. Pydantic schemas in `backend/schemas.py` (Create / Update / Read variants)
3. Router function in `backend/routers/` (or new file)
4. Register router in `backend/main.py`
5. Alembic migration if schema changed: `cd backend && uv run alembic revision --autogenerate -m "describe"`
6. Call `log_activity()` before `db.commit()` in every write endpoint (Architecture Rule #7)
7. Call `broadcast_sync(op_id, event)` after `db.commit()` in every write endpoint (Architecture Rule #18)
8. Tests in `tests/test_api/`
9. TypeScript types in `frontend/src/types/index.ts`
10. API client functions in `frontend/src/api/`

## Adding a New Parser

1. Create `backend/parsers/<name>.py` implementing `BaseParser`
2. Register in `backend/parsers/registry.py`: `"file_type": ParserClass`
3. Add fixture file(s) in `tests/fixtures/`
4. Add parser tests in `tests/test_parsers/test_<name>.py`

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
    host_users_found: list[tuple[str, Optional[str], Optional[str]]]  # (username, shell, home_dir)
    patterns_found: list[SshConfigPatternData]   # SSH Host wildcard/token blocks
    warnings: list[str]
    stats: dict

class BaseParser:
    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult: ...
```

**Parser guidelines (must follow):**
- Never crash on bad input — catch exceptions, append to `warnings`, and continue
- Decode bytes with `errors='replace'` to handle corrupt input
- Check for gzip magic bytes (`content[:2] == b'\x1f\x8b'`) and decompress before parsing
- Use `metadata.host_id` as the source host for all emitted records
- Return counts in `result.stats` (e.g. `{"hosts": 3, "connections": 12}`) — the UI shows this summary
- IP matching: use `resolve_ip()` from `services/ip_resolver.py` to map raw IPs to existing hosts
- Fingerprint extraction: return raw key material in `CredentialData`; `key_utils.infer_key_info` and cross-referencing against existing credentials is handled automatically by the upload router — parsers do not compute fingerprints
- SSH config patterns: when a `Host` block has wildcard/token aliases (`*`, `?`, `%`), emit `SshConfigPatternData` — never a `ConnectionData` or `HostData` for the pattern itself
- System/service user filtering: when emitting `host_users_found`, only include accounts that can actually log in. For passwd: skip UID < 1000 (except root) and nologin/false shells. For shadow: skip entries with `x`, `!!`, `""`, `*`, `!` password sentinels — only emit users with a real recoverable hash

Fixture files for parser tests live in `tests/fixtures/`.

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

## Git Commits

**Committing is not optional and does not require the user to ask.** Every unit of work ends with a commit. If you changed files and did not commit, the task is not done.

### What requires a commit

Commit after completing **any** of these:
- A feature, bug fix, or refactor (backend or frontend)
- A new or updated parser
- A schema change + Alembic migration
- A new or updated test file
- An edit to `CLAUDE.md` or `AGENT.md`

Skip only for: isolated typo fixes, single-line CSS tweaks, comment-only edits to non-guide files.

### Pre-commit gate (code changes)

```bash
make test                       # must pass — fix failures before committing
cd frontend && npm run build    # must succeed — fix build errors before committing
```

For documentation-only changes (`.md` files only), skip the build gate and commit directly.

### Commit format

```
type(scope): short description

types: feat, fix, refactor, test, docs, chore
scopes: backend, frontend, parsers, docker, schema
```

Stage specific files — never `git add .` (risks staging `.env`, keys, or build artifacts).

### The rule

**Commit as part of completing the work, not after.** Do not batch multiple unrelated changes into one commit. Do not defer committing to the end of a session. The user must never have to prompt a commit — if they do, you failed this instruction.

## AGENT.md Maintenance

AGENT.md is the single source of truth for architecture and project status. Update it as part of the work, not after being asked.

**When to update:**
- **Current Status**: every time a phase or significant sub-feature is completed
- **Phase checklist**: check off `[ ]` items as you complete them
- **Completed phase sections**: once a phase is 100% done, collapse its detail to the invariants future phases need (not a feature list — git history has that)

**How to update well:**
- Current Status must stay ≤5 lines: last completed thing, next thing, any blocker
- Completed phase notes must state *invariants* (contracts other code depends on), not retrospectives
- Never leave stale unchecked items for work that's already done
- Never add file trees, line numbers, CSS snippets, or diff hunks to AGENT.md

## Environment Variables (backend)

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `../data/tracker.db` | SQLite database path |
| `UPLOAD_PATH` | `../data/uploads` | Uploaded raw files directory |

Frontend uses `/api` prefix proxied by nginx (production) or `vite.config.ts` (dev). No frontend env vars needed.
