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

**Last completed phase: Phase 8 — Polish & UX (complete)**

Phases 1–8 are fully implemented and tested. Phase 9 (MCP server) is next.

**Next phase: Phase 9 — MCP Server**

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
- Once a phase is done, collapse its detail to 3–5 lines maximum. Keep only: what the phase added to the architecture and any invariants future phases must respect.
- Do NOT preserve a "What was built" component list — git history has that.
- The "Phases 1–5 — Complete" entry above is the model: one line, no detail.

**Planned File Structure:**
- Do NOT maintain a file tree in this document. The codebase is the source of truth.
- File trees drift with every phase and add pure noise. Omit entirely.

---

## Implementation Phases

### Phases 1–7 — Complete

All infrastructure, CRUD APIs, edit/delete UI, HostUser entity, schema hardening, graph visualization (cytoscape.js + BFS pivot analysis), file upload + parsing engine (8 parsers, IP resolver, pivot detection), and pivot path analysis are implemented and tested.

**Upload file invariants** (future phases must not break these):
- Files stored at `data/uploads/{op_id}/{uuid}_{filename}`
- `GET /api/ops/{op_id}/uploads` — lists files (disk scan + DB enrichment)
- `GET /api/ops/{op_id}/uploads/{safe_name}?download=true` — serves raw file
- Update/delete intentionally unsupported: parsed records have no per-file provenance marker; replacing a file creates duplicates

**Phase 7 invariants:** `classifyPath()` helper classifies paths as confirmed/observed/theoretical; active tab persists across refresh.

### Phase 8 — Complete

All polish features implemented: global search (`GET /ops/{op_id}/search?q=`), op export (`GET /ops/{op_id}/export`) and import (`POST /ops/import`, `create_new` mode with ID remapping), graph layout switcher (cola/cose-bilkent/breadthfirst/grid/circle), keyboard shortcuts (Ctrl+F search, Del hide node, Esc close modals), bulk file upload (multi-file queue, auto-detect, sequential processing), activity log (DB-backed, hooked into all write endpoints, `GET /ops/{op_id}/activity`), and notification banner (30s polling via `GET /ops/{op_id}/stats`).

**Phase 8 invariants:** `ActivityLog` table exists with composite index on `(op_id, created_at)`. `log_activity()` in `services/activity.py` must be called before `db.commit()` in write endpoints — it adds to the session, not commits independently. Export format is `lockpick_export_version: 1`.

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

---

## Architecture Rules

1. **Backend and frontend are separate directories**: `backend/` and `frontend/`
2. **The graph edge aggregation happens in the backend** (`services/graph_builder.py`), not the frontend. The frontend renders what the API gives it.
3. **The frontend never touches the DB** — all data flows through the REST API
4. **No authentication on the tool** — it runs on a trusted network / VPN. The red team trusts each other.
5. **All state in `./data/`** — DB file, uploaded raw files, nothing else. This directory is the only thing that needs to be backed up or moved.
6. **IP resolution is best-effort** — when a parser finds an IP, try to match it to an existing host. If no match, create an "unresolved" host with just that IP. The user can merge hosts later.

---
