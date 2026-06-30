"""Parser for RHEL/CentOS ifcfg-* files (/etc/sysconfig/network-scripts/).

Format: simple shell-style KEY=VALUE assignments. Both quoted and
unquoted values are accepted.

Address keys harvested:

* `IPADDR`, `IPADDR0`, `IPADDR2`, ... (numbered aliases)
* `IPV6ADDR`
* `IPV6ADDR_SECONDARIES` — whitespace-separated list

Gateway keys (counted but not emitted as hosts):

* `GATEWAY`, `IPV6_DEFAULTGW`

Per CLAUDE.md Parser guidelines (Network config parsers): emits one HostData with the first IP as primary,
rest as aliases. No ConnectionData.
"""
from __future__ import annotations

import ipaddress
import re

from parsers import BaseParser, HostData, ParseResult, UploadMetadata

# `KEY=value` or `KEY="value"` — value may be quoted or bare.
_ASSIGN_RE = re.compile(r"^\s*(?P<key>[A-Z][A-Z0-9_]*)\s*=\s*(?P<value>.+?)\s*$")

# Numbered IPADDR keys (IPADDR, IPADDR0, IPADDR1, ...).
_IPADDR_KEY_RE = re.compile(r"^IPADDR\d*$")

_GATEWAY_KEYS = frozenset({"GATEWAY", "IPV6_DEFAULTGW"})
_IPV6_KEYS = frozenset({"IPV6ADDR"})
_IPV6_SECONDARIES = frozenset({"IPV6ADDR_SECONDARIES"})


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _strip_cidr(addr: str) -> str | None:
    a = addr.strip().split("/", 1)[0].split("%", 1)[0]
    return a or None


def _is_routable(addr: str) -> bool:
    try:
        obj = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return not (obj.is_loopback or obj.is_multicast or obj.is_unspecified or obj.is_reserved)


class IfcfgParser(BaseParser):
    """Parses /etc/sysconfig/network-scripts/ifcfg-* style files."""

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
            line = raw_line.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            m = _ASSIGN_RE.match(line)
            if not m:
                continue
            key = m.group("key").upper()
            value = _strip_quotes(m.group("value"))
            if not value:
                continue

            if _IPADDR_KEY_RE.match(key) or key in _IPV6_KEYS:
                ip = _strip_cidr(value)
                if ip and _is_routable(ip):
                    addrs.append(ip)
            elif key in _IPV6_SECONDARIES:
                # whitespace-separated list of `ip/prefix` values
                for tok in value.split():
                    ip = _strip_cidr(tok)
                    if ip and _is_routable(ip):
                        addrs.append(ip)
            elif key in _GATEWAY_KEYS:
                ip = _strip_cidr(value)
                if ip and _is_routable(ip):
                    gateways.append(ip)
            # Other keys (DEVICE, BOOTPROTO, NETMASK, DNS*, etc) are ignored.

        all_addrs = list(dict.fromkeys(addrs))
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
