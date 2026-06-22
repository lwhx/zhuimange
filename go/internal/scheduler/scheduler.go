// Package scheduler 实现自动同步与定时备份调度。
package scheduler

import (
	"context"
	"log/slog"
	"strconv"
	"sync"
	"time"

	"github.com/lwhx/zhuimange/internal/backup"
	"github.com/lwhx/zhuimange/internal/model"
	"github.com/lwhx/zhuimange/internal/notify"
	"github.com/lwhx/zhuimange/internal/store"
	"github.com/lwhx/zhuimange/internal/syncsvc"
)

// Scheduler 是轻量定时同步器与备份调度器。
type Scheduler struct {
	store  *store.Store
	queue  *syncsvc.Queue
	notify *notify.Telegram
	backup *backup.Service
	stop   chan struct{}
	once   sync.Once
}

// New 创建调度器。
func New(st *store.Store, queue *syncsvc.Queue, tg *notify.Telegram, bk *backup.Service) *Scheduler {
	return &Scheduler{store: st, queue: queue, notify: tg, backup: bk, stop: make(chan struct{})}
}

// Start 启动自动同步循环、定时备份循环和 GC 循环。
func (s *Scheduler) Start(ctx context.Context) {
	go s.syncLoop(ctx)
	go s.backupLoop(ctx)
	go s.gcLoop(ctx)
}

// Stop 停止自动同步循环。
func (s *Scheduler) Stop() {
	s.once.Do(func() {
		close(s.stop)
	})
}

// syncLoop 按 settings 中的间隔循环执行自动同步。
func (s *Scheduler) syncLoop(ctx context.Context) {
	for {
		interval := s.syncInterval(ctx)
		select {
		case <-ctx.Done():
			return
		case <-s.stop:
			return
		case <-time.After(interval):
			s.CheckAndSync(ctx)
		}
	}
}

// backupLoop 按 settings 中的间隔循环执行定时 Telegram 备份。
// 仅当 tg_backup_enabled=true 时执行，间隔由 tg_backup_interval_days 控制。
func (s *Scheduler) backupLoop(ctx context.Context) {
	for {
		interval := s.backupInterval(ctx)
		select {
		case <-ctx.Done():
			return
		case <-s.stop:
			return
		case <-time.After(interval):
			s.runBackupIfNeeded(ctx)
		}
	}
}

// CheckAndSync 检查并同步需要更新的动漫。
// 先批量入队所有动漫的同步任务，再统一等待完成，
// 避免逐个 Enqueue+waitTask 交替阻塞（减少锁竞争和总耗时）。
func (s *Scheduler) CheckAndSync(ctx context.Context) {
	enabled, _ := s.store.GetSetting(ctx, "auto_sync_enabled", "true")
	if enabled != "true" {
		slog.Info("自动同步已禁用")
		return
	}
	animes, err := s.store.ListAnimes(ctx)
	if err != nil {
		slog.Warn("读取动漫列表失败", "error", err)
		return
	}
	notifyEnabled, _ := s.store.GetSetting(ctx, "tg_notify_enabled", "false")

	// 第一阶段：批量入队 + 记录同步前源数
	type pendingTask struct {
		anime     *model.Anime
		taskID    string
		preCounts map[int64]int
	}
	var pending []pendingTask
	for _, anime := range animes {
		if anime.Status == "Ended" && anime.TotalEpisodes > 0 && anime.WatchedEp >= anime.TotalEpisodes {
			continue
		}
		preCounts := map[int64]int{}
		if notifyEnabled == "true" {
			preCounts, _ = s.store.EpisodeSourceCounts(ctx, anime.ID)
		}
		task, created, err := s.queue.Enqueue(ctx, anime.ID, "incremental", "auto")
		if err != nil || !created {
			continue
		}
		pending = append(pending, pendingTask{anime: anime, taskID: task.ID, preCounts: preCounts})
	}

	if len(pending) == 0 {
		return
	}
	slog.Info("自动同步开始", "anime_count", len(pending))

	// 第二阶段：统一等待所有任务完成
	for _, p := range pending {
		s.waitTask(ctx, p.taskID)
	}

	// 第三阶段：收集新增源并发通知
	if notifyEnabled == "true" {
		updates := map[string][]notify.EpisodeUpdate{}
		for _, p := range pending {
			postCounts, _ := s.store.EpisodeSourceCounts(ctx, p.anime.ID)
			episodes, _ := s.store.ListEpisodes(ctx, p.anime.ID)
			for _, episode := range episodes {
				if p.preCounts[episode.ID] == 0 && postCounts[episode.ID] > 0 {
					updates[p.anime.TitleCN] = append(updates[p.anime.TitleCN], notify.EpisodeUpdate{EpisodeNum: episode.AbsoluteNum, SourceCount: postCounts[episode.ID]})
				}
			}
		}
		if len(updates) > 0 {
			if err := s.notify.SendNewEpisodeNotification(ctx, updates); err != nil {
				slog.Warn("发送新集通知失败", "error", err)
			}
		}
	}
	slog.Info("自动同步完成", "anime_count", len(pending))
}

// syncInterval 读取自动同步间隔。
func (s *Scheduler) syncInterval(ctx context.Context) time.Duration {
	value, _ := s.store.GetSetting(ctx, "auto_sync_interval", "360")
	minutes, err := strconv.Atoi(value)
	if err != nil || minutes <= 0 {
		minutes = 360
	}
	return time.Duration(minutes) * time.Minute
}

// backupInterval 读取定时备份间隔（天→Duration），仅用于休眠，实际是否备份由 runBackupIfNeeded 判断。
func (s *Scheduler) backupInterval(ctx context.Context) time.Duration {
	value, _ := s.store.GetSetting(ctx, "tg_backup_interval_days", "1")
	days, err := strconv.Atoi(value)
	if err != nil || days <= 0 {
		days = 1
	}
	return time.Duration(days) * 24 * time.Hour
}

// runBackupIfNeeded 检查是否启用定时备份并执行 Telegram 备份。
// 对齐 Python _tg_backup_task：仅当 tg_backup_enabled=true 时发送，失败发告警通知。
func (s *Scheduler) runBackupIfNeeded(ctx context.Context) {
	enabled, _ := s.store.GetSetting(ctx, "tg_backup_enabled", "false")
	if enabled != "true" {
		return
	}
	slog.Info("执行定时 Telegram 备份")
	result, err := s.backup.SendBackupToTelegram(ctx)
	if err != nil {
		slog.Error("定时 TG 备份异常", "error", err)
		_ = s.notify.SendAlert(ctx, "error", "备份异常: "+err.Error())
		return
	}
	if success, _ := result["success"].(bool); success {
		slog.Info("定时 TG 备份成功", "filename", result["filename"])
	} else {
		errMsg, _ := result["error"].(string)
		slog.Error("定时 TG 备份失败", "error", errMsg)
		_ = s.notify.SendAlert(ctx, "error", "备份失败: "+errMsg)
	}
}

// gcLoop 每 6 小时清理一次过期数据：sync_jobs 表和 sync_logs 表。
// 防止长期运行后磁盘单调膨胀。
func (s *Scheduler) gcLoop(ctx context.Context) {
	const gcInterval = 6 * time.Hour
	const syncJobKeepDays = 7
	const syncLogKeepDays = 30
	// 启动后先等 1 分钟再首次执行，避免与启动初始化竞争
	firstRun := time.NewTimer(time.Minute)
	defer firstRun.Stop()
	select {
	case <-ctx.Done():
		return
	case <-s.stop:
		return
	case <-firstRun.C:
	}
	s.runGC(ctx, syncJobKeepDays, syncLogKeepDays)

	ticker := time.NewTicker(gcInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-s.stop:
			return
		case <-ticker.C:
			s.runGC(ctx, syncJobKeepDays, syncLogKeepDays)
		}
	}
}

func (s *Scheduler) runGC(ctx context.Context, jobDays, logDays int) {
	if n, err := s.store.DeleteSyncJobsBefore(ctx, jobDays); err != nil {
		slog.Warn("清理 sync_jobs 失败", "error", err)
	} else if n > 0 {
		slog.Info("清理过期 sync_jobs", "deleted", n, "keep_days", jobDays)
	}
	if n, err := s.store.DeleteSyncLogsBefore(ctx, logDays); err != nil {
		slog.Warn("清理 sync_logs 失败", "error", err)
	} else if n > 0 {
		slog.Info("清理过期 sync_logs", "deleted", n, "keep_days", logDays)
	}
}

// waitTask 等待任务完成，带超时和 ctx/stop 响应。
// 超时上限 30 分钟，避免单任务卡死整个调度循环。
// 响应 ctx.Done() 和 s.stop，保证优雅关闭不被阻塞。
func (s *Scheduler) waitTask(ctx context.Context, taskID string) {
	const maxWait = 30 * time.Minute
	deadline := time.Now().Add(maxWait)
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		task := s.queue.GetTask(taskID)
		if task == nil || task.Status == "success" || task.Status == "error" {
			return
		}
		if time.Now().After(deadline) {
			slog.Warn("等待同步任务超时，跳过", "task_id", taskID, "timeout", maxWait)
			return
		}
		select {
		case <-ctx.Done():
			return
		case <-s.stop:
			return
		case <-ticker.C:
			// 继续轮询
		}
	}
}
