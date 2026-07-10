"""Unit tests for composable topology shapes (tests/opbuilder/shapes.py)."""
from __future__ import annotations

from tests.opbuilder import OpBuilder, shapes


# ── Structural tests (pure dict builders) ───────────────────────────────────

def test_linear_chain_structure():
    topo = shapes.linear_chain(3)
    assert [h["nickname"] for h in topo["hosts"]] == ["n0", "n1", "n2"]
    pairs = [(c["src"], c["dst"]) for c in topo["connections"]]
    assert pairs == [("n0", "n1"), ("n1", "n2")]


def test_linear_chain_accepts_explicit_names():
    topo = shapes.linear_chain(["a", "b", "c", "d"])
    assert [h["nickname"] for h in topo["hosts"]] == ["a", "b", "c", "d"]
    assert len(topo["connections"]) == 3


def test_star_structure():
    topo = shapes.star("hub", 3)
    nicks = [h["nickname"] for h in topo["hosts"]]
    assert nicks[0] == "hub"
    assert len(nicks) == 4
    assert all(c["src"] == "hub" for c in topo["connections"])
    assert len(topo["connections"]) == 3


def test_diamond_structure():
    topo = shapes.diamond()
    assert len(topo["hosts"]) == 4
    assert len(topo["connections"]) == 4


def test_mesh_is_fully_connected():
    topo = shapes.mesh(4)
    assert len(topo["hosts"]) == 4
    # every unordered pair once → C(4,2) = 6
    assert len(topo["connections"]) == 6


def test_isolated_host_has_no_connections():
    topo = shapes.isolated_host("lonely")
    assert [h["nickname"] for h in topo["hosts"]] == ["lonely"]
    assert topo["connections"] == []


def test_undated_edge_has_null_timestamp():
    topo = shapes.undated_edge("a", "b")
    assert len(topo["connections"]) == 1
    assert topo["connections"][0]["timestamp"] is None


def test_key_pivot_builds_cred_and_two_links():
    topo = shapes.key_pivot("src", "dst", src_user="alice", dst_user="alice")
    assert len(topo["credentials"]) == 1
    rels = {(link["host"], link["relationship_type"]) for link in topo["credential_links"]}
    assert rels == {("src", "found_on_disk"), ("dst", "authorized_key")}


def test_key_pivots_have_distinct_fingerprintable_values():
    a = shapes.key_pivot("h1", "h2")
    b = shapes.key_pivot("h3", "h4")
    assert a["credentials"][0]["value"] != b["credentials"][0]["value"]


# ── merge / assign_ips ──────────────────────────────────────────────────────

def test_merge_unions_hosts_and_concats_connections():
    merged = shapes.merge(shapes.password_conn("a", "b"), shapes.password_conn("b", "c"))
    nicks = [h["nickname"] for h in merged["hosts"]]
    assert nicks == ["a", "b", "c"]  # 'b' deduped
    assert len(merged["connections"]) == 2


def test_assign_ips_fills_missing_and_preserves_declared():
    topo = {"hosts": [{"nickname": "keep", "ip": "10.10.0.1", "files": []},
                      {"nickname": "fill", "ip": None, "files": []}]}
    shapes.assign_ips(topo)
    ips = {h["nickname"]: h["ip"] for h in topo["hosts"]}
    assert ips["keep"] == "10.10.0.1"
    assert ips["fill"] and ips["fill"] != "10.10.0.1"


def test_assign_ips_are_unique():
    topo = shapes.assign_ips(shapes.linear_chain(50))
    ips = [h["ip"] for h in topo["hosts"]]
    assert len(ips) == len(set(ips)) == 50


# ── Integration: shapes drive a real graph ──────────────────────────────────

def test_linear_chain_applies_to_connected_graph(client):
    topo = shapes.assign_ips(shapes.linear_chain(4))
    lo = OpBuilder(client).apply_topology(topo)
    assert len({n["nickname"] for n in lo["graph"]["nodes"]}) == 4
    assert len(lo["graph"]["edges"]) == 3


def test_key_pivot_applies_to_key_match_edge(client):
    topo = shapes.assign_ips(shapes.key_pivot("src", "dst"))
    lo = OpBuilder(client).apply_topology(topo)
    edge = next(
        e for e in lo["graph"]["edges"]
        if (e["src_host_id"], e["dst_host_id"]) == (lo.host_ids["src"], lo.host_ids["dst"])
    )
    assert any(ev["type"] == "key_match" for ev in edge["evidence"])
    assert edge["confidence"] == "confirmed"


def test_two_key_pivots_do_not_cross_link(client):
    """Distinct fingerprints per pivot → no spurious cross edges."""
    topo = shapes.assign_ips(shapes.merge(
        shapes.key_pivot("a", "b"),
        shapes.key_pivot("c", "d"),
    ))
    lo = OpBuilder(client).apply_topology(topo)
    key_edges = {
        (e["src_host_id"], e["dst_host_id"])
        for e in lo["graph"]["edges"]
        if any(ev["type"] == "key_match" for ev in e["evidence"])
    }
    ids = lo.host_ids
    assert key_edges == {(ids["a"], ids["b"]), (ids["c"], ids["d"])}
