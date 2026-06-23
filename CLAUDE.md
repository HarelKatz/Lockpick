# Lockpick — Claude Code Guide

## What this project is

SSH pivot tracker for red teams. Ingests raw evidence (private keys, `authorized_keys`, `auth.log`, `known_hosts`, bash history, `/etc/passwd`, `/etc/shadow`, `/etc/ssh/sshd_config`, nmap XML, `/etc/hosts`, sudoers) and builds a relationship graph showing lateral movement paths across an engagement. Runs as a shared web server — single `docker compose up -d`, no external dependencies.

> Human contributors browsing GitHub: see CONTRIBUTING.md for the welcome / commit format / gate.

@AGENT.md

## Working Style

- **Do not survey the codebase before starting.** Do not open files to "understand the project" — AGENT.md describes everything you need to know upfront.
- **Read files on-demand only.** Open a source file only when you are about to edit it or need to understand a specific function/interface it provides. Never read a file "just in case."

## Pyright LSP — Tagged-Hint False Positives

**Rule: a `★ "X is not accessed"` hint is not actionable on its own.** It is a tagged hint, not a diagnostic, and cannot be suppressed — `# pyright: ignore` does nothing for tagged hints (see [pyright #10132](https://github.com/microsoft/pyright/issues/10132)). When this hint fires on a protected pattern below, leave the code untouched and do not narrate the hint in your reply.

**Protected patterns — never delete, rename, alias, or "fix" on the basis of a tagged hint:**

- **Side-effect import** `import models  # noqa: F401` in `backend/main.py` — registers SQLAlchemy `Base.metadata` before Alembic runs. Removing it breaks migrations.
- **FastAPI lifespan parameter** `lifespan(app: FastAPI)` in `backend/main.py` — required by FastAPI's lifespan contract even when the body doesn't reference `app`.
- **Route-handler `Depends(...)` parameters** — e.g. `db: Session = Depends(get_db)` in `backend/routers/*.py`. The parameter exists to trigger DI; the body is not required to reference it.

**Forbidden when the only signal is a tagged hint on one of the above:**
- Deleting the import or parameter
- Renaming to `_app` / `_db` / any underscore-prefixed alias
- Adding `del app`, `_ = app`, or any throwaway reference
- Adding `# pyright: ignore[...]`, `# type: ignore`, or new `# noqa` comments (the existing `# noqa: F401` on `import models` stays — do not add others)
- Moving the import under `if TYPE_CHECKING:`

Real diagnostics (`reportMissingImports`, type errors — ✘/⚠) still matter. A tagged hint on a pattern NOT listed above is worth a closer look, but it is still not grounds for deletion without confirming at runtime that the symbol is unused.

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
- Decompress gzip when applicable: command-output and log parsers that may arrive gzipped (auth.log, ps, netstat, ip/iptables/nft output, etc.) must check gzip magic bytes (`content[:2] == b'\x1f\x8b'`) and decompress before parsing. Parsers for artifacts that never arrive gzipped need not.
- Use `metadata.host_id` as the source host for all emitted records
- Return counts in `result.stats` (e.g. `{"hosts": 3, "connections": 12}`) — the UI shows this summary
- IP matching: use `resolve_ip()` from `services/ip_resolver.py` to map raw IPs to existing hosts
- Multi-identifier hosts: when a parser finds multiple identifiers for the SAME host (e.g. a multi-IP nmap host, or `/etc/hosts` line with IP + hostnames), emit ONE `HostData` with the primary in `ip_address` and the rest in `aliases` — never emit separate `HostData` per identifier. The pipeline adds aliases as additional `HostIP` rows on the resolved host
- Fingerprint extraction: return raw key material in `CredentialData`; `key_utils.infer_key_info` and cross-referencing against existing credentials is handled automatically by the upload router — parsers do not compute fingerprints
- SSH config patterns: when a `Host` block has wildcard/token aliases (`*`, `?`, `%`), emit `SshConfigPatternData` — never a `ConnectionData` or `HostData` for the pattern itself
- System/service user filtering: when emitting `host_users_found`, only include accounts that can actually log in. For passwd: skip UID < 1000 (except root) and nologin/false shells. For shadow: skip entries with `x`, `!!`, `""`, `*`, `!` password sentinels — only emit users with a real recoverable hash
- Shell rc secret harvest: `ShellRcParser` (bashrc/zshrc) aggressively flags exported env vars whose names match `*_PASSWORD`/`*_TOKEN`/`*_SECRET`/`*_API_KEY`/`*_DSN`/`AWS_*` as `CredentialData` with `cred_type=password`. Common shell-internal vars (PATH, EDITOR, SSH_AUTH_SOCK, etc) are denylisted; dynamic values (`$VAR`, `$(cmd)`, backticks) are skipped — they don't carry a literal secret.
- Network config parsers (`network_interfaces`, `netplan`, `ifcfg`): emit only the upload host's own IPs as one `HostData` (first IP primary, rest aliases). Gateways are counted in `stats` but never emitted as host records — they belong to other hosts on the network and would create phantoms.
- Local-side sentinel `__upload_host__`: command-output parsers that observe a connection from the upload host's perspective emit `__upload_host__` for the local side instead of a literal local hostname/IP. Most (`netstat`, `ss_output`, `ip_neigh`, `arp`, `ps_output`) place it in `src_ip`; `iptables`/`nftables` place it on whichever side (`src_ip` or `dst_ip`) lacks a specific host. The pipeline (`_resolve_ip_side` in `services/upload_pipeline.py`) routes this sentinel to the upload host, same path as loopback (Architecture Rule #15). Avoids creating phantom hosts from truncated `localhost.localdom` strings or shifting local IPs.

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

Samples for future-phase parsers are staged in `real_examples/` but skipped by both layers until their parser is registered in `backend/parsers/registry.py`. Registering a new parser auto-lights-up its samples.

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

Key variables: `--text-primary`, `--text-muted`, `--bg-surface`, `--bg-surface-2`, `--border`, `--accent`, `--success` (confirmed), `--warning` (observed). The third confidence level (indicator) has **no** CSS custom property — graph-canvas confidence colors live as JS constants in `frontend/src/theme.ts` (`CONFIDENCE_*`) because the Canvas API cannot read CSS variables.

Use CSS modules (`.module.css` alongside the component) — not global styles.

### Create-form double-submit guard

Any handler that POSTs a non-idempotent create (`createHost`, `createCredential`, `createCredentialLink`, `createConnection`, `createHostNote`, etc.) — whether triggered by `<form onSubmit>`, an `onClick` button, or a keyboard shortcut — must guard with a `useRef`-based flag. The `disabled={loading}` attribute is React-state-driven and async, so rapid clicks in the same tick all see `loading=false` and dispatch concurrent POSTs (a stress test confirmed 5 clicks → 5 duplicate links). Pattern:

```tsx
const submittingRef = useRef(false)

async function handleSubmit(e: React.FormEvent) {
  e.preventDefault()
  if (submittingRef.current) return
  // ...validations that early-return without flipping the ref...
  submittingRef.current = true
  setLoading(true)
  try {
    await createX(...)
    onSuccess()
  } catch { setError(...) }
  finally {
    submittingRef.current = false
    setLoading(false)
  }
}
```

Pure-edit forms (PATCH/PUT only) don't need this — repeated identical updates are idempotent.

## Repository Layout

```
backend/
├── main.py          # App entry + CORS + lifespan (runs Alembic on startup)
├── config.py        # Settings via env vars (pydantic-settings)
├── database.py      # SQLAlchemy engine, session factory, Base
├── models.py        # ORM models
├── schemas.py       # Pydantic request/response models
├── ws_manager.py    # WebSocket manager; broadcast_sync() after db.commit()
├── routers/         # One file per resource group
├── parsers/         # File parsers + registry (file_type → class)
├── collection_script/ # Static bash collection script (Architecture Rule #21)
├── services/        # graph_builder, ip_resolver, pivot_analysis, upload_pipeline, host_merge, activity, key_utils, ssh_pattern
└── alembic/         # Migrations

frontend/src/
├── main.tsx         # Vite entrypoint (mounts App.tsx)
├── App.tsx          # Root component + page routing
├── theme.ts         # Dark theme color constants (source of truth)
├── index.css        # Global styles + CSS custom properties
├── types/           # TypeScript interfaces matching backend schemas
├── api/             # Typed API client functions
├── components/      # Shared UI components
├── hooks/           # Shared React hooks (e.g. useOpWebSocket.ts)
├── constants/       # Shared constants (e.g. credentialLink.ts)
├── utils/           # Shared utility functions
└── pages/           # Top-level page components

tests/
├── conftest.py      # Shared fixtures (in-memory DB, TestClient)
├── fixtures/        # Sample files for parser tests
├── test_api/        # API integration tests
├── test_parsers/    # Parser unit tests
├── test_services/   # Service layer tests
├── test_real_examples/  # Parser regression vs real_examples/ corpus (make test-real-examples)
└── test_scenario_*.py   # Network scenario tests (make test-scenarios)
```

## Environment Variables (backend)

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `../data/tracker.db` | SQLite database path |
| `UPLOAD_PATH` | `../data/uploads` | Uploaded raw files directory |
| `ARCHIVE_IMPORT_MAX_BYTES` | `104857600` | Size cap (100 MiB) on the compressed bulk archive upload |
| `ARCHIVE_IMPORT_MAX_UNCOMPRESSED_BYTES` | `524288000` | Size cap (500 MiB) on uncompressed archive contents — gzip-bomb defense |

Frontend uses `/api` prefix proxied by nginx (production) or `vite.config.ts` (dev). No frontend env vars needed.
