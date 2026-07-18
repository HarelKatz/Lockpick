"""Architecture Rule #27: an authorized_keys `from=` ACL edge is never `confirmed`.

A `from=` ACL is the destination host asserting who MAY connect in, so the parser
emits direction_context="from_dst_logs" with dst_ip="__upload_host__". That is one
`credential_id` away from the `confirmed` branch of _classify_connection_evidence —
and the key sits on the very same authorized_keys line, so resolving it later would
be a natural change to make. What stops a config assertion being promoted to the
strongest confidence tier is precedence: "authorized_keys" is in
_INDICATOR_PARSER_TYPES and that check runs FIRST.

These tests pin that precedence directly, including the hostile case where a
credential_id IS present — the arrangement a future change would produce.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from models import ConnectionRecord
from services.graph_builder import (
    _INDICATOR_PARSER_TYPES,
    _classify_connection_evidence,
)


def _acl_record(**overrides) -> ConnectionRecord:
    """A ConnectionRecord shaped exactly as the authorized_keys parser emits one."""
    defaults = dict(
        id="r1",
        op_id="op1",
        src_ip="10.0.0.5",
        dst_ip="10.0.0.9",
        direction_context="from_dst_logs",
        connection_type="ssh",
        auth_method="publickey",
        source_file="abc_authorized_keys",
        parser_file_type="authorized_keys",
        credential_id=None,
    )
    defaults.update(overrides)
    return ConnectionRecord(**defaults)


def test_authorized_keys_is_registered_as_an_indicator_type():
    assert "authorized_keys" in _INDICATOR_PARSER_TYPES


def test_acl_edge_classifies_as_indicator():
    ev_type, confidence = _classify_connection_evidence(_acl_record())
    assert confidence == "indicator"
    assert ev_type == "authorized_keys"


def test_acl_edge_stays_indicator_even_with_a_credential_resolved():
    """The hostile case: from_dst_logs + credential_id is exactly the confirmed branch.

    Drop "authorized_keys" from _INDICATOR_PARSER_TYPES and this becomes "confirmed" —
    which is the silent promotion Rule #27 exists to prevent.
    """
    ev_type, confidence = _classify_connection_evidence(
        _acl_record(credential_id="cred-1")
    )
    assert confidence == "indicator", (
        "an authorized_keys ACL asserts permission, never that a login happened"
    )
    assert ev_type == "authorized_keys"


def test_a_real_connection_log_still_reaches_confirmed():
    """Guard the guard: the confirmed branch must still work for genuine log evidence."""
    ev_type, confidence = _classify_connection_evidence(
        _acl_record(parser_file_type="auth_log", credential_id="cred-1")
    )
    assert (ev_type, confidence) == ("connection_log", "confirmed")
