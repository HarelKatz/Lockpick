"""add host os_version and kernel_version

Revision ID: 919e6f287b3e
Revises: 20c78a366696
Create Date: 2026-07-26 20:17:32.361018

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '919e6f287b3e'
down_revision: Union[str, Sequence[str], None] = '20c78a366696'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('hosts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('os_version', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('kernel_version', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('hosts', schema=None) as batch_op:
        batch_op.drop_column('kernel_version')
        batch_op.drop_column('os_version')
