"""Parser for `ip neigh` (ARP table via netlink) output.

Each entry says: "the upload host saw IP X at L2 on interface Y".  This is
indicator-confidence — a presence signal, not proof of any L7 connection.
"""
from __future__ import annotations

import gzip
import re

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata

# `10.0.0.2 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE`
# `fe80::1 dev eth0 lladdr aa:bb:cc:dd:ee:ff router REACHABLE`
_NEIGH_RE = re.compile(
    r"^(?P<ip>[0-9a-fA-F.:]+)\s+dev\s+\S+(?:\s+lladdr\s+\S+)?(?:\s+\S+)*\s*$"
)


class IpNeighParser(BaseParser):
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

        seen = 0
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            m = _NEIGH_RE.match(line)
            if not m:
                continue
            ip = m.group("ip")
            # FAILED entries with no lladdr still parse — keep them; the IP
            # is still a known peer that the upload host tried to reach.
            result.connections_found.append(ConnectionData(
                src_ip="__upload_host__",
                dst_ip=ip,
                connection_type="unknown",
                direction_context="from_src_logs",
                raw_line=raw_line[:512],
            ))
            seen += 1

        result.stats = {"neighbors": seen}
        return result
