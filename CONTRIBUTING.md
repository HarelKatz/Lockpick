# Contributing to Lockpick

Lockpick is a single-team-internal red team tool — PRs are welcome, but the canonical engineering reference lives in [CLAUDE.md](CLAUDE.md) (build, test, conventions) and [AGENT.md](AGENT.md) (architecture invariants, data model, roadmap).

## Commit format

```
type(scope): short description

types: feat, fix, refactor, test, docs, chore
scopes: backend, frontend, parsers, docker, schema
```

Stage specific files — never `git add .` (risks staging `.env`, keys, or build artifacts).

## Pre-commit gate

```bash
make test                       # must pass
cd frontend && npm run build    # must succeed
```

Doc-only changes (`.md`) can skip the build gate.

## Where to look

- **[AGENT.md](AGENT.md) → Architecture Rules** — invariants every change must respect (lazy-load gates, upload pipeline split, host merge contract, etc.)
- **[AGENT.md](AGENT.md) → Data Model** — relationships and pivot semantics; `backend/models.py` is authoritative for fields
- **[AGENT.md](AGENT.md) → Implementation Phases** — current roadmap and the next phase's spec
- **[CLAUDE.md](CLAUDE.md) → Adding a New Endpoint** — endpoint checklist (model, schema, router, migration, activity log, broadcast, tests, frontend types)
- **[CLAUDE.md](CLAUDE.md) → Adding a New Parser** — parser checklist (registry, fixtures, tests) plus parser guidelines
- **[CLAUDE.md](CLAUDE.md) → Frontend Conventions** — dark theme, create-form double-submit guard
