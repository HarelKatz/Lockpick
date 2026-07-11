"""Hypothesis strategies emitting generated Lockpick topologies.

Draws an INDEPENDENT seed rather than using ``profiles.scale(n)`` (which seeds its
RNG with ``n`` itself, yielding exactly one topology per size). Independent seeds let
the generator explore the full topology space for a given host count. The result is a
topology dict in the shape ``OpBuilder.apply_topology`` consumes.
"""
from __future__ import annotations

import random

from hypothesis import strategies as st

from tests.generate_random_network import build_structure_topology


@st.composite
def structure_topologies(draw, *, min_hosts: int = 2, max_hosts: int = 30) -> dict:
    """A deterministic-per-(n, seed) generated topology of ``min_hosts``..``max_hosts``."""
    n = draw(st.integers(min_value=min_hosts, max_value=max_hosts))
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    return build_structure_topology(random.Random(seed), n_hosts=n)
