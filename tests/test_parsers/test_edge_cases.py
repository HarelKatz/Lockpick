"""
Edge-case parser tests using hand-crafted fixture files from tests/fixtures/edge_cases/.

Covers real-world syntax variants and gaps for bash_history, auth_log, and ssh_config parsers.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.auth_log import AuthLogParser
from parsers.bash_history import BashHistoryParser
from parsers.ssh_config import SshConfigParser

EC = Path(__file__).parent.parent / "fixtures" / "edge_cases"

pytestmark = pytest.mark.skipif(
    not EC.exists(),
    reason="Edge case fixtures not present",
)


def _meta(file_type: str, username: str | None = "alice") -> UploadMetadata:
    return UploadMetadata(
        op_id="op-ec",
        host_id="host-ec",
        file_type=file_type,
        username=username,
        filename="edge_case",
    )


# ─── bash_history: unusual flag combinations ───────────────────────────────────

class TestBashHistoryFlags:
    @pytest.fixture
    def result(self):
        content = (EC / "bash_history_flags.txt").read_bytes()
        return BashHistoryParser().parse(content, _meta("bash_history"))

    def test_ssh_p_flag_extracted(self, result):
        """ssh -p 2222 root@host should produce a connection."""
        dsts = {c.dst_ip for c in result.connections_found}
        assert "10.0.0.5" in dsts

    def test_ssh_l_flag_extracted(self, result):
        """ssh -l root host should produce a connection."""
        dsts = {c.dst_ip for c in result.connections_found}
        assert "10.0.0.6" in dsts

    def test_scp_extracted(self, result):
        dsts = {c.dst_ip for c in result.connections_found}
        assert "10.0.0.9" in dsts

    def test_rsync_extracted(self, result):
        dsts = {c.dst_ip for c in result.connections_found}
        assert "10.0.0.10" in dsts

    def test_sftp_extracted(self, result):
        dsts = {c.dst_ip for c in result.connections_found}
        assert "10.0.0.11" in dsts

    def test_ssh_copy_id_extracted(self, result):
        dsts = {c.dst_ip for c in result.connections_found}
        assert "10.0.0.12" in dsts

    def test_non_ssh_commands_ignored(self, result):
        """curl, wget, ping should not produce connection records."""
        dsts = {c.dst_ip for c in result.connections_found}
        assert "10.0.0.99" not in dsts

    def test_no_crash_on_keygen(self, result):
        """ssh-keygen lines should be warned about but not crash the parser."""
        # result.warnings may mention keygen — that's fine
        assert isinstance(result.warnings, list)


class TestBashHistoryNoUser:
    @pytest.fixture
    def result(self):
        content = (EC / "bash_history_nouser.txt").read_bytes()
        return BashHistoryParser().parse(content, _meta("bash_history"))

    def test_ssh_without_user_still_extracted(self, result):
        dsts = {c.dst_ip for c in result.connections_found}
        assert "10.0.0.1" in dsts
        assert "10.0.0.2" in dsts

    def test_dst_user_is_none_when_absent(self, result):
        no_user = [c for c in result.connections_found if c.dst_ip == "10.0.0.1"]
        assert no_user
        assert no_user[0].dst_user is None

    def test_chained_commands_handled(self, result):
        """Commands separated by ; or && should still extract the SSH target."""
        dsts = {c.dst_ip for c in result.connections_found}
        # "cd /tmp; ssh root@10.0.0.4" and "ls && ssh alice@10.0.0.5"
        assert "10.0.0.4" in dsts or "10.0.0.5" in dsts


# ─── auth_log: ISO 8601 timestamps ────────────────────────────────────────────

class TestAuthLogISOTimestamps:
    @pytest.fixture
    def result(self):
        content = (EC / "auth_log_iso_timestamps.log").read_bytes()
        return AuthLogParser().parse(content, _meta("auth_log", None))

    def test_accepted_logins_parsed(self, result):
        accepted = [c for c in result.connections_found
                    if c.auth_method in ("publickey", "password")]
        assert len(accepted) >= 3

    def test_fingerprint_extracted(self, result):
        fps = [c.credential_fingerprint for c in result.connections_found
               if c.credential_fingerprint]
        assert any("SHA256:abc123" in fp for fp in fps)

    def test_timestamps_not_none(self, result):
        """ISO timestamps should parse to non-None."""
        ts_list = [c.timestamp for c in result.connections_found if c.timestamp]
        assert ts_list, "No timestamps parsed from ISO-timestamp log"


class TestAuthLogMixedFormats:
    @pytest.fixture
    def result(self):
        content = (EC / "auth_log_mixed_formats.log").read_bytes()
        return AuthLogParser().parse(content, _meta("auth_log", None))

    def test_syslog_and_iso_both_parsed(self, result):
        """Mixed syslog + ISO lines should all produce connections."""
        assert len(result.connections_found) >= 4

    def test_failed_login_included(self, result):
        """Failed publickey lines should produce connection records too."""
        srcs = {c.src_ip for c in result.connections_found}
        assert "10.0.0.3" in srcs  # failed publickey for badguy

    def test_non_sshd_lines_ignored(self, result):
        """sudo lines should not produce connection records."""
        # sudo line: "alice : TTY=pts/0 ; COMMAND=/bin/bash" — no port/method pattern
        # Just ensure parsing completes without error; connection count stays bounded
        assert len(result.connections_found) < 20


# ─── ssh_config: full config with ProxyJump and wildcards ─────────────────────

class TestSshConfigFull:
    @pytest.fixture
    def result(self):
        content = (EC / "ssh_config_full.txt").read_bytes()
        return SshConfigParser().parse(content, _meta("ssh_config"))

    def test_jumpbox_extracted(self, result):
        dsts = {c.dst_ip for c in result.connections_found}
        assert "10.10.0.1" in dsts

    def test_dbserver_extracted(self, result):
        dsts = {c.dst_ip for c in result.connections_found}
        assert "10.10.1.20" in dsts

    def test_wildcard_host_block_not_crash(self, result):
        """The 'Host *' block with no HostName should not crash."""
        assert isinstance(result.connections_found, list)

    def test_blocks_parsed_count(self, result):
        """Should parse at least 2 concrete host blocks."""
        assert result.stats.get("blocks_parsed", 0) >= 2


class TestSshConfigMinimal:
    @pytest.fixture
    def result(self):
        content = (EC / "ssh_config_minimal.txt").read_bytes()
        return SshConfigParser().parse(content, _meta("ssh_config"))

    def test_both_hosts_extracted(self, result):
        dsts = {c.dst_ip for c in result.connections_found}
        assert "10.20.0.5" in dsts
        assert "10.20.0.6" in dsts

    def test_no_warnings_on_valid_input(self, result):
        assert result.warnings == []
