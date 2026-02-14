import pytest
from app.db.database import (
    get_db_connection, init_db, get_all_animes, get_anime,
    add_anime, update_anime, delete_anime,
    get_setting, set_setting, get_all_settings
)


class TestDatabaseConnection:
    
    def test_get_db_connection_returns_connection(self, app):
        with app.app_context():
            conn = get_db_connection()
            assert conn is not None
            conn.close()
    
    def test_connection_has_row_factory(self, app):
        with app.app_context():
            conn = get_db_connection()
            assert conn.row_factory is not None
            conn.close()


class TestSettings:
    
    def test_set_and_get_setting(self, app):
        with app.app_context():
            set_setting('test_key', 'test_value')
            value = get_setting('test_key')
            assert value == 'test_value'
    
    def test_get_nonexistent_setting(self, app):
        with app.app_context():
            value = get_setting('nonexistent_key', 'default_value')
            assert value == 'default_value'
    
    def test_update_setting(self, app):
        with app.app_context():
            set_setting('update_key', 'value1')
            set_setting('update_key', 'value2')
            value = get_setting('update_key')
            assert value == 'value2'
    
    def test_get_all_settings(self, app):
        with app.app_context():
            set_setting('key1', 'value1')
            set_setting('key2', 'value2')
            settings = get_all_settings()
            assert 'key1' in settings
            assert 'key2' in settings


class TestAnimeCRUD:
    
    def test_add_anime(self, app):
        with app.app_context():
            anime_id = add_anime({
                'title_cn': '测试动漫',
                'title_en': 'Test Anime',
                'total_episodes': 12,
                'tmdb_id': 12345
            })
            assert anime_id is not None
            assert anime_id > 0
    
    def test_get_anime_by_id(self, app):
        with app.app_context():
            anime_id = add_anime({
                'title_cn': '查询测试',
                'title_en': 'Query Test',
                'total_episodes': 24,
                'tmdb_id': 54321
            })
            
            anime = get_anime(anime_id)
            assert anime is not None
            assert anime['title_cn'] == '查询测试'
            assert anime['total_episodes'] == 24
    
    def test_get_anime_by_tmdb_id(self, app):
        with app.app_context():
            add_anime({
                'title_cn': 'TMDB测试',
                'tmdb_id': 99999
            })
            
            from app.db.database import get_anime_by_tmdb_id
            anime = get_anime_by_tmdb_id(99999)
            assert anime is not None
            assert anime['title_cn'] == 'TMDB测试'
    
    def test_update_anime(self, app):
        with app.app_context():
            anime_id = add_anime({
                'title_cn': '更新测试',
                'title_en': 'Update Test',
                'total_episodes': 12,
                'tmdb_id': 11111
            })
            
            update_anime(anime_id, {'total_episodes': 24, 'watched_ep': 10})
            
            anime = get_anime(anime_id)
            assert anime['total_episodes'] == 24
            assert anime['watched_ep'] == 10
    
    def test_delete_anime(self, app):
        with app.app_context():
            anime_id = add_anime({
                'title_cn': '删除测试',
                'title_en': 'Delete Test',
                'total_episodes': 12,
                'tmdb_id': 22222
            })
            
            delete_anime(anime_id)
            
            anime = get_anime(anime_id)
            assert anime is None
    
    def test_get_all_animes(self, app):
        with app.app_context():
            add_anime({'title_cn': '动漫1', 'total_episodes': 12, 'tmdb_id': 10001})
            add_anime({'title_cn': '动漫2', 'total_episodes': 24, 'tmdb_id': 10002})
            
            animes = get_all_animes()
            assert len(animes) >= 2


class TestDatabaseInitialization:
    
    def test_init_db_creates_tables(self, app):
        with app.app_context():
            init_db()
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row['name'] for row in cursor.fetchall()]
            
            assert 'animes' in tables
            assert 'episodes' in tables
            assert 'settings' in tables
            
            conn.close()
