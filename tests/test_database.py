"""
数据库模块单元测试
"""
import pytest
from app.db import database as db


class TestAnimeCRUD:
    """动漫 CRUD 测试"""

    def test_add_and_get_anime(self, app):
        with app.app_context():
            anime_id = db.add_anime({
                "title_cn": "测试动漫",
                "title_en": "Test Anime",
                "total_episodes": 12,
            })
            assert anime_id > 0

            anime = db.get_anime(anime_id)
            assert anime is not None
            assert anime["title_cn"] == "测试动漫"
            assert anime["title_en"] == "Test Anime"

    def test_get_anime_not_found(self, app):
        with app.app_context():
            anime = db.get_anime(99999)
            assert anime is None

    def test_update_anime(self, app):
        with app.app_context():
            anime_id = db.add_anime({"title_cn": "原始名称"})
            db.update_anime(anime_id, {"title_cn": "更新名称", "watched_ep": 5})

            anime = db.get_anime(anime_id)
            assert anime["title_cn"] == "更新名称"
            assert anime["watched_ep"] == 5

    def test_update_anime_ignores_invalid_field(self, app):
        with app.app_context():
            anime_id = db.add_anime({"title_cn": "测试"})
            # 非法字段应被忽略，不应报错
            db.update_anime(anime_id, {"invalid_field": "value", "title_cn": "合法更新"})

            anime = db.get_anime(anime_id)
            assert anime["title_cn"] == "合法更新"

    def test_delete_anime(self, app):
        with app.app_context():
            anime_id = db.add_anime({"title_cn": "待删除"})
            db.delete_anime(anime_id)
            assert db.get_anime(anime_id) is None

    def test_duplicate_tmdb_id(self, app):
        with app.app_context():
            db.add_anime({"tmdb_id": 12345, "title_cn": "动漫A"})
            # 同一 tmdb_id 再次添加应抛异常
            with pytest.raises(Exception):
                db.add_anime({"tmdb_id": 12345, "title_cn": "动漫B"})


class TestEpisodeCRUD:
    """集数 CRUD 测试"""

    def test_add_and_get_episodes(self, app):
        with app.app_context():
            anime_id = db.add_anime({"title_cn": "测试动漫"})
            db.add_episodes(anime_id, [
                {"absolute_num": 1, "episode_number": 1, "season_number": 1},
                {"absolute_num": 2, "episode_number": 2, "season_number": 1},
            ])

            episodes = db.get_episodes(anime_id)
            assert len(episodes) == 2

    def test_mark_episode_watched(self, app):
        with app.app_context():
            anime_id = db.add_anime({"title_cn": "测试动漫"})
            db.add_episodes(anime_id, [
                {"absolute_num": 1, "episode_number": 1, "season_number": 1},
            ])
            db.mark_episode_watched(anime_id, 1, True)

            episode = db.get_episode_by_num(anime_id, 1)
            assert episode["watched"] == 1


class TestSettings:
    """设置 CRUD 测试"""

    def test_get_set_setting(self, app):
        with app.app_context():
            db.set_setting("test_key", "test_value")
            value = db.get_setting("test_key")
            assert value == "test_value"

    def test_get_setting_default(self, app):
        with app.app_context():
            value = db.get_setting("nonexistent", "default_val")
            assert value == "default_val"

    def test_update_setting(self, app):
        with app.app_context():
            db.set_setting("key1", "v1")
            db.set_setting("key1", "v2")
            assert db.get_setting("key1") == "v2"


class TestAliases:
    """别名 CRUD 测试"""

    def test_add_and_get_aliases(self, app):
        with app.app_context():
            anime_id = db.add_anime({"title_cn": "测试动漫"})
            db.add_alias(anime_id, "别名1")
            db.add_alias(anime_id, "别名2")

            aliases = db.get_aliases(anime_id)
            assert "别名1" in aliases
            assert "别名2" in aliases


class TestSyncLogs:
    """同步日志测试"""

    def test_add_and_get_sync_logs(self, app):
        with app.app_context():
            anime_id = db.add_anime({"title_cn": "测试动漫"})
            db.add_sync_log(anime_id, "manual", 5, 10, "success", "测试")

            logs = db.get_sync_logs(anime_id)
            assert len(logs) >= 1
            assert logs[0]["status"] == "success"
