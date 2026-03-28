"""add host_users table, host_user_id to credential_links, auth_method and credential_id to connection_records

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "host_users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("shell", sa.String(255), nullable=True),
        sa.Column("home_dir", sa.String(512), nullable=True),
        sa.Column(
            "source",
            sa.Enum("manual", "passwd_file", "authorized_keys", "log_evidence", name="hostuser_source"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("credential_links") as batch_op:
        batch_op.add_column(sa.Column("host_user_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_credential_links_host_user_id",
            "host_users",
            ["host_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("connection_records") as batch_op:
        batch_op.add_column(
            sa.Column(
                "auth_method",
                sa.Enum(
                    "publickey", "password", "keyboard-interactive", "hostbased", "unknown",
                    name="auth_method",
                ),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("credential_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_connection_records_credential_id",
            "credentials",
            ["credential_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("connection_records") as batch_op:
        batch_op.drop_column("credential_id")
        batch_op.drop_column("auth_method")

    with op.batch_alter_table("credential_links") as batch_op:
        batch_op.drop_column("host_user_id")

    op.drop_table("host_users")
