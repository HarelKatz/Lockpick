"""Registry aliases for RHEL/CentOS log filenames → AuthLogParser."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers.auth_log import AuthLogParser
from parsers.registry import PARSER_REGISTRY


def test_secure_aliases_authlog():
    assert PARSER_REGISTRY["secure"] is AuthLogParser


def test_syslog_aliases_authlog():
    assert PARSER_REGISTRY["syslog"] is AuthLogParser


def test_messages_aliases_authlog():
    assert PARSER_REGISTRY["messages"] is AuthLogParser
