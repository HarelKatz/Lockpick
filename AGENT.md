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

Phases 1–5 are fully implemented and tested. A post-phase review added physics layout, visual improvements, path finding, and credential filtering. See git history for details.

**Pending before Phase 6: 6 confirmed bugs from the Phase 5 review (see section below)**

All 6 bugs are still unimplemented in `HEAD`. `git stash` contains partial work. Do **not** skip these — several directly break the UX.

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

**All 6 bugs are unimplemented in HEAD. Fix all of them before starting Phase 6.**

#### What is in `git stash` (stash@{0})

Two files are stashed. Pop with `git stash pop` when ready:

| File | What it contains |
|------|-----------------|
| `backend/schemas.py` | `connection_type: Optional[str] = None` added to `EvidenceItem` |
| `frontend/src/components/GraphCanvas.tsx` | Smart diff update (Fix 1) + `pathFilter`/`credFilter` props replacing old `highlightedPath`/`credentialFilterId` (Fixes 3 & 5 canvas logic) + new `computeEdgeLabel` that reads `ev.connection_type` (Fix 4 label logic) |

**Critical:** After `git stash pop`, the TypeScript build will immediately break because `GraphView.tsx` still passes the old props (`highlightedPath`, `credentialFilterId`) but the canvas now expects `pathFilter`, `credFilter`. Fix 3 and Fix 5 wiring in `GraphView.tsx` must be done in the same sitting as the stash pop.

---

#### Fix 1 — Double-click expand causes graph flash

**Status:** Fully in stash — no other files needed.

**Problem:** Double-clicking a node to expand triggers a full canvas teardown + rebuild, causing a visible flash even though only new nodes are being added.

**Root cause:** The `graphData` useEffect always clears all elements and rebuilds from scratch (`cy.elements().remove()` then re-add all) regardless of whether it's a full reload or an incremental expand.

**Fix (stash has this in `GraphCanvas.tsx`):** Smart diff update — three cases:
- `goingAway.length > 0` → animate removed nodes out (200ms opacity), then `fullRebuild()`
- `incoming.length > 0 && currentNodeIds.size > 0` → **expand path**: `cy.add(incoming)` only, fade new nodes in, re-run layout without clearing existing canvas
- `currentNodeIds.size === 0` → initial load, `fullRebuild()`

`fullRebuild()` still clears and rebuilds, used only for initial load and for when nodes are removed.

---

#### Fix 2 — PathFinder dropdowns empty when no hosts on graph

**Status:** Not started — no stash content.

**Problem:** `PathFinder` receives `nodes: GraphNode[]` from `graphData.nodes`. When the graph canvas is empty (all hosts unchecked), the dropdowns are empty and the user cannot search for a path.

**Fix — 3 changes:**

1. **`frontend/src/pages/GraphView.tsx`** — compute a merged host list:
   ```ts
   const allSelectableHosts = useMemo(() => {
     const map = new Map<string, { id: string; nickname: string }>()
     for (const h of allHosts) map.set(h.id, { id: h.id, nickname: h.nickname })
     for (const n of graphData.nodes) map.set(n.host_id, { id: n.host_id, nickname: n.nickname })
     return Array.from(map.values())
   }, [allHosts, graphData.nodes])
   ```
   Pass `allSelectableHosts` to `<PathFinder nodes={allSelectableHosts} ...>` instead of `graphData.nodes`.

2. **`frontend/src/components/PathFinder.tsx`** — change the `nodes` prop type:
   ```ts
   // was: nodes: GraphNode[]
   nodes: { id: string; nickname: string }[]
   ```
   Update `getNickname` and all `<select>` mappings to use `h.id` / `h.nickname` directly (they already do this, just change the prop type annotation and remove the `host_id` references).

---

#### Fix 3 — Path result should hide unrelated nodes/edges

**Status:** Canvas logic in stash; `GraphView.tsx` wiring not started.

**Problem:** Selecting a path in PathFinder dims non-path nodes to 18% opacity but they remain visible. The user wants only the path nodes and edges shown.

**Fix — canvas side (stash has this):** The stashed `GraphCanvas.tsx` uses `cy.style('display', 'none')` instead of the `.dimmed` class for path filtering:
- Path nodes → `path-highlight` class
- Non-path nodes → `n.style('display', 'none')`
- Path edges → `path-highlight` class
- Non-path edges → `e.style('display', 'none')`
- When path is cleared → `cy.nodes().style('display', 'element')` + `cy.edges().style('display', 'element')` reset

**Fix — `GraphView.tsx` wiring (not started):** The stash changes `GraphCanvas` props:

Old (current HEAD):
```ts
highlightedPath: { nodeIds: string[]; edgeKeys: string[] } | null
credentialFilterId: string | null
```
New (in stash):
```ts
pathFilter: PathFilter | null   // exported from GraphCanvas.tsx; = { nodeIds: Set<string>; edgeKeys: Set<string> }
credFilter: CredFilter | null   // exported from GraphCanvas.tsx; = { credId: string; mode: 'highlight' | 'filter' }
```

In `GraphView.tsx`:
- Rename state `highlightedPath` → `pathFilter`, change type to `PathFilter | null`
- Build `pathFilter` as `{ nodeIds: new Set(path.host_ids), edgeKeys: new Set(path.edges.map(e => \`${e.src_host_id}__${e.dst_host_id}\`)) }` (was built as `computedHighlight` with arrays, now use Sets)
- Pass `pathFilter={pathFilter}` to `<GraphCanvas>` (was `highlightedPath={computedHighlight}`)
- Remove `computedHighlight` intermediate variable

---

#### Fix 4 — Edge labels show `key • 2` instead of connection type

**Status:** Label logic in stash (`GraphCanvas.tsx`); backend field and TS type not started.

**Problem:** Edge labels show `key • 2` (evidence type abbreviation + count) which is meaningless. The user wants the actual connection type: "SSH", "SCP", "key match", etc.

**Fix — edge label logic (stash has this in `GraphCanvas.tsx`):**
```ts
function computeEdgeLabel(e: GraphEdge): string {
  for (const ev of e.evidence) {
    if (ev.type === 'connection_log' && ev.connection_type) {
      return ev.connection_type.toUpperCase()   // "SSH", "SCP", "RSYNC", etc.
    }
  }
  if (e.evidence.some(ev => ev.type === 'key_match')) return 'key match'
  if (e.evidence.some(ev => ev.type === 'bash_history')) return 'bash history'
  if (e.evidence.some(ev => ev.type === 'known_hosts')) return 'known hosts'
  return 'connection'
}
```

**Fix — `connection_type` field on `EvidenceItem` (stash has schema change; 2 files still needed):**

The stash adds `connection_type: Optional[str] = None` to `EvidenceItem` in `backend/schemas.py`. Two files still need updating:

1. **`backend/services/graph_builder.py`** — in Pass 2 (connection records, around line 179), add the field to the `EvidenceItem(...)` constructor:
   ```python
   EvidenceItem(
       type=ev_type,
       detail=...,
       connection_type=record.connection_type,   # ← ADD THIS
       credential_id=record.credential_id,
       ...
   )
   ```

2. **`frontend/src/types/index.ts`** — add to `EvidenceItem` interface:
   ```ts
   connection_type: string | null   // ← ADD after credential_name
   ```

---

#### Fix 5 — Credential filter: meaningless names + single broken mode

**Status:** Canvas logic in stash; `GraphView.tsx` toolbar/state not started.

**Problem:**
- The dropdown shows truncated fingerprints or `null` — not useful.
- There is only one mode that half-works (dims non-matching edges but doesn't hide them).
- The user wants two explicit modes: **Highlight** (keep all visible, highlight matching) and **Filter** (hide non-matching entirely).

**Fix — credential display name (not started, goes in `GraphView.tsx`):**
```ts
function credLabel(c: Credential): string {
  const type = c.key_type
    ? c.key_type.replace('ssh-', '').toUpperCase()   // "ED25519", "RSA"
    : c.cred_type.replace('_', ' ')                  // "private key", "password"
  const label = c.name
    || c.comment
    || (c.fingerprint ? c.fingerprint.slice(7, 23) + '…' : c.id.slice(0, 8))
  return `${type}: ${label}`  // "ED25519: root@web01"  or  "RSA: SHA256:abc123…"
}
```

**Fix — two-mode state (not started, goes in `GraphView.tsx`):**

Replace `credentialFilterId: string | null` state with:
```ts
const [credFilter, setCredFilter] = useState<{ credId: string; mode: 'highlight' | 'filter' } | null>(null)
```

Default mode when a credential is first selected: `'highlight'`.

**Fix — toolbar UI update (not started, `GraphView.tsx` + `GraphView.module.css`):**
- `<select>` with `credLabel(c)` — replaces the current truncated-fingerprint display
- When a credential is selected, render two mode buttons inline: **Highlight** / **Filter** (toggle active with `.modeBtnActive` class from `PathFinder.module.css` as reference)
- **Clear** button to reset
- Pass `credFilter={credFilter}` to `<GraphCanvas>` (was `credentialFilterId={credentialFilterId}`)

**Fix — canvas side (stash has this):** The stashed `GraphCanvas.tsx` already handles both modes via the `credFilter` prop:
- **Highlight mode:** edges matching credential → `path-highlight`; their endpoint nodes → `path-highlight`; everything else → `.dimmed`
- **Filter mode:** edges not matching → `display: none`; nodes with no visible edges → `display: none`; matching edges → `path-highlight`

---

#### Fix 6 — FAB button overlaps edit/delete buttons at small window sizes

**Status:** Not started — one CSS line.

**Problem:** The floating `+` button in the data tab is `position: fixed; bottom: 32px; right: 32px`. When the window is not fullscreen, it covers the Edit/Delete buttons on the last few rows of the list.

**Fix:**
```css
/* frontend/src/pages/Workspace.module.css — .main class (~line 107) */
.main {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  padding-bottom: 80px;  /* stop FAB overlapping last row's buttons */
}
```

---

### Implementation order for pending fixes

Do these in a single session — the stash pop breaks the build until GraphView.tsx is updated.

1. **`git stash pop`** — applies `GraphCanvas.tsx` (smart diff, new props) + `schemas.py` (connection_type)
2. **Immediately fix `GraphView.tsx`** — rename `highlightedPath` → `pathFilter` (Set-based), pass `pathFilter`/`credFilter` to `<GraphCanvas>` instead of old props; replace `credentialFilterId` state with `credFilter`; add `credLabel()` helper; add mode toggle buttons to toolbar (Fixes 3 + 5 wiring)
3. **`frontend/src/components/PathFinder.tsx`** — change `nodes` prop type to `{ id: string; nickname: string }[]` (Fix 2 part 1)
4. **`frontend/src/pages/GraphView.tsx`** — add `allSelectableHosts` memo, pass it to `<PathFinder>` (Fix 2 part 2; same file as step 2, can be done together)
5. **`backend/services/graph_builder.py`** — add `connection_type=record.connection_type` to EvidenceItem in Pass 2 (Fix 4 backend)
6. **`frontend/src/types/index.ts`** — add `connection_type: string | null` to `EvidenceItem` (Fix 4 types)
7. **`frontend/src/pages/Workspace.module.css`** — add `padding-bottom: 80px` to `.main` (Fix 6)
8. **`make test && cd frontend && npm run build`** — must be clean before committing
9. **Commit:** `fix(frontend+backend): resolve Phase 5 review bugs`

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
