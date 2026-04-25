"""Parser for `arp -an` / `arp -a` / Linux `/proc/net/arp` output.

Same semantics as ip_neigh: each entry is an L2 sighting of an IP, indicator
confidence only.
"""
from __future__ import annotations

import gzip
import re

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata

# `arp -an` BSD/Linux format:  `? (10.0.0.2) at aa:bb:cc:dd:ee:ff [ether] on eth0`
_ARP_AN_RE = re.compile(
    r"^\S+\s+\((?P<ip>[0-9a-fA-F.:]+)\)\s+at\s+\S+"
)
# `arp -a`/Linux columnar:  `Address  HWtype  HWaddress  Flags Mask  Iface`
# Data row example:         `192.168.71.254  ether  00:50:56:fe:7a:b4  C   ens33`
_ARP_COL_RE = re.compile(
    r"^(?P<ip>\d{1,3}(?:\.\d{1,3}){3})\s+\S+\s+(?:\S+)\s+\S+(?:\s+\S+)*\s*$"
)
# `/proc/net/arp`: `IP address  HW type  Flags  HW address  Mask  Device`
_PROC_ARP_RE = re.compile(
    r"^(?P<ip>\d{1,3}(?:\.\d{1,3}){3})\s+0x[0-9a-fA-F]+\s+0x[0-9a-fA-F]+\s+"
    r"(?P<mac>[0-9a-fA-F:]+)\s+\S+\s+\S+\s*$"
)


class ArpParser(BaseParser):
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
            # Skip header rows
            low = line.lower()
            if low.startswith(("address", "ip address")) or "hwaddress" in low:
                continue

            ip = None
            for re_obj in (_ARP_AN_RE, _PROC_ARP_RE, _ARP_COL_RE):
                m = re_obj.match(line)
                if m:
                    ip = m.group("ip")
                    break
            if not ip:
                continue

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
