"""Helpers for parametrized tests against real_examples/.

Separate from tests/test_parsers/ (canonical behavior): this layer runs every
registered parser against every real sample and locks in regression coverage
via side-by-side `<file>.expected.json` snapshots.
"""
from __future__ import annotations

import os
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Iterator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

from parsers import BaseParser, ParseResult
from parsers.registry import PARSER_REGISTRY

REAL_EXAMPLES = Path(__file__).resolve().parent.parent.parent / "real_examples"

_SNAPSHOT_SUFFIX = ".expected.json"
_RAW_LINE_MAX = 200
_VALUE_PREFIX_LEN = 40


def parser_for(file_type: str) -> BaseParser:
    cls = PARSER_REGISTRY[file_type]
    return cls()


def _is_sample_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.name.endswith(_SNAPSHOT_SUFFIX):
        return False
    return True


def iter_sample_files(only_registered: bool = True) -> list[tuple[str, Path]]:
    """Yield (file_type, sample_path) for each file in real_examples/<type>/.

    Files ending in .expected.json are excluded (they are snapshots, not inputs).
    Subdirs whose name is not in PARSER_REGISTRY are skipped when only_registered=True.
    """
    out: list[tuple[str, Path]] = []
    if not REAL_EXAMPLES.is_dir():
        return out
    for type_dir in sorted(REAL_EXAMPLES.iterdir()):
        if not type_dir.is_dir():
            continue
        file_type = type_dir.name
        if only_registered and file_type not in PARSER_REGISTRY:
            continue
        for sample in sorted(type_dir.iterdir()):
            if _is_sample_file(sample):
                out.append((file_type, sample))
    return out


def iter_snapshotted_files() -> list[tuple[str, Path, Path]]:
    """Yield (file_type, sample_path, snapshot_path) for samples that already have a .expected.json sibling."""
    out: list[tuple[str, Path, Path]] = []
    for file_type, sample in iter_sample_files(only_registered=True):
        snapshot = sample.with_name(sample.name + _SNAPSHOT_SUFFIX)
        if snapshot.is_file():
            out.append((file_type, sample, snapshot))
    return out


def sample_id(file_type: str, sample_path: Path) -> str:
    return f"{file_type}/{sample_path.name}"


def _truncate(s: str | None, n: int) -> str | None:
    if s is None:
        return None
    return s if len(s) <= n else s[:n]


def _serialize_host(h) -> dict:
    return {
        "ip_address": h.ip_address,
        "nickname": h.nickname,
        "aliases": sorted(h.aliases),
    }


def _serialize_credential(c) -> dict:
    value = c.value or ""
    return {
        "cred_type": c.cred_type,
        "name": c.name,
        "username": c.username,
        "relationship_type": c.relationship_type,
        "value_length": len(value),
        "value_prefix": value[:_VALUE_PREFIX_LEN],
    }


def _serialize_connection(c) -> dict:
    return {
        "src_ip": c.src_ip,
        "dst_ip": c.dst_ip,
        "src_user": c.src_user,
        "dst_user": c.dst_user,
        "connection_type": c.connection_type,
        "direction_context": c.direction_context,
        "auth_method": c.auth_method,
        "credential_fingerprint": c.credential_fingerprint,
        "timestamp": c.timestamp,
        "raw_line": _truncate(c.raw_line, _RAW_LINE_MAX),
    }


def _serialize_pattern(p) -> dict:
    return {"aliases": list(p.aliases), "username": p.username}


def _serialize_sudo_rule(r) -> dict:
    return {
        "subject": r.subject,
        "subject_type": r.subject_type,
        "run_as": r.run_as,
        "commands": r.commands,
        "nopasswd": r.nopasswd,
        "raw_line": _truncate(r.raw_line, _RAW_LINE_MAX),
    }


def _serialize_host_user(t: tuple) -> list:
    # tuple (username, shell, home_dir) → list for JSON
    return list(t)


def snapshot_from_result(result: ParseResult) -> dict:
    """Canonical, order-stable dict representation of a ParseResult for snapshotting.

    - credentials are serialized without full value (prefix + length only)
    - raw_line fields are truncated to 200 chars
    - every list is sorted by a stable key so parser iteration order doesn't leak
    """
    hosts = sorted(
        (_serialize_host(h) for h in result.hosts_found),
        key=lambda d: (d["ip_address"], d["nickname"] or ""),
    )
    credentials = sorted(
        (_serialize_credential(c) for c in result.credentials_found),
        key=lambda d: (
            d["cred_type"],
            d["name"] or "",
            d["username"] or "",
            d["relationship_type"],
            d["value_prefix"],
        ),
    )
    connections = sorted(
        (_serialize_connection(c) for c in result.connections_found),
        key=lambda d: (
            d["src_ip"] or "",
            d["dst_ip"] or "",
            d["src_user"] or "",
            d["dst_user"] or "",
            d["timestamp"] or "",
            d["raw_line"] or "",
        ),
    )
    host_users = sorted(
        (_serialize_host_user(t) for t in result.host_users_found),
        key=lambda lst: tuple((x or "") for x in lst),
    )
    patterns = sorted(
        (_serialize_pattern(p) for p in result.patterns_found),
        key=lambda d: (tuple(d["aliases"]), d["username"] or ""),
    )
    sudo_rules = sorted(
        (_serialize_sudo_rule(r) for r in result.sudo_rules_found),
        key=lambda d: (d["subject"], d["subject_type"], d["run_as"], d["commands"]),
    )
    return {
        "hosts_found": hosts,
        "credentials_found": credentials,
        "connections_found": connections,
        "host_users_found": host_users,
        "patterns_found": patterns,
        "sudo_rules_found": sudo_rules,
        "warnings": list(result.warnings),
        "stats": dict(result.stats),
    }
