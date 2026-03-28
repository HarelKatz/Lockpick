"""add passphrase column to credentials

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("credentials") as batch_op:
        batch_op.add_column(sa.Column("passphrase", sa.String(1024), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("credentials") as batch_op:
        batch_op.drop_column("passphrase")
