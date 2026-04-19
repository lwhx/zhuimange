"""Add backup logs table

Revision ID: 003
Revises: 002
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''
        CREATE TABLE IF NOT EXISTS backup_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_type TEXT DEFAULT 'telegram',
            status TEXT DEFAULT 'success',
            message TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            file_name TEXT DEFAULT '',
            error_code TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    op.execute("CREATE INDEX IF NOT EXISTS idx_backup_logs_status ON backup_logs(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_backup_logs_type ON backup_logs(backup_type)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_backup_logs_status")
    op.execute("DROP INDEX IF EXISTS idx_backup_logs_type")
    op.execute("DROP TABLE IF EXISTS backup_logs")
