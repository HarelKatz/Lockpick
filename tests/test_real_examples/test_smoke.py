"""Smoke tests: every registered parser must not crash on any real sample.

Parametrized over every file under real_examples/<type>/ where <type> is a key
in PARSER_REGISTRY. Asserts the parser returns a ParseResult without raising.
Subdirs for unregistered file_types (future phases) are silently skipped.
"""
from __future__ import annotations

import pytest

from parsers import ParseResult, UploadMetadata

from .helpers import iter_sample_files, parser_for, sample_id

_SAMPLES = iter_sample_files(only_registered=True)


@pytest.mark.parametrize(
    "file_type,sample_path",
    _SAMPLES,
    ids=[sample_id(t, p) for t, p in _SAMPLES],
)
def test_parser_does_not_crash(file_type: str, sample_path):
    parser = parser_for(file_type)
    content = sample_path.read_bytes()
    metadata = UploadMetadata(
        op_id="test-op",
        host_id="test-host",
        file_type=file_type,
        filename=sample_path.name,
    )
    result = parser.parse(content, metadata)
    assert isinstance(result, ParseResult)
