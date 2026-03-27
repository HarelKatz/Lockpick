# SSH Pivot Tracker

A web-based tool for red teams to collaboratively organize SSH credentials, host relationships, and pivot paths during operations. The core value is **visualizing lateral movement opportunities** by correlating SSH keys, connection logs, and host data across an engagement.

## Quick Start (Docker)

```bash
# Start all services
make up

# View logs
make logs

# Stop
make down

# Backup all state (DB + uploaded files)
make backup
```

The frontend is available at **http://localhost:3000** and the backend API at **http://localhost:8000**.

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
tar czf pivot-tracker-backup.tar.gz data/
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
ssh-pivot-tracker/
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
