"""Named topology substrates.

``normal()`` is the default substrate for the whole test loop: it *is* the
current e2e seed (``tests/e2e/seed_e2e.py``) — the static 10-host network
(``tests/fixtures/network/topology.json``) plus the exact manual/undated
connections and the isolated ``workstation`` host that give the graph time
slider a real, draggable range and its edge cases.

Profiles return topology dicts ready for ``OpBuilder.apply_topology(...)``.
``normal()`` resolves its fixture file paths to absolute, so it needs no
``fixtures_root``.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from . import shapes

NETWORK_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "network"
NETWORK_TOPOLOGY = NETWORK_DIR / "topology.json"

# The seed's manual timestamped connections — between hosts with no key-match
# edge, so the slider can hide them while key-match edges stay pinned.
# (src, dst, src_user, dst_user, iso_timestamp)
_MANUAL_CONNECTIONS = [
    ("monitoring", "jumpbox", "svc", "root", "2026-03-10T09:00:00Z"),
    ("webserver", "dbserver", "www-data", "deploy", "2026-03-13T11:30:00Z"),
    ("fileserver", "internal", "ops", "deploy", "2026-03-17T15:45:00Z"),
    ("backup", "monitoring", "backup", "svc", "2026-03-21T20:15:00Z"),
]

# One entirely-undated connection — exercises the slider's "undated edges are
# always shown" exemption. (src, dst, src_user, dst_user)
_UNDATED_CONNECTIONS = [
    ("monitoring", "webserver", "svc", "www-data"),
]

# An isolated host (no connections) the slider must never hide. (nickname, ip)
_ISOLATED_HOST = ("workstation", "10.10.9.9")


def _seed_conn(src: str, dst: str, src_user: str, dst_user: str, timestamp: str | None) -> dict:
    return {
        "src": src,
        "dst": dst,
        "src_user": src_user,
        "dst_user": dst_user,
        "connection_type": "ssh",
        "direction_context": "from_dst_logs",
        "auth_method": "password",
        "timestamp": timestamp,
        "source_file": "seed_manual",
    }


def empty() -> dict:
    """An operation with no hosts."""
    return {"hosts": []}


def minimal() -> dict:
    """The smallest non-trivial op: two hosts, one connection."""
    return shapes.assign_ips(shapes.password_conn("alpha", "bravo"))


def normal() -> dict[str, Any]:
    """The default substrate — the e2e seed as a topology dict.

    Network fixture (absolute file paths) + manual/undated connections +
    isolated workstation. Every host already carries a real IP.
    """
    topo = json.loads(NETWORK_TOPOLOGY.read_text())
    for h in topo["hosts"]:
        for f in h.get("files", []):
            f["path"] = str(NETWORK_DIR / f["path"])

    topo["connections"] = [
        _seed_conn(src, dst, su, du, ts) for src, dst, su, du, ts in _MANUAL_CONNECTIONS
    ] + [
        _seed_conn(src, dst, su, du, None) for src, dst, su, du in _UNDATED_CONNECTIONS
    ]

    topo["hosts"].append(shapes.host(_ISOLATED_HOST[0], ip=_ISOLATED_HOST[1]))
    return topo


def edge_cases() -> dict:
    """normal() plus known model-completeness edge shapes.

    Layered on as the loop learns; today it adds a self-loop, a long-nickname
    isolated host, and a fresh undated edge — all with ``ec_`` nicknames and
    synthetic IPs, so they never collide with the network fixture.
    """
    return shapes.assign_ips(shapes.merge(
        normal(),
        shapes.self_loop("ec_selfloop"),
        shapes.isolated_host("ec_" + "long_nickname_" * 6 + "host"),
        shapes.undated_edge("ec_undated_a", "ec_undated_b"),
    ))


def scale(n: int) -> dict:
    """A random op of ``n`` hosts from the seeded generator (deterministic per ``n``).

    Delegates to the size-dialable generator's keygen-free in-memory export
    (`tests/generate_random_network.build_structure_topology`). Valid for
    ``0 <= n <= ~65k`` (raises above the generator's IP capacity). Imported lazily
    so this package stays free of generator internals unless ``scale`` is called.
    """
    from tests.generate_random_network import build_structure_topology

    return build_structure_topology(random.Random(n), n_hosts=n)
