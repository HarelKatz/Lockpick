# Lockpick — Backlog

> **Edit rules:** Future / large / conditional work — not scheduled. Promote an item to TODO.md when you commit to it. Keep entries short; rationale may run longer for items whose "why" isn't obvious.

## Pre-existing

- **MCP server** — standalone `mcp/` package (does **not** import from `backend/`) exposing op data over MCP/stdio so an AI agent can help navigate pivots. Talks to the Lockpick REST API over HTTP; configurable via `LOCKPICK_URL`. Implement only when all prior work is stable.
- **Agentic graph explorer skill** — Testing-foundation initiative, last phase (the frontend invariant suite it depended on has shipped; now unblocked). New `.claude/skills/graph-explore/SKILL.md`: a Playwright-MCP agent that seeds `normal`/`scale(N)`, drives the real browser (navigate/drag/evaluate-hook/console/screenshot) to hunt the aesthetic/rendering wall (jitter, overlap, off-canvas drift) — the "looks/feels right" gap deterministic specs miss — and distills every finding into a failing deterministic `*.spec.ts`/`test_invariants` case + a CLAUDE.md Misses-log row. On-demand only, never wired into `make gate` — a bug-FINDER feeding the deterministic layers, not the gate.
- **`systemd_journal` parser** — on journald-only hosts (no rsyslog / no text `auth.log`), the sshd Accepted-login, key-fingerprint and source-IP evidence Lockpick already mines from `auth.log` lives **only** in the binary journal (`/var/log/journal/<machine-id>/*.journal`), so Lockpick is currently blind to the auth/connection graph on those boxes. A journal parser would extend the existing pivot extraction to modern distros — same `ConnectionData` record shape as `AuthLogParser`, just a new input format. Collection: `.journal` is `0640 root:systemd-journal` (same privilege tier as `auth.log`'s `root:adm`, and usually `adm`-readable via tmpfiles ACL), so the sudo-free collector can typically `cp` the raw files. Build cost is real — binary format with object compression (LZ4/XZ) + optional FSS sealing; reference plaso's `systemd_journal.py` for the on-disk layout only (Apache-2.0; format reference, never an import — see the closed plaso/dissect parser-source evaluation). *Note: the text `journalctl -u ssh` route already ships (the `journalctl` registry alias → `AuthLogParser`, incl. the `short-iso`/`short-full` formats); this remains for the raw binary `.journal` format.*

## Credential lifecycle

- **Offline hash-crack bridge** — export crackable material (hashes/encrypted keys) for hashcat/john and re-import cracked plaintext, closing the loop between the harvested-credential store and the operator's cracking rig. `GET`/`POST` pair over the credential store.
- **In-tool passphrase recovery** — a service pass that tries the op's already-harvested cleartext password pool against encrypted private keys uploaded without a passphrase; unlock and enrich the credential on a match. Runs on the same retroactive triggers as `ssh_pattern`/`known_hosts` rematch.
- **Crack hashed known_hosts** — HMAC-SHA1 each known hostname/IP/alias in the op against `|1|salt|hash` entries (all of them, on the Debian/Ubuntu `HashKnownHosts` default) to recover the outbound edge the hashing hides; extract the trailing host-key fingerprint for cross-op correlation.

## Parser / evidence breadth

- **SSH host-key fingerprint correlation** — capture the host public-key material `known_hosts` discards today plus a host's own `/etc/ssh/ssh_host_*_key.pub` / sshd `HostKey`s, and use the fingerprint as a host-identity correlation signal (same box seen from two vantage points).
- **kubectl_pods + docker_network parsers** — the collection script already runs `kubectl get pods` / `docker network ls` but neither `file_type` is registered, so the evidence is silently dropped on import. Register both parsers to close the collection→parser gap.
- **WireGuard / OpenVPN config parser** — parse `/etc/wireguard/*.conf` and OpenVPN `.conf`/`.ovpn`: `HostData` per Peer Endpoint / remote, the `AllowedIPs` overlay range, and `CredentialData` for private keys.
- **Ansible inventory + group_vars parser** — an `/etc/ansible/hosts` or playbook repo on a control node is a curated lateral-movement map; INI+YAML inventory parser emitting one `HostData` per host plus any secrets in `group_vars`.
- **Reprocess stored raw evidence** — `POST /ops/{op_id}/reprocess` (optionally scoped to one file / file_type) that re-parses the raw files already retained in `data/uploads/{op_id}/` through today's registry via the idempotent `process_single_file` path — picks up newly-added parsers on old evidence.

## Graph / model

- **SSH trust-chain modeling** — model the trust primitives the fingerprint model can't represent as distinct edge/evidence types: ProxyJump/ProxyCommand bastion chains, `IdentityFile`→known-key linkage, `ForwardAgent` / live agent sockets, and hostbased/CA trust — traversable by pathfinding, correlated from `ssh_config`/`sshd_config`/`known_hosts`.
- **Subnet-grouping graph toggle** — graph-only toggle that soft-clusters nodes by /24 (color + CIDR label; groups created only for real /24s, IP-less hosts untouched; multi-homed grouped by primary IP), keeping every edge. No backend change; the scoped visualization slice of the larger network-segment idea.

## Workflow / UX

- **Data-tab triage + bulk host ops** — per-section filter/sort + inline host-status editing on the Workspace data lists, **plus** multi-select bulk delete/merge/retag and an "unresolved hosts" filter (the folded pivot/unresolved-host triage board — bulk actions back onto the existing merge semantics with one aggregated activity + broadcast).
- **Op-level collection bootstrap** — surface the collection-script download + archive import at the op level (empty-state CTA + workspace header) instead of only inside a per-host graph sidebar, killing the fresh-op dead-end; op-level import prompts pick-or-create host (manifest hostname pre-filled but editable & confirmed) — no silent auto-merge. Surfacing half is cheap — promote if you want the quick first-run win.
- **Undo-on-delete safety net** — buffered client-side delete: optimistically remove the row and show a "Deleted — Undo" toast, firing the actual DELETE only after the window elapses. Guards irreversible host-delete cascades on the unauthenticated shared box.

## Ops / test hardening

- **SQLite WAL + busy_timeout** — SQLAlchemy connect-event issuing `PRAGMA journal_mode=WAL, busy_timeout=5000, synchronous=NORMAL` so concurrent readers don't block writers and transient locks retry instead of throwing "database is locked" on the shared server.
- **Consistent hot backup + restore** — replace the naive live `tar czf data/` (which can capture a torn WAL) with a crash-consistent snapshot (SQLite online-backup API / `VACUUM INTO`) + uploads tar + `PRAGMA integrity_check`, plus a one-command `make restore`.
- **Upload-pipeline idempotency invariant** — property test applying a generated topology/archive twice, asserting the second pass creates zero new hosts/credentials/links/connections and byte-identical `build_graph` output.
- **Live-sync & audit-call invariant coverage** — static meta-test that AST-scans routers for mutating handlers and asserts each calls both `log_activity` and `broadcast_sync` (turns Rules #7/#18 into one self-updating check).
- **E2E for node-lock & detail-panel invariants** — committed Playwright specs for the two untested load-bearing graph interactions: double-click lock/unlock without the 250 ms single-click firing a competing selection (Rule #12), and the push/overlay detail-panel mode (Rule #13).

## Interop / export (operator-tagged)

- **Lockpick CLI client** — stdlib-argparse + httpx CLI wrapping the REST API (`upload`/`import-archive`/`paths`/`pivots`/`export`), resolving hosts by nickname, reading evidence from a file or stdin, with a `watch ./loot/` mode. Pure API client, no server change.
- **Graph & data export to external formats** — serialize `build_graph()` to Graphviz DOT / GraphML / Neo4j Cypher / Mermaid + a client-side canvas-to-PNG for report figures. *Debate caveat: only the PNG figure + a confirmed-pivots CSV clearly earn their keep; the four-format serializer zoo (esp. BloodHound-mismatched Cypher) is a maintenance tax on an evolving schema — ship the cheap slices, defer the spread, de-dupe against the engagement report.*
- **PuTTY .ppk + WinSCP.ini parsers** — Windows-side pivot creds: `.ppk` fingerprint (cross-references OpenSSH `authorized_keys`) and WinSCP.ini reversibly-obfuscated saved-password decrypt into cleartext `CredentialData`.
