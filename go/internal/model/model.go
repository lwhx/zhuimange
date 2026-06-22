// Package model 定义应用核心数据结构，对应数据库表与外部 API 响应。
//
// 字段命名遵循 Go 惯例（驼峰），通过 store 层的扫描映射到数据库列（下划线）。
// 时间字段统一用 *time.Time 指针，NULL 值为 nil。
package model

import "time"

// Anime 对应 animes 表，一部追更的动漫。
type Anime struct {
	ID            int64      `json:"id"`
	TMDBID        *int64     `json:"tmdb_id"`    // nil 表示手动添加（无 TMDB 元数据）
	BangumiID     *int64     `json:"bangumi_id"` // Bangumi 条目 ID，用于互通
	TitleCN       string     `json:"title_cn"`
	TitleEN       string     `json:"title_en"`
	PosterURL     string     `json:"poster_url"`
	Overview      string     `json:"overview"`
	AirDate       string     `json:"air_date"`
	TotalEpisodes int        `json:"total_episodes"`
	WatchedEp     int        `json:"watched_ep"`
	Status        string     `json:"status"` // Continuing/Ended/Upcoming
	SyncInterval  int        `json:"sync_interval"`
	LastSyncAt    *time.Time `json:"last_sync_at"`
	CreatedAt     time.Time  `json:"created_at"`
	UpdatedAt     time.Time  `json:"updated_at"`
}

// IsManual 是否手动添加（无 TMDB 元数据）。
// 这一分枝贯穿整个同步流程，影响集数探测策略、匹配阈值、海报补全。
func (a *Anime) IsManual() bool { return a.TMDBID == nil }

// Episode 对应 episodes 表，动漫的单集。
type Episode struct {
	ID            int64     `json:"id"`
	AnimeID       int64     `json:"anime_id"`
	SeasonNumber  int       `json:"season_number"`
	EpisodeNumber int       `json:"episode_number"`
	AbsoluteNum   int       `json:"absolute_num"` // 跨季连续编号（1,2,3...），追更场景核心标识
	Title         string    `json:"title"`
	Overview      string    `json:"overview"`
	AirDate       string    `json:"air_date"`
	StillPath     string    `json:"still_path"`
	Watched       bool      `json:"watched"`
	SourceCount   int       `json:"source_count"` // 该集视频源数（详情页展示用，非 DB 字段）
	CreatedAt     time.Time `json:"created_at"`
}

// Source 对应 sources 表，某集的一个视频源（来自 Invidious 搜索结果）。
type Source struct {
	ID             int64      `json:"id"`
	EpisodeID      int64      `json:"episode_id"`
	VideoID        string     `json:"video_id"`
	Title          string     `json:"title"`
	ChannelID      string     `json:"channel_id"`
	ChannelName    string     `json:"channel_name"`
	Duration       int        `json:"duration"`
	ViewCount      int64      `json:"view_count"`
	PublishedAt    string     `json:"published_at"`
	MatchScore     float64    `json:"match_score"`
	IsValid        bool       `json:"is_valid"`
	CreatedAt      time.Time  `json:"created_at"`
	HealthStatus   string     `json:"health_status"` // available/unknown/error/invalid
	LastCheckedAt  *time.Time `json:"last_checked_at"`
	LastCheckError string     `json:"last_check_error"`
	FailCount      int        `json:"fail_count"`
}

// SourceRule 对应 anime_source_rules 表，某动漫的搜索黑白名单规则。
// JSON 数组字段在 Go 侧反序列化为切片。
type SourceRule struct {
	ID            int64     `json:"id"`
	AnimeID       int64     `json:"anime_id"`
	AllowKeywords []string  `json:"allow_keywords"`
	DenyKeywords  []string  `json:"deny_keywords"`
	AllowChannels []string  `json:"allow_channels"`
	DenyChannels  []string  `json:"deny_channels"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

// SyncLog 对应 sync_logs 表，同步操作的结果摘要。
type SyncLog struct {
	ID             int64     `json:"id"`
	AnimeID        *int64    `json:"anime_id"`
	SyncType       string    `json:"sync_type"` // auto/manual/full/incremental
	EpisodesSynced int       `json:"episodes_synced"`
	SourcesFound   int       `json:"sources_found"`
	Status         string    `json:"status"` // success/error
	Message        string    `json:"message"`
	CreatedAt      time.Time `json:"created_at"`
}

// SyncJob 对应 sync_jobs 表，同步任务持久化（进程重启可恢复）。
type SyncJob struct {
	ID         int64      `json:"id"`
	TaskID     string     `json:"task_id"` // UUID，前端 SSE 订阅用
	AnimeID    int64      `json:"anime_id"`
	Status     string     `json:"status"`    // queued/running/success/error
	Mode       string     `json:"mode"`      // incremental/full
	SyncType   string     `json:"sync_type"` // auto/manual
	Progress   int        `json:"progress"`  // 0-100
	Message    string     `json:"message"`
	CreatedAt  time.Time  `json:"created_at"`
	FinishedAt *time.Time `json:"finished_at"`
}
