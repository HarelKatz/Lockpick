"""Parser for `ip addr` / `ifconfig` output — interface inventory.

Extracts every IPv4 and IPv6 address assigned to the upload host's interfaces.
Loopback addresses are skipped (they belong to the upload host but say nothing
about the network).  Output is consolidated into ONE HostData with the primary
IPv4 address as `ip_address` and all remaining (incl IPv6) addresses as
`aliases` — per the multi-identifier rule, one HostData per host.
"""
from __future__ import annotations

import gzip
import ipaddress
import re

from parsers import BaseParser, HostData, ParseResult, UploadMetadata

# `ip addr` style:
#     inet 10.0.0.5/24 brd 10.0.0.255 scope global eth0
#     inet6 fe80::1/64 scope link
# `ifconfig` style:
#     inet 10.0.0.5  netmask 255.255.255.0  broadcast 10.0.0.255
#     inet6 fe80::1  prefixlen 64  scopeid 0x20<link>
_INET_RE = re.compile(r"^\s*inet\s+(?P<addr>[0-9.]+)(?:/\d+)?\b")
_INET6_RE = re.compile(r"^\s*inet6\s+(?P<addr>[0-9a-fA-F:]+)(?:/\d+)?\b")


def _is_skippable(addr: str) -> bool:
    """Skip loopback and obvious junk; rule #6 — pipeline rejects garbage."""
    try:
        ip_obj = ipaddress.ip_address(addr)
    except ValueError:
        return True
    if ip_obj.is_loopback or ip_obj.is_unspecified:
        return True
    if ip_obj.is_multicast or ip_obj.is_reserved:
        return True
    # Link-local IPv6 (fe80::/10) is valid but not routable across the engagement.
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.is_link_local:
        return True
    # Same for 169.254.x.x APIPA — usually noise from DHCP failures.
    if isinstance(ip_obj, ipaddress.IPv4Address) and ip_obj.is_link_local:
        return True
    return False


class IpAddrParser(BaseParser):
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

        ipv4_addrs: list[str] = []
        ipv6_addrs: list[str] = []
        for raw_line in text.splitlines():
            m4 = _INET_RE.match(raw_line)
            if m4:
                addr = m4.group("addr")
                if _is_skippable(addr):
                    continue
                if addr not in ipv4_addrs:
                    ipv4_addrs.append(addr)
                continue
            m6 = _INET6_RE.match(raw_line)
            if m6:
                addr = m6.group("addr")
                if _is_skippable(addr):
                    continue
                if addr not in ipv6_addrs:
                    ipv6_addrs.append(addr)
                continue

        # No routable addrs — emit nothing (purely loopback host).
        if not ipv4_addrs and not ipv6_addrs:
            result.stats = {"hosts": 0, "ipv4": 0, "ipv6": 0}
            return result

        # Primary = first IPv4 if any, else first IPv6.
        if ipv4_addrs:
            primary = ipv4_addrs[0]
            rest = ipv4_addrs[1:] + ipv6_addrs
        else:
            primary = ipv6_addrs[0]
            rest = ipv6_addrs[1:]

        result.hosts_found.append(HostData(ip_address=primary, aliases=rest))
        result.stats = {
            "hosts": 1,
            "ipv4": len(ipv4_addrs),
            "ipv6": len(ipv6_addrs),
        }
        return result
