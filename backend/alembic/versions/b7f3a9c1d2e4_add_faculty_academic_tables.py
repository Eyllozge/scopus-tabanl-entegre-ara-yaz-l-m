"""faculties ve academics tabloları

Revision ID: b7f3a9c1d2e4
Revises: a1e9204b7f0c
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b7f3a9c1d2e4'
down_revision: Union[str, Sequence[str], None] = 'a1e9204b7f0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'faculties',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('unit_type', sa.String(), nullable=True),
        sa.Column('source_subdomain', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('source_subdomain'),
    )
    op.create_table(
        'academics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('full_name', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('department', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('orcid', sa.String(), nullable=True),
        sa.Column('yok_author_id', sa.String(), nullable=True),
        sa.Column('faculty_id', sa.Integer(), nullable=True),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['faculty_id'], ['faculties.id']),
        sa.ForeignKeyConstraint(['author_id'], ['authors.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('author_id'),
    )
    op.create_index(op.f('ix_academics_full_name'), 'academics', ['full_name'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_academics_full_name'), table_name='academics')
    op.drop_table('academics')
    op.drop_table('faculties')