"""add source health fields

Revision ID: 004
Revises: 003
Create Date: 2026-04-25

"""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def _has_column(conn, table_name, column_name):
    """判断指定数据表是否存在字段"""
    inspector = sa.inspect(conn)
    columns = inspector.get_columns(table_name)
    return any(column['name'] == column_name for column in columns)


def upgrade():
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, 'sources'):
        return

    if not _has_column(conn, 'sources', 'health_status'):
        op.add_column('sources', sa.Column('health_status', sa.String(), nullable=True, server_default='unknown'))
    if not _has_column(conn, 'sources', 'last_checked_at'):
        op.add_column('sources', sa.Column('last_checked_at', sa.DateTime(), nullable=True))
    if not _has_column(conn, 'sources', 'last_check_error'):
        op.add_column('sources', sa.Column('last_check_error', sa.String(), nullable=True, server_default=''))
    if not _has_column(conn, 'sources', 'fail_count'):
        op.add_column('sources', sa.Column('fail_count', sa.Integer(), nullable=True, server_default='0'))

    op.execute("UPDATE sources SET health_status = 'unknown' WHERE health_status IS NULL")
    op.execute("UPDATE sources SET last_check_error = '' WHERE last_check_error IS NULL")
    op.execute("UPDATE sources SET fail_count = 0 WHERE fail_count IS NULL")


def downgrade():
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, 'sources'):
        return

    if _has_column(conn, 'sources', 'fail_count'):
        op.drop_column('sources', 'fail_count')
    if _has_column(conn, 'sources', 'last_check_error'):
        op.drop_column('sources', 'last_check_error')
    if _has_column(conn, 'sources', 'last_checked_at'):
        op.drop_column('sources', 'last_checked_at')
    if _has_column(conn, 'sources', 'health_status'):
        op.drop_column('sources', 'health_status')
