"""remove host_users table, cidr column, and replace host_user_id with username in credential_links

Revision ID: a1b2c3d4e5f6
Revises: 2ddf7ad3d932
Create Date: 2026-03-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '2ddf7ad3d932'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rebuild credential_links without host_user_id FK, adding username string instead.
    # SQLite doesn't support DROP COLUMN / ALTER COLUMN directly, so use batch mode.
    with op.batch_alter_table("credential_links") as batch_op:
        batch_op.drop_constraint("fk_credential_links_host_user_id", type_="foreignkey")
        batch_op.drop_column("host_user_id")
        batch_op.add_column(sa.Column("username", sa.String(255), nullable=True))

    # Remove cidr from host_ips
    with op.batch_alter_table("host_ips") as batch_op:
        batch_op.drop_column("cidr")

    # Drop host_users table (no longer needed)
    op.drop_table("host_users")


def downgrade() -> None:
    op.create_table(
        "host_users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("host_id", sa.String(36), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("shell", sa.String(255), nullable=True),
        sa.Column("home_dir", sa.String(512), nullable=True),
        sa.Column(
            "source",
            sa.Enum("manual", "passwd_file", "authorized_keys", "home_dir_found", "log_evidence", name="hostuser_source"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["host_id"], ["hosts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("host_ips") as batch_op:
        batch_op.add_column(sa.Column("cidr", sa.String(3), nullable=True))

    with op.batch_alter_table("credential_links") as batch_op:
        batch_op.drop_column("username")
        batch_op.add_column(sa.Column("host_user_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_credential_links_host_user_id",
            "host_users",
            ["host_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
