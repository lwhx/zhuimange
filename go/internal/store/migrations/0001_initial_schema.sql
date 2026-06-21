-- 初始 schema：兼容 Python 版表结构 + 新增功能表
-- 字段命名与 Python 版保持一致，确保数据迁移脚本可直接导入

-- 动漫主表（兼容 Python animes，新增 bangumi_id 用于互通）
CREATE TABLE IF NOT EXISTS animes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tmdb_id         INTEGER UNIQUE,
    bangumi_id      INTEGER,
    title_cn        TEXT NOT NULL,
    title_en        TEXT DEFAULT '',
    poster_url      TEXT DEFAULT '',
    overview        TEXT DEFAULT '',
    air_date        TEXT DEFAULT '',
    total_episodes  INTEGER DEFAULT 0,
    watched_ep      INTEGER DEFAULT 0,
    status          TEXT DEFAULT '',
    sync_interval   INTEGER DEFAULT 0,
    last_sync_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 集数表（绝对编号 absolute_num 是追更核心标识）
CREATE TABLE IF NOT EXISTS episodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    anime_id        INTEGER NOT NULL REFERENCES animes(id) ON DELETE CASCADE,
    season_number   INTEGER DEFAULT 1,
    episode_number  INTEGER DEFAULT 0,
    absolute_num    INTEGER NOT NULL,
    title           TEXT DEFAULT '',
    overview        TEXT DEFAULT '',
    air_date        TEXT DEFAULT '',
    still_path      TEXT DEFAULT '',
    watched         INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(anime_id, absolute_num)
);
CREATE INDEX IF NOT EXISTS idx_episodes_anime_id ON episodes(anime_id);

-- 视频源表（含健康检测字段）
CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id      INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    video_id        TEXT NOT NULL,
    title           TEXT DEFAULT '',
    channel_id      TEXT DEFAULT '',
    channel_name    TEXT DEFAULT '',
    duration        INTEGER DEFAULT 0,
    view_count      INTEGER DEFAULT 0,
    published_at    TEXT DEFAULT '',
    match_score     REAL DEFAULT 0,
    is_valid        INTEGER DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    health_status   TEXT DEFAULT 'unknown',
    last_checked_at TIMESTAMP,
    last_check_error TEXT DEFAULT '',
    fail_count      INTEGER DEFAULT 0,
    UNIQUE(episode_id, video_id)
);
CREATE INDEX IF NOT EXISTS idx_sources_episode_id ON sources(episode_id);
CREATE INDEX IF NOT EXISTS idx_sources_video_id ON sources(video_id);

-- 用户自定义别名
CREATE TABLE IF NOT EXISTS custom_aliases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    anime_id        INTEGER NOT NULL REFERENCES animes(id) ON DELETE CASCADE,
    alias           TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(anime_id, alias)
);
CREATE INDEX IF NOT EXISTS idx_custom_aliases_anime_id ON custom_aliases(anime_id);

-- 搜索规则（黑白名单）
CREATE TABLE IF NOT EXISTS anime_source_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    anime_id        INTEGER NOT NULL UNIQUE REFERENCES animes(id) ON DELETE CASCADE,
    allow_keywords  TEXT DEFAULT '[]',
    deny_keywords   TEXT DEFAULT '[]',
    allow_channels  TEXT DEFAULT '[]',
    deny_channels   TEXT DEFAULT '[]',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 键值设置表
CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL DEFAULT '',
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 同步日志
CREATE TABLE IF NOT EXISTS sync_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    anime_id        INTEGER REFERENCES animes(id) ON DELETE SET NULL,
    sync_type       TEXT DEFAULT '',
    episodes_synced INTEGER DEFAULT 0,
    sources_found   INTEGER DEFAULT 0,
    status          TEXT DEFAULT '',
    message         TEXT DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sync_logs_anime_id ON sync_logs(anime_id);

-- 受信任频道
CREATE TABLE IF NOT EXISTS trusted_channels (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id      TEXT NOT NULL UNIQUE,
    channel_name    TEXT DEFAULT '',
    priority        INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 全局别名库（内置国漫别名 + 用户添加）
CREATE TABLE IF NOT EXISTS global_aliases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    alias           TEXT NOT NULL,
    category        TEXT DEFAULT 'donghua',
    UNIQUE(title, alias)
);
CREATE INDEX IF NOT EXISTS idx_global_aliases_title ON global_aliases(title);
CREATE INDEX IF NOT EXISTS idx_global_aliases_alias ON global_aliases(alias);

-- 备份日志
CREATE TABLE IF NOT EXISTS backup_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_type     TEXT DEFAULT 'telegram',
    status          TEXT DEFAULT 'success',
    message         TEXT DEFAULT '',
    file_size       INTEGER DEFAULT 0,
    file_name       TEXT DEFAULT '',
    error_code      TEXT DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_backup_logs_status ON backup_logs(status);
CREATE INDEX IF NOT EXISTS idx_backup_logs_type ON backup_logs(backup_type);

-- ===== 以下为 Go 版新增表 =====

-- 同步任务持久化（进程重启可恢复，Python 版纯内存）
CREATE TABLE IF NOT EXISTS sync_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL UNIQUE,
    anime_id        INTEGER NOT NULL REFERENCES animes(id) ON DELETE CASCADE,
    status          TEXT DEFAULT 'queued',
    mode            TEXT DEFAULT 'incremental',
    sync_type       TEXT DEFAULT 'manual',
    progress        INTEGER DEFAULT 0,
    message         TEXT DEFAULT '',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at     TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_anime_id ON sync_jobs(anime_id);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_status ON sync_jobs(status);

-- 观看历史（支撑时间线/统计，阶段 6）
CREATE TABLE IF NOT EXISTS watch_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    anime_id        INTEGER NOT NULL REFERENCES animes(id) ON DELETE CASCADE,
    episode_id      INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    watched_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_watch_history_anime_id ON watch_history(anime_id);
CREATE INDEX IF NOT EXISTS idx_watch_history_watched_at ON watch_history(watched_at);

-- 更新事件流（支撑日历/看板，阶段 6）
CREATE TABLE IF NOT EXISTS update_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    anime_id        INTEGER NOT NULL REFERENCES animes(id) ON DELETE CASCADE,
    type            TEXT DEFAULT '',
    source_count    INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_update_events_anime_id ON update_events(anime_id);
CREATE INDEX IF NOT EXISTS idx_update_events_created_at ON update_events(created_at);

-- 收藏夹（支撑播放体验，阶段 6）
CREATE TABLE IF NOT EXISTS favorites (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    anime_ids       TEXT DEFAULT '[]',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
