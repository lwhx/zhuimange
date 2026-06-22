package store

import (
	"context"
	"fmt"
	"time"
)

// BackupLog 表示一条备份日志记录。
type BackupLog struct {
	ID         int64     `json:"id"`
	BackupType string    `json:"backup_type"`
	Status     string    `json:"status"`
	Message    string    `json:"message"`
	FileSize   int64     `json:"file_size"`
	FileName   string    `json:"file_name"`
	ErrorCode  string    `json:"error_code"`
	CreatedAt  time.Time `json:"created_at"`
}

// BackupStats 表示备份统计概要。
type BackupStats struct {
	TotalBackups      int     `json:"total_backups"`
	SuccessfulBackups int     `json:"successful_backups"`
	FailedBackups     int     `json:"failed_backups"`
	SuccessRate       float64 `json:"success_rate"`
	TotalSizeBytes    int64   `json:"total_size_bytes"`
	TotalSizeMB       float64 `json:"total_size_mb"`
	PeriodDays        int     `json:"period_days"`
}

// AddBackupLog 记录备份结果。
func (s *Store) AddBackupLog(ctx context.Context, backupType string, status string, message string, fileSize int64, fileName string, errorCode string) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO backup_logs (backup_type, status, message, file_size, file_name, error_code)
		VALUES (?, ?, ?, ?, ?, ?)`, backupType, status, message, fileSize, fileName, errorCode)
	return err
}

// GetBackupLogs 查询备份日志，backupType/status 为空表示不过滤。
func (s *Store) GetBackupLogs(ctx context.Context, backupType, status string, limit int) ([]*BackupLog, error) {
	if limit <= 0 {
		limit = 50
	}
	query := "SELECT id, backup_type, status, message, file_size, file_name, error_code, created_at FROM backup_logs"
	conds := []string{}
	args := []any{}
	if backupType != "" {
		conds = append(conds, "backup_type = ?")
		args = append(args, backupType)
	}
	if status != "" {
		conds = append(conds, "status = ?")
		args = append(args, status)
	}
	if len(conds) > 0 {
		query += " WHERE " + joinStrings(conds, " AND ")
	}
	query += " ORDER BY created_at DESC LIMIT ?"
	args = append(args, limit)

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var list []*BackupLog
	for rows.Next() {
		item := &BackupLog{}
		if err := rows.Scan(&item.ID, &item.BackupType, &item.Status, &item.Message,
			&item.FileSize, &item.FileName, &item.ErrorCode, &item.CreatedAt); err != nil {
			return nil, err
		}
		list = append(list, item)
	}
	return list, rows.Err()
}

// GetBackupStats 统计最近 days 天的备份情况。
func (s *Store) GetBackupStats(ctx context.Context, days int) (*BackupStats, error) {
	if days <= 0 {
		days = 30
	}
	stats := &BackupStats{PeriodDays: days}
	since := fmt.Sprintf("-%d days", days)

	// 总数
	if err := s.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM backup_logs WHERE created_at >= datetime('now', ?)`, since).
		Scan(&stats.TotalBackups); err != nil {
		return nil, err
	}
	// 成功数
	if err := s.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM backup_logs WHERE status = 'success' AND created_at >= datetime('now', ?)`, since).
		Scan(&stats.SuccessfulBackups); err != nil {
		return nil, err
	}
	// 失败数
	if err := s.db.QueryRowContext(ctx,
		`SELECT COUNT(*) FROM backup_logs WHERE status = 'error' AND created_at >= datetime('now', ?)`, since).
		Scan(&stats.FailedBackups); err != nil {
		return nil, err
	}
	// 总字节数
	if err := s.db.QueryRowContext(ctx,
		`SELECT COALESCE(SUM(file_size), 0) FROM backup_logs WHERE status = 'success' AND created_at >= datetime('now', ?)`, since).
		Scan(&stats.TotalSizeBytes); err != nil {
		return nil, err
	}

	if stats.TotalBackups > 0 {
		stats.SuccessRate = float64(stats.SuccessfulBackups) / float64(stats.TotalBackups) * 100
	}
	stats.TotalSizeMB = float64(stats.TotalSizeBytes) / 1024.0 / 1024.0
	return stats, nil
}
