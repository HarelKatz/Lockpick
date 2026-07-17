"""Shared fixtures for the real_examples snapshot suite.

Parsers that infer wall-clock-relative values (e.g. auth.log inferring a year for
classic syslog timestamps) do so through a module-level `_now()`. Left to the wall
clock, the committed `.expected.json` snapshots would drift every New Year. Freeze
`_now()` on every parser module that defines one — generalized (not just auth_log)
so a future wall-clock parser following the `_now()` convention is covered
automatically. `tests/test_parsers/test_time_hygiene.py` enforces the convention.
Changing this instant re-bakes the affected snapshots.
"""
from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers.registry import PARSER_REGISTRY

_FROZEN_NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze_parser_now(monkeypatch):
    for module_name in {cls.__module__ for cls in PARSER_REGISTRY.values()}:
        mod = importlib.import_module(module_name)
        if hasattr(mod, "_now"):
            monkeypatch.setattr(mod, "_now", lambda: _FROZEN_NOW)
