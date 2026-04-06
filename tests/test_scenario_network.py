"""
End-to-end scenario test: upload all files for the static 10-host network and
assert that the graph contains the expected key pivots and password connections.

Requires tests/fixtures/network/ to exist.
Run `uv run --project backend tests/generate_fixtures.py` first if needed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

NET = Path(__file__).parent / "fixtures" / "network"
TOPOLOGY = NET / "topology.json"


# ─── Skip if fixtures not generated ───────────────────────────────────────────

pytestmark = pytest.mark.skipif(
    not TOPOLOGY.exists(),
    reason="Network fixtures not generated — run tests/generate_fixtures.py first",
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _create_op(client) -> str:
    r = client.post("/api/ops", json={"name": "ScenarioOp"})
    assert r.status_code == 201
    return r.json()["id"]


def _create_host(client, op_id: str, nickname: str) -> str:
    r = client.post(f"/api/ops/{op_id}/hosts", json={"nickname": nickname})
    assert r.status_code == 201
    return r.json()["id"]


def _register_ip(client, host_id: str, ip: str) -> None:
    r = client.post(f"/api/hosts/{host_id}/ips", json={"ip_address": ip})
    assert r.status_code == 201


def _upload_file(client, op_id: str, host_id: str, file_entry: dict) -> dict:
    path = NET / file_entry["path"]
    content = path.read_bytes()
    data = {
        "file_type": file_entry["file_type"],
        "host_id": host_id,
    }
    if file_entry.get("username"):
        data["username"] = file_entry["username"]
    r = client.post(
        f"/api/ops/{op_id}/upload",
        data=data,
        files={"file": (path.name, content, "application/octet-stream")},
    )
    assert r.status_code == 200, f"Upload failed for {file_entry['path']}: {r.text}"
    return r.json()


# ─── Main fixture: upload all 10 hosts ────────────────────────────────────────

@pytest.fixture(scope="function")
def loaded_op(client):
    """Create the operation, upload all network fixture files, return context."""
    topology = json.loads(TOPOLOGY.read_text())
    op_id = _create_op(client)

    # Create all hosts and register IPs first
    host_ids: dict[str, str] = {}  # nickname → id
    for h in topology["hosts"]:
        hid = _create_host(client, op_id, h["nickname"])
        host_ids[h["nickname"]] = hid
        _register_ip(client, hid, h["ip"])

    # Upload all files in manifest order (private keys before authorized_keys within each host)
    for h in topology["hosts"]:
        hid = host_ids[h["nickname"]]
        for f in h["files"]:
            _upload_file(client, op_id, hid, f)

    graph_resp = client.get(f"/api/ops/{op_id}/graph")
    assert graph_resp.status_code == 200

    return {
        "op_id": op_id,
        "host_ids": host_ids,
        "topology": topology,
        "graph": graph_resp.json(),
    }


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_all_hosts_appear_as_nodes(loaded_op):
    """All 10 hosts should appear as graph nodes."""
    graph = loaded_op["graph"]
    node_nicknames = {n["nickname"] for n in graph["nodes"]}
    expected = {h["nickname"] for h in loaded_op["topology"]["hosts"]}
    assert expected == node_nicknames


def test_key_pivot_edges_present(loaded_op):
    """Each expected key pivot should produce a 'confirmed' graph edge with key_match evidence."""
    graph = loaded_op["graph"]
    host_ids = loaded_op["host_ids"]
    edges_by_pair: dict[tuple[str, str], dict] = {}
    for e in graph["edges"]:
        edges_by_pair[(e["src_host_id"], e["dst_host_id"])] = e

    missing = []
    for pivot in loaded_op["topology"]["expected_key_pivots"]:
        src_id = host_ids[pivot["src"]]
        dst_id = host_ids[pivot["dst"]]
        edge = edges_by_pair.get((src_id, dst_id))
        if edge is None:
            missing.append(f"{pivot['src']} → {pivot['dst']} (no edge found)")
            continue
        key_match_ev = [ev for ev in edge["evidence"] if ev["type"] == "key_match"]
        if not key_match_ev:
            missing.append(f"{pivot['src']} → {pivot['dst']} (edge exists but no key_match evidence)")

    assert not missing, "Missing key pivot edges:\n" + "\n".join(missing)


def test_key_pivot_count(loaded_op):
    """Exactly 6 key-match edges should be in the graph."""
    graph = loaded_op["graph"]
    key_match_edges = [
        e for e in graph["edges"]
        if any(ev["type"] == "key_match" for ev in e["evidence"])
    ]
    assert len(key_match_edges) == 6, (
        f"Expected 6 key pivot edges, got {len(key_match_edges)}: "
        + str([(e["src_host_id"], e["dst_host_id"]) for e in key_match_edges])
    )


def test_password_connection_edges_present(loaded_op):
    """Each expected password connection should produce a graph edge."""
    graph = loaded_op["graph"]
    host_ids = loaded_op["host_ids"]
    edges_by_pair = {(e["src_host_id"], e["dst_host_id"]): e for e in graph["edges"]}

    missing = []
    for conn in loaded_op["topology"]["expected_password_connections"]:
        src_id = host_ids[conn["src"]]
        dst_id = host_ids[conn["dst"]]
        edge = edges_by_pair.get((src_id, dst_id))
        if edge is None:
            missing.append(f"{conn['src']} → {conn['dst']} (no edge found)")

    assert not missing, "Missing password connection edges:\n" + "\n".join(missing)


def test_password_connection_count(loaded_op):
    """At least 2 password connection edges should be in the graph."""
    graph = loaded_op["graph"]
    host_ids = loaded_op["host_ids"]
    password_edges = []
    for conn in loaded_op["topology"]["expected_password_connections"]:
        src_id = host_ids[conn["src"]]
        dst_id = host_ids[conn["dst"]]
        for e in graph["edges"]:
            if e["src_host_id"] == src_id and e["dst_host_id"] == dst_id:
                password_edges.append(e)
                break
    assert len(password_edges) >= 2


def test_monitoring_is_isolated(loaded_op):
    """monitoring host should appear as a node but have no edges."""
    graph = loaded_op["graph"]
    host_ids = loaded_op["host_ids"]
    monitoring_id = host_ids["monitoring"]
    connected_edges = [
        e for e in graph["edges"]
        if e["src_host_id"] == monitoring_id or e["dst_host_id"] == monitoring_id
    ]
    assert connected_edges == [], f"monitoring has unexpected edges: {connected_edges}"


def test_alice_key_pivots_all_confirmed(loaded_op):
    """All alice_key pivots should be 'confirmed' (key_match evidence exists)."""
    graph = loaded_op["graph"]
    host_ids = loaded_op["host_ids"]
    edges_by_pair = {(e["src_host_id"], e["dst_host_id"]): e for e in graph["edges"]}

    alice_pivots = [p for p in loaded_op["topology"]["expected_key_pivots"] if p["key"] == "alice_key"]
    for pivot in alice_pivots:
        src_id = host_ids[pivot["src"]]
        dst_id = host_ids[pivot["dst"]]
        edge = edges_by_pair.get((src_id, dst_id))
        assert edge is not None, f"No edge for alice_key pivot {pivot['src']} → {pivot['dst']}"
        assert edge["confidence"] == "confirmed", (
            f"alice_key pivot {pivot['src']} → {pivot['dst']} has confidence {edge['confidence']}"
        )


def test_pivotable_users_populated(loaded_op):
    """Key pivot edges should have pivotable_users entries."""
    graph = loaded_op["graph"]
    host_ids = loaded_op["host_ids"]
    edges_by_pair = {(e["src_host_id"], e["dst_host_id"]): e for e in graph["edges"]}

    for pivot in loaded_op["topology"]["expected_key_pivots"]:
        src_id = host_ids[pivot["src"]]
        dst_id = host_ids[pivot["dst"]]
        edge = edges_by_pair.get((src_id, dst_id))
        if edge is None:
            continue
        pu = edge.get("pivotable_users", [])
        assert pu, f"No pivotable_users on {pivot['src']} → {pivot['dst']}"


def test_upload_returns_ok_for_all_files(client):
    """Every file upload in the manifest must return ok=true (no parse failures blow up)."""
    if not TOPOLOGY.exists():
        pytest.skip("fixtures not generated")

    topology = json.loads(TOPOLOGY.read_text())
    op_id = _create_op(client)
    host_ids: dict[str, str] = {}
    for h in topology["hosts"]:
        hid = _create_host(client, op_id, h["nickname"])
        host_ids[h["nickname"]] = hid
        _register_ip(client, hid, h["ip"])

    for h in topology["hosts"]:
        hid = host_ids[h["nickname"]]
        for f in h["files"]:
            result = _upload_file(client, op_id, hid, f)
            assert result["ok"] is True, f"Upload not ok for {f['path']}: {result}"
