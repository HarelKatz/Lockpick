"""Composable topology-dict builders.

Each builder returns a *partial* topology dict (the shape the ``OpBuilder``
consumes). Shapes compose by :func:`merge` (dict-merge: hosts unioned by
nickname, connections/credentials/credential-links concatenated).

Generated hosts carry ``ip=None``; call :func:`assign_ips` on the composed
topology to fill unique synthetic IPs before applying it. Declared IPs (e.g.
from a real fixture topology) are preserved.
"""
from __future__ import annotations

import base64
from typing import Any, Iterable, Optional, Union

# Synthetic IPs live in 10.90.0.0/16 so they never collide with the real
# fixture networks (10.10.0.0/16).
_IP_BLOCK = 90

Names = Union[int, Iterable[str]]


def _names(spec: Names, prefix: str) -> list[str]:
    if isinstance(spec, int):
        return [f"{prefix}{i}" for i in range(spec)]
    return list(spec)


def host(nickname: str, *, ip: Optional[str] = None, files: Optional[list] = None) -> dict:
    return {"nickname": nickname, "ip": ip, "files": files or []}


def conn(
    src: str,
    dst: str,
    *,
    src_user: Optional[str] = None,
    dst_user: Optional[str] = None,
    auth_method: Optional[str] = "password",
    connection_type: str = "ssh",
    direction_context: str = "from_dst_logs",
    timestamp: Optional[str] = None,
    source_file: str = "shapes",
) -> dict:
    return {
        "src": src,
        "dst": dst,
        "src_user": src_user,
        "dst_user": dst_user,
        "auth_method": auth_method,
        "connection_type": connection_type,
        "direction_context": direction_context,
        "timestamp": timestamp,
        "source_file": source_file,
    }


def _topo(
    hosts: Optional[list] = None,
    connections: Optional[list] = None,
    credentials: Optional[list] = None,
    credential_links: Optional[list] = None,
) -> dict:
    return {
        "hosts": hosts or [],
        "connections": connections or [],
        "credentials": credentials or [],
        "credential_links": credential_links or [],
    }


# ── Connectivity shapes ─────────────────────────────────────────────────────

def linear_chain(spec: Names, *, prefix: str = "n", **kw) -> dict:
    """A → B → C → …  (n hosts, n-1 connections)."""
    names = _names(spec, prefix)
    conns = [conn(names[i], names[i + 1], **kw) for i in range(len(names) - 1)]
    return _topo(hosts=[host(n) for n in names], connections=conns)


def star(center: str, leaves: Names, *, prefix: str = "leaf", **kw) -> dict:
    """One center connected to every leaf."""
    leaf_names = _names(leaves, prefix)
    conns = [conn(center, leaf, **kw) for leaf in leaf_names]
    return _topo(hosts=[host(center)] + [host(n) for n in leaf_names], connections=conns)


def diamond(
    *, top: str = "d_top", left: str = "d_left", right: str = "d_right", bottom: str = "d_bottom", **kw
) -> dict:
    """top → {left, right} → bottom (a converging/diverging pair of paths)."""
    conns = [
        conn(top, left, **kw),
        conn(top, right, **kw),
        conn(left, bottom, **kw),
        conn(right, bottom, **kw),
    ]
    return _topo(hosts=[host(top), host(left), host(right), host(bottom)], connections=conns)


def mesh(spec: Names, *, prefix: str = "m", **kw) -> dict:
    """Fully connected: one connection per unordered pair."""
    names = _names(spec, prefix)
    conns = [
        conn(names[i], names[j], **kw)
        for i in range(len(names))
        for j in range(i + 1, len(names))
    ]
    return _topo(hosts=[host(n) for n in names], connections=conns)


def password_conn(src: str, dst: str, **kw) -> dict:
    """A single password-authenticated connection between two fresh hosts."""
    kw.setdefault("auth_method", "password")
    return _topo(hosts=[host(src), host(dst)], connections=[conn(src, dst, **kw)])


def undated_edge(src: str, dst: str, **kw) -> dict:
    """A connection with no timestamp (the always-shown 'undated' edge case)."""
    kw["timestamp"] = None
    return _topo(hosts=[host(src), host(dst)], connections=[conn(src, dst, **kw)])


def isolated_host(nickname: str, *, ip: Optional[str] = None) -> dict:
    """A host with no connections (an isolated graph node)."""
    return _topo(hosts=[host(nickname, ip=ip)])


def self_loop(nickname: str, **kw) -> dict:
    """A connection from a host to itself (self-loop edge case, Rule #23)."""
    return _topo(hosts=[host(nickname)], connections=[conn(nickname, nickname, **kw)])


def key_pivot(src: str, dst: str, *, src_user: str = "root", dst_user: str = "root", key: Optional[str] = None) -> dict:
    """A confirmed key-match pivot src → dst, synthesized without real keygen.

    Uses one public-key credential linked ``found_on_disk`` on ``src`` and
    ``authorized_key`` on ``dst``. The key blob is derived from the (src, dst)
    pair so each pivot gets a DISTINCT fingerprint — independent pivots never
    cross-link in the fingerprint index.
    """
    alias = f"kp_{src}_{dst}"
    blob = base64.b64encode(f"lockpick-keypivot-{src}-{dst}".encode()).decode()
    value = f"ssh-ed25519 {blob} {key or alias}"
    return _topo(
        hosts=[host(src), host(dst)],
        credentials=[{"key": alias, "cred_type": "public_key", "value": value, "name": key or alias}],
        credential_links=[
            {"credential": alias, "host": src, "relationship_type": "found_on_disk", "username": src_user},
            {"credential": alias, "host": dst, "relationship_type": "authorized_key", "username": dst_user},
        ],
    )


# ── Composition + finalization ──────────────────────────────────────────────

def merge(*parts: dict) -> dict:
    """Dict-merge topology parts: union hosts by nickname, concat the rest."""
    hosts_by_nick: dict[str, dict] = {}
    result = _topo()
    for part in parts:
        for h in part.get("hosts", []):
            existing = hosts_by_nick.get(h["nickname"])
            if existing is None:
                new = host(h["nickname"], ip=h.get("ip"), files=list(h.get("files", [])))
                hosts_by_nick[h["nickname"]] = new
                result["hosts"].append(new)
            else:
                existing["ip"] = existing.get("ip") or h.get("ip")
                existing["files"].extend(h.get("files", []))
        for keyname in ("connections", "credentials", "credential_links"):
            result[keyname].extend(part.get(keyname, []))
    return result


def assign_ips(topology: dict, *, block: int = _IP_BLOCK) -> dict:
    """Fill a unique IP for every host lacking one; preserve declared IPs.

    Mutates and returns ``topology``. Synthetic IPs come from ``10.<block>.x.x``.
    """
    used = {h["ip"] for h in topology.get("hosts", []) if h.get("ip")}
    counter = 0

    def _next() -> str:
        nonlocal counter
        while True:
            ip = f"10.{block}.{counter // 254}.{counter % 254 + 1}"
            counter += 1
            if ip not in used:
                used.add(ip)
                return ip

    for h in topology.get("hosts", []):
        if not h.get("ip"):
            h["ip"] = _next()
    return topology
