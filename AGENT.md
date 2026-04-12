# Lockpick — Red Team Operation Manager

## Project Overview

A web-based tool for red teams to collaboratively organize SSH credentials, host relationships, and pivot paths during operations. Runs as a shared server — the entire team accesses it, and any data one person adds is visible to everyone on their next query. The core value is **visualizing lateral movement opportunities** by correlating SSH keys, connection logs, and host data across an engagement.

**Portability:** This tool may run on a VPS for a week, get zipped up, moved to another box, and resumed. All state lives in `./data/` — the only thing to back up or move. No external dependencies.

> For tech stack, dev commands, repo layout, migration rules, frontend conventions, and git format — see **CLAUDE.md**.

---

## Data Model

### Core Entities

> Storage convention: all IDs are UUIDs stored as strings; all timestamps are timezone-aware UTC (ISO 8601).

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

**Last completed: Phase 12 — Parser Suite (nmap XML, /etc/shadow, /etc/ssh/sshd_config)**

Three new parsers added (`nmap_xml`, `shadow`, `sshd_config`), registered in registry, with fixture files and full unit test coverage (26 new tests). Phases 10 and 11 remain unimplemented.

**Next phase: Phase 10 — WebSocket Live Push + Per-Host Notes**

---

## Document Maintenance Rules

AGENT.md is both architecture documentation and the project roadmap.

**Current Status** — 3–5 lines maximum: last completed phase, next phase, any hard blockers. Nothing else.

**After completing a phase:**
1. Update Current Status to the new phase
2. Delete any "Pending Fixes" subsection for the completed phase
3. If the phase built something a future phase also describes, update the future phase to note what already exists

**What does NOT belong here:**
- Line numbers, CSS snippets, diff hunks, or "what's in the working tree"
- Per-fix `Status: ✅/❌` prose or implementation retrospectives
- Anything that will be wrong the moment the next commit lands

Those things belong in commit messages and GitHub issues.

**Completed phases:**
- Once a phase is done, collapse its entry to ONE sentence describing what was added — no feature lists, no invariants.
- Any constraint future phases must respect goes into **Architecture Rules** — never inline in a phase entry. Phase entries are temporary scaffolding; Architecture Rules are permanent.
- Merge consecutive completed phases into a single "Phases X–Y — Complete" block.
- Do NOT preserve a "What was built" component list — git history has that.
- The "Phases 1–9 — Complete" entry below is the model: one line, nothing else.

**Planned File Structure:**
- Do NOT maintain a file tree in this document. The codebase is the source of truth.
- File trees drift with every phase and add pure noise. Omit entirely.

---

## Implementation Phases

### Phases 1–9 — Complete

Full stack built and tested: CRUD APIs, graph visualization, file upload + 8 parsers, BFS pivot analysis, global search, export/import, activity log, and operational command generation.

---

### Phase 10 — WebSocket Live Push + Per-Host Notes

**WebSocket:**
- `GET /ops/{op_id}/ws` — WebSocket endpoint (FastAPI native `WebSocket` parameter)
- Server broadcasts a lightweight JSON event `{type, entity_type, entity_id, op_id}` after every successful DB write (post-commit in routers)
- Frontend replaces 30s stats polling with WS listener; on event, refetches only the affected entity type
- Graceful fallback: if WS disconnects, fall back to 30s polling

**Per-Host Notes:**
- New table `HostNote`: `id`, `op_id` (FK), `host_id` (FK), `content` (text), `created_at`
- New endpoints: `POST /hosts/{host_id}/notes`, `GET /hosts/{host_id}/notes`, `DELETE /hosts/{host_id}/notes/{note_id}`
- Host detail panel gains a "Notes" tab (timestamped, multi-entry, deletable)
- `log_activity()` on create/delete

**Invariants:** WS events are fire-and-forget — no guaranteed delivery, no replay. `Host.comment` is retained (single-line label; notes are the multi-entry scratchpad). Alembic migration required for `HostNote`.

---

### Phase 11 — Host Status Tags

Add a `status` enum column to `Host` (nullable, so existing hosts are unaffected):
- Values: `entry_point | compromised | pivot | target | scoped_out | unreachable`
- Alembic migration required (batch_alter_table)
- Extend `HostUpdate` schema and `PATCH /hosts/{host_id}` to accept `status`
- `GraphNode` schema gains `status` field (nullable string)
- Graph nodes reflect status via color/badge; graph filter panel can filter by status
- Host detail panel shows a status picker

**Invariants:** `Host.status` is nullable (null = unclassified). Graph node color falls back to confidence-based color when status is null.

---

### Phase 12 — Complete

Added three parsers (`nmap_xml`, `shadow`, `sshd_config`) with fixture files and unit tests; no schema changes required.

---

### Phase 13 — Domain/Hostname Support + /etc/hosts + /etc/sudoers

**Domain/Hostname Support:**
- Add `addr_type` enum column (`ipv4 | ipv6 | hostname`) to `HostIP`; default `ipv4` for existing rows. The `ip_address` field holds either a numeric IP or an FQDN depending on type.
- Alembic migration required (batch_alter_table)
- IP resolver (`services/ip_resolver.py`) extended to match on FQDNs/hostnames in addition to numeric IPs
- Frontend: host address list displays type badge (IPv4 / IPv6 / hostname) next to each entry

**`/etc/hosts` parser** (`file_type: etc_hosts`): Parses `<ip> <hostname> [aliases...]` lines (skips comments, loopback). Creates a `HostIP` record for the IP (addr_type: `ipv4`/`ipv6`) and one per hostname (addr_type: `hostname`), all linked to the same resolved or new host. If a host already has the IP, hostnames are added; otherwise a new host is created.

**`/etc/sudoers` + `sudoers.d/*` parser** (`file_type: sudoers`):
- New table `SudoRule`: `id`, `host_id` (FK), `op_id` (FK), `subject` (string), `subject_type` (enum: `user | group`), `run_as` (string, default `root`), `commands` (text), `nopasswd` (bool), `raw_line` (nullable), `created_at`
- Alembic migration required
- New endpoints: `GET /hosts/{host_id}/sudo-rules`, `DELETE /hosts/{host_id}/sudo-rules/{rule_id}` — no manual create (sudo rules come from parsed files only)
- Parser handles `%group` prefix (subject_type: group), `NOPASSWD:` tag, `ALL=(ALL:ALL)` patterns
- Host detail panel gains a "Sudo Rules" tab
- `sudoers.d/*` files use the same parser — each file uploaded individually with `file_type: sudoers`

**Invariants:** `SudoRule` records are host-scoped; `op_id` stored for bulk queries. Sudo rules do not affect BFS pivot path confidence — informational context only.

---

### Phase 14 — Engagement Report Export

New endpoint: `GET /ops/{op_id}/report?format=markdown|html`
- Renders a structured engagement summary using existing export logic: op metadata, host inventory table (nickname, IPs/hostnames, status tag, credential count), credential inventory, pivot paths (calls `find_paths`), sudo escalation summary per host, activity timeline
- Markdown is primary format; HTML wraps markdown output in a minimal printable template — no external PDF library
- Frontend: "Export Report" button in op header with format picker

**Invariants:** Report is read-only. Password hashes and private key material are redacted to first 8 chars + `...`. Fingerprints shown in full (not sensitive).

---

### Phase 15 — Graph Path Highlight + Time Slider

**Path Highlight Mode:** Shift+click a second node → graph dims all nodes/edges not on any BFS path between the two selected hosts. Calls existing `POST /ops/{op_id}/graph/paths`. Highlighted path edges shown in accent color with increased stroke width. Esc clears selection.

**Time Slider:** Appears at the bottom of GraphView when at least one `ConnectionRecord` in the op has a non-null timestamp. Range: min → max timestamp. Dragging filters edges: only show ConnectionRecords with `timestamp ≤ slider_value`. Key-match edges (no timestamp) always shown. Slider state is local — no DB writes, no API calls.

**Invariants:** Path highlight and time slider are independent features that can be active simultaneously. Neither modifies graph data — both are pure frontend filter/render state.

---

### Phase 16 — MCP Server

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

---

## Architecture Rules

1. **Backend and frontend are separate directories**: `backend/` and `frontend/`
2. **The graph edge aggregation happens in the backend** (`services/graph_builder.py`), not the frontend. The frontend renders what the API gives it.
3. **The frontend never touches the DB** — all data flows through the REST API
4. **No authentication on the tool** — it runs on a trusted network / VPN. The red team trusts each other.
5. **All state in `./data/`** — DB file, uploaded raw files, nothing else. This directory is the only thing that needs to be backed up or moved.
6. **IP resolution is best-effort** — when a parser finds an IP, try to match it to an existing host. If no match, create an "unresolved" host with just that IP. The user can merge hosts later.
7. **Activity log** — `log_activity()` (`services/activity.py`) must be called before `db.commit()` in every write endpoint. It adds to the current session and does not commit independently.
8. **Export format** — op exports use `lockpick_export_version: 1`. Import remaps all IDs — never re-use original IDs from an export.
9. **File uploads** — raw files stored at `data/uploads/{op_id}/{uuid}_{filename}`. Update/delete is intentionally unsupported: parsed records carry no per-file provenance marker, so replacing a file would create duplicates.
10. **Graph library** — frontend graph uses `react-force-graph-2d` (ForceGraph2D) + d3-force. Never reintroduce cytoscape.js or React Flow.
11. **Graph state ownership** — `GraphCanvas` owns all d3/simulation state; `GraphView` owns all selection/filter state. Keep these separate.
12. **Graph click timing** — node single-click is delayed 250 ms to let double-click (lock/unlock) preempt it. Do not remove or shorten this delay.
13. **Graph detail panel** — right detail panel uses `push` mode (shrinks canvas) when the clicked node falls in the rightmost 320 px of the canvas; `overlay` (absolute, canvas unchanged) otherwise. Mode is evaluated once on open and held through the close transition.

---
