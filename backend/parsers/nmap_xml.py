"""Parser for nmap XML output files."""
from __future__ import annotations

# SEC: xml.etree.ElementTree has limited protection against XML billion-laughs attacks.
# Mitigation: replace with defusedxml.ElementTree.fromstring() once defusedxml is added
# as a dependency (pip install defusedxml). Until then, only parse files from trusted ops.
import xml.etree.ElementTree as ET

from parsers import BaseParser, HostData, ParseResult, UploadMetadata


class NmapXmlParser(BaseParser):
    """Parses nmap XML scan output — creates HostData records (no credentials, no connections)."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        if not text.strip():
            return result

        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            result.warnings.append(f"XML parse error: {e}")
            return result

        hosts_found = 0
        for host_elem in root.iter("host"):
            status = host_elem.find("status")
            if status is not None and status.get("state", "up") != "up":
                continue

            ips: list[str] = []
            hostnames: list[str] = []

            for addr in host_elem.findall("address"):
                addrtype = addr.get("addrtype", "")
                addrval = addr.get("addr", "").strip()
                if addrtype in ("ipv4", "ipv6") and addrval:
                    ips.append(addrval)

            for hn_list in host_elem.findall("hostnames"):
                for hn in hn_list.findall("hostname"):
                    name = hn.get("name", "").strip()
                    if name:
                        hostnames.append(name)

            if not ips:
                if hostnames:
                    result.warnings.append(
                        f"Host with hostname(s) {hostnames} has no IP address — skipping"
                    )
                continue

            nickname = hostnames[0] if hostnames else ips[0]

            # One HostData per scanned host: the first IP is the primary,
            # the other IPs and any hostnames ride along as aliases so they
            # land as additional HostIPs on the same Host record.
            primary_ip = ips[0]
            aliases = ips[1:] + hostnames
            result.hosts_found.append(HostData(
                ip_address=primary_ip,
                nickname=nickname,
                aliases=aliases,
            ))
            hosts_found += 1

        result.stats = {"hosts_found": hosts_found}
        return result
