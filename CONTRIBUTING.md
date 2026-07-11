# Contributing to Lockpick

Lockpick is a single-team-internal red team tool — PRs are welcome, but the canonical engineering reference lives in [CLAUDE.md](CLAUDE.md) (build, test, conventions), [ARCHITECTURE.md](ARCHITECTURE.md) (architecture invariants), [DATA_MODEL.md](DATA_MODEL.md) (data model), and [TODO.md](TODO.md) (near-term work).

## Commit format & pre-commit gate

Both are defined canonically in **[CLAUDE.md → Git Commits](CLAUDE.md#git-commits)**: the conventional `type(scope): …` format, and the gate (`make test-backend` + `make test-unit` must pass; `cd frontend && npm run build` must succeed for code changes; `.md`-only changes may skip the build gate). `make test-full` runs every layer (backend + frontend unit + e2e).

Stage specific files — never `git add .` (risks staging `.env`, keys, or build artifacts).

## Where to look

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — invariants every change must respect (lazy-load gates, upload pipeline split, host merge contract, etc.)
- **[DATA_MODEL.md](DATA_MODEL.md)** — relationships and pivot semantics; `backend/models.py` is authoritative for fields
- **[TODO.md](TODO.md)** — near-term task pool; **[BACKLOG.md](BACKLOG.md)** — future work
- **[CLAUDE.md](CLAUDE.md) → Adding a New Endpoint** — endpoint checklist (model, schema, router, migration, activity log, broadcast, tests, frontend types)
- **[CLAUDE.md](CLAUDE.md) → Adding a New Parser** — parser checklist (registry, fixtures, tests) plus parser guidelines
- **[CLAUDE.md](CLAUDE.md) → Frontend Conventions** — dark theme, create-form double-submit guard
