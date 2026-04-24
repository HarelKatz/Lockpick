# Lockpick — Claude Code Guide

## What this project is

SSH pivot tracker for red teams. Ingests raw evidence (private keys, `authorized_keys`, `auth.log`, `known_hosts`, bash history, `/etc/passwd`, `/etc/shadow`, `/etc/ssh/sshd_config`, nmap XML, `/etc/hosts`, sudoers) and builds a relationship graph showing lateral movement paths across an engagement. Runs as a shared web server — single `docker compose up -d`, no external dependencies.

@AGENT.md

## Working Style

- **Do not survey the codebase before starting.** Do not open files to "understand the project" — AGENT.md describes everything you need to know upfront.
- **Read files on-demand only.** Open a source file only when you are about to edit it or need to understand a specific function/interface it provides. Never read a file "just in case."

## Git Commits

Commit after every unit of completed work: feature, bug fix, refactor, parser, schema change + migration, test file, or edit to `CLAUDE.md` / `AGENT.md`. Skip only for isolated typos and single-line CSS tweaks. One commit per unit, not batched at end of session — the user should never have to prompt a commit.

**Before the pre-commit gate, ask:** did this change introduce a runtime-enforced invariant or cross-file contract (a new `lazy="raise_on_sql"`, a new required-call-before-commit, a new structural rule)? If yes, add an Architecture Rule to AGENT.md in the same commit — the gate catches violations, but the rule is what tells the next contributor the invariant exists before they trip it.

**Pre-commit gate (code changes):**

```bash
make test                       # must pass
cd frontend && npm run build    # must succeed
```

Doc-only changes (`.md`) can skip the build gate.

**Format:**

```
type(scope): short description

types: feat, fix, refactor, test, docs, chore
scopes: backend, frontend, parsers, docker, schema
```

Stage specific files — never `git add .` (risks staging `.env`, keys, or build artifacts).

> AGENT.md maintenance rules live in AGENT.md itself.

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

# Tests (full suite — required before every commit)
make test           # full suite, parallel, quiet — failures only

# Tests (by group — for fast iteration while working in a specific area)
make test-api       # API integration tests (~14s)
make test-parsers   # parser unit tests (~0.1s)
make test-services  # service layer tests (~0.7s)
make test-scenarios # scenario tests (~4.5s)
make test-real-examples  # parser regression vs real_examples/ corpus (~0.5s)
```

**Always use `uv run` for Python — never `python` directly.**

## Adding a New Endpoint

1. ORM model in `backend/models.py` (if new table)
2. Pydantic schemas in `backend/schemas.py` (Create / Update / Read variants)
3. Router function in `backend/routers/` (or new file)
4. Register router in `backend/main.py`
5. If the endpoint ingests parseable evidence files, dispatch through `services/upload_pipeline.process_single_file()` — do not duplicate parser-dispatch logic (Architecture Rule #20)
6. Alembic migration if schema changed: `cd backend && uv run alembic revision --autogenerate -m "describe"`
7. Call `log_activity()` before `db.commit()` in every write endpoint (Architecture Rule #7)
8. Call `broadcast_sync(op_id, event)` after `db.commit()` in every write endpoint (Architecture Rule #18)
9. Tests in `tests/test_api/`
10. TypeScript types in `frontend/src/types/index.ts`
11. API client functions in `frontend/src/api/`

## Adding a New Parser

1. Create `backend/parsers/<name>.py` implementing `BaseParser`
2. Register in `backend/parsers/registry.py`: `"file_type": ParserClass`
3. Add fixture file(s) in `tests/fixtures/`
4. Add parser tests in `tests/test_parsers/test_<name>.py`

## SQLite Migration Rules

- **Always use `batch_alter_table`** — SQLite does not support `ALTER COLUMN`
- **Never drop constraints by name** — SQLite does not store named FK constraints; dropping by name raises `ValueError`; dropping the column alone is sufficient

## Parser Pattern

Parsers in `backend/parsers/` implement `BaseParser` — see `parsers/__init__.py` for the authoritative `ParseResult` / `BaseParser` signatures. Register in `parsers/registry.py` (`"file_type": ParserClass`).

**Parser guidelines (must follow):**
- Never crash on bad input — catch exceptions, append to `warnings`, and continue
- Decode bytes with `errors='replace'` to handle corrupt input
- Check for gzip magic bytes (`content[:2] == b'\x1f\x8b'`) and decompress before parsing
- Use `metadata.host_id` as the source host for all emitted records
- Return counts in `result.stats` (e.g. `{"hosts": 3, "connections": 12}`) — the UI shows this summary
- IP matching: use `resolve_ip()` from `services/ip_resolver.py` to map raw IPs to existing hosts
- Multi-identifier hosts: when a parser finds multiple identifiers for the SAME host (e.g. a multi-IP nmap host, or `/etc/hosts` line with IP + hostnames), emit ONE `HostData` with the primary in `ip_address` and the rest in `aliases` — never emit separate `HostData` per identifier. The pipeline adds aliases as additional `HostIP` rows on the resolved host
- Fingerprint extraction: return raw key material in `CredentialData`; `key_utils.infer_key_info` and cross-referencing against existing credentials is handled automatically by the upload router — parsers do not compute fingerprints
- SSH config patterns: when a `Host` block has wildcard/token aliases (`*`, `?`, `%`), emit `SshConfigPatternData` — never a `ConnectionData` or `HostData` for the pattern itself
- System/service user filtering: when emitting `host_users_found`, only include accounts that can actually log in. For passwd: skip UID < 1000 (except root) and nologin/false shells. For shadow: skip entries with `x`, `!!`, `""`, `*`, `!` password sentinels — only emit users with a real recoverable hash

Fixture files for parser tests live in `tests/fixtures/`.

## Parser Testing

Two layers:

- **Canonical behavior** — `tests/test_parsers/` with hand-crafted assertions against curated `tests/fixtures/` (e.g. "exactly 2 Accepted lines"). Canonical spec; edit these when parser behavior intentionally changes.
- **Regression coverage** — `tests/test_real_examples/` runs every registered parser against every sample in `real_examples/<type>/`. Smoke layer asserts no crash; snapshot layer diffs parser output against committed `<file>.expected.json` siblings (jc convention).

To regenerate snapshots after an intentional parser change:

```bash
REGEN_SNAPSHOTS=1 uv run pytest tests/test_real_examples/test_snapshots.py
git diff real_examples/     # skim for unexpected deltas
git add real_examples/
```

Samples for future-phase parsers (Phase 17–19) are staged in `real_examples/` but skipped by both layers until their parser is registered in `backend/parsers/registry.py`. Registering a new parser auto-lights-up its samples.

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

## Repository Layout

```
backend/
├── main.py          # App entry point, CORS, lifespan (runs Alembic on startup)
├── config.py        # Settings via env vars (pydantic-settings)
├── database.py      # SQLAlchemy engine, session factory, Base
├── models.py        # ORM models
├── schemas.py       # Pydantic request/response models
├── ws_manager.py    # WebSocket connection manager; broadcast_sync() called after db.commit()
├── routers/         # One file per resource group (operations, hosts, credentials, connections, graph, upload, collection, search, stats, export_import, activity, ws)
├── parsers/         # File parsers implementing BaseParser; registry.py maps file_type → class
├── collection_script/ # Static bash script served by GET /ops/{op_id}/collection-script
│   └── lockpick_collect.sh  # Byte-identical per op (Architecture Rule #21)
├── services/        # Graph builder, IP resolver, pivot analysis, shared upload helper
│   ├── graph_builder.py   # Aggregate CredentialLinks + ConnectionRecords → edge objects
│   ├── ip_resolver.py     # Match IPs/hostnames to known hosts (best-effort)
│   ├── key_utils.py       # Cross-reference fingerprints across an op
│   ├── pivot_analysis.py  # BFS path finding between hosts
│   ├── ssh_pattern.py     # ssh_match() SSH glob semantics; apply_patterns_to_host()
│   ├── upload_pipeline.py # process_single_file() — shared by upload + archive import (Architecture Rule #20)
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

## Environment Variables (backend)

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `../data/tracker.db` | SQLite database path |
| `UPLOAD_PATH` | `../data/uploads` | Uploaded raw files directory |
| `ARCHIVE_IMPORT_MAX_BYTES` | `104857600` | Size cap (100 MiB) on the compressed bulk archive upload |
| `ARCHIVE_IMPORT_MAX_UNCOMPRESSED_BYTES` | `524288000` | Size cap (500 MiB) on uncompressed archive contents — gzip-bomb defense |

Frontend uses `/api` prefix proxied by nginx (production) or `vite.config.ts` (dev). No frontend env vars needed.
