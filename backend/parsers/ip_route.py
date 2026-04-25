"""Parser for `ip route` / `route -n` / `netstat -r` output — gateway extraction.

We only care about the default gateway IP; subnets and link-local routes are
just network topology, not pivot targets.  Emits one HostData per unique
gateway IP found.  No ConnectionData — gateways are observed network peers,
not connections we made.
"""
from __future__ import annotations

import gzip
import ipaddress
import re

from parsers import BaseParser, HostData, ParseResult, UploadMetadata

# `ip route` style: `default via 10.0.0.1 dev eth0 proto dhcp metric 100`
# Also matches lines like `10.0.0.0/24 via 10.0.0.1 dev eth0` (next-hop on a
# specific subnet).
_VIA_RE = re.compile(r"\bvia\s+(?P<gw>[0-9a-fA-F.:]+)\b")

# `route -n` numeric output:  `0.0.0.0   10.0.0.1   0.0.0.0  UG  ...`
_ROUTE_RE = re.compile(
    r"^(?P<dst>[0-9.]+)\s+(?P<gw>[0-9.]+)\s+\S+\s+(?P<flags>\S+)"
)


def _looks_like_real_gateway(addr: str) -> bool:
    """A real gateway is a unicast routable IPv4/IPv6, not 0.0.0.0 etc."""
    try:
        ip_obj = ipaddress.ip_address(addr)
    except ValueError:
        return False
    if ip_obj.is_loopback or ip_obj.is_unspecified:
        return False
    if ip_obj.is_multicast or ip_obj.is_reserved:
        return False
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.is_link_local:
        return False
    return True


class IpRouteParser(BaseParser):
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

        gateways: list[str] = []

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            # `ip route` style — `via <gw>` token
            m_via = _VIA_RE.search(line)
            if m_via:
                gw = m_via.group("gw")
                if _looks_like_real_gateway(gw) and gw not in gateways:
                    gateways.append(gw)
                continue

            # `route -n` style — gateway in column 2, with UG flag
            m_route = _ROUTE_RE.match(line)
            if m_route:
                gw = m_route.group("gw")
                flags = m_route.group("flags")
                if "G" in flags and _looks_like_real_gateway(gw) and gw not in gateways:
                    gateways.append(gw)

        for gw in gateways:
            result.hosts_found.append(HostData(ip_address=gw))

        result.stats = {"gateways": len(gateways)}
        return result
