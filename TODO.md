# Lockpick — Active Tasks

> **Edit rules:** A task pool, not a sequential roadmap. Pick freely within a tier; `## Now` outranks `## Next` outranks `## Later`. An `After:` line marks an *open* hard prerequisite — don't start until it ships; no `After:` = independent. When a bug fix introduces a new invariant, move that invariant to ARCHITECTURE.md. Keep specs short; detail belongs in commits.

**Status:** Full stack shipped — 49 file types / 44 parser classes, host merge (manual + auto), one-click collection workflow. See git history for completed work.

## Now

> **Testing-foundation (shipped).** All four foundation items are done — the shared REST op-builder (`tests/opbuilder/`: `OpBuilder`/`shapes`/`profiles`, with `profiles.normal()` = the e2e seed and `scale(n)` = the size-dialable generator's in-memory export), the frontend vitest unit layer (`frontend/src/utils/` + 54 tests over the extracted graph/slider logic), the size-dialable random generator (`build_structure_topology`, deterministic + golden-hashed), and the test doctrine in CLAUDE.md (Feature Design Pre-flight Checklist + Test-Layering Doctrine + Misses log). The invariant layers that build on this substrate have since **shipped** too — the backend hypothesis battery (`tests/test_invariants/`), the frontend graph/layout invariant suite (`frontend/e2e/invariants*.spec.ts`), and the tiered marker targets + `make gate` — closing the initiative.

- **Fix `createHostNote` double-submit race** — the "Add note" action in `HostDetailSidebar` (onClick + Ctrl/Cmd+Enter) is guarded only by React state (`setNoteAdding`), not a `useRef` flag, so rapid double-activation in the same tick dispatches concurrent POSTs → duplicate notes. Apply the `useRef` double-submit guard per CLAUDE.md → Frontend Conventions.
- **Engagement report export** — `GET /ops/{op_id}/report?format=markdown|html`: structured engagement summary (op metadata, host inventory, credential inventory, pivot paths via `find_paths`, sudo escalation summary, activity timeline). Markdown primary; HTML wraps it in a minimal printable template. Full credential values are shown — Lockpick never redacts, including in reports (ARCHITECTURE.md Rule #4).

## Later

- **Credential blast-radius rollup** — per-credential "unlocks N hosts across Y users", surfaced in the credential detail panel and list row, derived from existing `CredentialLink` data (no schema change).
- **Op summary + briefing fields** — Operation gains two markdown fields: `summary` (short, rendered in op header) and `briefing` (long, collapsible in op detail view). Both user-editable, optional. Requires two new columns + an Alembic migration.
