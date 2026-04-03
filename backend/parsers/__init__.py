"""Parser infrastructure for Lockpick file upload engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HostData:
    """A host discovered while parsing a file."""
    ip_address: str
    nickname: Optional[str] = None  # suggested name; backend may override


@dataclass
class CredentialData:
    """A credential discovered while parsing a file."""
    cred_type: str  # "private_key" | "public_key" | "password"
    value: str
    username: Optional[str] = None   # which user owns this cred (from metadata or file)
    relationship_type: str = "found_on_disk"  # CredentialLink relationship
    name: Optional[str] = None


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
class ParseResult:
    """Aggregate output from a parser."""
    hosts_found: list[HostData] = field(default_factory=list)
    credentials_found: list[CredentialData] = field(default_factory=list)
    connections_found: list[ConnectionData] = field(default_factory=list)
    # (username, host label) pairs for HostUser records to create
    host_users_found: list[tuple[str, Optional[str], Optional[str]]] = field(default_factory=list)
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
