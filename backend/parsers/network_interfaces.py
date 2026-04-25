"""Parser for Debian /etc/network/interfaces.

Format:

    auto eth0
    iface eth0 inet static
        address 192.168.1.10
        netmask 255.255.255.0
        gateway 192.168.1.1

    iface eth1 inet static
        address 10.0.0.5/24

CIDR notation in `address` is also accepted.

Per AGENT.md Phase 16: network config parsers emit only the upload host's
own IPs and gateways. The first IP becomes the HostData primary; the rest
go into `aliases`. No ConnectionData is emitted.
"""
from __future__ import annotations

import ipaddress
import re

from parsers import BaseParser, HostData, ParseResult, UploadMetadata

_IFACE_RE = re.compile(r"^\s*iface\s+(?P<name>\S+)\s+inet6?\s+(?P<method>\S+)", re.IGNORECASE)
_ADDRESS_RE = re.compile(r"^\s*address\s+(?P<addr>\S+)", re.IGNORECASE)
_GATEWAY_RE = re.compile(r"^\s*gateway\s+(?P<addr>\S+)", re.IGNORECASE)


def _strip_cidr(addr: str) -> str | None:
    """Return just the IP portion of an `IP[/prefix]` value, or None if invalid."""
    a = addr.strip().split("/", 1)[0]
    if not a:
        return None
    return a


def _is_routable(addr: str) -> bool:
    try:
        obj = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return not (obj.is_loopback or obj.is_multicast or obj.is_unspecified or obj.is_reserved)


class NetworkInterfacesParser(BaseParser):
    """Parses Debian /etc/network/interfaces."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Decode error: {e}")
            return result

        addrs: list[str] = []
        gateways: list[str] = []

        for raw_line in text.splitlines():
            # Strip comments after `#` (but not `#` inside quotes — interfaces
            # config doesn't use quoting much, simple split is fine).
            stripped = raw_line.split("#", 1)[0]
            line = stripped.rstrip()
            if not line.strip():
                continue

            # `iface` lines themselves don't carry an address — addresses
            # follow on indented lines. We don't gate on iface-block state
            # because the format is flexible.
            if _IFACE_RE.match(line):
                continue

            m_a = _ADDRESS_RE.match(line)
            if m_a:
                addr = _strip_cidr(m_a.group("addr"))
                if addr and _is_routable(addr):
                    addrs.append(addr)
                continue

            m_g = _GATEWAY_RE.match(line)
            if m_g:
                addr = _strip_cidr(m_g.group("addr"))
                if addr and _is_routable(addr):
                    gateways.append(addr)
                continue
            # `auto` / `allow-hotplug` / `mapping` / etc are unused.

        # Emit ONE HostData with the first address as primary, rest as aliases.
        # Gateways are NOT emitted as host IPs (they belong to other hosts on
        # the same network — Phase 16 explicitly forbids that).
        all_addrs = list(dict.fromkeys(addrs))  # preserve order, dedupe
        if all_addrs:
            primary = all_addrs[0]
            aliases = all_addrs[1:]
            result.hosts_found.append(HostData(
                ip_address=primary,
                aliases=aliases,
            ))

        result.stats = {
            "addresses": len(all_addrs),
            "gateways": len(gateways),
        }
        return result
