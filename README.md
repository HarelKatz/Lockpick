# Lockpick

## What is this?

SSH-based pivoting is a core red team technique: you land on a box, find a private key in `~/.ssh/`, and use it to jump to the next host — then the next. In a large environment this quickly becomes a maze. Which key unlocks which user on which host? Where was that key found? Who connected to whom, and when?

Lockpick is a shared web tool for tracking all of that during an operation. It ingests raw evidence — SSH private keys found on compromised hosts, `authorized_keys` files, `auth.log` entries, bash history, `known_hosts` — and builds a relationship graph across the environment. The graph shows you pivot paths: "this private key found on HostA as `bob` is authorized on HostB as `root`". That's a confirmed pivot, and Lockpick surfaces it so you don't miss it in the noise.

It is designed to run as a shared server in a trusted network. Every operator reads and writes to the same state, so information one person uncovers is immediately visible to the rest of the team. Deployment is a single `docker compose up -d` — no database server, no cloud dependencies, no configuration beyond standing up the container.

**Core value:** visualizing lateral movement opportunities by correlating SSH keys, connection logs, and host data across an engagement.

## Features

- **One-click evidence collection** — generate a sudo-free bash collector (`GET /api/ops/{op_id}/collection-script`), run it on a host, and upload the resulting tarball (`POST /api/.../import-archive`) for bulk ingest
- **44 parsers across 49 evidence file types** — SSH artifacts, system files (`passwd`/`shadow`/`sshd_config`/…), command output (`netstat`/`ss`/`iptables`/…), and credential files (cloud, database, and app secrets)
- **Key-fingerprint pivot detection** — correlates private keys, `authorized_keys`, and connection logs into confirmed pivots
- **BFS pivot path-finding** — shortest credential-backed path between two hosts (`POST /api/ops/{op_id}/graph/paths`)
- **Host merge** — collapse duplicate or placeholder hosts, manually or automatically
- **Search, activity log, live updates** — global search, an audit timeline, and WebSocket push so the whole team sees new data instantly
- **Export / import** — snapshot an operation and move it between servers

## Quick Start

```bash
make run
```

This builds images, starts containers in the background, and attaches to logs. `Ctrl+C` stops log tailing — containers keep running.

- Frontend: **http://localhost:3000**
- Backend API: **http://localhost:8000**

> **buildx/bake error?** If `make run` fails with a Docker buildx or bake error, run `cp .env.example .env` (sets `COMPOSE_BAKE=false`) and retry.

### Other commands

```bash
make up       # start without rebuilding
make down     # stop and remove containers
make logs     # re-attach to logs
make backup   # tar ./data/ with a timestamp
make test-full # run every test layer (backend + frontend unit + e2e)
```

## Local Development (without Docker)

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 20+

### Backend

```bash
cd backend
uv sync
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
# or: make dev-backend
```

API available at **http://localhost:8000**. Interactive docs at **http://localhost:8000/docs**.

### Frontend

```bash
cd frontend
npm install
npm run dev
# or: make dev-frontend
```

Dev server at **http://localhost:5173** — proxies `/api` requests to `localhost:8000`.

### Running Tests

```bash
make test-full     # everything: backend + frontend unit + e2e
make test-backend  # backend pytest only
make test-unit     # frontend unit (vitest)
make test-e2e      # frontend e2e (playwright)
make gate          # fast pre-PR check: build + unit + fast backend + fast e2e (run with -j)
```

## Data Storage

All persistent state lives in `./data/`:

```
data/
├── tracker.db        # SQLite database
└── uploads/          # Raw uploaded files (organized by op_id)
```

This directory is **gitignored**. To move the tool to another machine:

```bash
docker compose down
tar czf lockpick-backup.tar.gz data/
# Transfer and extract on new machine, then:
make run
```

## API Documentation

Full interactive docs are available when the backend is running: Swagger UI at **http://localhost:8000/docs** and ReDoc at **http://localhost:8000/redoc**.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for architecture rules and [DATA_MODEL.md](DATA_MODEL.md) for the data model. See [CLAUDE.md](CLAUDE.md) for build, test, and contribution conventions.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the commit format and the pre-commit gate.

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy ORM, Alembic, uv
- **Database**: SQLite (single file in `./data/`)
- **Frontend**: React 18, Vite, TypeScript, react-force-graph-2d + d3-force
- **Container**: Docker Compose (multi-stage builds)
- **Tests**: pytest, httpx

## No Authentication

This tool runs on a **trusted network/VPN**. The red team trusts each other. There is no login screen — open the URL and you're in.
