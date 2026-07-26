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
- **Interaction modes** — `createHostNote` add-note (onClick button + Ctrl/Cmd+Enter on the textarea, one shared handler) guarded only by React state (`setNoteAdding`) fired concurrent POSTs in one tick → duplicate notes; fixed with the `useRef` double-submit guard → e2e `host-notes.spec.ts` "rapid Ctrl+Enter on the note input creates exactly one note".
- **Model completeness** — isolated host hidden as the window narrowed → e2e "narrowing hides hosts left with no in-window connection" (+ the genuinely-isolated-host visibility fix).
- **Model completeness** — undated edge must never be hidden → e2e "narrowing the end keeps key-match + undated edges even when their date is out of window".
- **Layout / rendering** — floating nodes after filtering → e2e `invariants.spec.ts` "every visible node stays finitely in-canvas (full graph and after filtering)": on the settled full graph every visible node is finite and in-canvas; after a host-toggle reflow every visible node stays finite/attached — in-canvas is deliberately *not* asserted post-filter because the app doesn't auto-refit after a toggle. Catches detached / null / NaN positions; `zoomToFit` reframes finite positions so far-but-finite drift is out of scope. Also asserted (full graph) at scale(50) in `invariants-scale.spec.ts`.
- **Test independence** — `test_wtmp.py` packed its fixtures with the parser's *own* `_UTMP_FMT`, so a 382-vs-384 `struct utmp` size bug round-tripped green and every real wtmp/btmp imported as **zero** logins; a binary-format test must pack at a layout independent of the impl (a hardcoded 384-byte format) + a direct `_UTMP_SIZE == 384` guard → `tests/test_parsers/test_wtmp.py`.
- **Model completeness** — `auth_log` stamped a naive `datetime.now().year` per line, so prior-year and Dec→Jan-spanning syslog logs were mis-dated (future-dated edges), and the real_examples snapshots baked the current year → they would break every New Year. Fixed with file-aware `_resolve_syslog_years` (anchor newest entry, walk backward across month-boundary crossings) + a `_now()` patch-point + a frozen reference in the snapshot suite → `tests/test_parsers/test_auth_log.py` year-inference tests (`test_year_boundary_split`, `test_prior_year_detected`) + `tests/test_real_examples/conftest.py`.
- **Model completeness** — standing rules (`ssh_config` patterns, and now `authorized_keys` `from=` ACLs) were only replayed against hosts created via `POST /hosts` / the add-IP route, never against hosts auto-created by `resolve_ip` during an upload — which is how hosts usually appear. So whether a stored rule ever reached a host was a coin flip on its creation path, and a test asserted the gap as intended behaviour rather than fixing it. Closed for both origins in `process_single_file` (Architecture Rule #28) → `tests/test_api/test_acl_standing_rules.py::test_rule_applies_retroactively_to_a_host_created_by_a_later_upload`. Lesson: "which creation paths does this fire on?" is a model-completeness question, and a test that documents a gap is not the same as covering it.
- **Cross-file contract** — the backend `EvidenceItem.type` Literal gained `arp`/`ip_neigh`/`iptables`/`nftables`, but the frontend `EvidenceType` union and **two duplicate** `EVIDENCE_LABELS` maps (`EdgeDetailPanel` + `PathDetailPanel`) kept the original 4. Nothing failed — both maps were loose `Record<string, string>` behind a `?? ev.type` fallback — so those edges silently rendered the raw slug (`ip_neigh`), including in the Copy-as-Markdown path export. Fixed by one shared `utils/evidenceLabels.ts` typed `Record<EvidenceType, string>`, which turns the next drift into a compile error (verified: adding a 9th union member fails the build with TS2741) → `frontend/src/utils/evidenceLabels.test.ts`. Lesson: a lockstep rule (#25) that only lives in prose gets skipped; give it a type that breaks the build.
- **Model completeness** — `PATCH /ops/{id}` used `if body.X is not None` for every optional field, so an operator could *set* a description but never *clear* one: the edit modal sends `null` for a blanked textarea, and the router read that as "not provided" and silently kept the old value. The empty shape (a field being cleared) was never in the test set — only set-and-read-back was. Fixed with `model_dump(exclude_unset=True)` so an omitted key preserves and an explicit `null` clears, while a `null` `name` is still ignored (NOT NULL) → `tests/test_api/test_operations.py::test_update_operation_can_clear_optional_field_with_null` + `::test_update_operation_null_name_is_ignored`. **Note:** the other routers' PATCH handlers still use the `is not None` form and carry the same gap. Lesson: "can it be un-set?" is a model-completeness question for every optional field, not just a nice-to-have.
- **Test honesty** — the host OS/kernel "long value wraps instead of overflowing the sidebar" e2e test passed with the wrapping CSS *removed*: its fixture string contained `-` and `/`, which are break opportunities the browser already wraps on, so it never exercised `overflow-wrap: anywhere`. Caught by mutating the CSS before trusting green (same drill as the wtmp and Feb-29 rows). Fixed by making the fixture a single unbreakable token (`'x'.repeat(120)`), which fails by 51px without the CSS → `frontend/e2e/host-system-info.spec.ts`. Lesson: a truncate/wrap test is only as honest as its fixture — pick a string with **no** break opportunities, or you are testing the browser's default, not your CSS.
- **Test honesty** — `test_feb29_non_leap_no_crash` passed for the *wrong reason*: `strptime` defaults classic syslog to year 1900 (non-leap), so `"Feb 29"` failed to parse and returned `None` *before* the resolver — the `_safe_replace_year` leap guard was never exercised (dead code), same class as the wtmp round-trip. Fixed by parsing classic syslog against a leap-year placeholder (`Feb 29` now reaches the resolver) + splitting into two fail-provable tests: `test_feb29_resolves_in_leap_year` (leap inference → dated) and `test_feb29_dropped_on_non_leap_inference` (non-leap inference → guard drops it). Lesson: prove a new edge-case test can fail (mutation/direct-call) before trusting green.

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
7. Validate client-supplied foreign keys (`host_id`, `credential_id`, `host_user_id`, …) resolve within the op/host — reject with 400 (see the `_require_*_in_op` / `_require_host_user_on_host` helpers in `routers/connections.py` / `routers/credentials.py`). The REST API is the real surface (CLI + scripts), so this can't be client-only. Applies to create **and** update paths.
8. Call `log_activity()` before `db.commit()` in every write endpoint (Architecture Rule #7)
9. Call `broadcast_sync(op_id, event)` after `db.commit()` in every write endpoint (Architecture Rule #18)
10. Tests in `tests/test_api/`
11. TypeScript types in `frontend/src/types/index.ts`
12. API client functions in `frontend/src/api/`

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
- Wall-clock time: a parser must never call `datetime.now()`/`utcnow()`/`date.today()`/`time.time()` inline — route it through a module-level `_now()` (see `parsers/auth_log.py`). The snapshot suite freezes every parser `_now()` so `real_examples` snapshots don't drift each New Year; `tests/test_parsers/test_time_hygiene.py` fails the build if you bypass it.
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
