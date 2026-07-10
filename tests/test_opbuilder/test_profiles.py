"""Unit tests for named substrate profiles (tests/opbuilder/profiles.py).

The load-bearing test is ``test_normal_reproduces_seed_graph``: profiles.normal()
must *be* the current e2e seed (tests/e2e/seed_e2e.py) so the migration is a
faithful drop-in.
"""
from __future__ import annotations

import pytest

from tests.opbuilder import OpBuilder, profiles

pytestmark = pytest.mark.skipif(
    not profiles.NETWORK_TOPOLOGY.exists(), reason="network fixtures not generated"
)


# ── Structure ───────────────────────────────────────────────────────────────

def test_empty_has_no_hosts():
    assert profiles.empty()["hosts"] == []


def test_minimal_is_two_hosts_one_edge():
    topo = profiles.minimal()
    assert len(topo["hosts"]) == 2
    assert len(topo["connections"]) == 1
    assert all(h["ip"] for h in topo["hosts"])


def test_normal_has_network_hosts_plus_isolated_workstation():
    topo = profiles.normal()
    nicks = {h["nickname"] for h in topo["hosts"]}
    assert "workstation" in nicks
    assert nicks >= {"attackbox", "jumpbox", "monitoring", "webserver"}
    assert len(topo["hosts"]) == 11  # 10 network hosts + workstation


def test_normal_connections_include_one_undated():
    topo = profiles.normal()
    undated = [c for c in topo["connections"] if c["timestamp"] is None]
    dated = [c for c in topo["connections"] if c["timestamp"] is not None]
    assert len(undated) == 1
    assert len(dated) == 4


def test_normal_file_paths_are_absolute():
    topo = profiles.normal()
    for h in topo["hosts"]:
        for f in h.get("files", []):
            assert f["path"].startswith("/"), f"expected absolute path, got {f['path']}"


def test_scale_produces_n_hosts_with_unique_ips():
    topo = profiles.scale(20)
    assert len(topo["hosts"]) == 20
    ips = [h["ip"] for h in topo["hosts"]]
    assert len(set(ips)) == 20


def test_edge_cases_is_superset_of_normal():
    normal_nicks = {h["nickname"] for h in profiles.normal()["hosts"]}
    ec_nicks = {h["nickname"] for h in profiles.edge_cases()["hosts"]}
    assert normal_nicks <= ec_nicks
    assert len(ec_nicks) > len(normal_nicks)


# ── Integration: profiles drive a real graph ────────────────────────────────

def test_normal_reproduces_seed_graph(client):
    """apply(normal()) yields the graph the e2e seed produces: 11 nodes, 6
    key-match edges, isolated workstation, connected monitoring, an undated edge."""
    lo = OpBuilder(client).apply_topology(profiles.normal())
    graph = lo["graph"]

    assert len(graph["nodes"]) == 11

    key_match = [e for e in graph["edges"] if any(ev["type"] == "key_match" for ev in e["evidence"])]
    assert len(key_match) == 6

    # workstation is isolated; monitoring is NOT (this is what distinguishes the
    # seed from the raw scenario topology — manual connections wired monitoring up)
    ws = lo.host_ids["workstation"]
    mon = lo.host_ids["monitoring"]
    assert [e for e in graph["edges"] if ws in (e["src_host_id"], e["dst_host_id"])] == []
    assert [e for e in graph["edges"] if mon in (e["src_host_id"], e["dst_host_id"])] != []

    # the time-slider substrate: at least one dated edge and one entirely-undated edge
    def has_dated(e):
        return any(ev.get("timestamp") for ev in e["evidence"])
    assert any(has_dated(e) for e in graph["edges"])
    assert any(not has_dated(e) and e["evidence"] for e in graph["edges"])


def test_empty_applies_to_zero_node_graph(client):
    lo = OpBuilder(client).apply_topology(profiles.empty())
    assert lo["graph"]["nodes"] == []


def test_scale_applies(client):
    lo = OpBuilder(client).apply_topology(profiles.scale(12))
    assert len(lo["graph"]["nodes"]) == 12
