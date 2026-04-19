"""Add bangumi_id to animes table

Revision ID: 004
Revises: 003
Create Date: 2026-04-12
"""
from alembic import op

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.execute("ALTER TABLE animes ADD COLUMN bangumi_id INTEGER")
    except Exception:
        pass  # 字段已存在时忽略
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_animes_bangumi_id "
        "ON animes(bangumi_id) WHERE bangumi_id IS NOT NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_animes_bangumi_id")
