"""Parser for /etc/hosts files.

Extracts IP addresses and hostnames, emitting each as a HostData record
so they can be correlated with existing hosts in the operation.
"""
from __future__ import annotations

from parsers import BaseParser, HostData, ParseResult, UploadMetadata


class EtcHostsParser(BaseParser):
    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Decode error: {e}")
            return result

        ip_count = 0
        hostname_count = 0

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip inline comments
            line = line.split("#")[0].strip()
            parts = line.split()
            if len(parts) < 2:
                continue
            ip = parts[0]
            hostnames = parts[1:]

            # Skip loopback — not a real pivot target, already resolved to
            # the upload host by the pipeline.
            if ip.startswith("127.") or ip == "::1" or ip.lower() == "localhost":
                continue

            # Drop obvious localhost-family hostnames. Multicast / reserved
            # IPv6 hostnames like `ip6-allnodes` are filtered by the IP
            # validation: if the line's IP is itself non-routable, the
            # whole line is skipped here so the hostnames never leak in as
            # phantom hosts.
            try:
                import ipaddress
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.is_multicast or ip_obj.is_reserved or ip_obj.is_unspecified:
                    continue
            except ValueError:
                # Non-IP on the left side of /etc/hosts is malformed; skip.
                continue

            filtered_hostnames = [
                h for h in hostnames
                if not (h.lower() == "localhost" or h.lower().startswith("localhost."))
            ]

            # Emit ONE HostData per line — the IP is the primary identifier,
            # hostnames ride along as aliases so they end up as additional
            # HostIPs on the same host instead of spawning phantom hosts.
            result.hosts_found.append(HostData(
                ip_address=ip,
                aliases=filtered_hostnames,
            ))
            ip_count += 1
            hostname_count += len(filtered_hostnames)

        result.stats = {"ips": ip_count, "hostnames": hostname_count}
        return result
