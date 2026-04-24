"""Snapshot regression tests: parser output on each real sample must match
its committed <sample>.expected.json sibling.

With REGEN_SNAPSHOTS=1 the test writes the snapshot instead of comparing
(covers ALL registered-parser samples when regenerating, not only those that
already have a snapshot).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from parsers import UploadMetadata

from .helpers import (
    iter_sample_files,
    iter_snapshotted_files,
    parser_for,
    sample_id,
    snapshot_from_result,
)

_SNAPSHOT_SUFFIX = ".expected.json"
_REGEN = os.environ.get("REGEN_SNAPSHOTS") == "1"


def _regen_params() -> list[tuple[str, Path, Path]]:
    out: list[tuple[str, Path, Path]] = []
    for file_type, sample in iter_sample_files(only_registered=True):
        snapshot = sample.with_name(sample.name + _SNAPSHOT_SUFFIX)
        out.append((file_type, sample, snapshot))
    return out


_PARAMS = _regen_params() if _REGEN else iter_snapshotted_files()


@pytest.mark.parametrize(
    "file_type,sample_path,snapshot_path",
    _PARAMS,
    ids=[sample_id(t, s) for t, s, _ in _PARAMS],
)
def test_parser_output_matches_snapshot(
    file_type: str, sample_path: Path, snapshot_path: Path
):
    parser = parser_for(file_type)
    content = sample_path.read_bytes()
    metadata = UploadMetadata(
        op_id="test-op",
        host_id="test-host",
        file_type=file_type,
        filename=sample_path.name,
    )
    result = parser.parse(content, metadata)
    actual = snapshot_from_result(result)

    if _REGEN:
        snapshot_path.write_text(
            json.dumps(actual, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        )
        return

    expected = json.loads(snapshot_path.read_text())
    assert actual == expected, (
        f"Parser output for {sample_id(file_type, sample_path)} diverged from snapshot. "
        f"Regenerate with: REGEN_SNAPSHOTS=1 uv run pytest {__file__}"
    )
