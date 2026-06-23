package store

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"sort"
	"strings"

	"github.com/lwhx/zhuimange/internal/config"
)

// migrate 执行所有未应用的迁移文件，并初始化默认数据。
// 使用自管理的 schema_migrations 表记录已应用的迁移版本（轻量，无需额外库）。
func (s *Store) migrate(ctx context.Context) error {
	// 创建迁移记录表
	if _, err := s.db.ExecContext(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version TEXT PRIMARY KEY,
			applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	`); err != nil {
		return fmt.Errorf("创建迁移记录表失败: %w", err)
	}

	// 读取已应用的迁移
	applied, err := s.appliedMigrations(ctx)
	if err != nil {
		return err
	}

	// 读取待执行的迁移文件
	entries, err := migrationsFS.ReadDir("migrations")
	if err != nil {
		return fmt.Errorf("读取迁移目录失败: %w", err)
	}

	// 按文件名排序执行
	names := make([]string, 0, len(entries))
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".sql") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)

	for _, name := range names {
		if applied[name] {
			continue
		}
		slog.Info("应用数据库迁移", "version", name)
		if err := s.applyMigration(ctx, name); err != nil {
			return fmt.Errorf("迁移 %s 失败: %w", name, err)
		}
	}

	// 初始化默认数据（幂等）
	if err := s.seedDefaults(ctx); err != nil {
		return fmt.Errorf("初始化默认数据失败: %w", err)
	}

	return nil
}

func (s *Store) appliedMigrations(ctx context.Context) (map[string]bool, error) {
	rows, err := s.db.QueryContext(ctx, "SELECT version FROM schema_migrations")
	if err != nil {
		return nil, fmt.Errorf("查询已应用迁移失败: %w", err)
	}
	defer rows.Close()

	applied := make(map[string]bool)
	for rows.Next() {
		var version string
		if err := rows.Scan(&version); err != nil {
			return nil, err
		}
		applied[version] = true
	}
	return applied, rows.Err()
}

// applyMigration 在单个事务内执行迁移文件，并记录版本号。
func (s *Store) applyMigration(ctx context.Context, name string) error {
	// embed.FS 使用正斜杠路径，不能用 filepath.Join（Windows 会产生反斜杠）
	content, err := migrationsFS.ReadFile("migrations/" + name)
	if err != nil {
		return fmt.Errorf("读取迁移文件失败: %w", err)
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()

	// modernc.org/sqlite 支持 exec 多语句
	if _, err := tx.ExecContext(ctx, string(content)); err != nil {
		return fmt.Errorf("执行迁移 SQL 失败: %w", err)
	}

	if _, err := tx.ExecContext(ctx, "INSERT INTO schema_migrations (version) VALUES (?)", name); err != nil {
		return fmt.Errorf("记录迁移版本失败: %w", err)
	}

	return tx.Commit()
}

// seedDefaults 初始化默认设置项与全局别名库（幂等，已存在则跳过）。
func (s *Store) seedDefaults(ctx context.Context) error {
	// 默认设置（仅当 key 不存在时插入）
	// 注意：invidious_url / invidious_fallback_urls / invidious_instance_weights
	// 不在此处种子化——它们由 .env 的 INVIDIOUS_URL 等环境变量提供默认值
	// （loadPrimaryURL 在 settings 无值时回退到 config），用户在设置页修改后才落库。
	// 若此处硬编码（如 yewtu.be），会覆盖 .env 配置且永不回退。
	defaults := map[string]string{
		"auto_sync_enabled":         "true",
		"auto_sync_interval":        "360",
		"match_threshold":           "50",
		"match_recommend_threshold": "70",
		"episode_sort_order":        "desc",
		"tg_notify_enabled":         "false",
		"tg_backup_enabled":         "false",
		"tg_backup_interval_days":   "7",
	}
	for key, val := range defaults {
		if _, err := s.db.ExecContext(ctx,
			`INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)`, key, val); err != nil {
			return fmt.Errorf("初始化设置 %s 失败: %w", key, err)
		}
	}

	// 清理旧版本种子写入的 invidious 默认值（曾硬编码为 yewtu.be，覆盖了 .env 配置）。
	// 删除后 loadPrimaryURL 会回退到 config.InvidiousURL（来自 .env），用户在设置页
	// 修改后重新写入，此后以用户值为准。仅删除仍为旧默认值的行，避免覆盖用户自定义。
	if _, err := s.db.ExecContext(ctx,
		`DELETE FROM settings WHERE key = 'invidious_url' AND value = 'https://yewtu.be'`); err != nil {
		slog.Warn("清理旧 invidious_url 种子值失败", "error", err)
	}

	// 全局别名库（国漫内置）
	for title, aliases := range config.DonghuaAliases {
		for _, alias := range aliases {
			if _, err := s.db.ExecContext(ctx,
				`INSERT OR IGNORE INTO global_aliases (title, alias, category) VALUES (?, ?, 'donghua')`,
				title, alias); err != nil {
				return fmt.Errorf("初始化全局别名 %s/%s 失败: %w", title, alias, err)
			}
		}
	}

	return nil
}

// ==================== Settings CRUD ====================

// GetSetting 读取设置值，不存在返回默认值。
func (s *Store) GetSetting(ctx context.Context, key, defaultVal string) (string, error) {
	var val string
	err := s.db.QueryRowContext(ctx, `SELECT value FROM settings WHERE key = ?`, key).Scan(&val)
	if err == sql.ErrNoRows {
		return defaultVal, nil
	}
	if err != nil {
		return "", err
	}
	return val, nil
}

// SetSetting 设置键值（upsert）。
func (s *Store) SetSetting(ctx context.Context, key, val string) error {
	_, err := s.db.ExecContext(ctx,
		`INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
		 ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP`,
		key, val)
	return err
}

// GetAllSettings 返回全部设置键值对。
func (s *Store) GetAllSettings(ctx context.Context) (map[string]string, error) {
	rows, err := s.db.QueryContext(ctx, `SELECT key, value FROM settings`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	m := make(map[string]string)
	for rows.Next() {
		var k, v string
		if err := rows.Scan(&k, &v); err != nil {
			return nil, err
		}
		m[k] = v
	}
	return m, rows.Err()
}
