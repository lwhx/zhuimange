"""add uniqueness constraints for duplicate-prone tables

Revision ID: 005
Revises: 004
Create Date: 2026-05-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlite3
from datetime import datetime
from pathlib import Path


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(conn, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(conn)
    return any(idx['name'] == index_name for idx in inspector.get_indexes(table_name))


def _backup_sqlite_database(conn) -> None:
    if conn.dialect.name != "sqlite":
        return

    database_path = conn.execute(sa.text("PRAGMA database_list")).fetchone()[2]
    if not database_path or database_path == ":memory:":
        return

    source_path = Path(database_path)
    if not source_path.exists():
        return

    backup_path = source_path.with_name(
        f"{source_path.stem}.pre-005-{datetime.now().strftime('%Y%m%d%H%M%S')}{source_path.suffix}"
    )

    source = sqlite3.connect(str(source_path))
    try:
        destination = sqlite3.connect(str(backup_path))
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    print(f"Created SQLite backup before duplicate cleanup: {backup_path}")


def upgrade() -> None:
    conn = op.get_bind()
    _backup_sqlite_database(conn)

    if conn.dialect.has_table(conn, 'episodes'):
        op.execute("UPDATE episodes SET absolute_num = 0 WHERE absolute_num IS NULL")

        # Move sources from duplicate episode rows to the first row for that anime/episode.
        if conn.dialect.has_table(conn, 'sources'):
            op.execute("""
                UPDATE sources
                SET episode_id = (
                    SELECT MIN(e2.id)
                    FROM episodes e1
                    JOIN episodes e2
                      ON e2.anime_id = e1.anime_id
                     AND e2.absolute_num = e1.absolute_num
                    WHERE e1.id = sources.episode_id
                )
                WHERE episode_id IN (
                    SELECT e.id
                    FROM episodes e
                    WHERE e.id NOT IN (
                        SELECT MIN(id)
                        FROM episodes
                        GROUP BY anime_id, absolute_num
                    )
                )
            """)

        # Keep the first row for each anime/episode number pair before enforcing uniqueness.
        op.execute("""
            DELETE FROM episodes
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM episodes
                GROUP BY anime_id, absolute_num
            )
        """)
        if not _index_exists(conn, 'episodes', 'uq_episodes_anime_absolute_num'):
            op.create_index(
                'uq_episodes_anime_absolute_num',
                'episodes',
                ['anime_id', 'absolute_num'],
                unique=True,
            )

    if conn.dialect.has_table(conn, 'sources'):
        op.execute("UPDATE sources SET video_id = '' WHERE video_id IS NULL")

        # Keep the first source for each episode/video pair before enforcing uniqueness.
        op.execute("""
            DELETE FROM sources
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM sources
                GROUP BY episode_id, video_id
            )
        """)
        if not _index_exists(conn, 'sources', 'uq_sources_episode_video'):
            op.create_index(
                'uq_sources_episode_video',
                'sources',
                ['episode_id', 'video_id'],
                unique=True,
            )

    if conn.dialect.has_table(conn, 'custom_aliases'):
        # Keep the first alias for each anime/alias pair before enforcing uniqueness.
        op.execute("""
            DELETE FROM custom_aliases
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM custom_aliases
                GROUP BY anime_id, alias
            )
        """)
        if not _index_exists(conn, 'custom_aliases', 'uq_custom_aliases_anime_alias'):
            op.create_index(
                'uq_custom_aliases_anime_alias',
                'custom_aliases',
                ['anime_id', 'alias'],
                unique=True,
            )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.has_table(conn, 'custom_aliases') and _index_exists(conn, 'custom_aliases', 'uq_custom_aliases_anime_alias'):
        op.drop_index('uq_custom_aliases_anime_alias', table_name='custom_aliases')
    if conn.dialect.has_table(conn, 'sources') and _index_exists(conn, 'sources', 'uq_sources_episode_video'):
        op.drop_index('uq_sources_episode_video', table_name='sources')
    if conn.dialect.has_table(conn, 'episodes') and _index_exists(conn, 'episodes', 'uq_episodes_anime_absolute_num'):
        op.drop_index('uq_episodes_anime_absolute_num', table_name='episodes')
