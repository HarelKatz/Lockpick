"""Parser for `docker ps` / `docker ps -a` text output.

Default `docker ps` output rarely shows container IPs (the PORTS column
shows host port mappings, not container IPs).  We only emit a HostData when
the row contains a recognisable container IP — typically from `docker ps`
runs with custom `--format` columns that include `{{.NetworkSettings.IPAddress}}`.

For typical default output (no IP), we emit nothing rather than fake hosts.
The container name (last column) is preserved as `nickname` if a HostData
is emitted.
"""
from __future__ import annotations

import gzip
import ipaddress
import re

from parsers import BaseParser, HostData, ParseResult, UploadMetadata


# Match an IPv4 anywhere on the line — but only treat it as a container IP
# if it's not part of a port mapping (`0.0.0.0:8080->80/tcp`) or an image
# tag/registry reference (`172.30.90.140:5000/...`).
_IP_RE = re.compile(r"\b(?P<ip>(?:\d{1,3}\.){3}\d{1,3})\b")


def _is_routable(addr: str) -> bool:
    try:
        ip_obj = ipaddress.IPv4Address(addr)
    except ValueError:
        return False
    if ip_obj.is_unspecified or ip_obj.is_loopback:
        return False
    if ip_obj.is_multicast or ip_obj.is_reserved or ip_obj.is_link_local:
        return False
    return True


def _strip_port_mappings(line: str) -> str:
    """Remove `0.0.0.0:8080->80/tcp`, `[::]:443->443/tcp` and image refs.

    These contain IPs but they are not container IPs — they're host port
    bindings or registry hostnames.
    """
    # Drop `host:port->container_port/proto`
    line = re.sub(r"\b\S*?\d+(?:\.\d+){0,3}\S*?:\d+->[^\s,]+", "", line)
    # Drop `registry.host:5000/path` style image refs (rough — we only want
    # to scrub the IP-like portion before the `/`).
    line = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d+/\S+", "", line)
    return line


# Header keywords (we use these to detect the header row and the container-name column)
_HEADER_KEYWORDS = ("CONTAINER ID", "IMAGE", "COMMAND", "STATUS", "NAMES")


class DockerPsParser(BaseParser):
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

        emitted = 0
        seen_ips: set[str] = set()
        in_header = False
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            if not line:
                continue
            stripped = line.strip()

            # Skip shell prompt lines / blank rows.  We only want data rows.
            if stripped.startswith(("#", "$", ">")):
                continue
            if any(kw in line for kw in _HEADER_KEYWORDS):
                in_header = True
                continue

            if not in_header:
                # No header seen → still try to parse; jc samples sometimes
                # include a shell-prompt prefix line before the header.
                pass

            scrubbed = _strip_port_mappings(line)
            ips_in_line = [
                m.group("ip") for m in _IP_RE.finditer(scrubbed)
                if _is_routable(m.group("ip"))
            ]
            if not ips_in_line:
                continue

            ip = ips_in_line[0]
            if ip in seen_ips:
                continue
            seen_ips.add(ip)

            # Last whitespace-separated token tends to be the container NAME.
            tokens = stripped.split()
            nickname = tokens[-1] if tokens else None
            # Reject obvious non-name tokens (timestamps, statuses).
            if nickname and not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", nickname):
                nickname = None

            result.hosts_found.append(HostData(
                ip_address=ip,
                nickname=nickname,
            ))
            emitted += 1

        result.stats = {"containers": emitted}
        return result
