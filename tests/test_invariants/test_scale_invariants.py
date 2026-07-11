"""Heavy scale invariant — the graph contracts must hold at 200 hosts.

Marked ``slow`` (not ``property``): the sole member of ``make test-scale`` and the
backend's scale coverage. Runs once, deterministically (fixed seed), not under
Hypothesis, so it stays out of the fast gate and the ``property`` battery.
"""
from __future__ import annotations

import random

import pytest

from services.graph_builder import build_graph
from tests.generate_random_network import build_structure_topology
from tests.opbuilder import OpBuilder

pytestmark = pytest.mark.slow

_CONFIDENCES = {"confirmed", "observed", "indicator"}
_RANK = {"indicator": 0, "observed": 1, "confirmed": 2}


def test_graph_invariants_hold_at_scale(client, db_session):
    topo = build_structure_topology(random.Random(0), n_hosts=200)
    lo = OpBuilder(client).apply_topology(topo)
    g = build_graph(db_session, lo.op_id)

    assert len(g.nodes) == 200
    node_ids = {n.host_id for n in g.nodes}
    for e in g.edges:
        assert e.src_host_id != e.dst_host_id
        assert e.src_host_id in node_ids and e.dst_host_id in node_ids
        assert e.confidence in _CONFIDENCES
        assert _RANK[e.confidence] == max(_RANK[ev.confidence] for ev in e.evidence)
