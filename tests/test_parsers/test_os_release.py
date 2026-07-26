"""Unit tests for the os_release parser."""
import gzip
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.os_release import OsReleaseParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "os_release"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="os_release")


def _parse(name: str):
    return OsReleaseParser().parse((FIXTURES / name).read_bytes(), _meta())


def test_pretty_name_becomes_the_os_version():
    result = _parse("os-release")
    assert result.system_info is not None
    assert result.system_info.os_version == "Ubuntu 22.04.3 LTS"


def test_kernel_version_is_never_set_from_os_release():
    """os-release describes the distro; the kernel comes from uname only."""
    result = _parse("os-release")
    assert result.system_info.kernel_version is None


def test_falls_back_to_name_and_version_id_without_pretty_name():
    result = _parse("os-release-no-pretty")
    assert result.system_info.os_version == "Alpine Linux 3.18.4"


def test_emits_no_hosts_or_connections():
    """Inventory metadata only — this parser must never create graph entities."""
    result = _parse("os-release")
    assert result.hosts_found == []
    assert result.connections_found == []
    assert result.credentials_found == []


def test_stats_report_the_fields_read():
    result = _parse("os-release")
    assert result.stats.get("os_version") == 1


def test_gzipped_content_is_decompressed():
    raw = (FIXTURES / "os-release").read_bytes()
    result = OsReleaseParser().parse(gzip.compress(raw), _meta())
    assert result.system_info.os_version == "Ubuntu 22.04.3 LTS"


def test_empty_file_warns_and_does_not_crash():
    result = OsReleaseParser().parse(b"", _meta())
    assert result.system_info is None
    assert result.warnings


def test_garbage_does_not_crash():
    result = OsReleaseParser().parse(b"\x00\xff not an os-release at all", _meta())
    assert result.system_info is None
