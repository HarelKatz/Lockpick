"""Pydantic request/response models."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


# ─── Operation ───────────────────────────────────────────────────────────────

class OperationCreate(BaseModel):
    name: str
    description: Optional[str] = None


class OperationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class OperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str]
    created_at: datetime


class OpStats(BaseModel):
    host_count: int
    credential_count: int
    connection_count: int
    total_records: int
    latest_activity_at: Optional[datetime]


class SearchResult(BaseModel):
    type: Literal["host", "host_ip", "host_user", "credential", "connection"]
    host_id: Optional[str] = None
    credential_id: Optional[str] = None
    connection_id: Optional[str] = None
    nickname: Optional[str] = None
    matched_field: str
    snippet: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int


class ActivityLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    op_id: str
    action: str
    entity_type: str
    entity_id: Optional[str]
    detail: Optional[str]
    created_at: datetime


# ─── HostUser ────────────────────────────────────────────────────────────────

class HostUserCreate(BaseModel):
    username: str
    shell: Optional[str] = None
    home_dir: Optional[str] = None
    source: Literal["manual", "passwd_file", "authorized_keys", "log_evidence"] = "manual"


class HostUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    host_id: str
    username: str
    shell: Optional[str]
    home_dir: Optional[str]
    source: str
    created_at: datetime


# ─── HostIP ───────────────────────────────────────────────────────────────────

class HostIPCreate(BaseModel):
    ip_address: str
    source: Literal["manual", "parsed"] = "manual"


class HostIPRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    host_id: str
    ip_address: str
    source: str
    first_seen_at: datetime


# ─── Host ─────────────────────────────────────────────────────────────────────

class HostCreate(BaseModel):
    nickname: str
    comment: Optional[str] = None


class HostUpdate(BaseModel):
    nickname: Optional[str] = None
    comment: Optional[str] = None


class HostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    op_id: str
    nickname: str
    comment: Optional[str]
    created_at: datetime
    ips: list[HostIPRead] = []
    users: list[HostUserRead] = []


# ─── Credential ───────────────────────────────────────────────────────────────

class CredentialCreate(BaseModel):
    cred_type: Literal["password", "private_key", "public_key"]
    name: Optional[str] = None
    value: str
    passphrase: Optional[str] = None  # for encrypted private keys
    comment: Optional[str] = None


class CredentialUpdate(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    passphrase: Optional[str] = None
    comment: Optional[str] = None


class CredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    op_id: str
    cred_type: str
    name: Optional[str]
    value: str
    fingerprint: Optional[str]   # inferred on save
    key_type: Optional[str]      # inferred on save
    passphrase: Optional[str]
    comment: Optional[str]
    created_at: datetime


# ─── CredentialLink ───────────────────────────────────────────────────────────

class CredentialLinkUpdate(BaseModel):
    username: Optional[str] = None
    host_user_id: Optional[str] = None
    relationship_type: Optional[Literal[
        "found_on_disk", "authorized_key", "accepted_password", "used_in_connection"
    ]] = None
    file_source: Optional[str] = None


class CredentialLinkCreate(BaseModel):
    credential_id: str
    host_id: str
    username: Optional[str] = None
    host_user_id: Optional[str] = None
    relationship_type: Literal[
        "found_on_disk", "authorized_key", "accepted_password", "used_in_connection"
    ]
    file_source: Optional[str] = None


class CredentialLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    credential_id: str
    host_id: str
    username: Optional[str]
    host_user_id: Optional[str]
    relationship_type: str
    file_source: Optional[str]


# ─── ConnectionRecord ─────────────────────────────────────────────────────────

class ConnectionRecordUpdate(BaseModel):
    src_host_id: Optional[str] = None
    src_ip: Optional[str] = None
    src_user: Optional[str] = None
    dst_host_id: Optional[str] = None
    dst_ip: Optional[str] = None
    dst_user: Optional[str] = None
    connection_type: Optional[Literal["ssh", "scp", "rsync", "sftp", "ssh_copy_id", "unknown"]] = None
    direction_context: Optional[Literal["from_src_logs", "from_dst_logs"]] = None
    auth_method: Optional[Literal["publickey", "password", "keyboard-interactive", "hostbased", "unknown"]] = None
    credential_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    raw_line: Optional[str] = None
    source_file: Optional[str] = None


class ConnectionRecordCreate(BaseModel):
    src_host_id: Optional[str] = None
    src_ip: str
    src_user: Optional[str] = None
    dst_host_id: Optional[str] = None
    dst_ip: str
    dst_user: Optional[str] = None
    connection_type: Literal["ssh", "scp", "rsync", "sftp", "ssh_copy_id", "unknown"] = "unknown"
    direction_context: Literal["from_src_logs", "from_dst_logs"]
    auth_method: Optional[Literal["publickey", "password", "keyboard-interactive", "hostbased", "unknown"]] = None
    credential_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    raw_line: Optional[str] = None
    source_file: str


class ConnectionRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    op_id: str
    src_host_id: Optional[str]
    src_ip: str
    src_user: Optional[str]
    dst_host_id: Optional[str]
    dst_ip: str
    dst_user: Optional[str]
    connection_type: str
    direction_context: str
    auth_method: Optional[str]
    credential_id: Optional[str]
    timestamp: Optional[datetime]
    raw_line: Optional[str]
    source_file: str
    created_at: datetime


# ─── Evidence Files ───────────────────────────────────────────────────────────

class UploadFileInfo(BaseModel):
    safe_name: str           # UUID-prefixed filename (used in download URL)
    original_name: str       # filename without UUID prefix (for display)
    size_bytes: int
    host_ids: list[str]      # host IDs that reference this file (from credential_links + connection_records)
    uploaded_at: datetime    # file mtime on disk — written before DB records


# ─── Graph ────────────────────────────────────────────────────────────────────

class EvidenceItem(BaseModel):
    type: Literal["key_match", "connection_log", "bash_history", "known_hosts"]
    detail: str
    credential_id: Optional[str] = None
    credential_fingerprint: Optional[str] = None
    credential_name: Optional[str] = None
    connection_type: Optional[str] = None
    src_user: Optional[str] = None
    dst_user: Optional[str] = None
    auth_method: Optional[str] = None
    timestamp: Optional[datetime] = None
    source_file: Optional[str] = None
    confidence: Literal["confirmed", "observed", "indicator"]


class PivotableUser(BaseModel):
    src_user: str
    dst_user: str
    method: Literal["key", "password", "connection"]
    credential_id: Optional[str] = None


class GraphNode(BaseModel):
    host_id: str
    nickname: str
    ips: list[str]
    user_count: int
    credential_count: int


class GraphEdge(BaseModel):
    src_host_id: str
    dst_host_id: str
    confidence: Literal["confirmed", "observed", "indicator"]
    evidence: list[EvidenceItem]
    pivotable_users: list[PivotableUser]


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# ─── Path Finding ──────────────────────────────────────────────────────────────

class WaypointConstraint(BaseModel):
    host_id: str
    position: Literal["anywhere", "after", "before"]
    relative_to: Optional[str] = None  # host_id anchor when position is "after"/"before"


class PathFinderRequest(BaseModel):
    src_host_id: str
    dst_host_id: str
    mode: Literal["shortest", "all"] = "shortest"
    waypoints: list[WaypointConstraint] = []


class PathResult(BaseModel):
    host_ids: list[str]
    edges: list[GraphEdge]


class PathFinderResponse(BaseModel):
    paths: list[PathResult]
    truncated: bool


# ─── Export / Import ──────────────────────────────────────────────────────────

class ExportHostIP(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ip_address: str
    source: str
    first_seen_at: datetime


class ExportHostUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str
    shell: Optional[str]
    home_dir: Optional[str]
    source: str
    created_at: datetime


class ExportHost(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    nickname: str
    comment: Optional[str]
    created_at: datetime
    ips: list[ExportHostIP]
    users: list[ExportHostUser]


class ExportCredential(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    cred_type: str
    name: Optional[str]
    value: str
    fingerprint: Optional[str]
    key_type: Optional[str]
    passphrase: Optional[str]
    comment: Optional[str]
    created_at: datetime


class ExportCredentialLink(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    credential_id: str
    host_id: str
    username: Optional[str]
    host_user_id: Optional[str]
    relationship_type: str
    file_source: Optional[str]


class ExportConnection(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    src_host_id: Optional[str]
    src_ip: str
    src_user: Optional[str]
    dst_host_id: Optional[str]
    dst_ip: str
    dst_user: Optional[str]
    connection_type: str
    direction_context: str
    auth_method: Optional[str]
    credential_id: Optional[str]
    timestamp: Optional[datetime]
    raw_line: Optional[str]
    source_file: str
    created_at: datetime


class ExportActivityEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    action: str
    entity_type: str
    entity_id: Optional[str]
    detail: Optional[str]
    created_at: datetime


class OpExport(BaseModel):
    lockpick_export_version: int = 1
    exported_at: datetime
    operation: OperationRead
    hosts: list[ExportHost]
    credentials: list[ExportCredential]
    credential_links: list[ExportCredentialLink]
    connections: list[ExportConnection]
    activity_log: list[ExportActivityEntry]


class ImportRequest(BaseModel):
    mode: Literal["create_new"] = "create_new"
    name_override: Optional[str] = None
    data: OpExport


class ImportResponse(BaseModel):
    op_id: str
    op_name: str
