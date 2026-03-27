# Contributing to Lockpick

## Architecture Overview

### High-Level Layout

```
backend/               Python FastAPI application
├── main.py            App entry point, CORS, lifespan (runs Alembic on startup)
├── config.py          Settings via environment variables (pydantic-settings)
├── database.py        SQLAlchemy engine, session factory, Base class
├── models.py          ORM models (Operation, Host, HostIP, HostUser, Credential, ...)
├── schemas.py         Pydantic request/response models
├── routers/           One file per resource group
│   ├── operations.py  CRUD for Operations
│   ├── hosts.py       CRUD for Hosts, HostIPs, HostUsers
│   ├── credentials.py CRUD for Credentials and CredentialLinks
│   └── connections.py CRUD for ConnectionRecords
├── parsers/           (Phase 4) File parsers, one per file type
├── services/          (Phase 3+) Graph builder, IP resolver, pivot analysis
└── alembic/           Database migrations

frontend/              React + TypeScript SPA
├── src/
│   ├── main.tsx       App bootstrap
│   ├── App.tsx        Root component, page routing
│   ├── theme.ts       Dark theme color constants (CSS variables source of truth)
│   ├── index.css      Global styles, CSS custom properties
│   ├── types/         TypeScript interfaces matching backend schemas
│   ├── api/           Typed API client functions
│   └── pages/         Top-level page components

tests/
├── conftest.py        Shared fixtures (in-memory DB, TestClient)
└── test_api/          API integration tests
```

### Data Flow

```
Browser → nginx (port 3000)
           ├─ static files (React app)
           └─ /api/* → FastAPI backend (port 8000)
                         └─ SQLAlchemy → SQLite (./data/tracker.db)
```

### Key Design Decisions

1. **All IDs are UUIDs** stored as strings in SQLite
2. **Timestamps are timezone-aware** (UTC) — stored as ISO 8601
3. **No authentication** — trusted network tool
4. **All state in `./data/`** — the only thing to backup
5. **Backend-side edge aggregation** — the frontend renders what the API gives it, never calculates relationships itself
6. **HostUser entries require evidence** — never create a HostUser entry without concrete evidence the user exists on that host

## Adding a New API Endpoint

1. Add the ORM model to `backend/models.py` if needed
2. Add Pydantic schemas to `backend/schemas.py` (Create, Update, Read variants)
3. Add router functions to the appropriate file in `backend/routers/` (or create a new one)
4. Register the router in `backend/main.py` with `app.include_router(...)`
5. Generate an Alembic migration if the schema changed:
   ```bash
   cd backend
   uv run alembic revision --autogenerate -m "describe change"
   ```
6. Add tests in `tests/test_api/`
7. Add TypeScript types to `frontend/src/types/index.ts`
8. Add API client functions to `frontend/src/api/`

## How to Add a New File Parser (Phase 4+)

All parsers live in `backend/parsers/` and implement the `BaseParser` interface.

### Step 1: Define the parser class

Create `backend/parsers/my_file_type.py`:

```python
from parsers import BaseParser, ParseResult, UploadMetadata

class MyFileTypeParser(BaseParser):
    """Parser for <describe the file type>."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        try:
            lines = content.decode('utf-8', errors='replace').splitlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                try:
                    # Parse the line and populate result
                    # result.hosts_found.append(...)
                    # result.connections_found.append(...)
                    pass
                except Exception as e:
                    result.warnings.append(f"Skipped malformed line: {line!r} — {e}")
        except Exception as e:
            result.warnings.append(f"Parse error: {e}")
        return result
```

### Step 2: Register the parser

In `backend/parsers/__init__.py`, add your parser to the registry:

```python
from parsers.my_file_type import MyFileTypeParser

PARSER_REGISTRY = {
    # existing parsers ...
    "my_file_type": MyFileTypeParser,
}
```

### Step 3: Write tests with fixture files

1. Add a sample file to `tests/fixtures/sample_my_file_type`
2. Create `tests/test_parsers/test_my_file_type.py`:

```python
import pytest
from pathlib import Path
from parsers.my_file_type import MyFileTypeParser
from parsers import UploadMetadata

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_my_file_type"

@pytest.fixture
def parser():
    return MyFileTypeParser()

@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="test-op-id",
        host_id="test-host-id",
        username="testuser",
        file_type="my_file_type",
    )

def test_parse_basic(parser, metadata):
    result = parser.parse(FIXTURE.read_bytes(), metadata)
    assert len(result.warnings) == 0
    # Add specific assertions about parsed data

def test_parse_malformed_input(parser, metadata):
    """Parser must never crash on bad input."""
    result = parser.parse(b"malformed\x00\xff data", metadata)
    # Should have warnings but not crash
    assert result is not None
```

### Parser Guidelines

- **Never crash on bad input** — catch all exceptions and add to `result.warnings`
- **Handle encoding issues** — use `errors='replace'` when decoding bytes
- **Handle gzip** — check for gzip magic bytes and decompress if needed
- **Use `metadata.host_id`** as the source host for the parsed data
- **Return counts in `result.stats`** for the UI summary (e.g. `{"hosts": 3, "connections": 12}`)
- **IP resolution** — use the `IpResolver` service to match raw IPs to existing hosts in the op
- **Fingerprint matching** — use `KeyMatcher` service when parsing SSH keys to find instant pivot opportunities

## Dark Theme Guidelines

All UI uses CSS custom properties defined in `frontend/src/index.css`. The source of truth for color values is `frontend/src/theme.ts`.

To add a new UI component:

1. Use CSS modules (`.module.css` files alongside the component)
2. Reference only CSS variables — never hardcode colors:
   ```css
   /* Good */
   color: var(--text-primary);
   background: var(--bg-surface);
   border: 1px solid var(--border);

   /* Bad */
   color: #c9d1d9;
   background: #161b22;
   ```
3. For interactive states: use `var(--bg-surface-2)` for hover, `var(--accent)` for focus/active
4. For status/confidence: use `var(--success)` (confirmed), `var(--warning)` (observed), `var(--text-muted)` (indicator)

## Git Workflow

### Commit format

```
type(scope): short description

types: feat, fix, refactor, test, docs, chore
scope: backend, frontend, parsers, docker, schema
```

### Examples

```
feat(parsers): authorized_keys parser with fingerprint extraction
test(parsers): fixture files and tests for auth_log parser
fix(backend): handle duplicate IPs during upload resolution
feat(frontend): host detail sidebar with IP and user lists
```

### Before committing

1. Run tests: `make test`
2. Verify frontend builds: `cd frontend && npm run build`
3. Commit only specific files — avoid `git add .` (may accidentally stage secrets)

## Environment Variables

The backend reads these from the environment or a `.env` file in `backend/`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `../data/tracker.db` | Path to the SQLite database file |
| `UPLOAD_PATH` | `../data/uploads` | Directory for uploaded raw files |

The frontend uses a relative `/api` prefix — nginx proxies this to the backend. No frontend env vars needed for production. For local dev, `vite.config.ts` configures the proxy.
