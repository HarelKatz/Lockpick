"""Property invariants over the aggregated graph and the pivot-path finder.

Style B: build a generated op through the REST ``OpBuilder``, then call the service
directly against the shared test session. Every graph the builder produces must
satisfy these invariants for ANY generated topology.
"""
from __future__ import annotations

import base64

import pytest
from hypothesis import given

from schemas import PathFinderRequest
from services.graph_builder import _max_confidence, build_graph
from services.pivot_analysis import _MAX_DEPTH, _MAX_PATHS, find_paths
from tests.opbuilder import OpBuilder
from tests.test_invariants.strategies import structure_topologies

pytestmark = pytest.mark.property

_CONFIDENCES = {"confirmed", "observed", "indicator"}
# Independent confidence rank — deliberately NOT graph_builder._max_confidence:
# asserting with the impl would make the max-of-evidence check tautological and
# blind to a broken guard (the same circularity the render invariant avoids).
_RANK = {"indicator": 0, "observed": 1, "confirmed": 2}


@given(topo=structure_topologies())
def test_graph_structural_invariants(client, db_session, topo):
    lo = OpBuilder(client).apply_topology(topo)
    g = build_graph(db_session, lo.op_id)
    node_ids = {n.host_id for n in g.nodes}

    for e in g.edges:
        # no self-loop
        assert e.src_host_id != e.dst_host_id
        # no null-host / no floating edge — both endpoints are real nodes
        assert e.src_host_id in node_ids
        assert e.dst_host_id in node_ids
        # confidence is a valid level, on the edge and every evidence item
        assert e.confidence in _CONFIDENCES
        assert all(ev.confidence in _CONFIDENCES for ev in e.evidence)
        # edge confidence == max-of-evidence (ranked independently of the impl)
        assert _RANK[e.confidence] == max(_RANK[ev.confidence] for ev in e.evidence)


def test_max_confidence_returns_the_maximum():
    """Edge confidence is the max-of-evidence. Asserted with the maximum deliberately
    NOT first, so the check is position-independent (build_graph happens to add the
    highest-confidence key-match evidence first, so the graph-level invariant alone
    wouldn't catch a `return confidences[0]` regression — this does)."""
    assert _max_confidence(["observed", "confirmed", "indicator"]) == "confirmed"
    assert _max_confidence(["indicator", "observed"]) == "observed"
    assert _max_confidence(["indicator", "indicator"]) == "indicator"


def test_key_match_self_loop_is_dropped(client, db_session):
    """A credential found_on_disk AND authorized_key on the SAME host must not
    produce a self-loop edge (the key-match guard). Pinned explicitly because the
    generated topologies only sometimes hit a shared-key self-pivot — this makes
    the guard's break-to-fail reliable."""
    blob = base64.b64encode(b"lockpick-selfloop-key").decode()
    topo = {
        "hosts": [{"nickname": "solo", "ip": "10.90.0.1", "files": []}],
        "credentials": [
            {"key": "k", "cred_type": "public_key",
             "value": f"ssh-ed25519 {blob} k", "name": "k"},
        ],
        "credential_links": [
            {"credential": "k", "host": "solo",
             "relationship_type": "found_on_disk", "username": "root"},
            {"credential": "k", "host": "solo",
             "relationship_type": "authorized_key", "username": "root"},
        ],
        "connections": [],
    }
    lo = OpBuilder(client).apply_topology(topo)
    g = build_graph(db_session, lo.op_id)
    assert all(e.src_host_id != e.dst_host_id for e in g.edges)


@given(topo=structure_topologies())
def test_find_paths_bounds(client, db_session, topo):
    lo = OpBuilder(client).apply_topology(topo)
    graph = build_graph(db_session, lo.op_id)
    ids = list(lo.host_ids.values())

    # src == dst → no paths, ever.
    same = PathFinderRequest(src_host_id=ids[0], dst_host_id=ids[0], mode="all")
    assert find_paths(db_session, lo.op_id, same, graph=graph).paths == []

    # Any real pair: bounded depth (≤ _MAX_DEPTH hops ⇒ ≤ _MAX_DEPTH+1 nodes) and
    # count (≤ _MAX_PATHS). Holds whether or not a path actually exists.
    req = PathFinderRequest(src_host_id=ids[0], dst_host_id=ids[-1], mode="all")
    resp = find_paths(db_session, lo.op_id, req, graph=graph)
    assert len(resp.paths) <= _MAX_PATHS
    for p in resp.paths:
        assert len(p.host_ids) <= _MAX_DEPTH + 1
