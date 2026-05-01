"""Parser for `iptables -L -n` / `iptables-save` output.

Firewall rules describe INTENDED traffic, not observed connections — every
edge produced is indicator confidence at best.

We only emit ConnectionData for rules that name a specific peer IP (single
host: `1.2.3.4` or `1.2.3.4/32`).  Subnets, `0.0.0.0/0`, RFC1918 catch-alls
(`10.0.0.0/8`, `192.168.0.0/16`, `172.16.0.0/12`), wildcard `anywhere`, and
chain-jump references are skipped — they don't identify a specific host.
"""
from __future__ import annotations

import gzip
import ipaddress
import re

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata


# Match a host-like IPv4 address with optional /32 (single-host) suffix.
_IP_HOST_RE = re.compile(
    r"^(?P<ip>\d{1,3}(?:\.\d{1,3}){3})(?:/32)?$"
)
# `iptables-save` style:  `-A INPUT -s 10.0.0.5/32 -p tcp -j ACCEPT`
_SAVE_S_RE = re.compile(r"-s\s+(?P<ip>\d{1,3}(?:\.\d{1,3}){3})(?:/(?P<pref>\d+))?")
_SAVE_D_RE = re.compile(r"-d\s+(?P<ip>\d{1,3}(?:\.\d{1,3}){3})(?:/(?P<pref>\d+))?")
# `iptables-save -c` prefixes each rule with `[pkts:bytes] `.
_COUNTER_PREFIX_RE = re.compile(r"^\[\d+:\d+\]\s+")


def _is_specific_host(addr: str, prefix: int | None = None) -> bool:
    """Return True only if the rule names a single routable host."""
    try:
        ip_obj = ipaddress.IPv4Address(addr)
    except ValueError:
        return False
    if prefix is not None and prefix != 32:
        return False
    if ip_obj.is_unspecified or ip_obj.is_loopback:
        return False
    if ip_obj.is_multicast or ip_obj.is_reserved:
        return False
    if ip_obj.is_link_local:
        return False
    return True


class IptablesParser(BaseParser):
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

        # We deduplicate (src, dst) tuples within a single file — many
        # iptables tables contain hundreds of repeated rules.
        seen_pairs: set[tuple[str, str]] = set()
        emitted = 0

        in_filter_section = False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            line = _COUNTER_PREFIX_RE.sub("", line)

            # `iptables-save` style first — covers IP-with-prefix idioms cleanly.
            if line.startswith(("-A ", "-I ", "-N ", ":")):
                src_ip: str | None = None
                dst_ip: str | None = None
                m_s = _SAVE_S_RE.search(line)
                if m_s:
                    pref = int(m_s.group("pref")) if m_s.group("pref") else None
                    if _is_specific_host(m_s.group("ip"), pref):
                        src_ip = m_s.group("ip")
                m_d = _SAVE_D_RE.search(line)
                if m_d:
                    pref = int(m_d.group("pref")) if m_d.group("pref") else None
                    if _is_specific_host(m_d.group("ip"), pref):
                        dst_ip = m_d.group("ip")
                pair = self._emit(src_ip, dst_ip, raw_line, result, seen_pairs)
                if pair:
                    emitted += 1
                continue

            # `iptables -L -n` or `-L -nv` columnar format.
            # Header rows / chain headers / blank.
            if line.startswith(("Chain ", "target", "pkts", "Destination", "Active")):
                continue

            parts = line.split()
            # `-L -n` format:  target  prot  opt  source  destination  [...]
            # `-L -nv` format: pkts bytes target prot opt in out source destination [...]
            # Distinguish by whether parts[0] looks like a packet count (digits or 'K'/'M')
            if len(parts) >= 5 and re.match(r"^\d+[KMG]?$", parts[0]):
                # -nv format
                if len(parts) < 9:
                    continue
                src = parts[7]
                dst = parts[8]
            elif len(parts) >= 5:
                # -n format
                src = parts[3]
                dst = parts[4]
            else:
                continue

            # Skip `anywhere` (textual placeholder) and chain-jump targets.
            src_ip = self._extract_ip(src)
            dst_ip = self._extract_ip(dst)
            pair = self._emit(src_ip, dst_ip, raw_line, result, seen_pairs)
            if pair:
                emitted += 1

        result.stats = {"rules": emitted}
        return result

    @staticmethod
    def _extract_ip(token: str) -> str | None:
        """Return a single specific IP, or None if the token is not host-specific."""
        if not token or token.lower() in {"anywhere", "0.0.0.0/0", "::/0"}:
            return None
        # CIDR — only accept /32.
        if "/" in token:
            ip, _, pref_str = token.partition("/")
            try:
                pref = int(pref_str)
            except ValueError:
                return None
            if _is_specific_host(ip, pref):
                return ip
            return None
        m = _IP_HOST_RE.match(token)
        if not m:
            return None
        if _is_specific_host(m.group("ip")):
            return m.group("ip")
        return None

    @staticmethod
    def _emit(
        src_ip: str | None,
        dst_ip: str | None,
        raw_line: str,
        result: ParseResult,
        seen_pairs: set[tuple[str, str]],
    ) -> bool:
        """Emit ConnectionData if at least one side is a specific host."""
        if not src_ip and not dst_ip:
            return False
        s = src_ip or "__upload_host__"
        d = dst_ip or "__upload_host__"
        if s == d:
            # Both sides resolve to upload host — nothing to record.
            return False
        if (s, d) in seen_pairs:
            return False
        seen_pairs.add((s, d))
        result.connections_found.append(ConnectionData(
            src_ip=s,
            dst_ip=d,
            connection_type="unknown",
            direction_context="from_src_logs",
            raw_line=raw_line[:512],
        ))
        return True
