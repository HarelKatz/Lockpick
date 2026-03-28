# Lockpick — Red Team Operation Manager

## Project Overview

A web-based tool for red teams to collaboratively organize SSH credentials, host relationships, and pivot paths during operations. Runs as a shared server — the entire team accesses it, and any data one person adds is visible to everyone on their next query. The core value is **visualizing lateral movement opportunities** by correlating SSH keys, connection logs, and host data across an engagement.

**Portability:** This tool may run on a VPS for a week, get zipped up, moved to another box, and resumed. All state lives in `./data/` — the only thing to back up or move. No external dependencies.

> For tech stack, dev commands, repo layout, migration rules, frontend conventions, and git format — see **CLAUDE.md**.

---

## Data Model

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
├── name (nullable — human-readable label), comment (nullable), created_at
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

---

## Current Status

**Last completed phase: Phase 5 — Host Selection & Graph Visualization**

Phases 1–5 are fully implemented and tested. See git history for details.

**Next phase: Phase 6 — File Upload & Parsing Engine**

---

## Implementation Phases

### Phases 1–5 — Complete

See git history for details. All infrastructure, CRUD APIs, edit/delete UI, HostUser entity, schema hardening, and the graph visualization layer (backend aggregation service + cytoscape.js frontend) are implemented and tested.

### Phase 5 — Host Selection & Graph Visualization

#### Backend — Graph API

New router: `backend/routers/graph.py`. New service: `backend/services/graph_builder.py`.

```
GET /api/ops/{op_id}/graph?host_ids=id1,id2,...
```

Returns nodes + edges for the requested host subset (omit `host_ids` for all hosts in op).

Response shape:
```json
{
  "nodes": [
    {
      "host_id": "...", "nickname": "...", "ips": ["10.0.0.1"],
      "user_count": 2, "credential_count": 3
    }
  ],
  "edges": [
    {
      "src_host_id": "...", "dst_host_id": "...",
      "confidence": "confirmed",
      "evidence": [...],
      "pivotable_users": [
        {"src_user": "bob", "dst_user": "root", "method": "key", "credential_id": "..."}
      ]
    }
  ]
}
```

`graph_builder.py` aggregates evidence in two passes:
1. **Key matches** — CredentialLink pairs where a `found_on_disk` link on host A shares a fingerprint with an `authorized_key` link on host B → `key_match` evidence, `confirmed` confidence
2. **Connection records** — ConnectionRecord rows grouped by (src_host_id, dst_host_id) → `connection_log`, `bash_history`, or `known_hosts` evidence

Edge `confidence` = highest confidence among all evidence items.

```
GET /api/ops/{op_id}/hosts/{host_id}/expand?evidence_type=all|key_match|connection_log|indicator
```

Returns all hosts related to the given host (with their edges), filtered by evidence type. Used by double-click / right-click "Expand" on graph nodes.

Tests: `tests/test_api/test_graph.py`, `tests/test_services/test_graph_builder.py`

#### Frontend

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

**Note:** Usernames from parsed files are stored as plain strings on `CredentialLink.username` and `ConnectionRecord.src_user/dst_user`. When a file reveals that a user *account exists* on a host (e.g. `/etc/passwd`, LDAP dump), create a `HostUser` record. When a file reveals a credential belongs to a user, create a `CredentialLink` with the `username` string (and optionally link `host_user_id` if a matching `HostUser` record exists).

#### Upload API

- Endpoint: `POST /api/ops/{op_id}/upload`
- Accepts: multipart file + JSON metadata (file_type, host_id, username)
- Steps: parse → resolve IPs to existing hosts where possible → insert records → return ParseResult summary
- Raw uploaded files stored in `./data/uploads/{op_id}/` for audit

#### Parsers to implement (one at a time, with tests):

**6a. `.ssh/authorized_keys`** (per user)
- Extract public keys, compute SHA256 fingerprints via paramiko
- Create Credential (cred_type=public_key, fingerprint inferred) + CredentialLink (relationship=authorized_key, username from upload metadata)
- Create or reuse HostUser (source=authorized_keys) for the username on this host; set `host_user_id` on the resulting CredentialLink

**6b. `.ssh/known_hosts`** (per user)
- Parse hostnames/IPs and key fingerprints (handle hashed known_hosts too)
- Create ConnectionRecords (outbound indicators from this host)
- Match IPs to existing hosts; create unresolved placeholder hosts for unknown IPs

**6c. `.ssh/config`** (per user)
- Parse Host/Match blocks: Hostname, User, Port, IdentityFile, ProxyJump
- Create connection hints and host aliases
- If IdentityFile references a key we have, link them

**6d. SSH private/public key files** (id_rsa, id_ed25519, etc.)
- Read key with paramiko, compute SHA256 fingerprint
- Store as Credential with relationship=found_on_disk; set `username` from upload metadata
- Create or reuse HostUser (source=log_evidence or manual) for the username on this host; set `host_user_id` on the CredentialLink
- **Immediately cross-reference** fingerprint against ALL authorized_keys in the op
- Return any newly discovered pivot opportunities in the ParseResult

**6e. `auth.log` / `secure`** (including .gz)
- Decompress gzip if needed
- Parse sshd log lines: accepted/failed, user, source IP, auth method (publickey/password), key fingerprint if present, timestamp
- Store as inbound ConnectionRecords on this host (dst_user = username from log line)
- Set `auth_method` on ConnectionRecord from the log line
- If log line includes a key fingerprint, match against `Credential.fingerprint` in the op — if found, set `credential_id` on the ConnectionRecord (raises confidence to "confirmed")
- Match source IPs to existing hosts

**6f. `wtmp`** (binary format)
- Parse using struct-based parsing (utmp record format)
- Extract login records: user, source IP/hostname, login/logout timestamps
- Store as inbound ConnectionRecords (dst_user = username from record)

**6g. `.bash_history`** (per user)
- Regex for: `ssh`, `scp`, `rsync`, `sftp`, `ssh-copy-id` commands
- Extract destination host/IP, user (@user syntax, -l flag), port (-p flag)
- Store as outbound ConnectionRecords from this host
- Look for `ssh-keygen`, `ssh-add` as context indicators (note in host comment)

**6h. `/etc/passwd`**
- Extract user accounts (username, shell, home_dir)
- Create `HostUser` records (source=`passwd_file`) for each non-system user — NOT CredentialLinks or ConnectionRecords
- Skip system users (uid < 1000) by default, but keep root and any with a valid login shell
- If a matching `HostUser` already exists for that (host, username), update shell/home_dir rather than creating a duplicate

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

---

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

---

## Planned File Structure

```
lockpick/
├── docker-compose.yml
├── Makefile
├── README.md
├── CONTRIBUTING.md
├── data/                        # All persistent state (gitignored, Docker volume)
│   ├── tracker.db
│   └── uploads/
│       └── {op_id}/
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── routers/
│   │   ├── operations.py
│   │   ├── hosts.py
│   │   ├── credentials.py
│   │   ├── connections.py
│   │   ├── upload.py            # Phase 6
│   │   └── graph.py             # Phase 5
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
│   │   ├── graph_builder.py     # Aggregate evidence into edge objects (Phase 5)
│   │   ├── ip_resolver.py       # Match IPs to existing hosts
│   │   ├── key_matcher.py       # Cross-reference key fingerprints across op
│   │   └── pivot_analysis.py    # BFS path finding (Phase 7)
│   └── alembic/
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx
│       ├── theme.ts
│       ├── pages/
│       │   ├── OpSelector.tsx
│       │   └── Workspace.tsx
│       ├── components/
│       │   ├── AddDataModal.tsx
│       │   ├── ManualEntryForm.tsx
│       │   ├── ConfirmDeleteModal.tsx
│       │   ├── DeleteOpModal.tsx
│       │   ├── EditModal.tsx
│       │   ├── EditHostForm.tsx
│       │   ├── EditCredentialForm.tsx
│       │   ├── EditCredentialLinkForm.tsx
│       │   ├── EditConnectionForm.tsx
│       │   ├── FileUploadTab.tsx        # Phase 6
│       │   ├── GraphCanvas.tsx          # Phase 5
│       │   ├── NodeContextMenu.tsx      # Phase 5
│       │   ├── EdgeContextMenu.tsx      # Phase 5
│       │   ├── HostDetailSidebar.tsx    # Phase 5
│       │   ├── EdgeDetailPanel.tsx      # Phase 5
│       │   ├── HostSelector.tsx         # Phase 5
│       │   ├── PathFinder.tsx           # Phase 7
│       │   └── PathDetail.tsx           # Phase 7
│       ├── api/
│       │   ├── client.ts
│       │   ├── operations.ts
│       │   ├── hosts.ts
│       │   ├── credentials.ts
│       │   ├── connections.ts
│       │   ├── graph.ts                 # Phase 5
│       │   └── upload.ts               # Phase 6
│       └── types/
│           └── index.ts
├── mcp/                                 # Phase 9
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── server.py
│   ├── api_client.py
│   ├── tools/
│   │   ├── operations.py
│   │   ├── hosts.py
│   │   ├── credentials.py
│   │   ├── connections.py
│   │   ├── pivot.py
│   │   └── search.py
│   ├── tests/
│   │   └── test_tools.py
│   └── README.md
├── tests/
│   ├── fixtures/
│   │   ├── sample_authorized_keys
│   │   ├── sample_known_hosts
│   │   ├── sample_auth.log
│   │   ├── sample_auth.log.gz
│   │   ├── sample_wtmp
│   │   ├── sample_bash_history
│   │   ├── sample_ssh_config
│   │   ├── sample_passwd
│   │   └── sample_keys/
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
└── .gitignore
```
