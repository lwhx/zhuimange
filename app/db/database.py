"""
追漫阁 - 数据库模块
"""
import sqlite3
import os
import logging
from contextlib import contextmanager
from typing import Any, Optional
from app import config

logger = logging.getLogger(__name__)

DB_PATH = None


def get_db_path() -> str:
    """获取数据库文件路径"""
    global DB_PATH
    if DB_PATH:
        return DB_PATH
    db_path = config.DATABASE_PATH
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    return db_path


def get_db_connection():
    """获取数据库连接（非上下文管理器版本，用于测试）"""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_connection():
    """获取数据库连接上下文管理器"""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_connection():
    """检查数据库连接是否正常"""
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"数据库连接检查失败: {e}")
        raise


def init_db(use_migrations: bool = None):
    """初始化数据库，创建所有表
    
    Args:
        use_migrations: 是否使用 Alembic 迁移，默认 True（测试环境为 False）
    """
    from flask import current_app
    
    if use_migrations is None:
        use_migrations = current_app.config.get('USE_MIGRATIONS', not getattr(current_app.config, 'TESTING', False))
    
    if use_migrations:
        from app.db.migration import upgrade_database
        try:
            upgrade_database()
            return
        except Exception as e:
            logger.warning(f"迁移执行失败，回退到传统初始化: {e}")
    
    with get_connection() as conn:
        c = conn.cursor()

        # 动漫基本信息表
        c.execute('''CREATE TABLE IF NOT EXISTS animes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tmdb_id INTEGER UNIQUE,
            title_cn TEXT NOT NULL,
            title_en TEXT DEFAULT '',
            poster_url TEXT DEFAULT '',
            overview TEXT DEFAULT '',
            air_date TEXT DEFAULT '',
            total_episodes INTEGER DEFAULT 0,
            watched_ep INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Unknown',
            sync_interval INTEGER DEFAULT 0,
            last_sync_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # 集数信息表
        c.execute('''CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_id INTEGER NOT NULL,
            season_number INTEGER DEFAULT 1,
            episode_number INTEGER DEFAULT 0,
            absolute_num INTEGER DEFAULT 0,
            title TEXT DEFAULT '',
            overview TEXT DEFAULT '',
            air_date TEXT DEFAULT '',
            still_path TEXT DEFAULT '',
            watched INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (anime_id) REFERENCES animes(id) ON DELETE CASCADE
        )''')

        # 视频源表
        c.execute('''CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_id INTEGER NOT NULL,
            video_id TEXT NOT NULL,
            title TEXT DEFAULT '',
            channel_id TEXT DEFAULT '',
            channel_name TEXT DEFAULT '',
            duration INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            published_at TEXT DEFAULT '',
            match_score REAL DEFAULT 0,
            is_valid INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
        )''')

        # 自定义别名表
        c.execute('''CREATE TABLE IF NOT EXISTS custom_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_id INTEGER NOT NULL,
            alias TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (anime_id) REFERENCES animes(id) ON DELETE CASCADE
        )''')

        # 搜索规则表
        c.execute('''CREATE TABLE IF NOT EXISTS anime_source_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_id INTEGER NOT NULL UNIQUE,
            allow_keywords TEXT DEFAULT '[]',
            deny_keywords TEXT DEFAULT '[]',
            allow_channels TEXT DEFAULT '[]',
            deny_channels TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (anime_id) REFERENCES animes(id) ON DELETE CASCADE
        )''')

        # 全局设置表
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # 同步日志表
        c.execute('''CREATE TABLE IF NOT EXISTS sync_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anime_id INTEGER,
            sync_type TEXT DEFAULT 'manual',
            episodes_synced INTEGER DEFAULT 0,
            sources_found INTEGER DEFAULT 0,
            status TEXT DEFAULT 'success',
            message TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (anime_id) REFERENCES animes(id) ON DELETE SET NULL
        )''')

        # 信任频道表
        c.execute('''CREATE TABLE IF NOT EXISTS trusted_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL UNIQUE,
            channel_name TEXT DEFAULT '',
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # 全局别名表
        c.execute('''CREATE TABLE IF NOT EXISTS global_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            alias TEXT NOT NULL,
            category TEXT DEFAULT 'donghua',
            UNIQUE(title, alias)
        )''')

        # 创建索引
        c.execute("CREATE INDEX IF NOT EXISTS idx_episodes_anime_id ON episodes(anime_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sources_episode_id ON sources(episode_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sources_video_id ON sources(video_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sync_logs_anime_id ON sync_logs(anime_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_custom_aliases_anime_id ON custom_aliases(anime_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_global_aliases_title ON global_aliases(title)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_global_aliases_alias ON global_aliases(alias)")

        # 插入默认设置
        default_settings = {
            "auto_sync_enabled": "true",
            "auto_sync_interval": "360",
            "match_threshold": str(config.MATCH_THRESHOLD),
            "match_recommend_threshold": str(config.MATCH_RECOMMEND_THRESHOLD),
            "invidious_url": config.INVIDIOUS_URL,
        }
        for key, value in default_settings.items():
            c.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )

        logger.info("数据库初始化完成")


# ==================== 动漫 CRUD ====================

def get_all_animes() -> list[dict]:
    """获取所有动漫"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM animes ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def get_anime(anime_id: int) -> Optional[dict]:
    """获取单个动漫详情"""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM animes WHERE id = ?", (anime_id,)).fetchone()
        return dict(row) if row else None


def get_anime_by_tmdb_id(tmdb_id: int) -> Optional[dict]:
    """根据 TMDB ID 查找动漫"""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM animes WHERE tmdb_id = ?", (tmdb_id,)).fetchone()
        return dict(row) if row else None


def add_anime(data: dict) -> int:
    """添加动漫，返回新记录 ID"""
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO animes (tmdb_id, title_cn, title_en, poster_url, overview,
               air_date, total_episodes, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.get("tmdb_id"),
                data.get("title_cn", ""),
                data.get("title_en", ""),
                data.get("poster_url", ""),
                data.get("overview", ""),
                data.get("air_date", ""),
                data.get("total_episodes", 0),
                data.get("status", "Unknown"),
            )
        )
        return cursor.lastrowid


def update_anime(anime_id: int, data: dict):
    """更新动漫信息"""
    fields = []
    values = []
    for key in ["title_cn", "title_en", "poster_url", "overview",
                 "total_episodes", "watched_ep", "status", "sync_interval",
                 "last_sync_at"]:
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])
    if not fields:
        return
    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(anime_id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE animes SET {', '.join(fields)} WHERE id = ?",
            values
        )


def touch_anime_sync(anime_id: int):
    """更新动漫最后同步时间"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE animes SET last_sync_at = CURRENT_TIMESTAMP WHERE id = ?",
            (anime_id,)
        )


def delete_anime(anime_id: int):
    """删除动漫及其关联数据"""
    with get_connection() as conn:
        conn.execute("DELETE FROM animes WHERE id = ?", (anime_id,))


# ==================== 集数 CRUD ====================

def get_episodes(anime_id: int) -> list[dict]:
    """获取动漫的所有集数"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM episodes WHERE anime_id = ? ORDER BY absolute_num ASC",
            (anime_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_episode(episode_id: int) -> Optional[dict]:
    """获取单个集数"""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        return dict(row) if row else None


def get_episode_by_num(anime_id: int, ep_num: int) -> Optional[dict]:
    """根据集数号获取"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM episodes WHERE anime_id = ? AND absolute_num = ?",
            (anime_id, ep_num)
        ).fetchone()
        return dict(row) if row else None


def add_episodes(anime_id: int, episodes_data: list[dict]):
    """批量添加集数"""
    with get_connection() as conn:
        for ep in episodes_data:
            conn.execute(
                """INSERT OR IGNORE INTO episodes
                   (anime_id, season_number, episode_number, absolute_num, title, overview, air_date, still_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    anime_id,
                    ep.get("season_number", 1),
                    ep.get("episode_number", 0),
                    ep.get("absolute_num", 0),
                    ep.get("title", ""),
                    ep.get("overview", ""),
                    ep.get("air_date", ""),
                    ep.get("still_path", ""),
                )
            )


def mark_episode_watched(anime_id: int, ep_num: int, watched: bool = True):
    """标记集数已看/未看"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE episodes SET watched = ? WHERE anime_id = ? AND absolute_num = ?",
            (1 if watched else 0, anime_id, ep_num)
        )
        if watched:
            conn.execute(
                """UPDATE animes SET watched_ep = (
                    SELECT COUNT(*) FROM episodes WHERE anime_id = ? AND watched = 1
                ), updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (anime_id, anime_id)
            )


# ==================== 视频源 CRUD ====================

def get_sources_for_episode(episode_id: int) -> list[dict]:
    """获取集数的视频源"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sources WHERE episode_id = ? AND is_valid = 1 ORDER BY match_score DESC",
            (episode_id,)
        ).fetchall()
        return [dict(row) for row in rows]


def add_source(data: dict) -> int:
    """添加视频源"""
    with get_connection() as conn:
        # 检查是否已存在
        existing = conn.execute(
            "SELECT id FROM sources WHERE episode_id = ? AND video_id = ?",
            (data["episode_id"], data["video_id"])
        ).fetchone()
        if existing:
            return existing["id"]

        cursor = conn.execute(
            """INSERT INTO sources
               (episode_id, video_id, title, channel_id, channel_name,
                duration, view_count, published_at, match_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["episode_id"],
                data["video_id"],
                data.get("title", ""),
                data.get("channel_id", ""),
                data.get("channel_name", ""),
                data.get("duration", 0),
                data.get("view_count", 0),
                data.get("published_at", ""),
                data.get("match_score", 0),
            )
        )
        return cursor.lastrowid


# ==================== 别名 CRUD ====================

def get_aliases(anime_id: int) -> list[str]:
    """获取动漫别名列表"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT alias FROM custom_aliases WHERE anime_id = ?",
            (anime_id,)
        ).fetchall()
        return [row["alias"] for row in rows]


def add_alias(anime_id: int, alias: str):
    """添加别名"""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO custom_aliases (anime_id, alias) VALUES (?, ?)",
            (anime_id, alias)
        )


# ==================== 搜索规则 ====================

def get_source_rules(anime_id: int) -> Optional[dict]:
    """获取搜索规则"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM anime_source_rules WHERE anime_id = ?",
            (anime_id,)
        ).fetchone()
        return dict(row) if row else None


def set_source_rules(anime_id: int, rules: dict):
    """设置搜索规则"""
    import json
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO anime_source_rules (anime_id, allow_keywords, deny_keywords, allow_channels, deny_channels)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(anime_id) DO UPDATE SET
               allow_keywords = excluded.allow_keywords,
               deny_keywords = excluded.deny_keywords,
               allow_channels = excluded.allow_channels,
               deny_channels = excluded.deny_channels,
               updated_at = CURRENT_TIMESTAMP""",
            (
                anime_id,
                json.dumps(rules.get("allow_keywords", []), ensure_ascii=False),
                json.dumps(rules.get("deny_keywords", []), ensure_ascii=False),
                json.dumps(rules.get("allow_channels", []), ensure_ascii=False),
                json.dumps(rules.get("deny_channels", []), ensure_ascii=False),
            )
        )


# ==================== 设置 ====================

def get_all_settings() -> dict[str, str]:
    """获取所有设置"""
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}


def get_setting(key: str, default: str = "") -> str:
    """获取单个设置"""
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    """设置/更新单个设置"""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value,
               updated_at = CURRENT_TIMESTAMP""",
            (key, value)
        )


# ==================== 同步日志 ====================

def add_sync_log(anime_id: int, sync_type: str, episodes_synced: int,
                 sources_found: int, status: str = "success", message: str = ""):
    """添加同步日志"""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO sync_logs (anime_id, sync_type, episodes_synced, sources_found, status, message)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (anime_id, sync_type, episodes_synced, sources_found, status, message)
        )


def get_sync_logs(anime_id: Optional[int] = None, limit: int = 20) -> list[dict]:
    """获取同步日志"""
    with get_connection() as conn:
        if anime_id:
            rows = conn.execute(
                "SELECT * FROM sync_logs WHERE anime_id = ? ORDER BY created_at DESC LIMIT ?",
                (anime_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sync_logs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(row) for row in rows]


def cleanup_old_sync_logs(days: int = 90):
    """清理过期同步日志"""
    with get_connection() as conn:
        conn.execute(
            f"DELETE FROM sync_logs WHERE created_at < datetime('now', '-{days} days')"
        )


# ==================== 信任频道 ====================

def get_trusted_channels() -> list[dict]:
    """获取所有信任频道"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM trusted_channels ORDER BY priority DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def is_trusted_channel(channel_id: str) -> bool:
    """检查是否为信任频道"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM trusted_channels WHERE channel_id = ?",
            (channel_id,)
        ).fetchone()
        return row is not None


# ==================== 全局别名 ====================

def get_all_global_aliases() -> list[dict]:
    """获取所有全局别名"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM global_aliases ORDER BY title, alias"
        ).fetchall()
        return [dict(row) for row in rows]


def get_global_aliases_by_title(title: str) -> list[str]:
    """根据标题获取别名列表"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT alias FROM global_aliases WHERE title = ?",
            (title,)
        ).fetchall()
        return [row["alias"] for row in rows]


def get_global_aliases_by_category(category: str) -> list[dict]:
    """根据类别获取全局别名"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM global_aliases WHERE category = ? ORDER BY title, alias",
            (category,)
        ).fetchall()
        return [dict(row) for row in rows]


def add_global_alias(title: str, alias: str, category: str = "donghua") -> bool:
    """添加全局别名
    
    Returns:
        True if added successfully, False if duplicate
    """
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO global_aliases (title, alias, category) VALUES (?, ?, ?)",
                (title, alias, category)
            )
        return True
    except sqlite3.IntegrityError:
        return False


def delete_global_alias(alias_id: int) -> bool:
    """删除全局别名
    
    Returns:
        True if deleted, False if not found
    """
    with get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM global_aliases WHERE id = ?",
            (alias_id,)
        )
        return cursor.rowcount > 0


def search_global_aliases_by_alias(alias: str) -> list[dict]:
    """根据别名搜索（模糊匹配）
    
    Returns:
        匹配的标题和别名列表
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT title FROM global_aliases WHERE alias LIKE ?",
            (f"%{alias}%",)
        ).fetchall()
        return [dict(row) for row in rows]


def get_all_global_aliases_dict() -> dict[str, list[str]]:
    """获取所有全局别名，返回字典格式 {title: [aliases]}"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT title, alias FROM global_aliases ORDER BY title, alias"
        ).fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            title = row["title"]
            alias = row["alias"]
            if title not in result:
                result[title] = []
            result[title].append(alias)
        return result


def init_default_global_aliases() -> int:
    """初始化默认全局别名（从 config.py 迁移）
    
    Returns:
        插入的别名数量
    """
    from app import config
    
    inserted_count = 0
    for title, aliases in config.DONGHUA_ALIASES.items():
        for alias in aliases:
            if add_global_alias(title, alias, "donghua"):
                inserted_count += 1
    return inserted_count


# ==================== 备份日志 ====================

def add_backup_log(backup_type: str, status: str, message: str = "", 
                   file_size: int = 0, file_name: str = "", error_code: str = "") -> int:
    """添加备份日志
    
    Args:
        backup_type: 备份类型 (telegram, local)
        status: 状态 (success, error, partial)
        message: 消息
        file_size: 文件大小（字节）
        file_name: 文件名
        error_code: 错误代码
    
    Returns:
        插入的记录ID
    """
    with get_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO backup_logs 
               (backup_type, status, message, file_size, file_name, error_code)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (backup_type, status, message, file_size, file_name, error_code)
        )
        return cursor.lastrowid


def get_backup_logs(backup_type: str = None, status: str = None, limit: int = 50) -> list[dict]:
    """获取备份日志
    
    Args:
        backup_type: 备份类型筛选
        status: 状态筛选
        limit: 返回数量限制
    
    Returns:
        备份日志列表
    """
    with get_connection() as conn:
        query = "SELECT * FROM backup_logs"
        params = []
        conditions = []
        
        if backup_type:
            conditions.append("backup_type = ?")
            params.append(backup_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def get_backup_stats(days: int = 30) -> dict:
    """获取备份统计信息
    
    Args:
        days: 统计最近多少天
    
    Returns:
        统计信息字典
    """
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as count FROM backup_logs WHERE created_at >= datetime('now', ?)",
            (f'-{days} days',)
        ).fetchone()["count"]
        
        success = conn.execute(
            "SELECT COUNT(*) as count FROM backup_logs WHERE status = 'success' AND created_at >= datetime('now', ?)",
            (f'-{days} days',)
        ).fetchone()["count"]
        
        error = conn.execute(
            "SELECT COUNT(*) as count FROM backup_logs WHERE status = 'error' AND created_at >= datetime('now', ?)",
            (f'-{days} days',)
        ).fetchone()["count"]
        
        total_size = conn.execute(
            "SELECT SUM(file_size) as total FROM backup_logs WHERE status = 'success' AND created_at >= datetime('now', ?)",
            (f'-{days} days',)
        ).fetchone()["total"] or 0
        
        return {
            "total_backups": total,
            "successful_backups": success,
            "failed_backups": error,
            "success_rate": round(success / total * 100, 2) if total > 0 else 0,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "period_days": days
        }


def get_latest_backup(backup_type: str = "telegram") -> dict:
    """获取最新备份记录
    
    Args:
        backup_type: 备份类型
    
    Returns:
        最新备份记录，如果没有则返回 None
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM backup_logs WHERE backup_type = ? ORDER BY created_at DESC LIMIT 1",
            (backup_type,)
        ).fetchone()
        return dict(row) if row else None


def cleanup_old_backup_logs(days: int = 180) -> int:
    """清理过期备份日志
    
    Args:
        days: 保留天数
    
    Returns:
        删除的记录数
    """
    with get_connection() as conn:
        cursor = conn.execute(
            f"DELETE FROM backup_logs WHERE created_at < datetime('now', '-{days} days')"
        )
        return cursor.rowcount
