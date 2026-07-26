"""Parser for `uname -a` (or `uname -r`) output.

Yields the kernel release only. `uname` cannot see the distro, so `os_version`
is deliberately left None — that is what lets a later `/etc/os-release` upload
fill it, since the pipeline only fills blanks (Architecture Rule #29).

The nodename in `uname -a` is NOT emitted as a host or alias: turning it into a
HostIP is a separate decision with its own phantom-host risk, and this parser's
contract is inventory metadata only.
"""
from __future__ import annotations

import gzip
import re

from parsers import BaseParser, ParseResult, SystemInfoData, UploadMetadata

# A kernel release: digits/dots up front, then the usual -generic/-amd64/+ tail.
# Anchored so a line of prose ("command not found") is rejected rather than
# guessed at — no data beats wrong data for an inventory field.
_RELEASE_RE = re.compile(r"^\d+\.\d+(?:\.\d+)*[A-Za-z0-9._+~-]*$")


class UnameOutputParser(BaseParser):
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

        line = next((l.strip() for l in text.splitlines() if l.strip()), "")
        if not line:
            result.warnings.append("Empty uname output")
            return result

        tokens = line.split()
        # `uname -r` → the whole line is the release. `uname -a` →
        # "<sysname> <nodename> <release> <version…>", so the release is token 3.
        candidate = tokens[0] if len(tokens) == 1 else (tokens[2] if len(tokens) >= 3 else "")

        if not candidate or not _RELEASE_RE.match(candidate):
            result.warnings.append(f"No kernel release found in uname output: {line[:120]!r}")
            return result

        result.system_info = SystemInfoData(kernel_version=candidate[:255])
        result.stats = {"kernel_version": 1}
        return result
