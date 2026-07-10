"""Shared, client-agnostic REST op-builder for Lockpick tests.

Test-only helper package. Imports no production or pytest code so it can be used
both under pytest (``TestClient``) and as a plain script (``httpx.Client`` in
``tests/e2e/seed_e2e.py``).
"""
from __future__ import annotations

from .rest import LoadedOp, OpBuilder

__all__ = ["LoadedOp", "OpBuilder"]
