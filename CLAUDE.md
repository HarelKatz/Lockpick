# Lockpick — Claude Code Guide

## What this project is

SSH pivot tracker for red teams: ingests raw evidence (keys, `authorized_keys`, `auth.log`, `known_hosts`, bash history, system files, nmap, credential files) and builds a relationship graph of lateral-movement paths. Runs as a shared web server — single `docker compose up -d`, no external dependencies. See **README.md** for the full overview.

> Human contributors browsing GitHub: see CONTRIBUTING.md for the welcome / commit format / gate.

@ARCHITECTURE.md

## Project docs

- **ARCHITECTURE.md** — runtime invariants / cross-file contracts (the Architecture Rules). Auto-loaded with this file.
- **DATA_MODEL.md** — entity relationships, edge aggregation, pivot/confidence semantics. Read on demand.
- **TODO.md** — near-term task pool (what to work on next). Read on demand.
- **BACKLOG.md** — future / conditional work. Read on demand.
- **README.md** — what Lockpick is + how to run it. **CONTRIBUTING.md** — contributor pointer.

> These docs are the current source of truth; git history is the audit log.

## Working Style

- **Do not survey the codebase before starting.** Do not open files to "understand the project" — ARCHITECTURE.md (invariants), DATA_MODEL.md (relationships), and TODO.md (what's next) describe everything you need upfront.
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

Commit after every unit of completed work: feature, bug fix, refactor, parser, schema change + migration, test file, or edit to `CLAUDE.md` / `ARCHITECTURE.md` / `DATA_MODEL.md` / `TODO.md` / `BACKLOG.md`. Skip only for isolated typos and single-line CSS tweaks. One commit per unit, not batched at end of session — the user should never have to prompt a commit.

**Before the pre-commit gate, ask:** did this change introduce a runtime-enforced invariant or cross-file contract (a new `lazy="raise_on_sql"`, a new required-call-before-commit, a new structural rule)? If yes, add an Architecture Rule to ARCHITECTURE.md in the same commit — the gate catches violations, but the rule is what tells the next contributor the invariant exists before they trip it.

**Pre-commit gate (code changes):**

```bash
make test-backend               # backend — must pass
cd frontend && npm run build    # frontend typecheck + build — must succeed
make test-unit                  # frontend unit tests — must pass (fast, ~0.2s)
```

e2e stays out of the per-commit gate (too slow); run `make test-full` before a PR or as an agent check.

Doc-only changes (`.md`) can skip the build gate.

**Format:**

```
type(scope): short description

types: feat, fix, refactor, test, docs, chore
scopes: backend, frontend, parsers, docker, schema
```

Stage specific files — never `git add .` (risks staging `.env`, keys, or build artifacts).

> Doc-maintenance rules live in each task doc's header (TODO.md / BACKLOG.md).

## Running Things

```bash
# Docker (production-like)
docker compose up -d --build
# Frontend: http://localhost:3000 | Backend API: http://localhost:8000

# Local dev
make dev-backend    # uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
make dev-frontend   # npm run dev  (dev server: http://localhost:5173)

# Everything — backend + frontend unit + e2e. Serial + fail-fast by default (each layer
# prints a '=== ... ===' banner; a red layer aborts and Make names it). Add -j3 to run the
# layers concurrently (~30% faster on a multi-core box; e2e shares CPU, so it can slow a bit).
make test-full                            # serial (default; agent/CI-safe)
make -j3 --output-sync=target test-full   # parallel, output grouped per layer

# Backend pytest — full backend suite, parallel (-n auto), quiet, failures only.
# This is the layer the pre-commit gate runs.
make test-backend

# Backend by group — fast iteration while working in one area
make test-api       # API integration tests (~14s)
make test-parsers   # parser unit tests (~0.1s)
make test-services  # service layer tests (~0.7s)
make test-scenarios # scenario tests (~4.5s)
make test-real-examples  # parser regression vs real_examples/ corpus (~0.5s)

# Frontend unit (vitest) — pure logic extracted to src/utils/ (node env, fast)
make test-unit

# Frontend e2e (Playwright) — isolated stack + deterministic seed; asserts on
# window.__lockpick_graph__ (not pixels). Spins its own backend+frontend (~10s startup).
# Runs ALL projects (committed specs + the heavy scale(50) sweep).
make test-e2e

# Marker-driven tiers + the sub-90s pre-PR gate
make test-fast        # backend minus the property battery + slow/scale (the gate's backend layer)
make test-invariants  # the hypothesis property battery (tests/test_invariants/, -m property)
make test-scale       # slow/scale backend tests (-m slow; excluded from the gate, in test-full)
make fast-e2e         # committed e2e only (chromium project; excludes the scale(50) sweep)
make test-scale-e2e   # heavy scale(50) e2e layout invariants (chromium-invariants; excl. gate, in test-full)
make -j gate          # build + test-unit + test-fast + fast-e2e — sub-90s pre-PR check (run with -j)
```

**Always use `uv run` for Python — never `python` directly.**

**Verifying frontend changes:** use the **frontend-verify** skill — it's the standard for testing UI/graph features (committed Playwright specs via `make test-e2e` + live Playwright-MCP checks). See ARCHITECTURE.md Rule #26 for the `window.__lockpick_graph__` canvas-verification hook.

## Feature Design Pre-flight Checklist

Before building or reshaping a feature, answer these four blind-spot questions. Each "always/never" answer you land on is an invariant — write it as a test. The classes come from real misses (see the Misses log), not speculation.

1. **Interaction modes** — does it hold under *click* AND *drag* AND *keyboard*? An `onChange`/`setState` path is **not** a real drag — a controlled `setRange()` can pass green while a pointer drag jitters. Drive the real input.
2. **Layout / rendering** — does toggling it resize a neighbor, add a scrollbar, overflow, or jitter on reflow? The `window.__lockpick_graph__` hook is **blind to CSS/layout** — assert `boundingBox()` / `scrollHeight`, not just the data model.
3. **Model completeness** — does it hold for empty / one-host / undated / isolated / self-loop / null-host / long-nickname ops? Every "always"/"never" you claim must survive these shapes.
4. **Data profiles** — does it hold at 5 hosts AND 200? Run it over `profiles.normal()` and `profiles.scale(N)`.

### Misses log

When a bug ships green, add one line: the blind-spot class + the invariant/test that now covers it. Grows from real misses.

- **Interaction modes** — time-slider drag-only jitter (Reset button reflow) → e2e `time-slider.spec.ts` "the Reset control never resizes the slider track (no drag jitter)".
- **Model completeness** — isolated host hidden as the window narrowed → e2e "narrowing hides hosts left with no in-window connection" (+ the genuinely-isolated-host visibility fix).
- **Model completeness** — undated edge must never be hidden → e2e "narrowing the end keeps key-match + undated edges even when their date is out of window".
- **Layout / rendering** — floating nodes after filtering → e2e `invariants.spec.ts` "every visible node is painted within the canvas bounds" (+ `invariants-scale.spec.ts` at scale(50)).

## Test-Layering Doctrine

**The loop:** design (with the pre-flight checklist) → build + test together → verify across layers → use/explore a `normal()` op → feed every discovery back as a regression test **and** a Misses-log row. The point is that *using the app produces a failing test*, so features ship freely.

**Layers, cheapest first** (cheap ones gate every change; heavier ones run on demand):

1. **Unit** — pure logic, no I/O (frontend `vitest`, backend function tests). Milliseconds.
2. **Property / invariant** — general properties over generated ops (backend `hypothesis`, `tests/test_invariants/`; each guard demonstrably fail-provable). `make test-invariants`.
3. **Scenario** — a known topology through the real REST API (`make test-scenarios`).
4. **E2E invariants** — the `window.__lockpick_graph__` hook + `boundingBox` + console capture over `normal()` / `scale(N)`. Committed specs (incl. `invariants.spec.ts` over `normal`) run in the fast `chromium` project (`make fast-e2e`, in the gate); the heavy `scale(50)` sweep (`invariants-scale.spec.ts`) is a separate `chromium-invariants` project — excluded from the gate but run by `make test-e2e` / `test-full` and standalone via `make test-scale-e2e`.
5. **Agentic explore** — an agent drives the real browser to hunt the "looks/feels right" wall; a bug-FINDER that distills findings into deterministic specs, **never the gate** (BACKLOG).

**Default substrate:** `tests/opbuilder/profiles.normal()` is the standard op every layer builds on; edge-case shapes and `scale(N)` layer on as learned. `OpBuilder` is the one REST substrate — the same builder drives the pytest `TestClient` and the live-server `httpx.Client`.

**Accepted walls** (don't fight these — assert around them):

- **Canvas pixels** — the graph is a `<canvas>`, invisible to the DOM; assert render *state* via `window.__lockpick_graph__` (Rule #26), never screenshot-diff force-layout positions.
- **Aesthetic judgment** — "does it look right" isn't automatable; that's the agentic layer's job, feeding deterministic specs.
- **Headless ≠ real browser** — headless rendering can diverge; reserve screenshots for stable chrome.

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
- Local-side sentinel `__upload_host__`: command-output parsers that observe a connection from the upload host's perspective emit `__upload_host__` for the local side instead of a literal local hostname/IP. Most (`netstat`, `ss_output`, `ip_neigh`, `arp`, `ps_output`) place it in `src_ip`; `iptables`/`nftables` place it on whichever side (`src_ip` or `dst_ip`) lacks a specific host (routed to the upload host by `_resolve_ip_side`; see ARCHITECTURE.md Rule #15). Avoids phantom hosts from truncated `localhost.localdom` strings or shifting local IPs.

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
├── utils/           # Shared utils + pure graph/slider logic extracted from components, vitest-tested (co-located *.test.ts)
└── pages/           # Top-level page components

tests/
├── conftest.py      # Shared fixtures (in-memory DB, TestClient)
├── fixtures/        # Sample files for parser tests
├── test_api/        # API integration tests
├── test_parsers/    # Parser unit tests
├── test_services/   # Service layer tests
├── test_real_examples/  # Parser regression vs real_examples/ corpus (make test-real-examples)
├── test_scenario_*.py   # Network scenario tests (make test-scenarios)
├── opbuilder/       # Shared REST op-builder: OpBuilder/shapes/profiles (drives TestClient + httpx)
└── e2e/             # Playwright seed — seed_e2e.py replays profiles.normal() over a live server
```

## Environment Variables (backend)

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `../data/tracker.db` | SQLite database path |
| `UPLOAD_PATH` | `../data/uploads` | Uploaded raw files directory |
| `ARCHIVE_IMPORT_MAX_BYTES` | `104857600` | Size cap (100 MiB) on the compressed bulk archive upload |
| `ARCHIVE_IMPORT_MAX_UNCOMPRESSED_BYTES` | `524288000` | Size cap (500 MiB) on uncompressed archive contents — gzip-bomb defense |

Frontend uses `/api` prefix proxied by nginx (production) or `vite.config.ts` (dev). No frontend env vars needed.
