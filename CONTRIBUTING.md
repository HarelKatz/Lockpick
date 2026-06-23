# Contributing to Lockpick

Lockpick is a single-team-internal red team tool — PRs are welcome, but the canonical engineering reference lives in [CLAUDE.md](CLAUDE.md) (build, test, conventions) and [AGENT.md](AGENT.md) (architecture invariants, data model, roadmap).

## Commit format & pre-commit gate

Both are defined canonically in **[CLAUDE.md → Git Commits](CLAUDE.md#git-commits)**: the conventional `type(scope): …` format, and the gate (`make test` must pass; `cd frontend && npm run build` must succeed for code changes; `.md`-only changes may skip the build gate).

Stage specific files — never `git add .` (risks staging `.env`, keys, or build artifacts).

## Where to look

- **[AGENT.md](AGENT.md) → Architecture Rules** — invariants every change must respect (lazy-load gates, upload pipeline split, host merge contract, etc.)
- **[AGENT.md](AGENT.md) → Data Model** — relationships and pivot semantics; `backend/models.py` is authoritative for fields
- **[AGENT.md](AGENT.md) → Implementation Phases** — current roadmap and the next phase's spec
- **[CLAUDE.md](CLAUDE.md) → Adding a New Endpoint** — endpoint checklist (model, schema, router, migration, activity log, broadcast, tests, frontend types)
- **[CLAUDE.md](CLAUDE.md) → Adding a New Parser** — parser checklist (registry, fixtures, tests) plus parser guidelines
- **[CLAUDE.md](CLAUDE.md) → Frontend Conventions** — dark theme, create-form double-submit guard
