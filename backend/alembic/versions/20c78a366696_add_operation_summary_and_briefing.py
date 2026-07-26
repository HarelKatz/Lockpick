"""add operation summary and briefing

Revision ID: 20c78a366696
Revises: b69f12d97634
Create Date: 2026-07-26 20:07:13.517508

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20c78a366696'
down_revision: Union[str, Sequence[str], None] = 'b69f12d97634'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('operations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('summary', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('briefing', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('operations', schema=None) as batch_op:
        batch_op.drop_column('briefing')
        batch_op.drop_column('summary')
