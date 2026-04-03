"""Parser for .ssh/config files."""
from __future__ import annotations

from parsers import BaseParser, ConnectionData, ParseResult, UploadMetadata


class SshConfigParser(BaseParser):
    """Parses .ssh/config — extracts Host blocks with Hostname/User/Port."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        filename = metadata.filename or "ssh_config"
        src_user = metadata.username

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        blocks_found = 0

        # Parse into blocks keyed by Host pattern
        current_aliases: list[str] = []
        current_props: dict[str, str] = {}

        def flush_block():
            nonlocal blocks_found
            if not current_aliases:
                return
            hostname = current_props.get("hostname")
            user = current_props.get("user", src_user)
            # Skip wildcard-only blocks with no real hostname
            if not hostname:
                # use the alias as destination if it looks like an IP/hostname
                for alias in current_aliases:
                    if alias != "*" and "?" not in alias and "!" not in alias:
                        conn = ConnectionData(
                            src_ip="__upload_host__",
                            dst_ip=alias,
                            connection_type="ssh",
                            direction_context="from_src_logs",
                            src_user=src_user,
                            dst_user=user if user != src_user else None,
                            raw_line=f"Host {' '.join(current_aliases)}",
                        )
                        result.connections_found.append(conn)
                        blocks_found += 1
                return

            conn = ConnectionData(
                src_ip="__upload_host__",
                dst_ip=hostname,
                connection_type="ssh",
                direction_context="from_src_logs",
                src_user=src_user,
                dst_user=user if user and user != src_user else None,
                raw_line=f"Host {' '.join(current_aliases)} → {hostname}",
            )
            result.connections_found.append(conn)
            blocks_found += 1

        for lineno, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            try:
                key, _, value = line.partition(" ")
                key = key.lower().strip()
                value = value.strip()
            except Exception:
                continue

            if key == "host":
                flush_block()
                current_aliases = value.split()
                current_props = {}
            elif key == "match":
                flush_block()
                current_aliases = [f"Match {value}"]
                current_props = {}
            elif current_aliases:
                current_props[key] = value

        flush_block()

        result.stats = {"blocks_parsed": blocks_found}
        return result
