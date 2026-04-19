"""add global_aliases table

Revision ID: 002
Revises: 001
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    
    if not conn.dialect.has_table(conn, 'global_aliases'):
        op.create_table(
            'global_aliases',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('title', sa.String(), nullable=False),
            sa.Column('alias', sa.String(), nullable=False),
            sa.Column('category', sa.String(), nullable=True, server_default='donghua'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('title', 'alias')
        )
    
    if conn.dialect.has_table(conn, 'global_aliases'):
        inspector = sa.inspect(conn)
        existing_indexes = inspector.get_indexes('global_aliases')
        if not any(idx['name'] == 'idx_global_aliases_title' for idx in existing_indexes):
            op.create_index('idx_global_aliases_title', 'global_aliases', ['title'], unique=False)
        if not any(idx['name'] == 'idx_global_aliases_alias' for idx in existing_indexes):
            op.create_index('idx_global_aliases_alias', 'global_aliases', ['alias'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_global_aliases_alias', table_name='global_aliases')
    op.drop_index('idx_global_aliases_title', table_name='global_aliases')
    op.drop_table('global_aliases')
