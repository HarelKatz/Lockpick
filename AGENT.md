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

**Last completed phase: Phase 5 — Host Selection & Graph Visualization (+ post-phase review)**

Phases 1–5 are fully implemented and tested. A post-phase review added physics layout, visual improvements, path finding, and credential filtering.

**Pending before Phase 6: 6 bugs from the Phase 5 review — partially implemented, uncommitted**

Work is in progress in the working tree (not committed). Several files have been modified but the build is not yet clean. Do **not** skip the remaining items — they directly break UX.

**Next phase after fixes: Phase 6 — File Upload & Parsing Engine**

---

## Implementation Phases

### Phases 1–5 — Complete

See git history for details. All infrastructure, CRUD APIs, edit/delete UI, HostUser entity, schema hardening, and the graph visualization layer (backend aggregation service + cytoscape.js frontend) are implemented and tested.

### Phase 5 — Host Selection & Graph Visualization

#### What was built (all implemented)

**Backend:**
- `backend/routers/graph.py` — `GET /ops/{op_id}/graph?host_ids=...` and `GET /ops/{op_id}/hosts/{host_id}/expand?evidence_type=...`
- `backend/services/graph_builder.py` — aggregates CredentialLinks + ConnectionRecords into edge objects in two passes (key matches → `confirmed`, connection records → `observed`/`indicator`)
- `backend/services/pivot_analysis.py` — BFS/DFS path finder, max depth 8, max 30 paths, waypoint constraints (`anywhere` / `after [host]` / `before [host]`)
- `POST /ops/{op_id}/graph/paths` — path finder endpoint
- `EvidenceItem` schema includes: `credential_fingerprint`, `credential_name` (populated from credential table)

**Frontend:**
- `frontend/src/components/GraphCanvas.tsx` — cytoscape-cola physics layout (spring physics on drag), navy nodes with blue ring (amber for credentialed nodes), confidence-colored edges, fade in/out animations on node add/remove, path highlighting (coral) and dimming, credential filter effect
- `frontend/src/components/HostSelector.tsx` — searchable list, row dims to 45% opacity when unchecked
- `frontend/src/components/EdgeDetailPanel.tsx` — shows all evidence items including credential fingerprint/name
- `frontend/src/components/PathFinder.tsx` — src/dst host selectors, shortest/all-paths mode, optional waypoints with position constraints, results list with click-to-highlight
- `frontend/src/pages/GraphView.tsx` — orchestrates graph, credential filter toolbar, PathFinder panel, path/credential filter state
- `frontend/src/pages/GraphView.module.css` — toolbar above canvas, canvasWrapper column layout

**Right-click context menus (nodes and edges):**
- Node: Expand all / by key match / by connection log / by indicator; Hide node
- Edge: View evidence

**Hidden nodes** can be restored via the Refresh button in HostSelector.

---

### Phase 5 — Pending Fixes

**Work is partially in progress in the working tree (not committed). The build is not yet clean.**

#### Current working tree state

The following files have been modified but not committed (`git diff --stat HEAD`):

| File | What changed |
|------|-------------|
| `backend/schemas.py` | `connection_type: Optional[str] = None` added to `EvidenceItem` ✅ |
| `frontend/src/components/GraphCanvas.tsx` | Smart diff update (Fix 1) ✅ · `pathFilter`/`credFilter` props with hide/highlight/filter logic (Fixes 3 & 5 canvas) ✅ · new `computeEdgeLabel` reading `ev.connection_type` (Fix 4 label) ✅ · exports `CredFilter`/`PathFilter` interfaces ✅ |
| `frontend/src/pages/GraphView.tsx` | `pathFilter`/`credFilter` state ✅ · `allSelectableHosts` memo ✅ · `credLabel()` helper ✅ · toolbar with Highlight/Filter mode buttons ✅ · updated `<GraphCanvas>` props ✅ · **BUT**: still passes `graphData.nodes` to `<PathFinder>` instead of `allSelectableHosts` ❌ · uses `.modeBtn`/`.modeBtnActive` CSS classes that don't exist yet ❌ |

**The build currently fails** because:
1. `GraphView.tsx` references `styles.modeBtn` and `styles.modeBtnActive` which are not in `GraphView.module.css`
2. `PathFinder.tsx` still expects `nodes: GraphNode[]` but will receive `{ id; nickname }[]` once GraphView is fixed

---

#### Fix 1 — Double-click expand causes graph flash

**Status: ✅ Done** — `GraphCanvas.tsx` in working tree has the smart diff update.

Three-case logic in the `graphData`/`hiddenIds` useEffect:
- `goingAway.length > 0` → animate removed nodes out (200ms), then `fullRebuild()`
- `incoming.length > 0 && currentNodeIds.size > 0` → expand path: `cy.add(incoming)` only, fade new in, re-run layout
- `currentNodeIds.size === 0` → initial load, `fullRebuild()`

---

#### Fix 2 — PathFinder dropdowns empty when no hosts on graph

**Status: Partially done — 2 files still needed.**

`GraphView.tsx` already defines `allSelectableHosts` useMemo but still passes `graphData.nodes` to `<PathFinder>`. Two files need changes:

1. **`frontend/src/pages/GraphView.tsx`** (line ~325) — change the PathFinder prop:
   ```tsx
   // was:
   <PathFinder nodes={graphData.nodes} ...>
   // change to:
   <PathFinder nodes={allSelectableHosts} ...>
   ```

2. **`frontend/src/components/PathFinder.tsx`** — change the `nodes` prop type and update all `host_id` references to `id`:
   ```ts
   // was:
   interface Props { nodes: GraphNode[]; ... }
   // change to:
   interface Props { nodes: { id: string; nickname: string }[]; ... }
   ```
   Also update these three places in PathFinder.tsx that use `n.host_id`:
   - `getNickname`: `nodes.find(n => n.host_id === hostId)` → `nodes.find(n => n.id === hostId)`
   - From/To selects: `<option key={n.host_id} value={n.host_id}>` → `<option key={n.id} value={n.id}>`
   - Waypoint host select: same change
   - Relative-to select: `n.host_id !== wp.host_id` → `n.id !== wp.host_id` (note: `wp.host_id` is the waypoint field name, leave that unchanged)
   - Remove `GraphNode` from the PathFinder.tsx imports if it's no longer referenced

---

#### Fix 3 — Path result should hide unrelated nodes/edges

**Status: ✅ Done** — `GraphCanvas.tsx` in working tree uses `display: none` for non-path elements.

When `pathFilter` is set: path nodes/edges get `path-highlight` class; all others get `style('display', 'none')`. Cleared by `style('display', 'element')` reset when `pathFilter` becomes null.

---

#### Fix 4 — Edge labels show `key • 2` instead of connection type

**Status: Partially done — 2 files still needed.**

`GraphCanvas.tsx` already has the new `computeEdgeLabel` that reads `ev.connection_type`. `backend/schemas.py` already has `connection_type: Optional[str] = None` on `EvidenceItem`. Still needed:

1. **`backend/services/graph_builder.py`** — Pass 2, inside the `EvidenceItem(...)` constructor (around line 189), add:
   ```python
   connection_type=record.connection_type,
   ```
   Place it after `credential_name=conn_cred_obj.name if conn_cred_obj else None,`.

2. **`frontend/src/types/index.ts`** — add to `EvidenceItem` interface (after `credential_name`):
   ```ts
   connection_type: string | null
   ```

---

#### Fix 5 — Credential filter: meaningless names + single broken mode

**Status: Partially done — 1 CSS file still needed.**

`GraphCanvas.tsx` handles both modes. `GraphView.tsx` has the `credFilter` state, `credLabel()` helper, updated toolbar UI with Highlight/Filter toggle buttons, and passes `credFilter` to `<GraphCanvas>`. Still needed:

**`frontend/src/pages/GraphView.module.css`** — add mode button styles (toolbar uses `styles.modeBtn` and `styles.modeBtnActive`):
```css
.modeBtn {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-muted);
  cursor: pointer;
  font-size: var(--font-size-xs);
  padding: 3px 10px;
  transition: color 0.1s, background 0.1s;
}

.modeBtnActive {
  background: var(--bg-surface-2);
  border-color: var(--accent);
  color: var(--text-primary);
}
```

---

#### Fix 6 — FAB button overlaps edit/delete buttons at small window sizes

**Status: Not started — one CSS change.**

**`frontend/src/pages/Workspace.module.css`** — `.main` class (line 107):
```css
.main {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  padding-bottom: 80px;  /* stop FAB overlapping last row's buttons */
}
```

---

### Remaining steps to finish all fixes

Execute in order — everything builds on the previous step:

1. **`frontend/src/pages/GraphView.tsx`** — change `<PathFinder nodes={graphData.nodes}` to `<PathFinder nodes={allSelectableHosts}` (Fix 2 part 1)
2. **`frontend/src/components/PathFinder.tsx`** — change `nodes: GraphNode[]` to `{ id: string; nickname: string }[]`; update `n.host_id` → `n.id` in all `<option>` and `getNickname` (Fix 2 part 2)
3. **`frontend/src/pages/GraphView.module.css`** — add `.modeBtn` and `.modeBtnActive` (Fix 5 CSS)
4. **`backend/services/graph_builder.py`** — add `connection_type=record.connection_type` in Pass 2 EvidenceItem (Fix 4 backend)
5. **`frontend/src/types/index.ts`** — add `connection_type: string | null` to `EvidenceItem` (Fix 4 types)
6. **`frontend/src/pages/Workspace.module.css`** — add `padding-bottom: 80px` to `.main` (Fix 6)
7. **`make test && cd frontend && npm run build`** — must be clean
8. **Commit:** `fix(frontend+backend): resolve Phase 5 review bugs`

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
