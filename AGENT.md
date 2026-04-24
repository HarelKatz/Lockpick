# Lockpick — Red Team Operation Manager

## Project Overview

A web-based tool for red teams to collaboratively organize SSH credentials, host relationships, and pivot paths during operations. Runs as a shared server — the entire team accesses it, and any data one person adds is visible to everyone on their next query. The core value is **visualizing lateral movement opportunities** by correlating SSH keys, connection logs, and host data across an engagement.

**Portability:** This tool may run on a VPS for a week, get zipped up, moved to another box, and resumed. All state lives in `./data/` — the only thing to back up or move. No external dependencies.

> For tech stack, dev commands, repo layout, migration rules, frontend conventions, and git format — see **CLAUDE.md**.

---

## Current Status

> **Edit rules:** ≤5 lines. Last completed · Next · Any blocker. Nothing else — detail belongs in commit messages.

**Last completed: Phases 1–13 — full stack, 14 parsers, WS live push, host notes, status enum, addr_type, SudoRule**

**Next: Phase 14 — Engagement Report Export**

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
14. **SSH config patterns** — `Host` blocks with wildcard/token aliases (`jb.*`, `*.example.com`, `%h`) are stored as `SshConfigPattern` records (table: `ssh_config_patterns`), never as hosts. The `services/ssh_pattern.py` `ssh_match()` function implements SSH glob semantics (`fnmatch` + `!` negation, case-insensitive). Pattern-to-host edges are created at upload time (existing hosts) and retroactively when a new host/IP is added.
15. **Loopback routing** — `127.x.x.x`, `::1`, and `localhost` in connection records always resolve to the upload host, never create new host records. Handled in `_resolve_ip_side()` (`routers/upload.py`).
16. **HostIP addr_type** — `HostIP.ip_address` holds either a numeric IP or FQDN; `addr_type` (ipv4|ipv6|hostname) disambiguates. IP resolver infers addr_type via `_infer_addr_type()` and sets it on new records. Hostname lookups are case-insensitive.
17. **SudoRule** — read-only from the upload pipeline; no manual create endpoint. `SudoRule.op_id` stored for bulk queries. Sudo rules do not affect BFS pivot path confidence — informational context only.
18. **WS live push** — `broadcast_sync(op_id, event)` (`ws_manager.py`) must be called after `db.commit()` in every write endpoint. Event shape: `{"type": "update", "entity_type": "<host|credential|connection|...>", "op_id": op_id}`. It is fire-and-forget and safe to call even when no clients are connected.
19. **Host lazy-load gate** — `Host.ips`, `Host.users`, `Host.credential_links`, `Host.notes` use `lazy="raise_on_sql"`. Any query that loads hosts for serialization or bulk iteration must `selectinload` the relationships it touches. `_host_q(db)` in `routers/hosts.py` covers the `HostRead` path; `services/graph_builder.py` applies its own options for the graph path.

---

## Document Maintenance Rules

AGENT.md is the project roadmap and architecture reference — the current source of truth. Git history is the audit log.

**After completing a phase:**
1. Update Current Status (phase range + one-line summary of what was built)
2. Collapse the phase entry to one sentence and merge it into the "Phases X–Y — Complete" block
3. Move any constraints future phases must respect into **Architecture Rules** — never leave invariants inside a phase entry

**What does NOT belong here:**
- Line numbers, CSS snippets, diff hunks, file trees, or "what's in the working tree"
- Per-fix status markers or implementation retrospectives
- Feature lists for completed phases — git history has that
- Anything that will be wrong the moment the next commit lands

---

## Implementation Phases

> Detail tracks imminence: the next phase gets a full spec, 1–2 phases out get a short summary + invariants, and anything further is a one-liner heading. Expand a phase when it becomes next.

### Phases 1–13 — Complete

Full stack built and tested: CRUD APIs, graph visualization, file upload + 14 parsers (8 original + nmap_xml, shadow, sshd_config, etc_hosts, sudoers, public_key alias), BFS pivot analysis, global search, export/import, activity log, operational command generation, WS live push, host notes, Host.status enum, HostIP addr_type, SudoRule table with sudoers CRUD.

---

### Phase 14 — Engagement Report Export

New endpoint: `GET /ops/{op_id}/report?format=markdown|html`
- Renders a structured engagement summary using existing export logic: op metadata, host inventory table (nickname, IPs/hostnames, status tag, credential count), credential inventory, pivot paths (calls `find_paths`), sudo escalation summary per host, activity timeline
- Markdown is primary format; HTML wraps markdown output in a minimal printable template — no external PDF library
- Frontend: "Export Report" button in op header with format picker

**Invariants:** Report is read-only. Password hashes and private key material are redacted to first 8 chars + `...`. Fingerprints shown in full (not sensitive).

---

### Phase 15 — Graph Path Highlight + Time Slider

Shift+click a second node dims everything not on any BFS path between the two selected hosts (uses existing `POST /ops/{op_id}/graph/paths`). Time slider at the bottom of GraphView filters edges by `ConnectionRecord.timestamp` when any op has timestamped connections; key-match edges always shown.

**Invariants:** Pure frontend filter state — no DB writes, no API changes. Path highlight and time slider can be active simultaneously.

---

### Phase 17 — System File Parsers

Static files from disk — RHEL/CentOS log aliases (`secure`/`syslog`/`messages` → `AuthLogParser`), binary login records (`lastlog`, `last`), shell histories and configs (`zsh_history`, `fish_history`, `bashrc`, `zshrc`), and network configs (`/etc/network/interfaces`, netplan, ifcfg). No schema changes. Network config parsers emit only the upload host's own IPs and gateways — no connection records.

---

### Phase 18 — Command Output Parsers

Output captured from commands run on the target — network state (`ip addr`, `ip route`, `ip neigh`, `arp`), active connections (`netstat`, `ss`), firewall rules (`iptables`, `nftables`), process/env state (`ps aux`, `env`), and container state (`docker ps`, `docker network`, `kubectl get pods`). No schema changes. Parsers emitting only `HostData`/`CredentialData` surface in the host detail panel only; firewall and tunnel parsers emit indicator-confidence edges at best.

---

### Phase 19 — Secret & Credential File Parsers

Files storing non-SSH credentials — `netrc`, `pgpass`, `~/.my.cnf`, cloud credentials (AWS / GCP ADC / kubeconfig / boto), `.env`, `~/.docker/config.json`, `~/.git-credentials`, and rclone. No schema changes — non-key secrets use `cred_type: password` with a descriptive `name`. Export redaction (Phase 14) applies to all secret values.

---

### Phase 20 — Collection Script + Bulk Archive Import

`GET /ops/{op_id}/collection-script` returns a bash script that snapshots parseable files and command outputs on a compromised host into `lockpick_<hostname>_<ts>.tar.gz`, using filename convention `<file_type>__<username>.<ext>` plus a `manifest.json`. `POST /ops/{op_id}/hosts/{host_id}/import-archive` accepts that tarball and dispatches each file through the normal upload pipeline. No schema changes.

---

### Phase 16 — MCP Server

Standalone `mcp/` package (does **not** import from `backend/`) exposing op data over MCP/stdio so an AI agent like Claude Desktop can help navigate pivots. Talks to the Lockpick REST API over HTTP; configurable via `LOCKPICK_URL`. Last phase — implement only when all others are stable.

---

## Data Model

> `backend/models.py` is authoritative for exact fields and types. This section documents *relationships* and *pivot semantics* — the "why" that isn't in the ORM. Read on demand; update only when relationship semantics change.

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
