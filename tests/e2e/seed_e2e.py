#!/usr/bin/env python
"""Deterministic e2e seed for the Lockpick frontend (Playwright) test suite.

Replays the static 10-host network topology (``tests/fixtures/network``) against
a LIVE backend over REST — the same recipe as ``tests/test_scenario_network.py``,
but pointed at a running server instead of an in-process ``TestClient``. It then
adds a handful of manual SSH connections with spread-out timestamps so the graph
**time slider** has a real, draggable date range: every generated fixture shares
one hardcoded timestamp (``Mar 15 14:20:00``), so without these the slider domain
collapses to ``min == max`` and cannot be exercised. It also adds one connection
with *no* timestamp, yielding an entirely-undated edge that exercises the slider's
"undated edges are always shown" exemption.

Usage::

    uv run --project backend python tests/e2e/seed_e2e.py [--url http://localhost:8000]

The created operation id is printed as the FINAL stdout line (consumed by the
Playwright global-setup); human-readable progress goes to stderr.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

NET = Path(__file__).resolve().parent.parent / "fixtures" / "network"
TOPOLOGY = NET / "topology.json"

# Manual connections with spread-out timestamps, between hosts that do NOT have a
# key-match edge — so the time slider can hide them while key-match edges stay
# pinned. (src_nick, dst_nick, src_user, dst_user, iso_timestamp)
MANUAL_CONNECTIONS = [
    ("monitoring", "jumpbox", "svc", "root", "2026-03-10T09:00:00Z"),
    ("webserver", "dbserver", "www-data", "deploy", "2026-03-13T11:30:00Z"),
    ("fileserver", "internal", "ops", "deploy", "2026-03-17T15:45:00Z"),
    ("backup", "monitoring", "backup", "svc", "2026-03-21T20:15:00Z"),
]

# One connection with NO timestamp, between a fresh host pair with no other edge.
# It yields an entirely-undated edge, exercising the time slider's "undated edges
# are always shown" exemption (the dated edges above cannot — they all have a date).
# (src_nick, dst_nick, src_user, dst_user)
UNDATED_CONNECTIONS = [
    ("monitoring", "webserver", "svc", "www-data"),
]


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed a deterministic Lockpick op for e2e tests.")
    ap.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    ap.add_argument("--name", default="E2E Graph Fixture", help="Operation name")
    args = ap.parse_args()

    if not TOPOLOGY.exists():
        _log(f"ERROR: fixtures missing at {TOPOLOGY} — run tests/generate_fixtures.py first")
        return 1

    topology = json.loads(TOPOLOGY.read_text())
    base = args.url.rstrip("/")

    with httpx.Client(base_url=base, timeout=30.0) as c:
        # 1. Operation
        r = c.post("/api/ops", json={"name": args.name})
        r.raise_for_status()
        op_id = r.json()["id"]
        _log(f"op created: {op_id}")

        # 2. Hosts + IPs
        host_ids: dict[str, str] = {}
        host_ips: dict[str, str] = {}
        for h in topology["hosts"]:
            r = c.post(f"/api/ops/{op_id}/hosts", json={"nickname": h["nickname"]})
            r.raise_for_status()
            hid = r.json()["id"]
            host_ids[h["nickname"]] = hid
            host_ips[h["nickname"]] = h["ip"]
            r = c.post(f"/api/hosts/{hid}/ips", json={"ip_address": h["ip"]})
            r.raise_for_status()
        _log(f"hosts created: {len(host_ids)}")

        # 3. Evidence uploads (manifest order: keys before authorized_keys per host)
        uploads = 0
        for h in topology["hosts"]:
            hid = host_ids[h["nickname"]]
            for f in h["files"]:
                path = NET / f["path"]
                data = {"file_type": f["file_type"], "host_id": hid}
                if f.get("username"):
                    data["username"] = f["username"]
                r = c.post(
                    f"/api/ops/{op_id}/upload",
                    data=data,
                    files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
                )
                r.raise_for_status()
                if not r.json().get("ok"):
                    _log(f"WARNING: upload not ok for {f['path']}: {r.text}")
                uploads += 1
        _log(f"files uploaded: {uploads}")

        # 4. Manual timestamped connections (give the time slider a real range)
        for src, dst, su, du, ts in MANUAL_CONNECTIONS:
            r = c.post(
                f"/api/ops/{op_id}/connections",
                json={
                    "src_host_id": host_ids[src],
                    "src_ip": host_ips[src],
                    "src_user": su,
                    "dst_host_id": host_ids[dst],
                    "dst_ip": host_ips[dst],
                    "dst_user": du,
                    "connection_type": "ssh",
                    "direction_context": "from_dst_logs",
                    "auth_method": "password",
                    "timestamp": ts,
                    "source_file": "seed_manual",
                },
            )
            r.raise_for_status()
        _log(f"manual connections added: {len(MANUAL_CONNECTIONS)}")

        # 4b. Undated connection(s) — no timestamp → an always-shown undated edge
        for src, dst, su, du in UNDATED_CONNECTIONS:
            r = c.post(
                f"/api/ops/{op_id}/connections",
                json={
                    "src_host_id": host_ids[src],
                    "src_ip": host_ips[src],
                    "src_user": su,
                    "dst_host_id": host_ids[dst],
                    "dst_ip": host_ips[dst],
                    "dst_user": du,
                    "connection_type": "ssh",
                    "direction_context": "from_dst_logs",
                    "auth_method": "password",
                    "timestamp": None,
                    "source_file": "seed_manual",
                },
            )
            r.raise_for_status()
        _log(f"undated connections added: {len(UNDATED_CONNECTIONS)}")

        # 5. Sanity: fetch graph, report edge counts
        r = c.get(f"/api/ops/{op_id}/graph")
        r.raise_for_status()
        graph = r.json()
        key_match = sum(
            1 for e in graph["edges"] if any(ev["type"] == "key_match" for ev in e["evidence"])
        )
        dated = sum(
            1
            for e in graph["edges"]
            if any(ev.get("timestamp") for ev in e["evidence"])
        )
        _log(
            f"graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges "
            f"({key_match} key-match, {dated} with dated evidence)"
        )

    # FINAL stdout line: the op id (consumed by Playwright global-setup)
    print(op_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
