"""is_firat, is_firat_academic, metadata_source ekle

Revision ID: a1e9204b7f0c
Revises: 0a8ddd32f1cf
Create Date: 2026-08-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1e9204b7f0c'
down_revision: Union[str, Sequence[str], None] = '0a8ddd32f1cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('articles', sa.Column('metadata_source', sa.String(), nullable=True))
    op.add_column(
        'authors',
        sa.Column('is_firat_academic', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'institutions',
        sa.Column('is_firat', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('institutions', 'is_firat')
    op.drop_column('authors', 'is_firat_academic')
    op.drop_column('articles', 'metadata_source')