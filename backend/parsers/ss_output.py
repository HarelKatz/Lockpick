"""Parser for `ss -tunap` / `ss -a` output — modern socket statistics.

Same shape as netstat: emit one ConnectionData per ESTABLISHED inet socket.
Skip listening, unconnected, and UNIX-domain sockets.
"""
from __future__ import annotations

import gzip
import re

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata


def _split_ss_addr_port(token: str) -> tuple[str, str | None]:
    """Strip ss-style decoration: `127.0.0.53%lo:domain` → ("127.0.0.53", "domain")."""
    token = token.strip()
    if not token:
        return ("", None)
    # Strip `%iface` interface qualifier
    token = re.sub(r"%[A-Za-z0-9._-]+", "", token)
    # IPv6 [::]:port style
    if token.startswith("["):
        m = re.match(r"^\[(?P<host>[^\]]+)\](?::(?P<port>\S+))?$", token)
        if m:
            return (m.group("host"), m.group("port"))
        return (token, None)
    if ":" in token:
        host, _, port = token.rpartition(":")
        return (host, port or None)
    return (token, None)


def _is_skippable_host(host: str) -> bool:
    if not host:
        return True
    if host in {"*", "0.0.0.0", "::", "[::]"}:
        return True
    return False


# `ss` netids we want.
_INET_NETIDS = {"tcp", "udp"}


class SsOutputParser(BaseParser):
    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        if content[:2] == b"\x1f\x8b":
            try:
                content = gzip.decompress(content)
            except Exception as e:
                result.warnings.append(f"Failed to decompress gzip: {e}")
                return result

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        connections = 0
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            # Header rows
            low = line.lower()
            if low.startswith("netid"):
                continue

            parts = line.split()
            if len(parts) < 5:
                continue

            netid = parts[0].lower()
            state = parts[1].upper()

            if netid not in _INET_NETIDS:
                continue
            if state != "ESTAB":
                continue

            # Layout:  netid state recv send local peer [extras...]
            local = parts[4]
            peer = parts[5] if len(parts) > 5 else ""

            peer_host, _ = _split_ss_addr_port(peer)
            if _is_skippable_host(peer_host):
                continue

            result.connections_found.append(ConnectionData(
                src_ip="__upload_host__",
                dst_ip=peer_host,
                connection_type="unknown",
                direction_context="from_src_logs",
                raw_line=raw_line[:512],
            ))
            connections += 1

        result.stats = {"connections": connections}
        return result
