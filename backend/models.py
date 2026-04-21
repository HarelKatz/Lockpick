"""SQLAlchemy ORM models for Lockpick."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Operation(Base):
    __tablename__ = "operations"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    hosts = relationship("Host", back_populates="operation", cascade="all, delete-orphan")
    credentials = relationship("Credential", back_populates="operation", cascade="all, delete-orphan")
    connection_records = relationship("ConnectionRecord", back_populates="operation", cascade="all, delete-orphan")


class Host(Base):
    __tablename__ = "hosts"

    id = Column(String(36), primary_key=True, default=_uuid)
    op_id = Column(String(36), ForeignKey("operations.id", ondelete="CASCADE"), nullable=False)
    nickname = Column(String(255), nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    operation = relationship("Operation", back_populates="hosts")
    ips = relationship("HostIP", back_populates="host", cascade="all, delete-orphan")
    users = relationship("HostUser", back_populates="host", cascade="all, delete-orphan")
    credential_links = relationship("CredentialLink", back_populates="host", cascade="all, delete-orphan")
    src_connections = relationship(
        "ConnectionRecord",
        foreign_keys="ConnectionRecord.src_host_id",
        back_populates="src_host",
    )
    dst_connections = relationship(
        "ConnectionRecord",
        foreign_keys="ConnectionRecord.dst_host_id",
        back_populates="dst_host",
    )


class HostIP(Base):
    __tablename__ = "host_ips"

    id = Column(String(36), primary_key=True, default=_uuid)
    host_id = Column(String(36), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    ip_address = Column(String(45), nullable=False)  # IPv6 max length
    source = Column(
        Enum("manual", "parsed", name="hostip_source"),
        nullable=False,
        default="manual",
    )
    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    host = relationship("Host", back_populates="ips")


class HostUser(Base):
    __tablename__ = "host_users"

    id = Column(String(36), primary_key=True, default=_uuid)
    host_id = Column(String(36), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    username = Column(String(255), nullable=False)
    shell = Column(String(255), nullable=True)
    home_dir = Column(String(512), nullable=True)
    source = Column(
        Enum("manual", "passwd_file", "authorized_keys", "log_evidence", name="hostuser_source"),
        nullable=False,
        default="manual",
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    host = relationship("Host", back_populates="users")


class Credential(Base):
    __tablename__ = "credentials"

    id = Column(String(36), primary_key=True, default=_uuid)
    op_id = Column(String(36), ForeignKey("operations.id", ondelete="CASCADE"), nullable=False)
    cred_type = Column(
        Enum("password", "private_key", "public_key", name="cred_type"),
        nullable=False,
    )
    name = Column(String(255), nullable=True)  # human-readable label, e.g. "id_rsa for root@web01"
    value = Column(Text, nullable=False)
    fingerprint = Column(String(255), nullable=True)  # SHA256 for SSH keys
    key_type = Column(String(64), nullable=True)  # inferred: rsa, ed25519, ecdsa, etc.
    passphrase = Column(String(1024), nullable=True)  # for encrypted private keys
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    operation = relationship("Operation", back_populates="credentials")
    links = relationship("CredentialLink", back_populates="credential", cascade="all, delete-orphan")


class CredentialLink(Base):
    __tablename__ = "credential_links"

    id = Column(String(36), primary_key=True, default=_uuid)
    credential_id = Column(String(36), ForeignKey("credentials.id", ondelete="CASCADE"), nullable=False)
    host_id = Column(String(36), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    username = Column(String(255), nullable=True)  # authoritative pivot-query field
    host_user_id = Column(String(36), ForeignKey("host_users.id", ondelete="SET NULL"), nullable=True)
    relationship_type = Column(
        "relationship",
        Enum(
            "found_on_disk",
            "authorized_key",
            "accepted_password",
            "used_in_connection",
            name="credlink_relationship",
        ),
        nullable=False,
    )
    file_source = Column(String(512), nullable=True)

    credential = relationship("Credential", back_populates="links")
    host = relationship("Host", back_populates="credential_links")
    host_user = relationship("HostUser")


class ConnectionRecord(Base):
    __tablename__ = "connection_records"

    id = Column(String(36), primary_key=True, default=_uuid)
    op_id = Column(String(36), ForeignKey("operations.id", ondelete="CASCADE"), nullable=False)
    src_host_id = Column(String(36), ForeignKey("hosts.id", ondelete="SET NULL"), nullable=True)
    src_ip = Column(String(45), nullable=False)
    src_user = Column(String(255), nullable=True)
    dst_host_id = Column(String(36), ForeignKey("hosts.id", ondelete="SET NULL"), nullable=True)
    dst_ip = Column(String(45), nullable=False)
    dst_user = Column(String(255), nullable=True)
    connection_type = Column(
        Enum("ssh", "scp", "rsync", "sftp", "ssh_copy_id", "unknown", name="connection_type"),
        nullable=False,
        default="unknown",
    )
    direction_context = Column(
        Enum("from_src_logs", "from_dst_logs", name="direction_context"),
        nullable=False,
    )
    auth_method = Column(
        Enum("publickey", "password", "keyboard-interactive", "hostbased", "unknown", name="auth_method"),
        nullable=True,
    )
    credential_id = Column(String(36), ForeignKey("credentials.id", ondelete="SET NULL"), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=True)
    raw_line = Column(Text, nullable=True)
    source_file = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    operation = relationship("Operation", back_populates="connection_records")
    src_host = relationship(
        "Host",
        foreign_keys=[src_host_id],
        back_populates="src_connections",
    )
    dst_host = relationship(
        "Host",
        foreign_keys=[dst_host_id],
        back_populates="dst_connections",
    )
    credential = relationship("Credential")


class SshConfigPattern(Base):
    """Stored SSH config Host pattern for retroactive edge creation when hosts are added."""
    __tablename__ = "ssh_config_patterns"

    id = Column(String(36), primary_key=True, default=_uuid)
    op_id = Column(String(36), ForeignKey("operations.id", ondelete="CASCADE"), nullable=False)
    source_host_id = Column(String(36), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    pattern = Column(String(512), nullable=False)   # space-joined alias list, e.g. "jb.*" or "box? !box0"
    username = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(String(36), primary_key=True, default=_uuid)
    op_id = Column(String(36), ForeignKey("operations.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(64), nullable=False)       # e.g. "host.create"
    entity_type = Column(String(64), nullable=False)  # "host" | "credential" | "connection" | "upload"
    entity_id = Column(String(36), nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
