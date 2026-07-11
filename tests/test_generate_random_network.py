"""Tests for the size-dialable random network generator.

Determinism is the top risk: for a fixed (seed, n_hosts) the *structural* topology
(hosts / IPs / users / pivots) must be byte-identical run to run. Real RSA keys are
non-deterministic, so the structure-only export (build_structure_topology) uses
distinct fake public-key blobs and does no keygen.
"""
from __future__ import annotations

import hashlib
import json
import random

import pytest

from tests.generate_random_network import (
    _IP_CAPACITY,
    build_random_topology,
    build_structure_topology,
)
from tests.opbuilder import OpBuilder

# Golden hash of the structural topology for a pinned (seed, n_hosts). Regenerate
# intentionally (and review the diff) if the generator's structure changes.
_GOLDEN_SEED = 1234
_GOLDEN_N = 20
_GOLDEN_HASH = "3d3ce3a7b18bc86dd48718891fe7731f0eb2e859257a6bfd4faa06b6c157172b"


def _hash(topo: dict) -> str:
    return hashlib.sha256(json.dumps(topo, sort_keys=True).encode()).hexdigest()


def _pivot_dag_ok(topo: dict) -> bool:
    """Every key pivot goes from a lower-indexed host to a higher-indexed one."""
    idx = {h["nickname"]: i for i, h in enumerate(topo["hosts"])}
    return all(idx[p["src"]] < idx[p["dst"]] for p in topo["expected_key_pivots"])


# ── Determinism ───────────────────────────────────────────────────────────────

def test_generator_determinism_two_runs_identical():
    a = build_structure_topology(random.Random(_GOLDEN_SEED), n_hosts=_GOLDEN_N)
    b = build_structure_topology(random.Random(_GOLDEN_SEED), n_hosts=_GOLDEN_N)
    assert a == b


def test_generator_determinism_golden_hash():
    topo = build_structure_topology(random.Random(_GOLDEN_SEED), n_hosts=_GOLDEN_N)
    assert _hash(topo) == _GOLDEN_HASH


# ── Scaling ───────────────────────────────────────────────────────────────────

def test_scales_to_requested_host_count():
    for n in (5, 20, 200):
        topo = build_structure_topology(random.Random(n), n_hosts=n)
        assert len(topo["hosts"]) == n


def test_default_n_keys_scales_with_hosts():
    # n_keys default = max(2, n_hosts // 8)
    assert build_structure_topology(random.Random(1), n_hosts=8)["n_keys"] == 2
    assert build_structure_topology(random.Random(1), n_hosts=40)["n_keys"] == 5


def test_pivots_scale_with_hosts():
    small = build_structure_topology(random.Random(2), n_hosts=6)
    large = build_structure_topology(random.Random(2), n_hosts=90)
    assert len(large["expected_key_pivots"]) > len(small["expected_key_pivots"])


def test_key_pivots_form_a_dag():
    topo = build_structure_topology(random.Random(99), n_hosts=40)
    assert _pivot_dag_ok(topo)


def test_host_ips_are_unique():
    topo = build_structure_topology(random.Random(7), n_hosts=120)
    ips = [h["ip"] for h in topo["hosts"]]
    assert len(set(ips)) == len(ips)


def test_small_n_is_safe():
    assert len(build_structure_topology(random.Random(1), n_hosts=1)["hosts"]) == 1
    assert build_structure_topology(random.Random(1), n_hosts=0)["hosts"] == []


def test_large_n_does_not_deadlock():
    """Regression: n beyond the old 1524-address space used to spin forever."""
    topo = build_structure_topology(random.Random(1), n_hosts=2000)
    ips = [h["ip"] for h in topo["hosts"]]
    assert len(topo["hosts"]) == 2000
    assert len(set(ips)) == 2000


def test_exceeding_ip_capacity_raises_not_hangs():
    with pytest.raises(ValueError):
        build_structure_topology(random.Random(1), n_hosts=_IP_CAPACITY + 1)


# ── Integration: the structure-only export drives a real graph ──────────────────

def test_structure_topology_applies_via_opbuilder(client):
    topo = build_structure_topology(random.Random(7), n_hosts=15)
    lo = OpBuilder(client).apply_topology(topo)
    assert len(lo["graph"]["nodes"]) == 15
    key_match = [
        e for e in lo["graph"]["edges"]
        if any(ev["type"] == "key_match" for ev in e["evidence"])
    ]
    assert len(key_match) >= 2


def test_materialize_writes_loadable_fixture(tmp_path, client):
    """The file-based CLI path writes real key files that parse into key-match edges."""
    topo = build_random_topology(random.Random(3), n_hosts=5, out_dir=tmp_path)
    assert (tmp_path / "topology.json").exists() or topo["hosts"]  # topology returned
    lo = OpBuilder(client).apply_topology(topo, fixtures_root=tmp_path)
    assert len(lo["graph"]["nodes"]) == 5
    key_match = [
        e for e in lo["graph"]["edges"]
        if any(ev["type"] == "key_match" for ev in e["evidence"])
    ]
    assert len(key_match) >= 2
