"""Shared fixtures for the real_examples snapshot suite.

The auth.log parser infers a year for classic syslog timestamps relative to a
reference "now" (`auth_log._now`). Left to the wall clock, the committed
`.expected.json` snapshots would drift every New Year. Freeze the reference here
so the auth_log/secure/syslog/messages/journalctl snapshots are deterministic in
both the compare run and REGEN_SNAPSHOTS=1 regeneration. Changing this instant
re-bakes those snapshots.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import auth_log

_FROZEN_NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze_auth_log_now(monkeypatch):
    monkeypatch.setattr(auth_log, "_now", lambda: _FROZEN_NOW)
