"""Tests for auth.log parser."""
import gzip
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers import auth_log
from parsers.auth_log import AuthLogParser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def metadata():
    return UploadMetadata(
        op_id="op1",
        host_id="host1",
        file_type="auth_log",
        filename="auth.log",
    )


def test_parses_accepted_logins(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    # Fixture has exactly 2 Accepted lines and 2 Failed lines; only accepted become connections
    assert len(result.connections_found) == 2
    assert all("Accepted" in c.raw_line for c in result.connections_found)


def test_failed_logins_not_in_connections(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    assert not any("Failed" in c.raw_line for c in result.connections_found)



def test_fingerprint_extracted(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    fps = [c.credential_fingerprint for c in result.connections_found if c.credential_fingerprint]
    assert any("SHA256:abc123" in fp for fp in fps)


def test_all_dst_upload_host(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    assert all(c.dst_ip == "__upload_host__" for c in result.connections_found)
    assert all(c.direction_context == "from_dst_logs" for c in result.connections_found)


def test_stats_populated(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    assert result.stats["accepted_logins"] == 2


def test_gzip_decompressed(metadata):
    content = (FIXTURES / "auth.log").read_bytes()
    gz = gzip.compress(content)
    result = AuthLogParser().parse(gz, metadata)
    assert len(result.connections_found) == 2


def test_empty_file(metadata):
    result = AuthLogParser().parse(b"", metadata)
    assert result.connections_found == []


# ─── Syslog year inference (file-aware; _now() frozen for determinism) ──────────

def _ts_by_user(result):
    return {c.dst_user: c.timestamp for c in result.connections_found}


def test_year_boundary_split(metadata, monkeypatch):
    """A file spanning Dec->Jan must split across two years, not collapse to one."""
    monkeypatch.setattr(auth_log, "_now", lambda: datetime(2026, 2, 1, tzinfo=timezone.utc))
    content = (FIXTURES / "auth_log_year_boundary.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    ts = _ts_by_user(result)
    assert ts["alice"].startswith("2025-12-30")
    assert ts["bob"].startswith("2025-12-31")
    assert ts["carol"].startswith("2026-01-01")
    assert ts["dave"].startswith("2026-01-02")


def test_prior_year_detected(metadata, monkeypatch):
    """Collected mid-January, a log full of December entries is from last year."""
    monkeypatch.setattr(auth_log, "_now", lambda: datetime(2026, 1, 15, tzinfo=timezone.utc))
    content = (FIXTURES / "auth_log_prior_year.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    assert all(v.startswith("2025-12") for v in _ts_by_user(result).values())


def test_current_year_default(metadata, monkeypatch):
    """Entries earlier in the current year keep the current year."""
    monkeypatch.setattr(auth_log, "_now", lambda: datetime(2026, 7, 1, tzinfo=timezone.utc))
    content = (FIXTURES / "auth.log").read_bytes()  # March entries
    result = AuthLogParser().parse(content, metadata)
    assert all(c.timestamp.startswith("2026-03") for c in result.connections_found)


def test_iso_timestamp_year_preserved(metadata, monkeypatch):
    """ISO timestamps carry their own year — never run through inference."""
    monkeypatch.setattr(auth_log, "_now", lambda: datetime(2030, 1, 1, tzinfo=timezone.utc))
    content = (FIXTURES / "edge_cases" / "auth_log_iso_timestamps.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    dated = [c.timestamp for c in result.connections_found if c.timestamp]
    assert dated and all(t.startswith("2024-") for t in dated)


def test_feb29_non_leap_no_crash(metadata, monkeypatch):
    """Feb 29 on a non-leap inferred year drops the timestamp but keeps the login."""
    monkeypatch.setattr(auth_log, "_now", lambda: datetime(2026, 3, 1, tzinfo=timezone.utc))
    content = (FIXTURES / "auth_log_feb29.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    assert len(result.connections_found) == 1
    assert result.connections_found[0].timestamp is None


# ─── journalctl -u ssh coverage (default / short-iso / short-full formats) ──────

def test_journalctl_registered():
    from parsers.registry import PARSER_REGISTRY

    assert PARSER_REGISTRY["journalctl"] is AuthLogParser


def test_journalctl_default_format(metadata, monkeypatch):
    """Default `journalctl -u ssh` is syslog-shaped — parses via the same path."""
    monkeypatch.setattr(auth_log, "_now", lambda: datetime(2026, 7, 1, tzinfo=timezone.utc))
    content = (FIXTURES / "journalctl_default.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    assert {c.dst_user for c in result.connections_found} == {"root", "alice"}
    assert not any("Failed" in c.raw_line for c in result.connections_found)
    root = next(c for c in result.connections_found if c.dst_user == "root")
    assert root.auth_method == "publickey"
    assert root.src_ip == "10.10.0.5"
    assert root.credential_fingerprint == "SHA256:abc123def456"
    assert all(c.timestamp.startswith("2026-03-15") for c in result.connections_found)


def test_journalctl_short_iso_format(metadata):
    """`-o short-iso` timestamps carry a year — preserved, no inference."""
    content = (FIXTURES / "journalctl_short_iso.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    assert {c.dst_user for c in result.connections_found} == {"root", "alice"}
    assert all(c.timestamp.startswith("2024-03-15") for c in result.connections_found)


def test_journalctl_short_full_format(metadata):
    """`-o short-full` prefixes a weekday + full date; both parse, year preserved."""
    content = (FIXTURES / "journalctl_short_full.log").read_bytes()
    result = AuthLogParser().parse(content, metadata)
    assert {c.dst_user for c in result.connections_found} == {"root", "alice"}
    assert all(c.timestamp.startswith("2024-03-15") for c in result.connections_found)
    root = next(c for c in result.connections_found if c.dst_user == "root")
    assert root.auth_method == "publickey"
    assert root.credential_fingerprint == "SHA256:abc123def456"
