package store

import (
	"context"
)

// StatsSummary 表示统计页概要数据。
type StatsSummary struct {
	AnimeCount        int `json:"anime_count"`
	EpisodeCount      int `json:"episode_count"`
	SourceCount       int `json:"source_count"`
	WatchedCount      int `json:"watched_count"`
	ContinuingCount   int `json:"continuing_count"`
	EndedCount        int `json:"ended_count"`
	RecentSyncSuccess int `json:"recent_sync_success"`
	RecentSyncError   int `json:"recent_sync_error"`
	// 扩展字段（对齐 Python get_watch_stats）
	EstimatedHours float64           `json:"estimated_hours"`
	CompletionRate float64           `json:"completion_rate"`
	StatusDist     []StatusDistItem  `json:"status_dist"`
	TopProgress    []ProgressItem    `json:"top_progress"`
	MostPending    []PendingItem     `json:"most_pending"`
	SyncActivity   []SyncActivityDay `json:"sync_activity"`
	MaxSyncCount   int               `json:"max_sync_count"`
}

// StatusDistItem 表示状态分布条目。
type StatusDistItem struct {
	Status string `json:"status"`
	Label  string `json:"label"`
	Count  int    `json:"count"`
}

// ProgressItem 表示完成度排行条目。
type ProgressItem struct {
	ID           int64   `json:"id"`
	TitleCN      string  `json:"title_cn"`
	EpCount      int     `json:"ep_count"`
	WatchedCount int     `json:"watched_count"`
	Pct          float64 `json:"pct"`
}

// PendingItem 表示待追条目。
type PendingItem struct {
	ID        int64  `json:"id"`
	TitleCN   string `json:"title_cn"`
	Unwatched int    `json:"unwatched"`
}

// SyncActivityDay 表示单日同步活动。
type SyncActivityDay struct {
	Date    string `json:"date"`
	Syncs   int    `json:"syncs"`
	Sources int    `json:"sources"`
}

var statusLabels = map[string]string{
	"Returning Series": "连载中",
	"Ended":            "已完结",
	"In Production":    "制作中",
	"Planned":          "未开播",
	"Canceled":         "已取消",
	"Continuing":       "连载中",
}

// GetStatsSummary 查询统计页概要数据（含完整图表数据，对齐 Python get_watch_stats）。
func (s *Store) GetStatsSummary(ctx context.Context) (*StatsSummary, error) {
	summary := &StatsSummary{}
	queries := []struct {
		SQL    string
		Target *int
	}{
		{`SELECT COUNT(*) FROM animes`, &summary.AnimeCount},
		{`SELECT COUNT(*) FROM episodes`, &summary.EpisodeCount},
		{`SELECT COUNT(*) FROM sources WHERE is_valid = 1`, &summary.SourceCount},
		{`SELECT COUNT(*) FROM episodes WHERE watched = 1`, &summary.WatchedCount},
		{`SELECT COUNT(*) FROM animes WHERE status = 'Continuing'`, &summary.ContinuingCount},
		{`SELECT COUNT(*) FROM animes WHERE status = 'Ended'`, &summary.EndedCount},
		{`SELECT COUNT(*) FROM sync_logs WHERE status = 'success' AND created_at >= datetime('now', '-7 days')`, &summary.RecentSyncSuccess},
		{`SELECT COUNT(*) FROM sync_logs WHERE status = 'error' AND created_at >= datetime('now', '-7 days')`, &summary.RecentSyncError},
	}
	for _, query := range queries {
		if err := s.db.QueryRowContext(ctx, query.SQL).Scan(query.Target); err != nil {
			return nil, err
		}
	}

	// 完成率与预计时长
	if summary.EpisodeCount > 0 {
		summary.CompletionRate = roundFloat(float64(summary.WatchedCount)/float64(summary.EpisodeCount)*100, 1)
	}
	summary.EstimatedHours = roundFloat(float64(summary.WatchedCount)*24/60, 1)

	// 状态分布
	rows, err := s.db.QueryContext(ctx,
		`SELECT COALESCE(status,''), COUNT(*) FROM animes GROUP BY status ORDER BY COUNT(*) DESC`)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var status string
			var count int
			if err := rows.Scan(&status, &count); err != nil {
				continue
			}
			label, ok := statusLabels[status]
			if !ok {
				if status == "" {
					label = "未知"
				} else {
					label = status
				}
			}
			summary.StatusDist = append(summary.StatusDist, StatusDistItem{Status: status, Label: label, Count: count})
		}
	}

	// 完成度 TOP 10
	topRows, err := s.db.QueryContext(ctx, `
		SELECT a.id, a.title_cn, COUNT(e.id) AS ep_count, COALESCE(SUM(e.watched), 0) AS watched_count
		FROM animes a LEFT JOIN episodes e ON a.id = e.anime_id
		GROUP BY a.id HAVING ep_count > 0
		ORDER BY (CAST(COALESCE(SUM(e.watched),0) AS FLOAT) / COUNT(e.id)) DESC, watched_count DESC
		LIMIT 10`)
	if err == nil {
		for topRows.Next() {
			var item ProgressItem
			if err := topRows.Scan(&item.ID, &item.TitleCN, &item.EpCount, &item.WatchedCount); err != nil {
				continue
			}
			if item.EpCount > 0 {
				item.Pct = roundFloat(float64(item.WatchedCount)/float64(item.EpCount)*100, 0)
			}
			summary.TopProgress = append(summary.TopProgress, item)
		}
		topRows.Close()
	}

	// 待追最多
	pendingRows, err := s.db.QueryContext(ctx, `
		SELECT a.id, a.title_cn, COUNT(CASE WHEN e.watched = 0 THEN 1 END) AS unwatched
		FROM animes a LEFT JOIN episodes e ON a.id = e.anime_id
		GROUP BY a.id HAVING unwatched > 0
		ORDER BY unwatched DESC LIMIT 6`)
	if err == nil {
		for pendingRows.Next() {
			var item PendingItem
			if err := pendingRows.Scan(&item.ID, &item.TitleCN, &item.Unwatched); err != nil {
				continue
			}
			summary.MostPending = append(summary.MostPending, item)
		}
		pendingRows.Close()
	}

	// 近 14 天同步活动
	actRows, err := s.db.QueryContext(ctx, `
		SELECT DATE(created_at) AS date, COUNT(*) AS syncs,
		       SUM(CASE WHEN status='success' THEN sources_found ELSE 0 END) AS sources
		FROM sync_logs
		WHERE created_at >= datetime('now', '-14 days')
		GROUP BY DATE(created_at) ORDER BY date`)
	if err == nil {
		for actRows.Next() {
			var day SyncActivityDay
			if err := actRows.Scan(&day.Date, &day.Syncs, &day.Sources); err != nil {
				continue
			}
			if day.Syncs > summary.MaxSyncCount {
				summary.MaxSyncCount = day.Syncs
			}
			summary.SyncActivity = append(summary.SyncActivity, day)
		}
		actRows.Close()
	}
	if summary.MaxSyncCount == 0 {
		summary.MaxSyncCount = 1
	}

	return summary, nil
}

func roundFloat(v float64, precision int) float64 {
	pow := 1.0
	for i := 0; i < precision; i++ {
		pow *= 10
	}
	return float64(int64(v*pow+0.5)) / pow
}

// CountAnimeSources 统计某动漫的全部有效视频源数（跨集）。
func (s *Store) CountAnimeSources(ctx context.Context, animeID int64) (int, error) {
	var count int
	err := s.db.QueryRowContext(ctx, `
		SELECT COUNT(*) FROM sources s
		JOIN episodes e ON s.episode_id = e.id
		WHERE e.anime_id = ? AND s.is_valid = 1`, animeID).Scan(&count)
	return count, err
}

// AnimeCardStats 表示首页卡片所需的统计字段。
type AnimeCardStats struct {
	EpisodeCount int
	SourceCount  int
}

// ListAnimeCardStats 批量查询所有动漫的集数和源数（单次 JOIN GROUP BY，替代 N+1）。
func (s *Store) ListAnimeCardStats(ctx context.Context) (map[int64]AnimeCardStats, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT e.anime_id,
		       COUNT(DISTINCT e.id) AS ep_count,
		       COUNT(DISTINCT CASE WHEN s.is_valid = 1 THEN s.id END) AS src_count
		FROM episodes e
		LEFT JOIN sources s ON s.episode_id = e.id
		GROUP BY e.anime_id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := make(map[int64]AnimeCardStats)
	for rows.Next() {
		var animeID int64
		var stats AnimeCardStats
		if err := rows.Scan(&animeID, &stats.EpisodeCount, &stats.SourceCount); err != nil {
			continue
		}
		result[animeID] = stats
	}
	return result, nil
}

// EpisodeSourceCounts 返回某动漫每集的视频源数量。
func (s *Store) EpisodeSourceCounts(ctx context.Context, animeID int64) (map[int64]int, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT e.id, COUNT(src.id)
		FROM episodes e
		LEFT JOIN sources src ON src.episode_id = e.id AND src.is_valid = 1
		WHERE e.anime_id = ?
		GROUP BY e.id`, animeID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := map[int64]int{}
	for rows.Next() {
		var episodeID int64
		var count int
		if err := rows.Scan(&episodeID, &count); err != nil {
			return nil, err
		}
		result[episodeID] = count
	}
	return result, rows.Err()
}

// ListAllSources 返回全部视频源，用于健康检查。
func (s *Store) ListAllSources(ctx context.Context, limit int) ([]*SourceWithEpisode, error) {
	if limit <= 0 {
		limit = 100
	}
	rows, err := s.db.QueryContext(ctx, `
		SELECT s.id, s.episode_id, s.video_id, s.title, s.health_status, s.fail_count, e.anime_id, e.absolute_num
		FROM sources s
		JOIN episodes e ON e.id = s.episode_id
		WHERE s.is_valid = 1
		ORDER BY s.last_checked_at IS NOT NULL, s.last_checked_at ASC, s.id DESC
		LIMIT ?`, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []*SourceWithEpisode{}
	for rows.Next() {
		item := &SourceWithEpisode{}
		if err := rows.Scan(&item.ID, &item.EpisodeID, &item.VideoID, &item.Title, &item.HealthStatus, &item.FailCount, &item.AnimeID, &item.AbsoluteNum); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

// SourceWithEpisode 表示带动漫和集数信息的视频源。
type SourceWithEpisode struct {
	ID           int64  `json:"id"`
	EpisodeID    int64  `json:"episode_id"`
	VideoID      string `json:"video_id"`
	Title        string `json:"title"`
	HealthStatus string `json:"health_status"`
	FailCount    int    `json:"fail_count"`
	AnimeID      int64  `json:"anime_id"`
	AbsoluteNum  int    `json:"absolute_num"`
}
