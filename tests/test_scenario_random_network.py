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

from tests.opbuilder import OpBuilder

RND = Path(__file__).parent / "fixtures" / "random_network"
TOPOLOGY = RND / "topology.json"

pytestmark = pytest.mark.skipif(
    not TOPOLOGY.exists(),
    reason="Random network fixtures not generated — run tests/generate_random_network.py first",
)


@pytest.fixture(scope="function")
def loaded_op(client):
    topology = json.loads(TOPOLOGY.read_text())
    return OpBuilder(client).apply_topology(topology, fixtures_root=RND)


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



def test_key_pivots_are_confirmed(loaded_op):
    """All key pivot edges should have confidence 'confirmed'."""
    host_ids = loaded_op["host_ids"]
    edges_by_pair = {(e["src_host_id"], e["dst_host_id"]): e for e in loaded_op["graph"]["edges"]}
    for pivot in loaded_op["topology"]["expected_key_pivots"]:
        src_id = host_ids[pivot["src"]]
        dst_id = host_ids[pivot["dst"]]
        edge = edges_by_pair.get((src_id, dst_id))
        if edge is None:
            continue
        assert edge["confidence"] == "confirmed", (
            f"{pivot['src']} → {pivot['dst']} has confidence {edge['confidence']}"
        )


def test_no_file_host_is_isolated(loaded_op):
    """Hosts with no files should appear as nodes but have no edges."""
    host_ids = loaded_op["host_ids"]
    no_file_hosts = [h["nickname"] for h in loaded_op["topology"]["hosts"] if not h["files"]]
    for nickname in no_file_hosts:
        h_id = host_ids[nickname]
        connected = [
            e for e in loaded_op["graph"]["edges"]
            if e["src_host_id"] == h_id or e["dst_host_id"] == h_id
        ]
        assert connected == [], f"{nickname} (no files) has unexpected edges: {connected}"


def test_pivotable_users_populated(loaded_op):
    """Key pivot edges should have pivotable_users entries."""
    host_ids = loaded_op["host_ids"]
    edges_by_pair = {(e["src_host_id"], e["dst_host_id"]): e for e in loaded_op["graph"]["edges"]}
    for pivot in loaded_op["topology"]["expected_key_pivots"]:
        src_id = host_ids[pivot["src"]]
        dst_id = host_ids[pivot["dst"]]
        edge = edges_by_pair.get((src_id, dst_id))
        if edge is None:
            continue
        assert edge.get("pivotable_users"), (
            f"No pivotable_users on {pivot['src']} → {pivot['dst']}"
        )


def test_all_uploads_return_ok(client):
    """Every file in the random topology manifest must upload without error."""
    topology = json.loads(TOPOLOGY.read_text())
    b = OpBuilder(client)
    op_id = b.op("RandomNetworkOp")
    host_ids: dict[str, str] = {}
    for h in topology["hosts"]:
        hid = b.host(op_id, h["nickname"])
        host_ids[h["nickname"]] = hid
        if h.get("ip"):
            b.ip(hid, h["ip"])

    for h in topology["hosts"]:
        hid = host_ids[h["nickname"]]
        for f in h["files"]:
            path = RND / f["path"]
            result = b.upload(op_id, hid, f["file_type"], path.read_bytes(), path.name, f.get("username"))
            assert result["ok"] is True, f"Upload not ok for {f['path']}: {result}"
