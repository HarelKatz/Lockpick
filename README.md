# Lockpick

## What is this?

SSH-based pivoting is a core red team technique: you land on a box, find a private key in `~/.ssh/`, and use it to jump to the next host — then the next. In a large environment this quickly becomes a maze. Which key unlocks which user on which host? Where was that key found? Who connected to whom, and when?

Lockpick is a shared web tool for tracking all of that during an operation. It ingests raw evidence — SSH private keys found on compromised hosts, `authorized_keys` files, `auth.log` entries, bash history, `known_hosts` — and builds a relationship graph across the environment. The graph shows you pivot paths: "this private key found on HostA as `bob` is authorized on HostB as `root`". That's a confirmed pivot, and Lockpick surfaces it so you don't miss it in the noise.

It is designed to run as a shared server in a trusted network. Every operator reads and writes to the same state, so information one person uncovers is immediately visible to the rest of the team. Deployment is a single `docker compose up -d` — no database server, no cloud dependencies, no configuration beyond standing up the container.

**Core value:** visualizing lateral movement opportunities by correlating SSH keys, connection logs, and host data across an engagement.

## Quick Start

```bash
make run
```

This builds images, starts containers in the background, and attaches to logs. `Ctrl+C` stops log tailing — containers keep running.

- Frontend: **http://localhost:3000**
- Backend API: **http://localhost:8000**

### Other commands

```bash
make up       # start without rebuilding
make down     # stop and remove containers
make logs     # re-attach to logs
make backup   # tar ./data/ with a timestamp
make test     # run the pytest suite
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
mkdir -p ../data
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
make test
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

Full interactive docs (Swagger UI + ReDoc) are available at **http://localhost:8000/docs** when the backend is running.

## Architecture

See [CONTRIBUTING.md](CONTRIBUTING.md) for a full architecture overview, data flow diagram, and instructions for adding endpoints and parsers.

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy ORM, Alembic, uv
- **Database**: SQLite (single file in `./data/`)
- **Frontend**: React 18, Vite, TypeScript, react-force-graph-2d + d3-force
- **Container**: Docker Compose (multi-stage builds)
- **Tests**: pytest, httpx

## No Authentication

This tool runs on a **trusted network/VPN**. The red team trusts each other. There is no login screen — open the URL and you're in.
