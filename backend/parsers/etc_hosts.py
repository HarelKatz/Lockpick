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

            # Skip loopback
            if ip.startswith("127.") or ip == "::1" or ip.lower() == "localhost":
                continue
            # Skip broadcast/any
            if ip in ("0.0.0.0", "255.255.255.255"):
                continue

            result.hosts_found.append(HostData(ip_address=ip))
            ip_count += 1

            for hostname in hostnames:
                hn = hostname.lower()
                if hn == "localhost" or hn.startswith("localhost."):
                    continue
                result.hosts_found.append(HostData(ip_address=hostname))
                hostname_count += 1

        result.stats = {"ips": ip_count, "hostnames": hostname_count}
        return result
