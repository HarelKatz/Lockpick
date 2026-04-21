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

**Last completed: Phase 11 — Host Status Tags**

`Host.status` nullable enum column added (entry_point, compromised, pivot, target, scoped_out, unreachable). `PATCH /hosts/{host_id}` accepts status (Pydantic Literal validation, 422 on invalid). `GraphNode` now includes `status`. Graph nodes use status color for border; status filter pills in graph toolbar dim non-matching nodes. HostDetailSidebar Info tab has a status picker dropdown with color dot indicator.

**Next: Phase 10 — WebSocket Live Push + Per-Host Notes**

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

Full stack built and tested: CRUD APIs, graph visualization, file upload + 8 parsers, BFS pivot analysis, global search, export/import, activity log, and operational command generation. (Parser count is now 11 — see Phase 12.)

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

### Phases 11–13 — Complete

Phase 11: Added `Host.status` nullable enum; graph node colors and filter pills for status; HostDetailSidebar status picker. Phase 12: Added `nmap_xml`, `shadow`, `sshd_config` parsers. Phase 13: Added `addr_type` to `HostIP`, `SudoRule` table, `etc_hosts` and `sudoers` parsers, sudo rules CRUD endpoints, addr_type badges on IPs, and Sudo Rules tab in HostDetailSidebar.

---

### Phases 12–13 — Complete

Phase 12: Added `nmap_xml`, `shadow`, `sshd_config` parsers. Phase 13: Added `addr_type` to `HostIP`, `SudoRule` table, `etc_hosts` and `sudoers` parsers, sudo rules CRUD endpoints, addr_type badges on IPs, and Sudo Rules tab in HostDetailSidebar.

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

### Phase 17 — System File Parsers

Static files found on disk. No schema changes.

**Log file aliases** (zero new code — one registry line each):

| `file_type` | Source | Parser |
|---|---|---|
| `secure` | `/var/log/secure` | `AuthLogParser` alias — RHEL/CentOS auth.log equivalent |
| `syslog` | `/var/log/syslog` | `AuthLogParser` alias — already filters for `sshd` lines |
| `messages` | `/var/log/messages` | `AuthLogParser` alias — RHEL syslog equivalent |

**Binary login records:**
- `lastlog` (`/var/log/lastlog`) — binary struct, UID-indexed fixed records (4-byte tv_sec + 32-byte tty + 256-byte src_host); emit `ConnectionData` (last login per user + source IP) + `host_users_found`; emit raw UID as username fallback when passwd unavailable

**Text login records:**
- `last_output` (`last` command output) — whitespace-delimited: username, tty, src_host, date range; emit `ConnectionData` per login session

**Shell history:**
- `zsh_history` (`~/.zsh_history`) — `BashHistoryParser` with EXTENDED_HISTORY prefix stripping (`: <ts>:<elapsed>;<cmd>`)
- `fish_history` (`~/.local/share/fish/fish_history`) — YAML-like: extract `cmd:` values, apply SSH regex; `when:` used as timestamp

**Shell config files:**
- `bashrc` (`~/.bashrc`, `~/.bash_profile`, `~/.profile`) — strip `alias name='...'` wrappers and `function name() {...}` bodies; apply BashHistoryParser SSH regex; `ssh-add <path>` emitted as warning
- `zshrc` (`~/.zshrc`, `~/.zprofile`) — alias to `BashrcParser`

**Network configuration files:**
- `network_interfaces` (`/etc/network/interfaces`) — `address`/`iface` stanzas → `HostData` (upload host IPs); `gateway` → `HostData`
- `netplan` (`/etc/netplan/*.yaml`) — YAML: `addresses:` → `HostData`; `gateway4`/`routes` → `HostData`
- `ifcfg` (`/etc/sysconfig/network-scripts/ifcfg-*`) — `IPADDR=`, `GATEWAY=` → `HostData` — RHEL/CentOS equivalent

**Invariants:** `secure`/`syslog`/`messages` are pure registry aliases. `network_interfaces`/`netplan`/`ifcfg` emit `HostData` only (host's own IPs + gateways, no connection records).

---

### Phase 18 — Command Output Parsers

Output captured from executing commands on the target. No schema changes.

**Network interface & routing:**
- `ip_addr` (`ip addr show` / `ifconfig -a`) — interface IPs → `HostData` (upload host's own IPs)
- `ip_route` (`ip route show` / `route -n`) — `default via` + non-local routes → `HostData` per gateway (RFC1918 only)
- `ip_neigh` (`ip neigh show`) — neighbor IPs + state (REACHABLE/STALE) → `HostData`
- `arp` (`arp -a`) — `hostname (ip)` pairs → `HostData`

**Active connections & listening ports:**
- `netstat` (`netstat -an`) — ESTABLISHED rows → `ConnectionData`; remote IPs → `HostData`
- `ss_output` (`ss -anp`) — ESTAB rows → `ConnectionData`; LISTEN rows → stats only

**Firewall rules:**
- `iptables` (`iptables -L -n -v` / `iptables-legacy`) — IPs in ACCEPT rules → `HostData`; FORWARD + `dpt:22` ACCEPT → `ConnectionData` (indicator)
- `nftables` (`nft list ruleset`) — same extraction; parse `table/chain/rule` structure; `tcp dport 22` accept rules → `ConnectionData` (indicator)

**Process & environment state:**
- `ps_output` (`ps aux`) — SSH tunnel args (`-L`/`-R`/`-D`) in COMMAND → `ConnectionData` (indicator); `user@host` patterns → `ConnectionData`; `-i <keyfile>` → warnings
- `env_output` (`env` / `printenv`) — variables matching `*PASSWORD*`, `*SECRET*`, `*TOKEN*`, `*KEY*`, `*PASS*` → `CredentialData`; PEM blocks → `CredentialData` (private_key)

**Container & orchestration state:**
- `docker_ps` (`docker ps`) — exposed `0.0.0.0:<port>` bindings → `HostData` + stats
- `docker_network` (`docker network inspect`) — JSON container IPs + gateway → `HostData`
- `kubectl_pods` (`kubectl get pods -o wide`) — pod IPs + node names → `HostData`

**Invariants:** `iptables`/`nftables` skip 0.0.0.0, broadcast, multicast, loopback; only emit `ConnectionData` for `dport 22` rules. `ip_addr`/`ip_route`/`ip_neigh`/`arp` skip all non-RFC1918 IPs — internet-facing gateways would create graph noise with no pivot value. `docker_ps`/`docker_network`/`kubectl_pods` emit `HostData` only. `env_output` and `env_file` (Phase 19) share keyword-matching logic — extract to a shared utility when implemented together.

**Graph rule:** parsers that emit `ConnectionData` create indicator-confidence edges. Parsers that emit only `HostData`/`CredentialData` surface in the host detail panel only — never as graph edges.

---

### Phase 19 — Secret & Credential File Parsers

Files storing credentials for non-SSH services. No schema changes — use `cred_type: password` with descriptive `name` for non-key secrets (avoids migration; revisit if Phase 16 MCP needs type filtering).

**Direct host-credential mappings:**
- `netrc` (`~/.netrc`) — `machine <host> login <user> password <pass>` → `CredentialData` + `HostData`; `default` stanza → warning
- `pgpass` (`~/.pgpass`) — `hostname:port:db:user:pass` → `CredentialData` + `HostData`; wildcard `*` fields → warnings
- `mysql_config` (`~/.my.cnf`) — `[client]` section `password=`, `user=`, `host=` → `CredentialData` + `HostData`

**Cloud credentials:**
- `aws_credentials` (`~/.aws/credentials`) — INI: `aws_access_key_id` + `aws_secret_access_key` per profile → `CredentialData` (name: `AWS:<profile>`)
- `aws_config` (`~/.aws/config`) — `role_arn` → `CredentialData` (name: `AWS role:<arn>`); emitted only when `role_arn` present
- `gcloud_credentials` (`~/.config/gcloud/application_default_credentials.json`) — `access_token`, `refresh_token`, `client_secret` → `CredentialData` (name: `GCP ADC`)
- `kubeconfig` (`~/.kube/config`) — cluster `server` URLs → `HostData`; user `token` → `CredentialData`; client-cert + client-key PEM blocks → `CredentialData` (private_key / public_key)
- `boto` (`~/.boto` / `~/.s3cfg`) — `aws_access_key_id`, `aws_secret_access_key`, `s3_host` → `CredentialData` + `HostData`

**Application & service credentials:**
- `env_file` (`.env`) — variables matching `*PASSWORD*`, `*SECRET*`, `*TOKEN*`, `*KEY*`, `*PASS*` → `CredentialData`; PEM blocks → `CredentialData` (private_key)
- `docker_config` (`~/.docker/config.json`) — `auths`: base64-decode `auth` → `user:pass` → `CredentialData`; registry hostname → `HostData`
- `git_credentials` (`~/.git-credentials`) — `https://user:pass@hostname` → `CredentialData` + `HostData`
- `rclone_config` (`~/.config/rclone/rclone.conf`) — `pass`/`token`/`secret`/`access_key_id` keys per remote → `CredentialData`; `host`/`endpoint` → `HostData`

**Invariants:** `kubeconfig` requires PyYAML — verify transitive dep. `docker_config` auth is base64(`user:password`) — store decoded password as `Credential.value`. `rclone_config` parsed generically across all providers (40+). All secret values stored verbatim; Phase 14 export redacts to first 8 chars + `...`. Phase 19 parsers emit no `ConnectionData` — credentials and discovered hosts surface in host detail panel only.

---

### Phase 20 — Collection Script + Bulk Archive Import

Mirrors the operational command generation from Phase 9: "here's what to run on a compromised host to feed Lockpick evidence automatically."

**Collection script** — `GET /ops/{op_id}/collection-script` returns a bash script that:
- Collects all parseable files + command outputs from the current host
- Names output files with the convention `<file_type>__<username>.<ext>` (e.g. `bash_history__root.txt`, `ip_addr.txt`)
- Handles Debian/RHEL distros: tries `ip addr` then falls back to `ifconfig`; tries `auth.log` then `secure`; etc.
- Silently skips missing files/commands (no root required for non-privileged files)
- Packages everything into `lockpick_<hostname>_<ts>.tar.gz` with a `manifest.json` at the root
- `manifest.json` format: `[{"filename": "...", "file_type": "...", "username": "..."}]`
- Never exfiltrates automatically — writes to `/tmp` only; upload is a separate manual step

**Bulk import endpoint** — `POST /ops/{op_id}/hosts/{host_id}/import-archive`:
- Accepts a `multipart/form-data` tarball
- Reads `manifest.json` for `file_type` + `username` per file; falls back to filename convention if absent
- Dispatches each file through the normal upload pipeline (same parser registry, same `log_activity()` flow)
- Returns `{"processed": N, "warnings": [...], "stats": {...}}`
- No new tables; no Alembic migration required

**Invariants:** Naming convention is `<file_type>__<username>.<ext>` (double underscore); files without a username use `<file_type>.<ext>`. Manifest is authoritative when present.

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
14. **SSH config patterns** — `Host` blocks with wildcard/token aliases (`jb.*`, `*.example.com`, `%h`) are stored as `SshConfigPattern` records (table: `ssh_config_patterns`), never as hosts. The `services/ssh_pattern.py` `ssh_match()` function implements SSH glob semantics (`fnmatch` + `!` negation, case-insensitive). Pattern-to-host edges are created at upload time (existing hosts) and retroactively when a new host/IP is added.
15. **Loopback routing** — `127.x.x.x`, `::1`, and `localhost` in connection records always resolve to the upload host, never create new host records. Handled in `_resolve_ip_side()` (`routers/upload.py`).
16. **HostIP addr_type** — `HostIP.ip_address` holds either a numeric IP or FQDN; `addr_type` (ipv4|ipv6|hostname) disambiguates. IP resolver infers addr_type via `_infer_addr_type()` and sets it on new records. Hostname lookups are case-insensitive.
17. **SudoRule** — read-only from the upload pipeline; no manual create endpoint. `SudoRule.op_id` stored for bulk queries. Sudo rules do not affect BFS pivot path confidence — informational context only.

---
