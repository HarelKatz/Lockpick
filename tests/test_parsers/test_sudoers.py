"""Unit tests for the sudoers parser."""
import os

import pytest

from parsers.sudoers import SudoersParser
from parsers import UploadMetadata

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sudoers")


def _meta() -> UploadMetadata:
    return UploadMetadata(op_id="op1", host_id="host1", file_type="sudoers")


def _load_fixture() -> bytes:
    with open(FIXTURE, "rb") as f:
        return f.read()


def test_parses_real_fixture_min_rules():
    result = SudoersParser().parse(_load_fixture(), _meta())
    assert len(result.sudo_rules_found) == 19


def test_parses_user_rule():
    result = SudoersParser().parse(_load_fixture(), _meta())
    root = next((r for r in result.sudo_rules_found if r.subject == "root"), None)
    assert root is not None
    assert root.subject_type == "user"


def test_parses_group_rule():
    result = SudoersParser().parse(_load_fixture(), _meta())
    wheel = next((r for r in result.sudo_rules_found if r.subject == "wheel"), None)
    assert wheel is not None
    assert wheel.subject_type == "group"


def test_nopasswd_flag():
    result = SudoersParser().parse(_load_fixture(), _meta())
    # FULLTIMERS has NOPASSWD
    ft = next((r for r in result.sudo_rules_found if r.subject == "FULLTIMERS"), None)
    assert ft is not None
    assert ft.nopasswd is True


def test_no_nopasswd_for_bob():
    result = SudoersParser().parse(_load_fixture(), _meta())
    bob = next((r for r in result.sudo_rules_found if r.subject == "bob"), None)
    assert bob is not None
    assert bob.nopasswd is False


def test_run_as_extracted():
    result = SudoersParser().parse(_load_fixture(), _meta())
    bob = next((r for r in result.sudo_rules_found if r.subject == "bob"), None)
    assert bob is not None
    assert bob.run_as == "OP"


def test_skips_defaults():
    result = SudoersParser().parse(_load_fixture(), _meta())
    defaults_rules = [r for r in result.sudo_rules_found if r.subject.startswith("Defaults")]
    assert defaults_rules == []


def test_raw_line_preserved():
    result = SudoersParser().parse(_load_fixture(), _meta())
    root = next((r for r in result.sudo_rules_found if r.subject == "root"), None)
    assert root is not None
    assert root.raw_line is not None
    assert "root" in root.raw_line


def test_continuation_lines_joined():
    # operator rule uses backslash continuation
    result = SudoersParser().parse(_load_fixture(), _meta())
    op = next((r for r in result.sudo_rules_found if r.subject == "operator"), None)
    assert op is not None
    # commands should include content from continuation lines
    assert "KILL" in op.commands or "DUMPS" in op.commands or "SHUTDOWN" in op.commands


def test_group_prefix_stripped():
    content = b"%devs ALL=(ALL) /usr/bin/git\n"
    result = SudoersParser().parse(content, _meta())
    assert len(result.sudo_rules_found) == 1
    rule = result.sudo_rules_found[0]
    assert rule.subject == "devs"
    assert rule.subject_type == "group"


def test_no_parens_rule():
    content = b"jack CSNETS = ALL\n"
    result = SudoersParser().parse(content, _meta())
    assert len(result.sudo_rules_found) == 1
    rule = result.sudo_rules_found[0]
    assert rule.subject == "jack"
    assert rule.run_as == "ALL"


def test_empty_file():
    result = SudoersParser().parse(b"", _meta())
    assert result.sudo_rules_found == []
    assert result.warnings == []
    assert result.stats == {"rules": 0}


def test_stats_counts():
    result = SudoersParser().parse(_load_fixture(), _meta())
    assert result.stats["rules"] == 19
