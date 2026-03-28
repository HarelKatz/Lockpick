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
    value: str
    passphrase: Optional[str] = None  # for encrypted private keys
    comment: Optional[str] = None


class CredentialUpdate(BaseModel):
    value: Optional[str] = None
    passphrase: Optional[str] = None
    comment: Optional[str] = None


class CredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    op_id: str
    cred_type: str
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
