"""add connection_record parser_file_type

Revision ID: 7e2e0b6453f3
Revises: 4ee247f98898
Create Date: 2026-05-02 01:28:28.816548

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e2e0b6453f3'
down_revision: Union[str, Sequence[str], None] = '4ee247f98898'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("connection_records") as batch:
        batch.add_column(sa.Column("parser_file_type", sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("connection_records") as batch:
        batch.drop_column("parser_file_type")
