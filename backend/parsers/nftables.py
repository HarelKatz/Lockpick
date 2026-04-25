"""Parser for `nft list ruleset` / nftables config output.

Same indicator-confidence semantics as iptables: rules describe intent, not
observed traffic.  We extract `ip saddr <ip>` and `ip daddr <ip>` (and the
`ip6` variants) where the value is a single specific host (or /32, /128).
Sets, named references (`@blackhole`, `$admin`), wildcard matches, and
non-host CIDRs are skipped.
"""
from __future__ import annotations

import gzip
import ipaddress
import re

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata

# `ip saddr 1.2.3.4` or `ip6 daddr 2001:db8::1`
_SADDR_RE = re.compile(
    r"\bip6?\s+saddr\s+(?P<addr>[0-9a-fA-F.:]+)(?:/(?P<pref>\d+))?\b"
)
_DADDR_RE = re.compile(
    r"\bip6?\s+daddr\s+(?P<addr>[0-9a-fA-F.:]+)(?:/(?P<pref>\d+))?\b"
)


def _is_specific_host(addr: str, prefix: int | None = None) -> bool:
    try:
        ip_obj = ipaddress.ip_address(addr)
    except ValueError:
        return False
    if prefix is not None:
        if isinstance(ip_obj, ipaddress.IPv4Address) and prefix != 32:
            return False
        if isinstance(ip_obj, ipaddress.IPv6Address) and prefix != 128:
            return False
    if ip_obj.is_unspecified or ip_obj.is_loopback:
        return False
    if ip_obj.is_multicast or ip_obj.is_reserved:
        return False
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.is_link_local:
        return False
    if isinstance(ip_obj, ipaddress.IPv4Address) and ip_obj.is_link_local:
        return False
    return True


class NftablesParser(BaseParser):
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

        seen_pairs: set[tuple[str, str]] = set()
        emitted = 0

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            src_ip: str | None = None
            dst_ip: str | None = None

            m_s = _SADDR_RE.search(line)
            if m_s:
                pref = int(m_s.group("pref")) if m_s.group("pref") else None
                if _is_specific_host(m_s.group("addr"), pref):
                    src_ip = m_s.group("addr")

            m_d = _DADDR_RE.search(line)
            if m_d:
                pref = int(m_d.group("pref")) if m_d.group("pref") else None
                if _is_specific_host(m_d.group("addr"), pref):
                    dst_ip = m_d.group("addr")

            if not src_ip and not dst_ip:
                continue

            s = src_ip or "__upload_host__"
            d = dst_ip or "__upload_host__"
            if s == d:
                continue
            if (s, d) in seen_pairs:
                continue
            seen_pairs.add((s, d))
            result.connections_found.append(ConnectionData(
                src_ip=s,
                dst_ip=d,
                connection_type="unknown",
                direction_context="from_src_logs",
                raw_line=raw_line[:512],
            ))
            emitted += 1

        result.stats = {"rules": emitted}
        return result
