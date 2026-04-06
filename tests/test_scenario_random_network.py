"""
End-to-end scenario test: upload the randomly-generated network and assert that
the graph contains the pivot paths declared in topology.json.

Requires tests/fixtures/random_network/ to exist.
Run `uv run --project backend tests/generate_random_network.py` first if needed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

RND = Path(__file__).parent / "fixtures" / "random_network"
TOPOLOGY = RND / "topology.json"

pytestmark = pytest.mark.skipif(
    not TOPOLOGY.exists(),
    reason="Random network fixtures not generated — run tests/generate_random_network.py first",
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _create_op(client) -> str:
    r = client.post("/api/ops", json={"name": "RandomNetworkOp"})
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
    path = RND / file_entry["path"]
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


@pytest.fixture(scope="function")
def loaded_op(client):
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

def test_all_random_hosts_appear_as_nodes(loaded_op):
    graph = loaded_op["graph"]
    node_nicknames = {n["nickname"] for n in graph["nodes"]}
    expected = {h["nickname"] for h in loaded_op["topology"]["hosts"]}
    assert expected == node_nicknames


def test_all_key_pivots_produce_edges(loaded_op):
    """Every key pivot declared in topology.json should appear as a confirmed graph edge."""
    graph = loaded_op["graph"]
    host_ids = loaded_op["host_ids"]
    edges_by_pair = {(e["src_host_id"], e["dst_host_id"]): e for e in graph["edges"]}

    missing = []
    for pivot in loaded_op["topology"]["expected_key_pivots"]:
        src_id = host_ids[pivot["src"]]
        dst_id = host_ids[pivot["dst"]]
        edge = edges_by_pair.get((src_id, dst_id))
        if edge is None:
            missing.append(f"{pivot['src']} → {pivot['dst']} (no edge)")
            continue
        if not any(ev["type"] == "key_match" for ev in edge["evidence"]):
            missing.append(f"{pivot['src']} → {pivot['dst']} (no key_match evidence)")

    assert not missing, "Missing pivot edges:\n" + "\n".join(missing)


def test_all_password_connections_produce_edges(loaded_op):
    """Every password connection declared in topology.json should produce a graph edge."""
    graph = loaded_op["graph"]
    host_ids = loaded_op["host_ids"]
    edges_by_pair = {(e["src_host_id"], e["dst_host_id"]): e for e in graph["edges"]}

    missing = []
    for conn in loaded_op["topology"]["expected_password_connections"]:
        src_id = host_ids[conn["src"]]
        dst_id = host_ids[conn["dst"]]
        if (src_id, dst_id) not in edges_by_pair:
            missing.append(f"{conn['src']} → {conn['dst']} (no edge)")

    assert not missing, "Missing password connection edges:\n" + "\n".join(missing)


def test_all_uploads_return_ok(client):
    """Every file in the random topology manifest must upload without error."""
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
