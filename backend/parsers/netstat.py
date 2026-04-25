"""Parser for `netstat -an` / `netstat -tunp` output.

Emits one ConnectionData per ESTABLISHED inet socket — these are observed
TCP connections.  Listening sockets, UNIX sockets, and routing/interface
output are ignored.
"""
from __future__ import annotations

import gzip
import re

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata


def _split_addr_port(token: str) -> tuple[str, str | None]:
    """Split `host:port` or `[ipv6]:port`.

    Returns (host, port) where port may be a service name or numeric.  IPv6
    addresses surrounded in `[]` are unwrapped.  If there's no port,
    returns (token, None).
    """
    token = token.strip()
    if not token:
        return ("", None)
    # IPv6 [::]:port style
    if token.startswith("["):
        m = re.match(r"^\[(?P<host>[^\]]+)\](?::(?P<port>\S+))?$", token)
        if m:
            return (m.group("host"), m.group("port"))
        return (token, None)
    # `host:port` — but host may itself contain dots; rsplit on first colon from right.
    if ":" in token:
        host, _, port = token.rpartition(":")
        return (host, port or None)
    return (token, None)


def _is_skippable_host(host: str) -> bool:
    """Skip wildcard / unconnected entries and obvious junk."""
    if not host:
        return True
    if host in {"*", "0.0.0.0", "::", "[::]"}:
        return True
    return False


class NetstatParser(BaseParser):
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
        in_unix = False
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line:
                continue

            # Switch sections — once we're in UNIX/route output, stop emitting.
            stripped = line.strip()
            low = stripped.lower()
            if (
                "unix domain sockets" in low
                or low.startswith("kernel ip routing table")
                or low.startswith("kernel ipv6 routing table")
                or "active multipath ipv4" in low
            ):
                in_unix = True
                continue
            if (
                "active internet connections" in low
                or low.startswith("active lan connections")
            ):
                in_unix = False
                continue
            if in_unix:
                continue

            # Skip non-tcp/udp lines (raw, sctp, etc.) — we want established TCP.
            if not stripped.lower().startswith(("tcp", "udp")):
                continue

            parts = stripped.split()
            # Need at least: Proto Recv Send Local Foreign State
            if len(parts) < 6:
                continue

            proto = parts[0].lower()
            # Only TCP carries 'ESTABLISHED' as a meaningful evidence signal.
            if not proto.startswith("tcp"):
                continue

            # Find the State token — it's typically the 6th column on Linux,
            # but BSD has a different layout.  Look for ESTABLISHED anywhere.
            if "ESTABLISHED" not in parts:
                continue

            # Linux column layout:
            #   tcp 0 0 LocalAddr ForeignAddr State [extras...]
            foreign = parts[4]
            foreign_host, _ = _split_addr_port(foreign)

            if _is_skippable_host(foreign_host):
                continue

            # Local side is always the upload host — local-side hostnames in
            # netstat output are often truncated (`localhost.localdo`) and
            # would create phantom hosts if emitted as src_ip.  The pipeline
            # routes the sentinel back to the actual upload host.
            result.connections_found.append(ConnectionData(
                src_ip="__upload_host__",
                dst_ip=foreign_host,
                connection_type="unknown",
                direction_context="from_src_logs",
                raw_line=raw_line[:512],
            ))
            connections += 1

        result.stats = {"connections": connections}
        return result
