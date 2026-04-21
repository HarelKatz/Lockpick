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


def test_parses_user_rule():
    result = SudoersParser().parse(_load_fixture(), _meta())
    alice = next((r for r in result.sudo_rules_found if r.subject == "alice"), None)
    assert alice is not None
    assert alice.subject_type == "user"
    assert alice.nopasswd is True
    assert "/bin/bash" in alice.commands


def test_parses_group_rule():
    result = SudoersParser().parse(_load_fixture(), _meta())
    sudo_group = next((r for r in result.sudo_rules_found if r.subject == "sudo"), None)
    assert sudo_group is not None
    assert sudo_group.subject_type == "group"
    assert sudo_group.nopasswd is True


def test_skips_defaults():
    result = SudoersParser().parse(_load_fixture(), _meta())
    # Defaults lines should not generate rules
    default_rules = [r for r in result.sudo_rules_found if r.subject.startswith("Defaults")]
    assert default_rules == []


def test_raw_line_preserved():
    result = SudoersParser().parse(_load_fixture(), _meta())
    alice = next((r for r in result.sudo_rules_found if r.subject == "alice"), None)
    assert alice is not None
    assert alice.raw_line is not None
    assert "alice" in alice.raw_line
    assert "NOPASSWD:" in alice.raw_line


def test_run_as_extracted():
    result = SudoersParser().parse(_load_fixture(), _meta())
    alice = next((r for r in result.sudo_rules_found if r.subject == "alice"), None)
    assert alice is not None
    assert alice.run_as == "root"


def test_group_prefix_stripped():
    content = b"%devs ALL=(ALL) /usr/bin/git\n"
    result = SudoersParser().parse(content, _meta())
    assert len(result.sudo_rules_found) == 1
    rule = result.sudo_rules_found[0]
    assert rule.subject == "devs"
    assert rule.subject_type == "group"


def test_no_nopasswd_for_bob():
    result = SudoersParser().parse(_load_fixture(), _meta())
    bob = next((r for r in result.sudo_rules_found if r.subject == "bob"), None)
    assert bob is not None
    assert bob.nopasswd is False


def test_empty_file():
    result = SudoersParser().parse(b"", _meta())
    assert result.sudo_rules_found == []
    assert result.warnings == []
    assert result.stats == {"rules": 0}


def test_stats_counts():
    result = SudoersParser().parse(_load_fixture(), _meta())
    # root, %admin, alice, bob, %sudo = 5 rules
    assert result.stats["rules"] == 5
