"""remove interface_name from host_ips

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("host_ips") as batch_op:
        batch_op.drop_column("interface_name")


def downgrade() -> None:
    with op.batch_alter_table("host_ips") as batch_op:
        batch_op.add_column(sa.Column("interface_name", sa.String(64), nullable=True))
