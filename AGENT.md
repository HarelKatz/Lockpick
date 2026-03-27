# SSH Pivot Tracker — Red Team Operation Manager

## Project Overview

A web-based tool for red teams to collaboratively organize SSH credentials, host relationships, and pivot paths during operations. Runs as a shared server — the entire team accesses it, and any data one person adds is visible to everyone on their next query. The core value is **visualizing lateral movement opportunities** by correlating SSH keys, connection logs, and host data across an engagement.

## Tech Stack

- **Backend**: Python 3.12+ with FastAPI
- **Database**: SQLite (single file, lives in a Docker volume for portability)
- **Frontend**: React (Vite) with TypeScript
- **Graph Visualization**: cytoscape.js for the interactive network graph
- **File Parsing**: Python stdlib + paramiko (for SSH key handling)
- **Package Manager**: uv (for Python dependency management — fast, lockfile-based)
- **Deployment**: Docker Compose (one command up/down, entire state in one directory)

## Deployment & Portability

The project **must** be trivial to deploy, stop, move, and restart. This is a red team tool — it might run on a VPS for a week, get zipped up, moved to another box, and resumed.

```
# Start
docker compose up -d

# Stop
docker compose down

# Move to another machine
tar czf pivot-tracker-backup.tar.gz .
# transfer to new machine, extract, docker compose up -d

# All state lives in ./data/ (SQLite DB, uploaded files)
```

### Docker setup:

- `docker-compose.yml` at project root
- Two services: `backend` (Python/FastAPI) and `frontend` (nginx serving built React app)
- A `./data/` directory mounted as a volume holds the SQLite DB and any uploaded raw files
- Backend serves on a single port, frontend proxies API calls to backend
- No external dependencies (no Redis, no Postgres, no cloud services)
- `Makefile` with convenience targets: `make up`, `make down`, `make logs`, `make backup`, `make dev-backend` (runs `uv run uvicorn`), `make dev-frontend` (runs `vite dev`), `make test` (runs `uv run pytest`)

### Contributing

- `README.md` with clear setup instructions for local development (without Docker)
- `CONTRIBUTING.md` with code style, how to add a new parser, how to add a new relationship type
- Backend and frontend can each be run independently for development (`uv run uvicorn` + `vite dev`)
- All parsers follow a common interface so adding a new file type is mechanical

## Data Model

Design the schema with these entities and relationships. Use SQLAlchemy ORM.

### Core Entities

```
Operation (op)
├── id (UUID), name, created_at, description

Host
├── id (UUID), op_id (FK), nickname, comment, created_at
│
├── HostIP (one-to-many) — the IPs that BELONG to this host (from ip addr / ifconfig / manual entry)
│   └── id, host_id (FK), ip_address, cidr (nullable), interface_name (nullable),
│       source (enum: manual | parsed), first_seen_at
│       ** This is how we resolve "traffic from 10.0.0.5" → "that's HostA" **
│
├── HostUser (one-to-many) — local user accounts that EXIST on this host
│   └── id, host_id (FK), username, shell (nullable), home_dir (nullable),
│       source (enum: manual | passwd_file | authorized_keys | home_dir_found | log_evidence)
│       ** A HostUser is ONLY created when there is concrete evidence the user exists on the host:
│          - Parsed from /etc/passwd
│          - Has an authorized_keys entry
│          - Has a home directory with files (.bash_history, .ssh/)
│          - Appears in auth.log as a valid local user (successful auth target)
│          Do NOT create HostUser entries from connection source data (e.g. "someone SSHed
│          FROM this user on another box" does not mean the user exists on the destination) **

Credential (standalone entity — a key or password can unlock multiple hosts)
├── id (UUID), op_id (FK)
├── cred_type (enum: password | private_key | public_key)
├── value (the actual key content or password hash)
├── fingerprint (SHA256 for SSH keys — used for cross-referencing / matching)
├── key_type (nullable, e.g. rsa, ed25519, ecdsa)
├── comment (nullable), created_at
│
├── CredentialLink (junction: where was this credential found and what does it grant?)
│   └── id, credential_id (FK), host_id (FK), host_user_id (FK, nullable)
│       relationship (enum: found_on_disk | authorized_key | accepted_password | used_in_connection)
│       file_source (nullable — which uploaded file produced this link)
│       ** Example: private key found in /home/bob/.ssh/id_rsa on HostA →
│          credential_id=key1, host_id=HostA, host_user_id=bob, relationship=found_on_disk
│          That same key's fingerprint matches authorized_keys on HostB for user root →
│          credential_id=key1, host_id=HostB, host_user_id=root, relationship=authorized_key
│          This gives us a pivot: HostA(bob) → HostB(root) via key1 **
```

### Edges / Relationships Between Hosts

Edges are **not single records** — an edge between two hosts accumulates **all evidence** of their relationship. The backend builds edges by aggregating multiple evidence types.

```
ConnectionRecord (individual pieces of evidence — raw facts from logs/files)
├── id (UUID), op_id (FK)
├── src_host_id (FK, nullable), src_ip (string), src_user (string, nullable)
├── dst_host_id (FK, nullable), dst_ip (string), dst_user (string, nullable)
├── connection_type (enum: ssh | scp | rsync | sftp | ssh_copy_id | unknown)
├── direction_context (enum: from_src_logs | from_dst_logs)
│   ** Was this record extracted from the SOURCE's files (bash_history, known_hosts)
│      or the DESTINATION's files (auth.log, wtmp)? This matters for confidence. **
├── timestamp (nullable), raw_line (nullable)
├── source_file (which uploaded file produced this)
├── created_at
```

### Edge Aggregation (computed by backend, served to frontend)

When the frontend asks "give me the edge between HostA and HostB", the backend returns:

```json
{
  "src_host": "HostA",
  "dst_host": "HostB",
  "evidence": [
    {
      "type": "key_match",
      "detail": "Private key (SHA256:abc...) found on HostA(bob) matches authorized_key on HostB(root)",
      "credential_id": "...",
      "src_user": "bob",
      "dst_user": "root",
      "confidence": "confirmed"
    },
    {
      "type": "connection_log",
      "detail": "auth.log on HostB shows successful SSH login from 10.0.0.5 (HostA) as root",
      "timestamp": "2024-03-15T14:22:00",
      "source_file": "hostB_auth.log",
      "confidence": "observed"
    },
    {
      "type": "known_hosts",
      "detail": "HostA(bob) has HostB's IP in known_hosts",
      "confidence": "indicator"
    },
    {
      "type": "bash_history",
      "detail": "HostA(bob) ran 'ssh root@10.0.0.8'",
      "confidence": "indicator"
    }
  ],
  "overall_confidence": "confirmed",
  "pivotable_users": [
    {"src_user": "bob", "dst_user": "root", "method": "key", "credential_id": "..."}
  ]
}
```

**Confidence levels:**
- `confirmed` — key match exists (private on one side, authorized on the other)
- `observed` — connection logs prove it happened
- `indicator` — known_hosts entry, bash_history command, but no direct proof of success

**Edge rendering on the graph should reflect ALL evidence**, not just the "best" one. The edge tooltip/detail panel should list every piece of evidence.

## Implementation Phases

Implement these phases **sequentially**. Each phase should be a working, testable increment. Write tests as you go. Update this document's "Current Status" section after completing each phase.

### Phase 1 — Project Skeleton & Infrastructure

- [x] Docker Compose setup (backend + frontend services, ./data/ volume)
- [x] Makefile with: up, down, logs, backup, dev-backend, dev-frontend
- [x] Initialize FastAPI backend with SQLAlchemy + SQLite (DB path: ./data/tracker.db)
- [x] Initialize React frontend with Vite + TypeScript
- [x] Implement the full database schema with migrations (alembic)
- [x] CRUD API endpoints for: Operations, Hosts, HostIPs, HostUsers, Credentials, CredentialLinks, ConnectionRecords
- [x] Basic API tests (pytest)
- [x] Simple frontend shell: operation selector screen (list/create ops)
- [x] Dark theme from the start (all components)
- [x] README.md with setup instructions (Docker and local dev)
- [x] CONTRIBUTING.md with architecture overview and how-to-add-a-parser guide

### Phase 2 — Manual Data Entry

- [ ] Frontend: after selecting an op, show the main workspace
- [ ] Floating action button (bottom-right corner, + icon)
- [ ] Clicking FAB opens a modal with tabs: "Manual Entry" | "File Upload" (upload tab is placeholder for Phase 4)
- [ ] Manual entry form supports adding:
  - Host (nickname, one or more IPs, comment)
  - User on a host (select host, enter username — with evidence source)
  - Credential (type, value) linked to a host+user with relationship type
  - Connection record (src host → dst host/IP, users, type)
- [ ] Form validates that HostUser entries require an evidence source
- [ ] All entries tagged with op_id based on current op context

### Phase 3 — Host Selection & Graph Visualization

- [ ] Host query/filter panel: show all hosts in current op as a searchable/filterable list with checkboxes
- [ ] Selected hosts render on a cytoscape.js canvas as labeled nodes
- [ ] Node label shows nickname; badge/icon shows number of known users and credentials
- [ ] Nodes are draggable, graph uses force-directed layout (cola or cose-bilkent)
- [ ] Double-click a node to "expand" — backend returns all related hosts and aggregated edges, new nodes/edges added to canvas
- [ ] Edges rendered with:
  - Color based on highest confidence: green (confirmed/key match), orange (observed/logs), gray (indicator)
  - Thickness based on number of evidence items
  - Arrow showing direction
  - Label summary (e.g. "2 key matches, 3 log entries")
- [ ] Click an edge → detail panel showing ALL evidence items for that edge
- [ ] Click a node → sidebar showing host detail (IPs, users, credentials, comment, all connections)
- [ ] **Right-click context menu on nodes:**
  - "Expand all" — show all related hosts (default double-click behavior)
  - "Expand by key matches only" — only show hosts related by credential matching
  - "Expand by connection logs only" — only show hosts with observed connections
  - "Expand by indicators only" — only show hosts with known_hosts/bash_history links
  - Separator
  - "Hide this node" — remove from canvas (not from DB)
  - "Edit host" — open edit form
  - "Delete host" — delete from DB with confirmation
- [ ] **Right-click context menu on edges:**
  - "Show evidence detail" — open evidence panel
  - "Hide this edge" — remove from canvas
- [ ] Hidden nodes/edges can be restored via "Show all" button or re-selecting from the host list

### Phase 4 — File Upload & Parsing Engine

Build a parsing engine on the backend. Each parser is a module in `backend/parsers/`. All parsers implement a common interface.

#### Parser Interface

```python
class ParseResult:
    hosts_found: list[HostData]           # New hosts/IPs discovered
    users_found: list[HostUserData]       # Users with evidence
    credentials_found: list[CredentialData]  # Keys/passwords found
    connections_found: list[ConnectionData]  # Connection records
    warnings: list[str]                    # Parse issues (malformed lines, etc.)
    stats: dict                            # Summary counts for UI

class BaseParser:
    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult: ...
```

#### Upload API

- Endpoint: `POST /api/ops/{op_id}/upload`
- Accepts: multipart file + JSON metadata (file_type, host_id, username)
- Steps: parse → resolve IPs to existing hosts where possible → insert records → return ParseResult summary
- Raw uploaded files stored in `./data/uploads/{op_id}/` for audit

#### Parsers to implement (one at a time, with tests):

**4a. `.ssh/authorized_keys`** (per user)
- Extract public keys, compute SHA256 fingerprints
- Create Credential + CredentialLink (relationship=authorized_key)
- Creates/confirms HostUser with source=authorized_keys

**4b. `.ssh/known_hosts`** (per user)
- Parse hostnames/IPs and key fingerprints (handle hashed known_hosts too)
- Create ConnectionRecords (outbound indicators from this host)
- Match IPs to existing hosts; create unresolved placeholder hosts for unknown IPs

**4c. `.ssh/config`** (per user)
- Parse Host/Match blocks: Hostname, User, Port, IdentityFile, ProxyJump
- Create connection hints and host aliases
- If IdentityFile references a key we have, link them

**4d. SSH private/public key files** (id_rsa, id_ed25519, etc.)
- Read key with paramiko, compute SHA256 fingerprint
- Store as Credential with relationship=found_on_disk
- **Immediately cross-reference** fingerprint against ALL authorized_keys in the op
- Return any newly discovered pivot opportunities in the ParseResult

**4e. `auth.log` / `secure`** (including .gz)
- Decompress gzip if needed
- Parse sshd log lines: accepted/failed, user, source IP, auth method (publickey/password), key fingerprint if present, timestamp
- Store as inbound ConnectionRecords on this host
- Match source IPs to existing hosts
- Accepted logins confirm HostUser exists (source=log_evidence)

**4f. `wtmp`** (binary format)
- Parse using struct-based parsing (utmp record format)
- Extract login records: user, source IP/hostname, login/logout timestamps
- Store as inbound ConnectionRecords
- Confirms HostUser exists (source=log_evidence)

**4g. `.bash_history`** (per user)
- Regex for: `ssh`, `scp`, `rsync`, `sftp`, `ssh-copy-id` commands
- Extract destination host/IP, user (@user syntax, -l flag), port (-p flag)
- Store as outbound ConnectionRecords from this host
- Look for `ssh-keygen`, `ssh-add` as context indicators (note in host comment)

**4h. `/etc/passwd`**
- Extract user accounts (username, shell, home_dir)
- Create HostUser entries with source=passwd_file
- Skip system users (uid < 1000) by default, but keep root and any with valid shells

#### File upload frontend:

- "File Upload" tab in the Add modal
- Dropdown to select file type (from enum of supported types)
- Host selector (required — which host did this file come from?)
- Username field (required for per-user files: authorized_keys, known_hosts, config, bash_history, private keys)
- Drag-and-drop upload area
- After upload, show parsing results summary:
  - "Found: 3 new hosts, 5 connection records, 2 SSH keys"
  - "Warnings: 12 malformed lines skipped"
  - "New pivot opportunity: HostA(bob) → HostC(root) via key SHA256:xyz..."
- Support uploading multiple files in sequence (form resets but keeps host/user selection)

### Phase 5 — Pivot Path Analysis

- [ ] Backend endpoint: given two hosts, find all pivot paths (BFS on aggregated edge graph)
- [ ] Path results include: each hop's evidence, required credentials, confidence per hop
- [ ] Distinguish: confirmed path (all hops have key matches) vs observed path (log evidence) vs theoretical (indicators only)
- [ ] Frontend: "Find Path" mode — select two nodes, show all paths highlighted on graph
- [ ] Path detail panel showing each hop with full evidence breakdown
- [ ] Ability to filter paths by minimum confidence level

### Phase 6 — Polish & UX

- [ ] Global search across all data (hosts, IPs, users, key fingerprints, comments)
- [ ] Export op data as JSON (full op state: hosts, creds, connections, everything)
- [ ] Import op from JSON (restore or merge)
- [ ] Graph layout options (force-directed, hierarchical, circular, grid)
- [ ] Keyboard shortcuts (Esc close modals, Del hide selected node, Ctrl+F search)
- [ ] Bulk file upload (multiple files, auto-detect type where possible)
- [ ] Activity log (who added what, when — basic audit trail, stored in DB)
- [ ] Notification banner when data has changed since your last query ("15 new records since your last refresh" — click to refresh)

## Architecture Rules

1. **Backend and frontend are separate directories**: `backend/` and `frontend/`
2. **All file parsing logic lives in `backend/parsers/`**, one module per file type, all implementing `BaseParser`
3. **The graph edge aggregation happens in the backend** (`services/graph_builder.py`), not the frontend. The frontend renders what the API gives it.
4. **Every API endpoint has input validation** (Pydantic models in `schemas.py`)
5. **Every parser has unit tests** with real-format fixture files in `tests/fixtures/`
6. **The frontend never touches the DB** — all data flows through the REST API
7. **No authentication on the tool** — it runs on a trusted network / VPN. The red team trusts each other.
8. **All state in `./data/`** — DB file, uploaded raw files, nothing else. This directory is the only thing that needs to be backed up or moved.
9. **Handle messy data gracefully** — real red team files are incomplete, corrupted, have weird encodings. Parsers must never crash on bad input; log warnings and continue.
10. **IP resolution is best-effort** — when a parser finds an IP, try to match it to an existing host. If no match, create an "unresolved" host with just that IP. The user can merge hosts later.
11. **Use `uv` for all Python operations** — `uv sync` to install deps, `uv run` to execute scripts/tests, `uv add` to add new packages. Never use raw `pip`. The `pyproject.toml` is the single source of truth for Python dependencies. Commit `uv.lock` to git.

## Git Workflow

Use **conventional commits** with short, descriptive messages. Commit after each logical unit of work — not at the end of an entire phase.

### Commit granularity:

- One commit per meaningful change (new model, new router, new parser, new component)
- Do NOT squash an entire phase into a single commit
- Do NOT commit broken/untested code — run tests before committing

### Commit message format:

```
type(scope): short description

types: feat, fix, refactor, test, docs, chore
scope: backend, frontend, parsers, docker, schema
```

### Examples:

```
feat(schema): add Host, HostIP, HostUser models
feat(backend): CRUD endpoints for operations
feat(frontend): operation selector page with dark theme
feat(parsers): authorized_keys parser with fingerprint extraction
test(parsers): fixture files and tests for auth_log parser
fix(backend): handle duplicate IPs during upload resolution
docs: update AGENT.md status to Phase 2 complete
chore(docker): add multi-stage build with uv caching
```

### Branch strategy:

- Work directly on `main` — this is a new project, not a team codebase yet
- If a phase turns out to be complex, the agent may create a feature branch and merge when stable

### After each phase:

1. Run all tests
2. Commit any remaining changes
3. Update the "Current Status" section in AGENT.md
4. Commit that status update: `docs: mark Phase N complete`

## File Structure

```
ssh-pivot-tracker/
├── docker-compose.yml
├── Makefile
├── README.md
├── CONTRIBUTING.md
├── data/                        # All persistent state (gitignored, Docker volume)
│   ├── tracker.db               # SQLite database
│   └── uploads/                 # Raw uploaded files organized by op_id
│       └── {op_id}/
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml           # Project metadata + dependencies (uv managed)
│   ├── uv.lock                  # Locked dependency versions
│   ├── main.py                  # FastAPI app entry, CORS, lifespan
│   ├── config.py                # Settings (DB path, upload path, etc.)
│   ├── database.py              # SQLAlchemy engine, session, base
│   ├── models.py                # All ORM models
│   ├── schemas.py               # Pydantic request/response models
│   ├── routers/
│   │   ├── operations.py
│   │   ├── hosts.py
│   │   ├── credentials.py
│   │   ├── connections.py
│   │   ├── upload.py            # File upload + parsing trigger
│   │   └── graph.py             # Graph queries: expand node, find path, aggregated edges
│   ├── parsers/
│   │   ├── __init__.py          # BaseParser, ParseResult, parser registry
│   │   ├── authorized_keys.py
│   │   ├── known_hosts.py
│   │   ├── ssh_config.py
│   │   ├── ssh_keys.py
│   │   ├── auth_log.py
│   │   ├── wtmp.py
│   │   ├── bash_history.py
│   │   └── passwd.py
│   ├── services/
│   │   ├── ip_resolver.py       # Match IPs to existing hosts
│   │   ├── key_matcher.py       # Cross-reference key fingerprints across op
│   │   ├── pivot_analysis.py    # BFS path finding between hosts
│   │   └── graph_builder.py     # Aggregate evidence into edge objects for frontend
│   └── alembic/
│       └── ...
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf               # Serves built app + proxies /api to backend
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── theme.ts             # Dark theme config
│       ├── pages/
│       │   ├── OpSelector.tsx
│       │   └── Workspace.tsx
│       ├── components/
│       │   ├── GraphCanvas.tsx          # cytoscape.js wrapper
│       │   ├── NodeContextMenu.tsx      # Right-click menu for nodes
│       │   ├── EdgeContextMenu.tsx      # Right-click menu for edges
│       │   ├── HostDetailSidebar.tsx    # Host info panel on node click
│       │   ├── EdgeDetailPanel.tsx      # All evidence for an edge
│       │   ├── AddDataModal.tsx         # FAB modal (tabs: manual / upload)
│       │   ├── ManualEntryForm.tsx
│       │   ├── FileUploadTab.tsx
│       │   ├── HostSelector.tsx         # Checkbox list for selecting hosts to display
│       │   ├── PathFinder.tsx           # Two-node path analysis UI
│       │   └── PathDetail.tsx           # Path result display
│       ├── api/                         # Typed API client functions
│       │   ├── client.ts
│       │   ├── operations.ts
│       │   ├── hosts.ts
│       │   ├── graph.ts
│       │   └── upload.ts
│       └── types/                       # TypeScript interfaces matching backend schemas
│           └── index.ts
├── tests/
│   ├── fixtures/                        # Sample files for parser tests
│   │   ├── sample_authorized_keys
│   │   ├── sample_known_hosts
│   │   ├── sample_auth.log
│   │   ├── sample_auth.log.gz
│   │   ├── sample_wtmp
│   │   ├── sample_bash_history
│   │   ├── sample_ssh_config
│   │   ├── sample_passwd
│   │   └── sample_keys/
│   │       ├── id_rsa
│   │       ├── id_rsa.pub
│   │       ├── id_ed25519
│   │       └── id_ed25519.pub
│   ├── test_parsers/
│   │   ├── test_authorized_keys.py
│   │   ├── test_known_hosts.py
│   │   ├── test_auth_log.py
│   │   ├── test_wtmp.py
│   │   ├── test_bash_history.py
│   │   ├── test_ssh_config.py
│   │   ├── test_passwd.py
│   │   └── test_ssh_keys.py
│   ├── test_api/
│   │   ├── test_operations.py
│   │   ├── test_hosts.py
│   │   ├── test_upload.py
│   │   └── test_graph.py
│   ├── test_services/
│   │   ├── test_ip_resolver.py
│   │   ├── test_key_matcher.py
│   │   ├── test_pivot_analysis.py
│   │   └── test_graph_builder.py
│   └── conftest.py
└── .gitignore                   # Includes data/, *.db, node_modules, __pycache__, .env
```

## Current Status

**Phase**: Phase 1 complete
**Last completed**: Phase 1 — Project Skeleton & Infrastructure
**Next step**: Phase 2 — Manual Data Entry

## Notes for the Agent

- Implement one phase at a time. After each phase, run all tests and confirm end-to-end before proceeding.
- When implementing parsers, handle malformed/incomplete files gracefully — real-world red team data is messy. Never crash on bad input.
- For SSH key fingerprint matching, use SHA256 fingerprints consistently. Use paramiko for key parsing.
- Edge aggregation is the core feature. When building graph_builder.py, think of it as: "collect ALL evidence between two hosts into one rich edge object." The frontend just renders what you give it.
- Dark theme from the start — not bolted on later. Use a CSS variable system or a component library with theme support.
- The right-click context menu on nodes is critical for usability. "Expand by relationship type" means: when expanding a node, the backend should accept a filter parameter for which evidence types to follow.
- HostUser entries are evidence-based. If you're writing a parser and it doesn't have clear evidence that a user exists on the host, do NOT create a HostUser. The bar is: could you prove this user has an account on this machine?
- For IP resolution: maintain an in-memory lookup (ip → host_id) per operation during parsing sessions. When a new file is uploaded, rebuild the lookup from HostIP table, then use it to resolve IPs in the parsed data.
- Docker builds should be fast for development. Use multi-stage builds, copy `pyproject.toml` + `uv.lock` first and run `uv sync` to cache the dependency layer before copying source code. Use `uv` inside the Dockerfile (install via `COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv`).
- The `./data/` directory is sacred. It's the only thing that matters for backup/restore. Everything else is reproducible from source.
