"""initial schema

Revision ID: 001
Revises: 
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    
    if not conn.dialect.has_table(conn, 'animes'):
        op.create_table(
            'animes',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('tmdb_id', sa.Integer(), nullable=True),
            sa.Column('title_cn', sa.String(), nullable=False),
            sa.Column('title_en', sa.String(), nullable=True),
            sa.Column('poster_url', sa.String(), nullable=True),
            sa.Column('overview', sa.String(), nullable=True),
            sa.Column('air_date', sa.String(), nullable=True),
            sa.Column('total_episodes', sa.Integer(), nullable=True),
            sa.Column('watched_ep', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(), nullable=True),
            sa.Column('sync_interval', sa.Integer(), nullable=True),
            sa.Column('last_sync_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('tmdb_id')
        )
    
    if not conn.dialect.has_table(conn, 'episodes'):
        op.create_table(
            'episodes',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('anime_id', sa.Integer(), nullable=False),
            sa.Column('season_number', sa.Integer(), nullable=True),
            sa.Column('episode_number', sa.Integer(), nullable=True),
            sa.Column('absolute_num', sa.Integer(), nullable=True),
            sa.Column('title', sa.String(), nullable=True),
            sa.Column('overview', sa.String(), nullable=True),
            sa.Column('air_date', sa.String(), nullable=True),
            sa.Column('still_path', sa.String(), nullable=True),
            sa.Column('watched', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['anime_id'], ['animes.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
    
    if not conn.dialect.has_table(conn, 'sources'):
        op.create_table(
            'sources',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('episode_id', sa.Integer(), nullable=False),
            sa.Column('video_id', sa.String(), nullable=False),
            sa.Column('title', sa.String(), nullable=True),
            sa.Column('channel_id', sa.String(), nullable=True),
            sa.Column('channel_name', sa.String(), nullable=True),
            sa.Column('duration', sa.Integer(), nullable=True),
            sa.Column('view_count', sa.Integer(), nullable=True),
            sa.Column('published_at', sa.String(), nullable=True),
            sa.Column('match_score', sa.Float(), nullable=True),
            sa.Column('is_valid', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['episode_id'], ['episodes.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
    
    if not conn.dialect.has_table(conn, 'custom_aliases'):
        op.create_table(
            'custom_aliases',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('anime_id', sa.Integer(), nullable=False),
            sa.Column('alias', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['anime_id'], ['animes.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
    
    if not conn.dialect.has_table(conn, 'anime_source_rules'):
        op.create_table(
            'anime_source_rules',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('anime_id', sa.Integer(), nullable=False),
            sa.Column('allow_keywords', sa.String(), nullable=True),
            sa.Column('deny_keywords', sa.String(), nullable=True),
            sa.Column('allow_channels', sa.String(), nullable=True),
            sa.Column('deny_channels', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['anime_id'], ['animes.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('anime_id')
        )
    
    if not conn.dialect.has_table(conn, 'settings'):
        op.create_table(
            'settings',
            sa.Column('key', sa.String(), nullable=False),
            sa.Column('value', sa.String(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('key')
        )
    
    if not conn.dialect.has_table(conn, 'sync_logs'):
        op.create_table(
            'sync_logs',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('anime_id', sa.Integer(), nullable=True),
            sa.Column('sync_type', sa.String(), nullable=True),
            sa.Column('episodes_synced', sa.Integer(), nullable=True),
            sa.Column('sources_found', sa.Integer(), nullable=True),
            sa.Column('status', sa.String(), nullable=True),
            sa.Column('message', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['anime_id'], ['animes.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
    
    if not conn.dialect.has_table(conn, 'trusted_channels'):
        op.create_table(
            'trusted_channels',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('channel_id', sa.String(), nullable=False),
            sa.Column('channel_name', sa.String(), nullable=True),
            sa.Column('priority', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('channel_id')
        )
    
    if conn.dialect.has_table(conn, 'episodes'):
        inspector = sa.inspect(conn)
        existing_indexes = inspector.get_indexes('episodes')
        if not any(idx['name'] == 'idx_episodes_anime_id' for idx in existing_indexes):
            op.create_index('idx_episodes_anime_id', 'episodes', ['anime_id'], unique=False)
    
    if conn.dialect.has_table(conn, 'sources'):
        inspector = sa.inspect(conn)
        existing_indexes = inspector.get_indexes('sources')
        if not any(idx['name'] == 'idx_sources_episode_id' for idx in existing_indexes):
            op.create_index('idx_sources_episode_id', 'sources', ['episode_id'], unique=False)
        if not any(idx['name'] == 'idx_sources_video_id' for idx in existing_indexes):
            op.create_index('idx_sources_video_id', 'sources', ['video_id'], unique=False)
    
    if conn.dialect.has_table(conn, 'sync_logs'):
        inspector = sa.inspect(conn)
        existing_indexes = inspector.get_indexes('sync_logs')
        if not any(idx['name'] == 'idx_sync_logs_anime_id' for idx in existing_indexes):
            op.create_index('idx_sync_logs_anime_id', 'sync_logs', ['anime_id'], unique=False)
    
    if conn.dialect.has_table(conn, 'custom_aliases'):
        inspector = sa.inspect(conn)
        existing_indexes = inspector.get_indexes('custom_aliases')
        if not any(idx['name'] == 'idx_custom_aliases_anime_id' for idx in existing_indexes):
            op.create_index('idx_custom_aliases_anime_id', 'custom_aliases', ['anime_id'], unique=False)
    
    if conn.dialect.has_table(conn, 'settings'):
        result = conn.execute(sa.text("SELECT COUNT(*) FROM settings WHERE key = 'auto_sync_enabled'")).scalar()
        if result == 0:
            op.execute("""
                INSERT INTO settings (key, value) VALUES 
                ('auto_sync_enabled', 'true'),
                ('auto_sync_interval', '360'),
                ('match_threshold', '50'),
                ('match_recommend_threshold', '70'),
                ('invidious_url', 'https://invidious.snopyta.org')
            """)


def downgrade() -> None:
    op.drop_index('idx_custom_aliases_anime_id', table_name='custom_aliases')
    op.drop_index('idx_sync_logs_anime_id', table_name='sync_logs')
    op.drop_index('idx_sources_video_id', table_name='sources')
    op.drop_index('idx_sources_episode_id', table_name='sources')
    op.drop_index('idx_episodes_anime_id', table_name='episodes')
    
    op.drop_table('trusted_channels')
    op.drop_table('sync_logs')
    op.drop_table('settings')
    op.drop_table('anime_source_rules')
    op.drop_table('custom_aliases')
    op.drop_table('sources')
    op.drop_table('episodes')
    op.drop_table('animes')
