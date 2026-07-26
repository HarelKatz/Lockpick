"""Parser infrastructure for Lockpick file upload engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HostData:
    """A host discovered while parsing a file.

    `aliases` are additional identifiers (IPs and/or hostnames) that belong
    to the SAME host as `ip_address` — e.g. the hostnames on an /etc/hosts
    line, or the secondary IPs plus hostnames on an nmap scan record. The
    upload pipeline resolves `ip_address` to a Host, then adds each alias
    as an additional HostIP on that same host (skipping non-routable
    values and aliases that already resolve to a different host).
    """
    ip_address: str
    nickname: Optional[str] = None  # suggested name; backend may override
    aliases: list[str] = field(default_factory=list)


@dataclass
class CredentialData:
    """A credential discovered while parsing a file."""
    cred_type: str  # "private_key" | "public_key" | "password"
    value: str
    username: Optional[str] = None   # which user owns this cred (from metadata or file)
    relationship_type: str = "found_on_disk"  # CredentialLink relationship
    name: Optional[str] = None
    # Verbatim authorized_keys option prefix (from=/command=/restrict/no-pty/…) when
    # the credential came from an authorized_keys line. Grant-scoped, not key-scoped:
    # the same key can be restricted on one host and unrestricted on another.
    key_options: Optional[str] = None


@dataclass
class ConnectionData:
    """A connection record discovered while parsing a file."""
    src_ip: str
    dst_ip: str
    connection_type: str = "ssh"        # ssh | scp | rsync | sftp | ssh_copy_id | unknown
    direction_context: str = "from_src_logs"
    src_user: Optional[str] = None
    dst_user: Optional[str] = None
    auth_method: Optional[str] = None  # publickey | password | keyboard-interactive | hostbased | unknown
    timestamp: Optional[str] = None    # ISO 8601 string; router converts to datetime
    raw_line: Optional[str] = None
    # fingerprint of the key used (for matching to Credential records later)
    credential_fingerprint: Optional[str] = None


@dataclass
class SshConfigPatternData:
    """An SSH config Host block whose alias(es) are patterns, not literal hostnames."""
    aliases: list[str]          # raw alias list including ! negations, e.g. ["jb.*"] or ["box?", "!box0"]
    username: Optional[str]     # User directive value (who connects)


@dataclass
class SudoRuleData:
    """A sudo rule discovered while parsing a sudoers file."""
    subject: str
    subject_type: str           # "user" | "group"
    run_as: str
    commands: str
    nopasswd: bool
    raw_line: Optional[str] = None


@dataclass
class SystemInfoData:
    """Inventory facts about the host the file was collected FROM.

    Unlike every other ParseResult payload this describes `metadata.host_id`
    itself, not a host discovered inside the file — so it can never create a
    host record. Fields left None mean "this artifact doesn't know": `uname`
    knows the kernel but not the distro, `/etc/os-release` the reverse, and the
    pipeline only fills blanks (Architecture Rule #29), so the two compose
    without either clobbering the other or an operator's manual edit.
    """
    os_version: Optional[str] = None
    kernel_version: Optional[str] = None


@dataclass
class ParseResult:
    """Aggregate output from a parser."""
    hosts_found: list[HostData] = field(default_factory=list)
    credentials_found: list[CredentialData] = field(default_factory=list)
    connections_found: list[ConnectionData] = field(default_factory=list)
    # (username, host label) pairs for HostUser records to create
    host_users_found: list[tuple[str, Optional[str], Optional[str]]] = field(default_factory=list)
    patterns_found: list[SshConfigPatternData] = field(default_factory=list)
    sudo_rules_found: list[SudoRuleData] = field(default_factory=list)
    # Inventory facts about the source host (metadata.host_id), not a discovered one
    system_info: Optional[SystemInfoData] = None
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


@dataclass
class UploadMetadata:
    """Metadata supplied by the frontend alongside the uploaded file."""
    op_id: str
    host_id: str        # the host this file was taken from
    file_type: str      # authorized_keys | known_hosts | ssh_config | private_key |
                        # public_key | auth_log | wtmp | bash_history | passwd
    username: Optional[str] = None   # required for per-user files
    filename: Optional[str] = None   # original filename for display


class BaseParser:
    """All file parsers implement this interface."""

    def parse(self, content: bytes, metadata: UploadMetadata) -> ParseResult:
        raise NotImplementedError
