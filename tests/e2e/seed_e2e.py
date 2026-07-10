#!/usr/bin/env python
"""Deterministic e2e seed for the Lockpick frontend (Playwright) test suite.

Seeds the shared ``profiles.normal()`` substrate over REST against a LIVE backend
— the very same ``OpBuilder`` the pytest scenarios drive in-process, here pointed
at a running server via ``httpx``. ``normal()`` is the static 10-host network
(``tests/fixtures/network``) plus a handful of manual SSH connections with
spread-out timestamps (so the graph **time slider** has a real, draggable range
— every generated fixture shares one hardcoded timestamp), one entirely-undated
connection (exercising the slider's "undated edges are always shown" exemption),
and one isolated host with no connections (which the slider must never hide).

Usage::

    uv run --project backend python tests/e2e/seed_e2e.py [--url http://localhost:8000]

The created operation id is printed as the FINAL stdout line (consumed by the
Playwright global-setup); human-readable progress goes to stderr.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

# Make the test-only op-builder importable when run as a standalone script
# (it imports no production/pytest code, so this is safe under `uv run python`).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.opbuilder import OpBuilder, profiles


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed a deterministic Lockpick op for e2e tests.")
    ap.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    ap.add_argument("--name", default="E2E Graph Fixture", help="Operation name")
    args = ap.parse_args()

    if not profiles.NETWORK_TOPOLOGY.exists():
        _log(f"ERROR: fixtures missing at {profiles.NETWORK_TOPOLOGY} — run tests/generate_fixtures.py first")
        return 1

    base = args.url.rstrip("/")
    with httpx.Client(base_url=base, timeout=30.0) as c:
        lo = OpBuilder(c).apply_topology(profiles.normal(), name=args.name)
        graph = lo.graph
        key_match = sum(
            1 for e in graph["edges"] if any(ev["type"] == "key_match" for ev in e["evidence"])
        )
        dated = sum(
            1 for e in graph["edges"] if any(ev.get("timestamp") for ev in e["evidence"])
        )
        _log(
            f"op created: {lo.op_id} — graph: {len(graph['nodes'])} nodes, "
            f"{len(graph['edges'])} edges ({key_match} key-match, {dated} with dated evidence)"
        )

    # FINAL stdout line: the op id (consumed by Playwright global-setup)
    print(lo.op_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
