"""Unit tests for the uname_output parser."""
import gzip
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.uname_output import UnameOutputParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "uname_output"


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="uname_output")


def _parse(name: str):
    return UnameOutputParser().parse((FIXTURES / name).read_bytes(), _meta())


def test_uname_a_yields_the_kernel_release():
    result = _parse("uname-a.out")
    assert result.system_info is not None
    assert result.system_info.kernel_version == "5.15.0-88-generic"


def test_uname_a_never_sets_os_version():
    """`uname` knows the kernel, not the distro — leaving os_version None is what
    lets a later /etc/os-release upload fill it (the pipeline only fills blanks)."""
    result = _parse("uname-a.out")
    assert result.system_info.os_version is None


def test_bare_uname_r_output_is_accepted():
    result = _parse("uname-r.out")
    assert result.system_info.kernel_version == "6.1.0-13-amd64"


def test_hostname_is_not_emitted_as_a_host():
    """`uname -a` carries the nodename, but turning it into a host record is a
    separate decision — this parser must not create graph entities."""
    result = _parse("uname-a.out")
    assert result.hosts_found == []
    assert result.connections_found == []


def test_gzipped_content_is_decompressed():
    raw = (FIXTURES / "uname-a.out").read_bytes()
    result = UnameOutputParser().parse(gzip.compress(raw), _meta())
    assert result.system_info.kernel_version == "5.15.0-88-generic"


def test_empty_file_warns_and_does_not_crash():
    result = UnameOutputParser().parse(b"", _meta())
    assert result.system_info is None
    assert result.warnings


def test_non_linux_uname_still_yields_a_release():
    content = b"Darwin mac01 23.1.0 Darwin Kernel Version 23.1.0: Mon Oct  9 21:27:27 PDT 2023 arm64\n"
    result = UnameOutputParser().parse(content, _meta())
    assert result.system_info.kernel_version == "23.1.0"


def test_a_line_of_prose_is_rejected_rather_than_guessed():
    """Two tokens with spaces is not a uname line — better no data than wrong data."""
    result = UnameOutputParser().parse(b"command not found\n", _meta())
    assert result.system_info is None
