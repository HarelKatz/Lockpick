# Lockpick — Active Tasks

> **Edit rules:** A task pool, not a sequential roadmap. Pick freely within a tier; `## Now` outranks `## Next` outranks `## Later`. An `After:` line marks an *open* hard prerequisite — don't start until it ships; no `After:` = independent. When a bug fix introduces a new invariant, move that invariant to ARCHITECTURE.md. Keep specs short; detail belongs in commits.

**Status:** Full stack shipped — 49 file types / 44 parser classes, host merge (manual + auto), one-click collection workflow. See git history for completed work.

## Now

> **Testing-foundation initiative (do first).** Origin: the time-slider shipped green but had 4 hand-caught bugs (drag-only jitter, floating nodes, model-completeness gap, isolated-host case) because e2e specs assert the `window.__lockpick_graph__` data model only (blind to CSS/layout + real drags). Goal: a quality *loop* whose spine is **invariants over a normal op** — general properties true for ANY op — so using the app produces a failing test. Full design in git history / the approved plan. **Keystone shipped:** the shared REST op-builder (`tests/opbuilder/` — `OpBuilder` + `shapes` + `profiles.{empty,minimal,normal,edge_cases,scale}`; scenario `loaded_op` fixtures + `seed_e2e.py` migrated onto it, ~20 scenario assertions + `make test-e2e` green with zero assertion edits). `profiles.normal()` *is* the e2e seed and the default substrate the BACKLOG invariant work builds on. **Doctrine landed** in CLAUDE.md (Feature Design Pre-flight Checklist + Test-Layering Doctrine + Misses log). **Frontend unit layer landed:** vitest + 54 unit tests over pure logic extracted into `frontend/src/utils/` (`timeWindow`/`graphMerge`/`edgeDisplay`/`layout`); components keep their `useMemo`/`useEffect` wrappers, and `make test-e2e` stays the regression gate for the extraction. One item remains below.

- **Dial the random generator to 5–200** — Parameterize `tests/generate_random_network.py` `build_random_topology(rng, *, n_hosts=None, n_keys=None)` (replace hardcoded `rng.randint(5,8)`; `n_keys=max(2, n_hosts//8)`, pivots ∝ hosts); add `--hosts N`; add an in-memory topology export (skip real RSA keygen for structure-only invariant runs — fake fingerprints); add `test_generator_determinism` golden-hashing the *structural* topology (not RSA keys). Preserve single `Random(seed)` draw order (new draws after existing). Feeds `profiles.scale(n)`.

- **Fix `createHostNote` double-submit race** — the "Add note" action in `HostDetailSidebar` (onClick + Ctrl/Cmd+Enter) is guarded only by React state (`setNoteAdding`), not a `useRef` flag, so rapid double-activation in the same tick dispatches concurrent POSTs → duplicate notes. Apply the `useRef` double-submit guard per CLAUDE.md → Frontend Conventions.
- **Engagement report export** — `GET /ops/{op_id}/report?format=markdown|html`: structured engagement summary (op metadata, host inventory, credential inventory, pivot paths via `find_paths`, sudo escalation summary, activity timeline). Markdown primary; HTML wraps it in a minimal printable template. Full credential values are shown — Lockpick never redacts, including in reports (ARCHITECTURE.md Rule #4).

## Later

- **Credential blast-radius rollup** — per-credential "unlocks N hosts across Y users", surfaced in the credential detail panel and list row, derived from existing `CredentialLink` data (no schema change).
- **Op summary + briefing fields** — Operation gains two markdown fields: `summary` (short, rendered in op header) and `briefing` (long, collapsible in op detail view). Both user-editable, optional. Requires two new columns + an Alembic migration.
