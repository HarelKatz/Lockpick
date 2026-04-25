"""Unit tests for the env_output parser."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import UploadMetadata
from parsers.env_output import EnvOutputParser

FIXTURES = Path(__file__).parent.parent / "fixtures" / "env_output"


def _meta(username: str | None = None) -> UploadMetadata:
    return UploadMetadata(
        op_id="op1", host_id="host1", file_type="env_output", username=username
    )


def test_harvests_secret_keys_only():
    """Fixture has 7 secret keys (AWS x2, DATABASE_URL, GITHUB_TOKEN,
    MY_API_KEY, APP_PASSWORD, SESSION_SECRET) and ignores PATH/HOME/etc."""
    content = (FIXTURES / "env.out").read_bytes()
    result = EnvOutputParser().parse(content, _meta())
    assert len(result.credentials_found) == 7

    names = {c.name for c in result.credentials_found}
    assert names == {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "DATABASE_URL",
        "GITHUB_TOKEN",
        "MY_API_KEY",
        "APP_PASSWORD",
        "SESSION_SECRET",
    }


def test_harmless_keys_skipped():
    """PATH, HOME, LANG, SHELL, LOGNAME, PWD, LD_LIBRARY_PATH, XDG_*, SSH_CLIENT skipped."""
    content = (FIXTURES / "env.out").read_bytes()
    result = EnvOutputParser().parse(content, _meta())
    names = {c.name for c in result.credentials_found}
    for skipped in ("PATH", "HOME", "LANG", "SHELL", "LOGNAME", "PWD",
                    "LD_LIBRARY_PATH", "XDG_RUNTIME_DIR", "SSH_CLIENT"):
        assert skipped not in names


def test_username_from_metadata_attached():
    content = (FIXTURES / "env.out").read_bytes()
    result = EnvOutputParser().parse(content, _meta(username="alice"))
    for c in result.credentials_found:
        assert c.username == "alice"


def test_all_creds_are_password_type():
    content = (FIXTURES / "env.out").read_bytes()
    result = EnvOutputParser().parse(content, _meta())
    for c in result.credentials_found:
        assert c.cred_type == "password"
        assert c.relationship_type == "found_on_disk"


def test_stats_count():
    content = (FIXTURES / "env.out").read_bytes()
    result = EnvOutputParser().parse(content, _meta())
    assert result.stats == {"credentials": 7}


def test_empty_file():
    result = EnvOutputParser().parse(b"", _meta())
    assert result.credentials_found == []
    assert result.stats == {"credentials": 0}


def test_dedupe_repeated_key_value_pairs():
    content = b"MY_TOKEN=abc\nMY_TOKEN=abc\nMY_TOKEN=def\n"
    result = EnvOutputParser().parse(content, _meta())
    # Two distinct values
    assert len(result.credentials_found) == 2


def test_continuation_lines_skipped():
    """Multi-line env values: only the first line counts; trailing lines
    that do not match `KEY=` syntax are dropped."""
    content = b"FOO=hello world\nbar continuation line\nMY_TOKEN=secret\n"
    result = EnvOutputParser().parse(content, _meta())
    # FOO is filtered (not a secret key); only MY_TOKEN counts.
    assert len(result.credentials_found) == 1
    assert result.credentials_found[0].name == "MY_TOKEN"
