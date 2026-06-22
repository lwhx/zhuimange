// Package store 实现 SQLite 数据访问层。
//
// 使用 modernc.org/sqlite（纯 Go，无 CGO），支持 WAL 模式 + busy_timeout，
// 并发同步场景下避免 "database is locked"。迁移通过内嵌 SQL 文件执行。
package store

import (
	"context"
	"database/sql"
	"embed"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"

	_ "modernc.org/sqlite"
)

//go:embed migrations/*.sql
var migrationsFS embed.FS

// Store 封装数据库连接，提供数据访问方法。
type Store struct {
	db *sql.DB
}

// Open 打开或创建 SQLite 数据库，配置 WAL/连接池，并执行迁移。
// dbPath 是 SQLite 文件路径。
func Open(ctx context.Context, dbPath string) (*Store, error) {
	// 确保父目录存在
	dir := filepath.Dir(dbPath)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("创建数据库目录失败: %w", err)
	}

	// SQLite 连接参数：
	// _pragma=journal_mode(WAL)     — WAL 模式，读写并发
	// _pragma=busy_timeout(30000)  — 锁等待 30 秒，避免并发写立即失败
	// _pragma=foreign_keys(ON)     — 开启外键约束（级联删除）
	// _pragma=synchronous(NORMAL)  — WAL 下 NORMAL 足够安全，减少 fsync 提升写性能
	// _pragma=cache_size(-20000)   — 20MB 内存页缓存，减少磁盘读
	// _pragma=mmap_size(268435456) — 256MB mmap，提升大表扫描速度
	dsn := fmt.Sprintf("file:%s?_pragma=journal_mode(WAL)&_pragma=busy_timeout(30000)&_pragma=foreign_keys(ON)&_pragma=synchronous(NORMAL)&_pragma=cache_size(-20000)&_pragma=mmap_size(268435456)", dbPath)

	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("打开数据库失败: %w", err)
	}

	// 验证连接可用
	if err := db.PingContext(ctx); err != nil {
		db.Close()
		return nil, fmt.Errorf("数据库连接测试失败: %w", err)
	}

	// 连接池配置：SQLite 写串行，适当控制并发
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)

	s := &Store{db: db}

	// 执行迁移
	if err := s.migrate(ctx); err != nil {
		db.Close()
		return nil, fmt.Errorf("数据库迁移失败: %w", err)
	}

	slog.Info("数据库初始化完成", "path", dbPath)
	return s, nil
}

// Close 关闭数据库连接。
func (s *Store) Close() error {
	if s.db != nil {
		return s.db.Close()
	}
	return nil
}
