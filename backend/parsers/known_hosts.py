"""Parser for .ssh/known_hosts files (plain and hashed)."""
from __future__ import annotations

import re

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata

# Loopback / link-local addresses we don't want to create hosts for
_SKIP_IPS = {"127.0.0.1", "::1", "localhost"}


class KnownHostsParser(BaseParser):
    """Parses .ssh/known_hosts — each line records a host the user connected to."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        filename = metadata.filename or "known_hosts"
        src_user = metadata.username

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        hosts_seen = 0
        for lineno, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            # Hashed entry: |1|<salt_b64>|<hash_b64> keytype base64key [comment]
            if line.startswith("|"):
                # We can't recover the hostname from a hashed entry — skip
                result.warnings.append(
                    f"Line {lineno}: hashed known_hosts entry — hostname not recoverable, skipped"
                )
                continue

            parts = line.split()
            if len(parts) < 2:
                result.warnings.append(f"Line {lineno}: too few fields, skipping")
                continue

            hostspec = parts[0]  # may be "hostname,ip" or just "hostname"
            # Strip optional [hostname]:port format
            hostspec = re.sub(r"^\[(.+?)\]:\d+$", r"\1", hostspec)

            for candidate in hostspec.split(","):
                candidate = candidate.strip()
                if not candidate or candidate in _SKIP_IPS:
                    continue

                # We record an outbound indicator from the upload host to each known host
                conn = ConnectionData(
                    src_ip=metadata.host_id,   # placeholder — router replaces with real IP
                    dst_ip=candidate,
                    connection_type="ssh",
                    direction_context="from_src_logs",
                    src_user=src_user,
                    raw_line=raw_line[:512],
                )
                # Tag with a sentinel so the router knows src is the upload host
                conn.src_ip = "__upload_host__"
                conn.dst_ip = candidate
                result.connections_found.append(conn)
                hosts_seen += 1

        result.stats = {"hosts_parsed": hosts_seen}
        return result
