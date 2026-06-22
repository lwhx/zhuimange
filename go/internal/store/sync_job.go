package store

import (
	"context"
	"fmt"

	"github.com/lwhx/zhuimange/internal/model"
)

// CreateSyncJob 创建同步任务持久化记录。
func (s *Store) CreateSyncJob(ctx context.Context, job *model.SyncJob) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO sync_jobs (task_id, anime_id, status, mode, sync_type, progress, message)
		VALUES (?, ?, ?, ?, ?, ?, ?)`,
		job.TaskID, job.AnimeID, job.Status, job.Mode, job.SyncType, job.Progress, job.Message)
	return err
}

// UpdateSyncJob 更新同步任务状态。
func (s *Store) UpdateSyncJob(ctx context.Context, taskID string, fields map[string]any) error {
	if len(fields) == 0 {
		return nil
	}
	sets := make([]string, 0, len(fields))
	args := make([]any, 0, len(fields)+1)
	for key, value := range fields {
		sets = append(sets, key+" = ?")
		args = append(args, value)
	}
	args = append(args, taskID)
	_, err := s.db.ExecContext(ctx, fmt.Sprintf(`UPDATE sync_jobs SET %s WHERE task_id = ?`, joinStrings(sets, ", ")), args...)
	return err
}

// GetSyncJob 按 task_id 查询同步任务。
func (s *Store) GetSyncJob(ctx context.Context, taskID string) (*model.SyncJob, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT id, task_id, anime_id, status, mode, sync_type, progress, message, created_at, finished_at
		FROM sync_jobs WHERE task_id = ?`, taskID)
	job := &model.SyncJob{}
	err := row.Scan(&job.ID, &job.TaskID, &job.AnimeID, &job.Status, &job.Mode, &job.SyncType, &job.Progress, &job.Message, &job.CreatedAt, &job.FinishedAt)
	if err != nil {
		return nil, err
	}
	return job, nil
}

// DeleteSyncJobsBefore 删除 created_at 早于指定时间的同步任务记录。
// 用于定时 GC，防止 sync_jobs 表无限增长。
func (s *Store) DeleteSyncJobsBefore(ctx context.Context, keepDays int) (int64, error) {
	if keepDays <= 0 {
		keepDays = 7
	}
	res, err := s.db.ExecContext(ctx,
		`DELETE FROM sync_jobs WHERE created_at < datetime('now', ?)`, fmt.Sprintf("-%d days", keepDays))
	if err != nil {
		return 0, err
	}
	return res.RowsAffected()
}
