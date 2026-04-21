"""Parser for .ssh/config files."""
from __future__ import annotations

from parsers import (
    BaseParser,
    ConnectionData,
    ParseResult,
    SshConfigPatternData,
    UploadMetadata,
)


def _is_pattern(s: str) -> bool:
    """Return True if the string is an SSH glob/token rather than a literal hostname."""
    return any(c in s for c in ("*", "?", "%"))


class SshConfigParser(BaseParser):
    """Parses .ssh/config — extracts Host blocks with Hostname/User/Port."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        result = ParseResult()
        src_user = metadata.username

        try:
            text = content.decode("utf-8", errors="replace")
        except Exception as e:
            result.warnings.append(f"Failed to decode file: {e}")
            return result

        blocks_found = 0

        current_aliases: list[str] = []
        current_props: dict[str, str] = {}

        def flush_block() -> None:
            nonlocal blocks_found
            if not current_aliases:
                return

            # Skip Match directive blocks — conditional, not hostname patterns
            if current_aliases[0].startswith("Match "):
                return

            hostname = current_props.get("hostname")
            user = current_props.get("user") or src_user

            positive_aliases = [a for a in current_aliases if not a.startswith("!")]
            has_pattern_alias = any(_is_pattern(a) for a in positive_aliases)
            has_pattern_hostname = bool(hostname and _is_pattern(hostname))

            # Pattern block: alias uses glob/token AND no concrete HostName
            if has_pattern_alias and (not hostname or has_pattern_hostname):
                result.patterns_found.append(
                    SshConfigPatternData(aliases=current_aliases[:], username=user)
                )
                blocks_found += 1
                return

            # Concrete destination available
            dst = hostname if hostname and not has_pattern_hostname else None

            if dst:
                result.connections_found.append(ConnectionData(
                    src_ip="__upload_host__",
                    dst_ip=dst,
                    connection_type="ssh",
                    direction_context="from_src_logs",
                    src_user=src_user,
                    dst_user=user if user and user != src_user else None,
                    raw_line=f"Host {' '.join(current_aliases)} → {dst}",
                ))
                blocks_found += 1
            else:
                for alias in positive_aliases:
                    if not _is_pattern(alias):
                        result.connections_found.append(ConnectionData(
                            src_ip="__upload_host__",
                            dst_ip=alias,
                            connection_type="ssh",
                            direction_context="from_src_logs",
                            src_user=src_user,
                            dst_user=user if user and user != src_user else None,
                            raw_line=f"Host {' '.join(current_aliases)}",
                        ))
                        blocks_found += 1

        for _lineno, raw_line in enumerate(text.splitlines(), 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            key, _, value = line.partition(" ")
            key = key.lower().strip()
            value = value.strip()

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
