# Lockpick

## What is this?

SSH-based pivoting is a core red team technique: you land on a box, find a private key in `~/.ssh/`, and use it to jump to the next host — then the next. In a large environment this quickly becomes a maze. Which key unlocks which user on which host? Where was that key found? Who connected to whom, and when?

Lockpick is a shared web tool for tracking all of that during an operation. It ingests raw evidence — SSH private keys found on compromised hosts, `authorized_keys` files, `auth.log` entries, bash history, `known_hosts` — and builds a relationship graph across the environment. The graph shows you pivot paths: "this private key found on HostA as `bob` is authorized on HostB as `root`". That's a confirmed pivot, and Lockpick surfaces it so you don't miss it in the noise.

It is designed to run as a shared server in a trusted network. Every operator reads and writes to the same state, so information one person uncovers is immediately visible to the rest of the team. Deployment is a single `docker compose up -d` — no database server, no cloud dependencies, no configuration beyond standing up the container.

**Core value:** visualizing lateral movement opportunities by correlating SSH keys, connection logs, and host data across an engagement.

## Quick Start (Docker)

### First run / after pulling updates

```bash
# Build images (required on first run and after any code change)
docker compose build

# Start all services in the background
docker compose up -d
```

The frontend is available at **http://localhost:3000** and the backend API at **http://localhost:8000**.

### Day-to-day

```bash
# Start (images already built)
docker compose up -d

# View live logs
docker compose logs -f

# Stop
docker compose down

# Rebuild + restart in one step (use after pulling/editing code)
docker compose up -d --build
```

### Makefile shortcuts

```bash
make up       # docker compose up -d
make down     # docker compose down
make logs     # docker compose logs -f
make backup   # tar the ./data/ directory with a timestamp
make test     # run pytest suite
```

### Backup & move to another machine

```bash
# On source machine — stop, archive data and images
docker compose down
tar czf lockpick-backup.tar.gz data/

# On destination machine — extract and start
tar xzf lockpick-backup.tar.gz
docker compose up -d --build
```

## Local Development (without Docker)

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 20+

### Backend

```bash
# Install dependencies
cd backend
uv sync

# Create data directory
mkdir -p ../data

# Run development server (auto-reload)
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at **http://localhost:8000**.
Interactive API docs: **http://localhost:8000/docs**

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at **http://localhost:5173** and proxies `/api` requests to `localhost:8000`.

### Running Tests

```bash
cd backend
uv run pytest ../tests/ -v
```

Or use the Makefile shortcut from the project root:

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
tar czf lockpick-backup.tar.gz data/
# Transfer and extract on new machine
make up
```

## API Documentation

When the backend is running, full interactive API documentation is available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/ops` | List all operations |
| POST | `/api/ops` | Create a new operation |
| GET | `/api/ops/{op_id}/hosts` | List hosts in an operation |
| POST | `/api/ops/{op_id}/hosts` | Add a host |
| POST | `/api/hosts/{host_id}/ips` | Add an IP to a host |
| POST | `/api/hosts/{host_id}/users` | Add a user to a host |
| GET | `/api/ops/{op_id}/credentials` | List credentials |
| POST | `/api/ops/{op_id}/credentials` | Add a credential |
| POST | `/api/credential-links` | Link a credential to a host/user |
| GET | `/api/ops/{op_id}/connections` | List connection records |
| POST | `/api/ops/{op_id}/connections` | Add a connection record |

## Architecture

```
lockpick/
├── backend/          # Python/FastAPI backend
├── frontend/         # React/Vite/TypeScript frontend
├── tests/            # pytest test suite
├── data/             # All persistent state (gitignored)
├── docker-compose.yml
└── Makefile
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture details and how to extend the tool.

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy ORM, Alembic, uv
- **Database**: SQLite (single file in `./data/`)
- **Frontend**: React 18, Vite, TypeScript
- **Container**: Docker Compose (multi-stage builds)
- **Tests**: pytest, httpx

## No Authentication

This tool runs on a **trusted network/VPN**. The red team trusts each other. There is no login screen — open the URL and you're in.
