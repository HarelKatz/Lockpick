"""Export → import round-trip fidelity as a graph invariant.

Style B (mirrors test_graph_invariants.py): generate an op, export it, import the export as a
new op, and assert the pivot GRAPH is preserved up to ID remapping. The example-based tests in
tests/test_api/test_export_import.py already cover entity fidelity, ID remap, and the documented
drops (SudoRule/HostNote/SshConfigPattern); this adds the one thing they do not — that a whole
generated topology's EDGES re-wire correctly across the remap (Architecture Rule #8: import
preserves nicknames/IPs but assigns fresh IDs to every row).

structure_topologies() emits only public-key credentials + password connections (no ssh_config
patterns), so none of the documented export drops apply and the round-trip must be lossless.
"""
from __future__ import annotations

from collections import Counter

import pytest
from hypothesis import given

from services.graph_builder import build_graph
from tests.opbuilder import OpBuilder
from tests.test_invariants.strategies import structure_topologies

pytestmark = pytest.mark.property


def _edge_multiset(graph) -> Counter:
    """Edges keyed by (src_nickname, dst_nickname, confidence) — the identity that survives ID
    remap. A Counter (not a set) so a duplicated or dropped edge can't hide."""
    id_to_nick = {n.host_id: n.nickname for n in graph.nodes}
    return Counter(
        (id_to_nick[e.src_host_id], id_to_nick[e.dst_host_id], e.confidence)
        for e in graph.edges
    )


@given(topo=structure_topologies())
def test_export_import_preserves_graph_up_to_id_remap(client, db_session, topo):
    lo = OpBuilder(client).apply_topology(topo)
    g1 = build_graph(db_session, lo.op_id)

    export_data = client.get(f"/api/ops/{lo.op_id}/export").json()
    import_resp = client.post("/api/ops/import", json={"data": export_data})
    assert import_resp.status_code == 201, import_resp.text
    new_op_id = import_resp.json()["op_id"]
    assert new_op_id != lo.op_id  # fresh op id per Rule #8

    g2 = build_graph(db_session, new_op_id)

    # Same nodes (matched by nickname, which import preserves) with the same IP sets.
    nick_to_ips_1 = {n.nickname: set(n.ips) for n in g1.nodes}
    nick_to_ips_2 = {n.nickname: set(n.ips) for n in g2.nodes}
    assert nick_to_ips_1 == nick_to_ips_2

    # Same edges up to ID remap, confidence included — the graph itself is intact.
    assert _edge_multiset(g1) == _edge_multiset(g2)
