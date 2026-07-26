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

Seeds three ops — the ``normal()`` graph fixture, a generated ``scale(50)`` op
for the graph/layout invariant suite, and a one-host ``key_options()`` op whose
authorized_keys carries option prefixes (for the Workspace credential-row layout
spec) — and prints their ids as the FINAL three stdout lines (normal, scale,
key-options), consumed by the Playwright global-setup. Human-readable progress
goes to stderr.
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
    # Generous per-request timeout: this one-time seed runs during Playwright's
    # concurrent server startup (the Vite dev server's cold-start pre-bundle can
    # saturate CPU/IO), so a single write can be transiently slow even though the
    # whole seed is ~2s on an idle box. A tight timeout here flakes the suite.
    with httpx.Client(base_url=base, timeout=120.0) as c:
        builder = OpBuilder(c)
        lo = builder.apply_topology(profiles.normal(), name=args.name)
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

        # Second op: a generated scale(50) fixture for the graph/layout invariant
        # suite (frontend/e2e/invariants-scale.spec.ts). Its connections are undated, so
        # this op has NO time slider — the slider-driven checks run only on normal().
        scale_lo = builder.apply_topology(profiles.scale(50), name=f"{args.name} — Scale 50")
        _log(
            f"scale op created: {scale_lo.op_id} — graph: "
            f"{len(scale_lo.graph['nodes'])} nodes, {len(scale_lo.graph['edges'])} edges"
        )

        # Third op: one host whose authorized_keys carries option prefixes, so the
        # Workspace Data tab renders credential-link rows both with and without the
        # `key_options` chip (frontend/e2e/credential-row.spec.ts).
        keyopts_lo = builder.apply_topology(
            profiles.key_options(), name=f"{args.name} — Key Options"
        )
        _log(f"key-options op created: {keyopts_lo.op_id}")

    # FINAL three stdout lines: the normal op id, the scale op id, then the
    # key-options op id (consumed by Playwright global-setup, which reads the
    # last three lines).
    print(lo.op_id)
    print(scale_lo.op_id)
    print(keyopts_lo.op_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
