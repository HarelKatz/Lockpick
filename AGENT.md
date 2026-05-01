# Lockpick — Red Team Operation Manager

## Project Overview

A web-based tool for red teams to collaboratively organize SSH credentials, host relationships, and pivot paths during operations. Runs as a shared server — the entire team accesses it, and any data one person adds is visible to everyone on their next query. The core value is **visualizing lateral movement opportunities** by correlating SSH keys, connection logs, and host data across an engagement.

**Portability:** This tool may run on a VPS for a week, get zipped up, moved to another box, and resumed. All state lives in `./data/` — the only thing to back up or move. No external dependencies.

> For tech stack, dev commands, repo layout, migration rules, frontend conventions, and git format — see **CLAUDE.md**.

---

## Current Status

> **Edit rules:** ≤5 lines. Last completed · Next · Any blocker. Nothing else — detail belongs in commit messages.

**Last completed: Phases 1–18 — full stack, 49 file types / 44 parser classes (Phase 16 system files, Phase 17 command output, Phase 18 secret/credential files including netrc/pgpass/mysql_config/AWS/GCP ADC/kubeconfig/env_file/docker_config/git_credentials/rclone_config), WS live push, host notes, status enum, addr_type, SudoRule, host merge, one-click collection script + bulk archive import**

**Next: Phase 19 — Engagement Report Export**

---

## Architecture Rules

1. **Backend and frontend are separate directories**: `backend/` and `frontend/`
2. **The graph edge aggregation happens in the backend** (`services/graph_builder.py`), not the frontend. The frontend renders what the API gives it.
3. **The frontend never touches the DB** — all data flows through the REST API
4. **No authentication on the tool** — it runs on a trusted network / VPN. The red team trusts each other.
5. **All state in `./data/`** — DB file, uploaded raw files, nothing else. This directory is the only thing that needs to be backed up or moved.
6. **IP resolution is best-effort** — when a parser finds an IP, try to match it to an existing host. If no match, create an "unresolved" host with just that IP. The user can merge hosts later. The resolver rejects (returns `None` for) multicast, reserved, unspecified addresses and non-hostname garbage (e.g. utmp magic values, strings with spaces) so they never become phantom hosts — callers should treat a `None` return as "skip this record." Loopback handling is a separate earlier-stage filter (see Rule #15).
7. **Activity log** — `log_activity()` (`services/activity.py`) must be called before `db.commit()` in every write endpoint. It adds to the current session and does not commit independently.
8. **Export format** — op exports use `lockpick_export_version: 1`. Import remaps all IDs — never re-use original IDs from an export.
9. **File uploads** — raw files stored at `data/uploads/{op_id}/{uuid}_{filename}`. Update/delete is intentionally unsupported: parsed records carry no per-file provenance marker, so replacing a file would create duplicates.
10. **Graph library** — frontend graph uses `react-force-graph-2d` (ForceGraph2D) + d3-force. Never reintroduce cytoscape.js or React Flow.
11. **Graph state ownership** — `GraphCanvas` owns all d3/simulation state; `GraphView` owns all selection/filter state. Keep these separate.
12. **Graph click timing** — node single-click is delayed 250 ms to let double-click (lock/unlock) preempt it. Do not remove or shorten this delay.
13. **Graph detail panel** — right detail panel uses `push` mode (shrinks canvas) when the clicked node falls in the rightmost 320 px of the canvas; `overlay` (absolute, canvas unchanged) otherwise. Mode is evaluated once on open and held through the close transition.
14. **SSH config patterns** — `Host` blocks with wildcard/token aliases (`jb.*`, `*.example.com`, `%h`) are stored as `SshConfigPattern` records (table: `ssh_config_patterns`), never as hosts. The `services/ssh_pattern.py` `ssh_match()` function implements SSH glob semantics (`fnmatch` + `!` negation, case-insensitive). Pattern-to-host edges are created at upload time (existing hosts) and retroactively when a new host/IP is added.
15. **Loopback routing** — `127.x.x.x`, `::1`, and `localhost` in connection records always resolve to the upload host, never create new host records. Handled in `_resolve_ip_side()` (`services/upload_pipeline.py`).
16. **HostIP addr_type** — `HostIP.ip_address` holds either a numeric IP or FQDN; `addr_type` (ipv4|ipv6|hostname) disambiguates. IP resolver infers addr_type via `_infer_addr_type()` and sets it on new records. Hostname lookups are case-insensitive.
17. **SudoRule** — read-only from the upload pipeline; no manual create endpoint. `SudoRule.op_id` stored for bulk queries. Sudo rules do not affect BFS pivot path confidence — informational context only.
18. **WS live push** — `broadcast_sync(op_id, event)` (`ws_manager.py`) must be called after `db.commit()` in every write endpoint. Event shape: `{"type": "update", "entity_type": "<host|credential|connection|...>", "op_id": op_id}`. It is fire-and-forget and safe to call even when no clients are connected.
19. **Host lazy-load gate** — `Host.ips`, `Host.users`, `Host.credential_links`, `Host.notes` use `lazy="raise_on_sql"`. Any query that loads hosts for serialization or bulk iteration must `selectinload` the relationships it touches. `_host_q(db)` in `routers/hosts.py` covers the `HostRead` path; `services/graph_builder.py` applies its own options for the graph path.
20. **Upload pipeline split** — `services/upload_pipeline.process_single_file()` is the authoritative record-persistence helper for parseable evidence. It parses, persists records with dedup, and returns a result dict (counters, fingerprints, safe_name); it does **not** commit, log activity, or broadcast. Callers own those, plus the pivot scan — which must run *after* `db.commit()` so newly-added links are visible. Any new endpoint ingesting parseable files must use this helper — do not duplicate parser-dispatch or dedup logic.
21. **Collection script invariants** — the bash script served by `GET /ops/{op_id}/collection-script` is byte-identical for every op (no op-specific data). Filename convention `<file_type>__<username>.<ext>` inside the tarball is authoritative for dispatch at import time; `manifest.json` is informational only. The script must remain sudo-free and must not perform network activity.
22. **Archive import safety** — `POST /ops/{op_id}/hosts/{host_id}/import-archive` extracts tarballs through two layers of defense: an explicit member pre-check that rejects absolute paths, `..` components, symlinks, hardlinks, and devices; and `tarfile.extractall(..., filter="data")` as fallback. Extraction goes into `tempfile.TemporaryDirectory()` only. Compressed payload is capped by `settings.archive_import_max_bytes` (default 100 MiB), AND the sum of declared `member.size` values must be below `settings.archive_import_max_uncompressed_bytes` (default 500 MiB) — the second check runs before `extractall()` to defend against gzip bombs where a tiny tarball expands to gigabytes.
23. **Host merge invariants** — `services/host_merge.merge_hosts()` is the single relation-mover for both manual merge (`POST /hosts/{source_id}/merge`) and the upload-pipeline auto-merge path. It moves `HostIP`, `HostUser`, `CredentialLink`, `ConnectionRecord` (src + dst), `HostNote`, `SshConfigPattern`, and `SudoRule` from source → target, then deletes source. Atomic — caller wraps in one transaction (the helper flushes but does not commit; activity log + broadcast are caller's responsibility, mirroring Rule #20). Call only from routers and `services/upload_pipeline.py`; parsers never invoke the merge service. Dedup keys: `HostIP` on `(host_id, ip_address)` and `CredentialLink` on `(credential_id, host_id, relationship_type, username)` — these match upload-time dedup. `HostUser` and `SudoRule` are NOT deduped. `ConnectionRecord` self-loops (src=dst=target) are preserved as audit evidence; graph rendering can filter them. Activity entries are emitted one per merge — `host.merge` for manual, `host.auto_merge` for pipeline auto-merges.
24. **Auto-merge constraint** — `services/ip_resolver.is_unresolved_host(host)` is the canonical "this row was created by the parser and has no operator content" predicate. Returns True iff `host.comment == AUTO_CREATED_COMMENT` (the marker `resolve_ip()` writes) AND `host.users`/`credential_links`/`notes`/`sudo_rules` are all empty. Two callers gate on it: the upload pipeline's nickname-clobber path (which renames placeholder hosts with parser-supplied nicknames), and the alias-conflict auto-merge path (which dissolves placeholders into resolved hosts). Caller must `selectinload` the four relationships before invoking. The upload-pipeline auto-merge additionally guards `existing != host_id` so the upload host itself is never dissolved as the source of an auto-merge.
25. **Indicator-confidence gap (Phase 17 follow-up)** — `arp`, `ip_neigh`, `iptables`, and `nftables` parsers emit `ConnectionRecord`s that should render at *indicator* confidence on the graph, but `services/graph_builder.py::_classify_connection_evidence` currently classifies them as *observed* (it only recognizes `bash_history`/`known_hosts` substrings in `source_file` for indicator status). This is a known limitation deferred to a future refinement (likely a `parser_file_type` field on `ConnectionRecord` or a hint argument to the classifier). Until fixed, edges from these parsers will look stronger than they are.

---

## Known Bugs

Behavioral defects awaiting a fix. Entries leave this section once the fix ships; any post-fix invariants the fix introduces belong in **Architecture Rules**.

1. **GraphCanvas remount-on-node-set-change race.** `frontend/src/components/GraphCanvas.tsx` keys the `<ForceGraph2D>` element on `nodeSetKey` (sorted join of `host_id`s) to sidestep a `forceLink.initialize()` "node not found" crash from d3-force when the node set grows or shrinks. Every host add/remove unmounts and remounts ForceGraph2D from scratch, then `Effect 1` (line 251) reruns and calls `setFgData(...)` to repopulate. Under rapid back-to-back `setGraphData` calls — bursts of WS-driven `loadFullGraph()` reloads from many writes within a few hundred ms (programmatic API flows, future bulk-add endpoints, integration tests) — the remount/effect/state cycle can interleave such that the freshly-mounted ForceGraph2D never lands on the latest `fgData`, leaving the canvas blank. The auto-fit gate (`fitNeededRef`, line 326-328) only fires when going from empty → non-empty, so subsequent reloads in the empty-canvas state have no recovery path. Symptom: blank canvas with the host sidebar correctly populated; the in-app Refresh button does not unstick it (same `nodeSetKey` → no remount). A full page reload always recovers (fresh mount, single fetch, single render). Normal user flows (file uploads, manual entry) don't reproduce because parser latency / human pace spaces events out. Real fix: replace the keyed-remount workaround with an incremental d3-force update (or a forced `graphRef.current?.refresh()` after each `setFgData`), but the d3-force "node not found" crash that motivated the remount needs to be addressed first.

2. **GraphCanvas pauseAnimation has no matching resume.** `frontend/src/components/GraphCanvas.tsx` line 339-341 calls `graphRef.current?.pauseAnimation()` 50ms after switching **to** a static layout (`grid`, `circle`, `breadthfirst`), to stop the d3 simulation from drifting pinned nodes. There is **no corresponding `resumeAnimation()`** anywhere when switching **away** from a static layout to a force layout (`cola`, `cose-bilkent`). Once paused, ForceGraph2D's internal `requestAnimationFrame` loop is dead — subsequent `setFgData(...)` writes update the React state but the canvas never repaints, and `onEngineStop` (line 577-581) never fires, so the auto-`zoomToFit` flagged by `fitNeededRef = true` (line 326-328) is never executed. Symptom: after one round-trip through a static layout, layout switches still update positions internally but the canvas appears frozen / hosts appear off-screen / "stuck"; clicking "Refresh" recovers because it forces a `nodeSetKey` change → full ForceGraph2D remount with a live rAF loop (see bug #1 above). Real fix: call `graphRef.current?.resumeAnimation()` at the top of Effect 1 (or in a `useEffect([layout])` watcher) when switching from a static to a non-static layout, before `setFgData`. Reproducible by: opening any populated op, switching layout from Force-directed → Organic → Hierarchical (broken on this third switch), or any sequence that goes static-then-non-static.

---

## Known UX Gaps

Frontend deficiencies surfaced during testing — not invariant violations, but missing affordances to address in a later session.

1. **No "Add link" affordance for an existing credential.** The credential card on the Data tab has Edit/Delete/Download for the credential record itself plus Edit/Remove on each existing `CredentialLink`, but no UI path to add a *second* link to the same credential. To attach the same private key as `authorized_key` on a destination host (the configuration that yields a `key_match` evidence type and upgrades the corresponding edge from `observed` to `confirmed`), an operator currently has to re-paste the key value through Add Data → Credential and rely on backend fingerprint dedup — which is not a discoverable or documented flow. Suggested fix: add a `+ Add link` button on each credential card that opens the same host/username/relationship form already used inside Add Data → Credential when its "Link to a host" checkbox is toggled.

2. **Host status not visible on the Data tab host card.** The Edit Host dialog exposes the `status` enum dropdown, and the Graph tab colors the node ring per `theme.statusColors`, but the Data tab host card (`HOSTS` section) shows nickname / IP / users / comment with no surface for status. Operators working on the Data tab can't tell at a glance which hosts are `compromised` vs `target` vs unset. Suggested fix: add a small colored pill (matching the Graph tab's color scheme) next to the host nickname on the Data tab card, rendered only when `host.status !== null`.

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

### Phases 1–18 — Complete

Full stack built and tested: CRUD APIs, graph visualization, file upload + parsers (8 original + nmap_xml, shadow, sshd_config, etc_hosts, sudoers, public_key alias), BFS pivot analysis, global search, export/import, activity log, operational command generation, WS live push, host notes, Host.status enum, HostIP addr_type, SudoRule table with sudoers CRUD; one-click collection via bash snapshot script + bulk archive import; host merge (atomic relation-mover with HostIP/CredentialLink dedup, structured `merge_candidates` per-file response field, manual merge dialog, and auto-merge of unresolved placeholder hosts on alias conflict). Phase 16 added system-file parsers: RHEL/CentOS log aliases (`secure`/`syslog`/`messages` → `AuthLogParser`), binary `lastlog` + textual `last` output, shell configs/histories (`bashrc` and `zshrc` via shared `ShellRcParser` with aggressive secret harvesting, plus `zsh_history` extended-format and `fish_history` YAML-ish), and network configs (`network_interfaces`, `netplan`, `ifcfg`) emitting only the upload host's own IPs as one HostData (primary + aliases) — gateways counted but never emitted as host records. Phase 17 added command-output parsers for network state (`ip addr`/`route`/`neigh`, `arp`), connections (`netstat`, `ss`), firewall (`iptables`, `nftables`), processes (`ps` with cmdline secret harvest), env vars (aggressive `*_KEY`/`*_TOKEN`/`*_PASSWORD` harvest), and Docker container inventory; `docker_network` and `kubectl_pods` deferred (no samples). Phase 18 added secret/credential file parsers for `netrc`, `pgpass`, `mysql_config`, AWS (`config`/`credentials`/`boto`), GCP ADC (`gcloud_credentials`), `kubeconfig` (token + decoded client-key), `.env` aggressive secret harvest, Docker registry auth (`docker_config`), `.git-credentials`, and rclone — all emitted as `CredentialData` (cred_type=password or private_key for actual keys).

---

### Phase 19 — Engagement Report Export

`GET /ops/{op_id}/report?format=markdown|html` — structured engagement summary (op metadata, host inventory, credential inventory, pivot paths via `find_paths`, sudo escalation summary, activity timeline). Markdown primary; HTML wraps it in a minimal printable template. Password hashes and private key material redacted to first 8 chars + `...`; fingerprints shown in full.

---

### Phase 20 — Graph Path Highlight + Time Slider

Shift+click a second node dims everything not on a BFS path between the two selected hosts (uses existing `POST /ops/{op_id}/graph/paths`). Time slider at the bottom of GraphView filters edges by `ConnectionRecord.timestamp`; key-match edges always shown. Pure frontend state — no API changes.

---

### Phase 21 — Credential Blast Radius + Op Briefing

Per-credential rollup — "unlocks N hosts across Y users" — surfaced in the credential detail panel and list row, derived from existing `CredentialLink` data (no schema change). Operation gains two new markdown fields: `summary` (short, rendered in op header) and `briefing` (long, rendered in op detail view, collapsible). Both user-editable, optional.

---

### Phase 22 — MCP Server

Standalone `mcp/` package (does **not** import from `backend/`) exposes op data over MCP/stdio so an AI agent can help navigate pivots. Talks to the Lockpick REST API over HTTP; configurable via `LOCKPICK_URL`. Implement only when all prior phases are stable.

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
