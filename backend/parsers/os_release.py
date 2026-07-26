"""Parser for `/etc/os-release` (systemd distro identification).

Pure inventory context: it says what distro the *upload host* runs. It never
emits hosts, connections or credentials — see `SystemInfoData` and Architecture
Rule #29.
"""
from __future__ import annotations

import gzip
import re

from parsers import BaseParser, ParseResult, SystemInfoData, UploadMetadata

# `KEY=value` / `KEY="quoted value"` — the os-release format is shell-like but we
# deliberately do not exec it; a plain key/value split is enough and is safe.
_KV_RE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)=(.*)$")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    # os-release escapes are shell escapes; only the ones that actually occur.
    return value.replace('\\"', '"').replace("\\$", "$").replace("\\\\", "\\").strip()


class OsReleaseParser(BaseParser):
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

        fields: dict[str, str] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            m = _KV_RE.match(line)
            if not m:
                continue
            value = _unquote(m.group(2))
            if value:
                fields[m.group(1)] = value

        # PRETTY_NAME is the human string every distro sets; fall back to
        # NAME + VERSION_ID for minimal images (Alpine ships an empty one).
        os_version = fields.get("PRETTY_NAME")
        if not os_version:
            name, version_id = fields.get("NAME"), fields.get("VERSION_ID")
            os_version = " ".join(p for p in (name, version_id) if p) or None

        if not os_version:
            result.warnings.append("No PRETTY_NAME/NAME field found — not an os-release file?")
            return result

        result.system_info = SystemInfoData(os_version=os_version[:255])
        result.stats = {"os_version": 1}
        return result
