# Lockpick — Red Team Operation Manager

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
tar czf lockpick-backup.tar.gz .
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
├── HostIP (one-to-many) — the IPs that BELONG to this host
│   └── id, host_id (FK), ip_address, source (enum: manual | parsed), first_seen_at
│       ** This is how we resolve "traffic from 10.0.0.5" → "that's HostA" **
│
├── HostUser (one-to-many) — user ACCOUNTS known to exist on this host
│   └── id, host_id (FK), username, shell (nullable), home_dir (nullable)
│       source (enum: manual | passwd_file | authorized_keys | log_evidence)
│       created_at
│       ** Represents a user account on a specific host — NOT a global user entity.
│          "bob" on HostA and "bob" on HostB are two separate HostUser records.
│          Populated from /etc/passwd parsing, LDAP dumps, or manual entry.
│          A user can exist on a host without having any credentials linked. **

Credential (standalone entity — a key or password can unlock multiple hosts)
├── id (UUID), op_id (FK)
├── cred_type (enum: password | private_key | public_key)
├── value (the actual key content or password)
├── passphrase (nullable — for encrypted private keys)
├── fingerprint (SHA256, inferred automatically by backend via paramiko — never user-supplied)
├── key_type (nullable, e.g. ssh-rsa, ssh-ed25519 — inferred automatically, never user-supplied)
├── comment (nullable), created_at
│
├── CredentialLink (junction: where was this credential found and what does it grant?)
│   └── id, credential_id (FK), host_id (FK)
│       username (nullable string — which user on that host; AUTHORITATIVE for pivot queries)
│       host_user_id (nullable FK → HostUser — optional enrichment; set when a formal HostUser record exists)
│       relationship_type (enum: found_on_disk | authorized_key | accepted_password | used_in_connection)
│       file_source (nullable — which uploaded file produced this link)
│       ** Example: private key found in /home/bob/.ssh/id_rsa on HostA →
│          credential_id=key1, host_id=HostA, username="bob", relationship=found_on_disk
│          That same key's fingerprint matches authorized_keys on HostB for user root →
│          credential_id=key1, host_id=HostB, username="root", relationship=authorized_key
│          This gives us a pivot: HostA(bob) → HostB(root) via key1
│
│          username is always the pivot query field. host_user_id is optional — link it
│          when a HostUser record exists for that (host, username) pair. **
```

**Usernames in CredentialLink:** `username` (plain string) is the authoritative field for all pivot path queries. `host_user_id` is optional enrichment for when a formal HostUser record exists. Pivot logic reads `username`, never `host_user_id`.

**Usernames in ConnectionRecord:** `src_user` / `dst_user` are plain strings from raw log evidence. They are not linked to HostUser records (log lines are raw facts, not structured entities).

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
├── auth_method (nullable enum: publickey | password | keyboard-interactive | hostbased | unknown)
│   ** How the connection was authenticated. Set when the source records it
│      (e.g. auth.log: "Accepted publickey for root"). Null for sources that don't
│      record auth method (bash_history, wtmp). **
├── credential_id (nullable FK → Credential)
│   ** The specific credential used, if identifiable. Set when auth.log includes a
│      key fingerprint that matches a Credential in the op. Raises confidence from
│      "observed" to "confirmed+observed" for that connection. **
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
      "detail": "auth.log on HostB shows successful SSH login from 10.0.0.5 (HostA) as root via publickey (SHA256:abc...)",
      "auth_method": "publickey",
      "credential_id": "...",
      "timestamp": "2024-03-15T14:22:00",
      "source_file": "hostB_auth.log",
      "confidence": "confirmed"
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

**Commit discipline:** commit at natural checkpoints within a phase — typically after each logical unit (e.g. backend done, frontend components done, page wiring done). Use conventional commit prefixes (`feat`, `fix`, `test`, `refactor`, `docs`). Never leave a phase's work uncommitted. At minimum, commit once when the phase is fully complete.

### Phase 1 — Project Skeleton & Infrastructure

- [x] Docker Compose setup (backend + frontend services, ./data/ volume)
- [x] Makefile with: up, down, logs, backup, dev-backend, dev-frontend
- [x] Initialize FastAPI backend with SQLAlchemy + SQLite (DB path: ./data/tracker.db)
- [x] Initialize React frontend with Vite + TypeScript
- [x] Implement the full database schema with migrations (alembic)
- [x] CRUD API endpoints for: Operations, Hosts, HostIPs, Credentials, CredentialLinks, ConnectionRecords
- [ ] CRUD API endpoints for: HostUsers (moved to Phase 4 — HostUser & Schema Hardening)
- [x] Basic API tests (pytest)
- [x] Simple frontend shell: operation selector screen (list/create ops)
- [x] Dark theme from the start (all components)
- [x] README.md with setup instructions (Docker and local dev)
- [x] CONTRIBUTING.md with architecture overview and how-to-add-a-parser guide

### Phase 2 — Manual Data Entry

- [x] Frontend: after selecting an op, show the main workspace (creating an op auto-navigates into it)
- [x] Floating action button (bottom-right corner, + icon)
- [x] Clicking FAB opens a modal with tabs: "Manual Entry" | "File Upload" (upload tab is placeholder for Phase 6)
- [x] Manual entry form — three sub-forms (Host / Credential / Connection):
  - **Host**: nickname, one or more IPs, comment
  - **Credential**: type (password / private_key / public_key), value, optional passphrase (for encrypted private keys), optional comment; optionally linked to a host + username + relationship type. `key_type` and `fingerprint` are inferred by the backend — not user input.
  - **Connection**: src host/IP/user → dst host/IP/user, connection type, direction context
- [x] All entries tagged with op_id based on current op context
- [x] Workspace shows hosts as cards with IP chips

### Phase 3 — Edit & Delete

Full edit and delete capabilities for every entity. The backend already exposes most PATCH/DELETE endpoints; this phase surfaces them in the UI and fills the remaining backend gaps.

#### Backend

- [x] Expand `CredentialUpdate` schema: add `value` and `passphrase` fields (re-infer `fingerprint`/`key_type` via paramiko when `value` changes)
- [x] Add `CredentialLinkUpdate` schema: `username`, `relationship_type`, `file_source`
- [x] Add `ConnectionRecordUpdate` schema: all mutable fields optional
- [x] Expand `PATCH /credentials/{cred_id}` to handle value/passphrase changes with fingerprint re-inference
- [x] Add `PATCH /credential-links/{link_id}`
- [x] Add `PATCH /connections/{connection_id}`
- [x] Tests: `tests/test_api/test_credentials.py`, `tests/test_api/test_connections.py`

#### Frontend — new components

- [x] `ConfirmDeleteModal` — reusable "Are you sure?" dialog with danger-styled button
- [x] `DeleteOpModal` — delete operation modal; user must type the full op UUID to confirm
- [x] `EditModal` — thin modal shell (title + X button + Esc close) that wraps entity-specific edit forms
- [x] `EditHostForm` — pre-filled nickname/comment; IPs managed inline (add/remove with immediate API calls)
- [x] `EditCredentialForm` — value (textarea), passphrase, comment; cred_type is read-only; hint shown when value changed ("fingerprint will be re-inferred")
- [x] `EditCredentialLinkForm` — username, relationship_type, file_source editable; credential and host shown read-only
- [x] `EditConnectionForm` — same src/dst grid layout as ManualEntryForm's ConnectionForm, pre-filled

#### Frontend — Workspace expansion

- [x] Fetch credentials, credential-links, and connections in parallel alongside hosts (`Promise.all`)
- [x] Add **Credentials** section (flat list): type badge, truncated value, fingerprint chip, comment; credential links as sub-rows; Edit + Delete per item
- [x] Add **Connections** section (flat list): `src_ip → dst_ip`, users, type badge, timestamp; Edit + Delete per row
- [x] Add Edit and Delete icon buttons to each existing Host card
- [x] Wire all edit/delete modals in Workspace

#### Frontend — OpSelector

- [x] Refactor op list items to `display: flex` (sibling buttons, not nested — valid HTML)
- [x] Add Edit and Delete buttons per op (revealed on hover via CSS opacity transition)
- [x] `EditOpModal` — pre-filled name/description, calls `updateOperation`
- [x] `DeleteOpModal` — UUID confirmation, calls `deleteOperation`

#### Frontend — API additions

- [x] `api/operations.ts`: add `updateOperation(opId, data)`
- [x] `api/credentials.ts`: add `updateCredential(credId, data)`, `updateCredentialLink(linkId, data)`
- [x] `api/connections.ts`: add `updateConnection(connectionId, data)`
- [x] `types/index.ts`: add `UpdateOperationRequest`, `UpdateCredentialRequest`, `UpdateCredentialLinkRequest`, `UpdateConnectionRequest`

### Phase 4 — HostUser & Schema Hardening

Implement the `HostUser` entity and the `ConnectionRecord` authentication fields before the graph visualization phase needs them. All changes are additive — no existing endpoints or data break.

#### Backend

- [ ] Add `HostUser` ORM model (`backend/models.py`): `id`, `host_id` (FK→hosts, cascade), `username`, `shell` (nullable), `home_dir` (nullable), `source` enum (`manual | passwd_file | authorized_keys | log_evidence`), `created_at`
- [ ] Add `users` relationship to `Host` model (cascade delete)
- [ ] Add `host_user_id` nullable FK (→ host_users, SET NULL on delete) to `CredentialLink` model; keep existing `username` string — it stays the authoritative pivot-query field
- [ ] Add `auth_method` nullable enum (`publickey | password | keyboard-interactive | hostbased | unknown`) to `ConnectionRecord`
- [ ] Add `credential_id` nullable FK (→ credentials, SET NULL on delete) to `ConnectionRecord`
- [ ] New Alembic migration: create `host_users` table; add `host_user_id` to `credential_links`; add `auth_method` + `credential_id` to `connection_records` (all via `batch_alter_table` for SQLite)
- [ ] Add `HostUserCreate` / `HostUserRead` Pydantic schemas (`backend/schemas.py`)
- [ ] Update `HostRead` to include `users: list[HostUserRead] = []`
- [ ] Update `CredentialLinkCreate` / `CredentialLinkRead` to include optional `host_user_id`
- [ ] Update `ConnectionRecordCreate` / `ConnectionRecordRead` to include optional `auth_method` and `credential_id`
- [ ] Add HostUser endpoints to `backend/routers/hosts.py`:
  - `POST /api/hosts/{host_id}/users`
  - `GET /api/hosts/{host_id}/users`
  - `DELETE /api/hosts/{host_id}/users/{user_id}`
- [ ] Update `POST /api/ops/{op_id}/connections` in `backend/routers/connections.py` to accept and persist `auth_method` and `credential_id`; validate `credential_id` belongs to the same op if provided
- [ ] Tests: `tests/test_api/test_host_users.py` (create, list, delete, host-read includes users, optional FK on credential-link); extend `tests/test_api/test_connections.py` (auth_method, credential_id, nil fields still work)

#### Frontend

- [ ] Add `HostUser` interface and `CreateHostUserRequest` to `frontend/src/types/index.ts`
- [ ] Update `Host` interface: add `users: HostUser[]`
- [ ] Update `CredentialLink` interface: add `host_user_id: string | null`
- [ ] Update `ConnectionRecord` / `CreateConnectionRequest`: add `auth_method` and `credential_id` fields
- [ ] Add `listHostUsers`, `createHostUser`, `deleteHostUser` to `frontend/src/api/hosts.ts`
- [ ] `ManualEntryForm` — HostForm: add repeatable "Known Users" rows (username, optional shell, source selector); calls `createHostUser` per row after host is created — same add/remove pattern as IP rows
- [ ] `ManualEntryForm` — ConnectionForm: add `auth_method` dropdown and optional credential selector (loaded from current op)

### Phase 5 — Host Selection & Graph Visualization

- [ ] Host query/filter panel: show all hosts in current op as a searchable/filterable list with checkboxes
- [ ] Selected hosts render on a cytoscape.js canvas as labeled nodes
- [ ] Node label shows nickname; badge/icon shows number of known users (from HostUser table) and credentials
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
  - "Edit host" — open edit form (reuses EditHostForm from Phase 3)
  - "Delete host" — delete from DB with confirmation (reuses ConfirmDeleteModal from Phase 3)
- [ ] **Right-click context menu on edges:**
  - "Show evidence detail" — open evidence panel
  - "Hide this edge" — remove from canvas
- [ ] Hidden nodes/edges can be restored via "Show all" button or re-selecting from the host list

### Phase 6 — File Upload & Parsing Engine

Build a parsing engine on the backend. Each parser is a module in `backend/parsers/`. All parsers implement a common interface.

#### Parser Interface

```python
class ParseResult:
    hosts_found: list[HostData]              # New hosts/IPs discovered
    credentials_found: list[CredentialData]  # Keys/passwords found
    connections_found: list[ConnectionData]  # Connection records
    warnings: list[str]                      # Parse issues (malformed lines, etc.)
    stats: dict                              # Summary counts for UI

class BaseParser:
    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult: ...
```

**Note:** Usernames from parsed files are stored as plain strings on `CredentialLink.username` and `ConnectionRecord.src_user/dst_user`. When a file reveals that a user *account exists* on a host (e.g. `/etc/passwd`, LDAP dump), create a `HostUser` record instead. When a file reveals a credential belongs to a user, create a `CredentialLink` with the `username` string (and optionally link `host_user_id` if a matching `HostUser` record exists).

#### Upload API

- Endpoint: `POST /api/ops/{op_id}/upload`
- Accepts: multipart file + JSON metadata (file_type, host_id, username)
- Steps: parse → resolve IPs to existing hosts where possible → insert records → return ParseResult summary
- Raw uploaded files stored in `./data/uploads/{op_id}/` for audit

#### Parsers to implement (one at a time, with tests):

**4a. `.ssh/authorized_keys`** (per user)
- Extract public keys, compute SHA256 fingerprints via paramiko
- Create Credential (cred_type=public_key, fingerprint inferred) + CredentialLink (relationship=authorized_key, username from upload metadata)
- Create or reuse HostUser (source=authorized_keys) for the username on this host; set `host_user_id` on the resulting CredentialLink

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
- Store as Credential with relationship=found_on_disk; set `username` from upload metadata
- Create or reuse HostUser (source=log_evidence or manual) for the username on this host; set `host_user_id` on the CredentialLink
- **Immediately cross-reference** fingerprint against ALL authorized_keys in the op
- Return any newly discovered pivot opportunities in the ParseResult

**4e. `auth.log` / `secure`** (including .gz)
- Decompress gzip if needed
- Parse sshd log lines: accepted/failed, user, source IP, auth method (publickey/password), key fingerprint if present, timestamp
- Store as inbound ConnectionRecords on this host (dst_user = username from log line)
- Set `auth_method` on ConnectionRecord from the log line (publickey / password / etc.)
- If log line includes a key fingerprint, match it against `Credential.fingerprint` in the op — if found, set `credential_id` on the ConnectionRecord (raises confidence to "confirmed")
- Match source IPs to existing hosts

**4f. `wtmp`** (binary format)
- Parse using struct-based parsing (utmp record format)
- Extract login records: user, source IP/hostname, login/logout timestamps
- Store as inbound ConnectionRecords (dst_user = username from record)

**4g. `.bash_history`** (per user)
- Regex for: `ssh`, `scp`, `rsync`, `sftp`, `ssh-copy-id` commands
- Extract destination host/IP, user (@user syntax, -l flag), port (-p flag)
- Store as outbound ConnectionRecords from this host
- Look for `ssh-keygen`, `ssh-add` as context indicators (note in host comment)

**4h. `/etc/passwd`**
- Extract user accounts (username, shell, home_dir)
- Create `HostUser` records (source=`passwd_file`) for each non-system user — NOT CredentialLinks or ConnectionRecords
- Skip system users (uid < 1000) by default, but keep root and any with a valid login shell
- If a matching `HostUser` already exists for that (host, username), update shell/home_dir rather than creating a duplicate

#### File upload frontend:

- "File Upload" tab in the Add modal
- Dropdown to select file type (from enum of supported types)
- Host selector (required — which host did this file come from?)
- Username field (required for per-user files: authorized_keys, known_hosts, config, bash_history, private keys — stored as plain string on resulting CredentialLinks/ConnectionRecords; also creates a HostUser record if one doesn't exist for that host+username)
- Drag-and-drop upload area
- After upload, show parsing results summary:
  - "Found: 3 new hosts, 5 connection records, 2 SSH keys"
  - "Warnings: 12 malformed lines skipped"
  - "New pivot opportunity: HostA(bob) → HostC(root) via key SHA256:xyz..."
- Support uploading multiple files in sequence (form resets but keeps host/user selection)

### Phase 7 — Pivot Path Analysis

- [ ] Backend endpoint: given two hosts, find all pivot paths (BFS on aggregated edge graph)
- [ ] Path results include: each hop's evidence, required credentials, confidence per hop
- [ ] Distinguish: confirmed path (all hops have key matches) vs observed path (log evidence) vs theoretical (indicators only)
- [ ] Frontend: "Find Path" mode — select two nodes, show all paths highlighted on graph
- [ ] Path detail panel showing each hop with full evidence breakdown
- [ ] Ability to filter paths by minimum confidence level

### Phase 8 — Polish & UX

- [ ] Global search across all data (hosts, IPs, users, key fingerprints, comments)
- [ ] Export op data as JSON (full op state: hosts, creds, connections, everything)
- [ ] Import op from JSON (restore or merge)
- [ ] Graph layout options (force-directed, hierarchical, circular, grid)
- [ ] Keyboard shortcuts (Esc close modals, Del hide selected node, Ctrl+F search)
- [ ] Bulk file upload (multiple files, auto-detect type where possible)
- [ ] Activity log (who added what, when — basic audit trail, stored in DB)
- [ ] Notification banner when data has changed since your last query ("15 new records since your last refresh" — click to refresh)

### Phase 9 — MCP Server

A standalone MCP (Model Context Protocol) server that lets an AI agent (e.g. Claude Desktop) help a red teamer navigate the operation data and find pivot paths using natural language. This phase is last — implement only when all other phases are complete and stable.

#### Architecture

- Standalone Python package in `mcp/` — does **not** import from `backend/`, calls the Lockpick REST API over HTTP
- Uses the `mcp` Python package (FastMCP high-level API)
- Configurable backend URL via `LOCKPICK_URL` environment variable (default: `http://localhost:8000`)
- stdio transport — Claude Desktop connects by running the server process directly
- Docker service with no exposed ports; Claude Desktop connects via `docker exec -i`

#### MCP Tools

| Tool | Backend calls | Purpose |
|------|--------------|---------|
| `list_operations()` | `GET /ops` | List all ops |
| `list_hosts(op_id)` | hosts + credential-links | Hosts with IPs and credential count |
| `get_host(host_id)` | `GET /hosts/{id}` | Full host detail |
| `expand_host(host_id, evidence_type?)` | connections + credential-links | Related hosts, optionally filtered by evidence type |
| `list_credentials(op_id)` | credentials + credential-links | Creds with fingerprints and host count |
| `list_connections(op_id)` | `GET /ops/{id}/connections` | Raw connection records |
| `find_pivot_paths(op_id, src_host_id, dst_host_id)` | connections + credential-links | BFS pivot paths with evidence and confidence |
| `search(op_id, query)` | Phase 8 search endpoint (client-side fallback if unavailable) | Global search |

`find_pivot_paths` performs BFS in the MCP layer: builds an adjacency graph from connection records and credential key matches (same fingerprint: `found_on_disk` on A + `authorized_key` on B), caps at depth 6 and 50 paths, annotates each edge with confidence (`confirmed` = key match, `observed` = connection log).

#### Checklist

- [ ] `mcp/pyproject.toml` — standalone package (`mcp>=1.0.0`, `httpx>=0.27.0`, `anyio>=4.0.0`)
- [ ] `mcp/api_client.py` — `LockpickClient` using `httpx.AsyncClient`
- [ ] `mcp/tools/` — one module per tool group (operations, hosts, credentials, connections, pivot, search)
- [ ] `mcp/server.py` — FastMCP entry point, registers all tools, runs with stdio transport
- [ ] `mcp/Dockerfile` — uv-based, `ENV LOCKPICK_URL=http://backend:8000`
- [ ] `docker-compose.yml` — add `mcp` service (no ports, depends on backend)
- [ ] `mcp/README.md` — Claude Desktop config instructions (Docker and local dev options)
- [ ] Tests: `mcp/tests/test_tools.py` using `respx` to mock HTTP calls; include BFS correctness tests

#### Claude Desktop config (from `mcp/README.md`)

```json
{
  "mcpServers": {
    "lockpick": {
      "command": "docker",
      "args": ["exec", "-i", "lockpick-mcp-1", "uv", "run", "--frozen", "python", "/app/server.py"]
    }
  }
}
```

Local dev alternative: use `uv run` directly with `LOCKPICK_URL=http://localhost:8000`.

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

Use **conventional commits** with short, descriptive messages. **Commit as you go** — after every meaningful unit of work, not at the end of a phase or session.

### Commit granularity:

- **Commit immediately** after each meaningful change: new model, new router, new parser, new component, schema migration, test file
- Do NOT squash an entire phase into a single commit
- Do NOT commit broken/untested code — run `uv run --directory backend pytest ../tests/ -v` before committing backend changes

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
lockpick/
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
│   │   ├── upload.py            # File upload + parsing trigger (Phase 6)
│   │   └── graph.py             # Graph queries: expand node, find path, aggregated edges (Phase 5)
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
│   │   ├── pivot_analysis.py    # BFS path finding between hosts (Phase 7)
│   │   └── graph_builder.py     # Aggregate evidence into edge objects for frontend (Phase 5)
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
│       │   ├── AddDataModal.tsx         # FAB modal (tabs: manual / upload)
│       │   ├── ManualEntryForm.tsx
│       │   ├── ConfirmDeleteModal.tsx   # Reusable delete confirmation (Phase 3)
│       │   ├── DeleteOpModal.tsx        # Op delete with UUID confirmation (Phase 3)
│       │   ├── EditModal.tsx            # Modal shell for edit forms (Phase 3)
│       │   ├── EditHostForm.tsx         # Edit host nickname/comment/IPs (Phase 3)
│       │   ├── EditCredentialForm.tsx   # Edit credential value/passphrase/comment (Phase 3)
│       │   ├── EditCredentialLinkForm.tsx # Edit credential link fields (Phase 3)
│       │   ├── EditConnectionForm.tsx   # Edit connection record fields (Phase 3)
│       │   ├── FileUploadTab.tsx        # File upload UI (Phase 6)
│       │   ├── GraphCanvas.tsx          # cytoscape.js wrapper (Phase 5)
│       │   ├── NodeContextMenu.tsx      # Right-click menu for nodes (Phase 5)
│       │   ├── EdgeContextMenu.tsx      # Right-click menu for edges (Phase 5)
│       │   ├── HostDetailSidebar.tsx    # Host info panel on node click (Phase 5)
│       │   ├── EdgeDetailPanel.tsx      # All evidence for an edge (Phase 5)
│       │   ├── HostSelector.tsx         # Checkbox list for selecting hosts to display (Phase 5)
│       │   ├── PathFinder.tsx           # Two-node path analysis UI (Phase 7)
│       │   └── PathDetail.tsx           # Path result display (Phase 7)
│       ├── api/                         # Typed API client functions
│       │   ├── client.ts
│       │   ├── operations.ts
│       │   ├── hosts.ts
│       │   ├── credentials.ts
│       │   ├── connections.ts
│       │   ├── graph.ts                 # Graph queries (Phase 5)
│       │   └── upload.ts               # File upload (Phase 6)
│       └── types/                       # TypeScript interfaces matching backend schemas
│           └── index.ts
├── mcp/                                 # MCP server — AI agent companion (Phase 9)
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── .python-version
│   ├── server.py                        # FastMCP entry point
│   ├── api_client.py                    # HTTP wrapper around Lockpick REST API
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── operations.py
│   │   ├── hosts.py
│   │   ├── credentials.py
│   │   ├── connections.py
│   │   ├── pivot.py                     # BFS find_pivot_paths tool
│   │   └── search.py
│   ├── tests/
│   │   └── test_tools.py
│   └── README.md                        # Claude Desktop connection instructions
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
│   │   ├── test_credentials.py
│   │   ├── test_connections.py
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

**Phase**: Phase 2 complete
**Last completed**: Phase 2 — Manual Data Entry
**Next step**: Phase 3 — Edit & Delete

## Notes for the Agent

- Implement one phase at a time. After each phase, run all tests and confirm end-to-end before proceeding.
- When implementing parsers, handle malformed/incomplete files gracefully — real-world red team data is messy. Never crash on bad input.
- For SSH key fingerprint matching, use SHA256 fingerprints consistently. Use paramiko for key parsing.
- Edge aggregation is the core feature. When building graph_builder.py, think of it as: "collect ALL evidence between two hosts into one rich edge object." The frontend just renders what you give it.
- Dark theme from the start — not bolted on later. Use a CSS variable system or a component library with theme support.
- The right-click context menu on nodes is critical for usability. "Expand by relationship type" means: when expanding a node, the backend should accept a filter parameter for which evidence types to follow.
- For IP resolution: maintain an in-memory lookup (ip → host_id) per operation during parsing sessions. When a new file is uploaded, rebuild the lookup from HostIP table, then use it to resolve IPs in the parsed data.
- Docker builds should be fast for development. Use multi-stage builds, copy `pyproject.toml` + `uv.lock` first and run `uv sync` to cache the dependency layer before copying source code. Use `uv` inside the Dockerfile (install via `COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv`).
- The `./data/` directory is sacred. It's the only thing that matters for backup/restore. Everything else is reproducible from source.
