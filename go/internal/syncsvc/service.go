// Package syncsvc 实现动漫同步流程。
package syncsvc

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/lwhx/zhuimange/internal/config"
	"github.com/lwhx/zhuimange/internal/model"
	"github.com/lwhx/zhuimange/internal/source"
	"github.com/lwhx/zhuimange/internal/store"
	"github.com/lwhx/zhuimange/internal/tmdb"
)

// Event 表示同步过程事件。
type Event map[string]any

// Emitter 用于向队列或 SSE 推送同步事件。
type Emitter func(Event)

// Service 封装同步流程依赖。
type Service struct {
	cfg    *config.Config
	store  *store.Store
	tmdb   *tmdb.Client
	finder *source.Finder
}

// Result 表示同步结果摘要。
type Result struct {
	Success         bool           `json:"success"`
	Mode            string         `json:"mode"`
	SyncedEpisodes  int            `json:"synced_episodes"`
	SkippedEpisodes int            `json:"skipped_episodes"`
	TotalEpisodes   int            `json:"total_episodes"`
	TargetEpisodes  int            `json:"target_episodes"`
	TotalSources    int            `json:"total_sources"`
	SkipReasons     map[string]int `json:"skip_reasons"`
	Message         string         `json:"message"`
	Error           string         `json:"error,omitempty"`
}

// NewService 创建同步服务。
func NewService(cfg *config.Config, st *store.Store, tmdbClient *tmdb.Client, finder *source.Finder) *Service {
	return &Service{cfg: cfg, store: st, tmdb: tmdbClient, finder: finder}
}

// NormalizeMode 规范化同步模式。
func NormalizeMode(mode string) string {
	if mode == "full" {
		return "full"
	}
	return "incremental"
}

// RunAnimeSync 同步一部动漫的视频源。
func (s *Service) RunAnimeSync(ctx context.Context, animeID int64, mode string, syncType string, emit Emitter) Result {
	mode = NormalizeMode(mode)
	anime, err := s.store.GetAnime(ctx, animeID)
	if err != nil || anime == nil {
		message := "动漫不存在"
		emitEvent(emit, Event{"type": "error", "message": message})
		return Result{Success: false, Mode: mode, Message: message, Error: message}
	}
	if anime.IsManual() {
		emitEvent(emit, Event{"type": "discovering", "message": "正在探测最新集数..."})
		if _, err := s.finder.DiscoverLatestEpisode(ctx, animeID); err != nil {
			slog.Warn("探测最新集数失败", "anime_id", animeID, "error", err)
		}
	} else {
		s.refreshTMDBEpisodes(ctx, anime)
	}
	episodes, err := s.store.FilterAiredEpisodes(ctx, animeID, time.Now().Format("2006-01-02"))
	if err != nil {
		return s.fail(ctx, animeID, syncType, mode, err, emit)
	}
	reverseEpisodes(episodes)
	emitEvent(emit, Event{"type": "start", "total": len(episodes), "mode": mode})
	syncItems := make([]*model.Episode, 0, len(episodes))
	skipReasons := map[string]int{"cached": 0}
	skipped := 0
	for _, episode := range episodes {
		shouldSync, reason, err := s.finder.ShouldSyncEpisode(ctx, episode, mode)
		if err != nil {
			return s.fail(ctx, animeID, syncType, mode, err, emit)
		}
		if shouldSync {
			syncItems = append(syncItems, episode)
		} else {
			skipped++
			skipReasons[reason]++
		}
	}
	emitEvent(emit, Event{"type": "plan", "mode": mode, "total": len(episodes), "target": len(syncItems), "skipped": skipped, "skip_reasons": skipReasons})
	synced, totalSources := s.syncEpisodes(ctx, animeID, mode, syncItems, skipped, len(episodes), emit)
	_ = s.store.TouchAnimeSync(ctx, animeID)
	// 手动添加动漫同步完成后，若无封面则用最高分视频缩略图补一个（对齐 Python _ensure_manual_poster）
	if posterURL := s.ensureManualPoster(ctx, anime); posterURL != "" {
		emitEvent(emit, Event{"type": "poster", "poster_url": posterURL})
	}
	message := fmt.Sprintf("同步完成: 模式=%s, 同步 %d/%d 集，跳过 %d/%d 集", mode, synced, len(syncItems), skipped, len(episodes))
	_ = s.store.AddSyncLog(ctx, animeID, syncType, synced, totalSources, "success", message)
	emitEvent(emit, Event{"type": "done", "mode": mode, "synced": synced, "skipped": skipped, "target": len(syncItems), "total": len(episodes), "total_sources": totalSources})
	return Result{Success: true, Mode: mode, SyncedEpisodes: synced, SkippedEpisodes: skipped, TotalEpisodes: len(episodes), TargetEpisodes: len(syncItems), TotalSources: totalSources, SkipReasons: skipReasons, Message: message}
}

// refreshTMDBEpisodes 从 TMDB 刷新集数。
func (s *Service) refreshTMDBEpisodes(ctx context.Context, anime *model.Anime) {
	if anime.TMDBID == nil || s.tmdb == nil {
		return
	}
	detail, err := s.tmdb.GetAnimeDetail(ctx, *anime.TMDBID)
	if err != nil || detail == nil {
		slog.Warn("TMDB 集数刷新失败", "anime_id", anime.ID, "error", err)
		return
	}
	episodes, err := s.tmdb.GetAllEpisodes(ctx, *anime.TMDBID, detail.Seasons)
	if err != nil {
		slog.Warn("TMDB 集数拉取失败", "anime_id", anime.ID, "error", err)
		return
	}
	items := make([]model.Episode, 0, len(episodes))
	keepNums := make([]int, 0, len(episodes))
	for _, episode := range episodes {
		items = append(items, model.Episode{AnimeID: anime.ID, SeasonNumber: episode.SeasonNumber, EpisodeNumber: episode.EpisodeNumber, AbsoluteNum: episode.AbsoluteNum, Title: episode.Title, Overview: episode.Overview, AirDate: episode.AirDate, StillPath: episode.StillPath})
		keepNums = append(keepNums, episode.AbsoluteNum)
	}
	_, _ = s.store.AddEpisodes(ctx, items)
	_ = s.store.DeleteEpisodesNotInAbsoluteNums(ctx, anime.ID, keepNums)
	_ = s.store.UpdateAnime(ctx, anime.ID, map[string]any{"total_episodes": detail.TotalEpisodes})
}

// ensureManualPoster 手动动漫无封面时，用最高分视频缩略图补一个封面。
// 优先用 Invidious 主实例的缩略图代理路径（国内可达），
// 无可用实例时回退到 img.youtube.com（可能不可达，仅兜底）。
// 非手动动漫或已有封面时返回空串。对齐 Python _ensure_manual_poster。
func (s *Service) ensureManualPoster(ctx context.Context, anime *model.Anime) string {
	if !anime.IsManual() || anime.PosterURL != "" {
		return ""
	}
	videoID, err := s.store.GetTopSourceVideoID(ctx, anime.ID)
	if err != nil || videoID == "" {
		return ""
	}
	var posterURL string
	if base := s.finder.PrimaryInstanceURL(); base != "" {
		posterURL = base + "/vi/" + videoID + "/hqdefault.jpg"
	} else {
		posterURL = "https://img.youtube.com/vi/" + videoID + "/hqdefault.jpg"
	}
	if err := s.store.UpdateAnime(ctx, anime.ID, map[string]any{"poster_url": posterURL}); err != nil {
		slog.Warn("自动设置封面失败", "anime_id", anime.ID, "error", err)
		return ""
	}
	slog.Info("自动设置封面(视频缩略图)", "anime_id", anime.ID, "poster_url", posterURL)
	return posterURL
}

// syncEpisodes 并发同步集数。
func (s *Service) syncEpisodes(ctx context.Context, animeID int64, mode string, episodes []*model.Episode, skipped int, overallTotal int, emit Emitter) (int, int) {
	if len(episodes) == 0 {
		return 0, 0
	}
	workers := s.cfg.EpisodeSyncWorkers
	if workers <= 0 || workers > len(episodes) {
		workers = len(episodes)
	}
	jobs := make(chan *model.Episode)
	results := make(chan episodeResult, len(episodes))
	var wg sync.WaitGroup
	for worker := 0; worker < workers; worker++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for episode := range jobs {
				sources, err := s.finder.FindSourcesForEpisode(ctx, animeID, episode.AbsoluteNum, mode == "full")
				if err != nil {
					slog.Warn("单集同步失败", "anime_id", animeID, "episode", episode.AbsoluteNum, "error", err)
					results <- episodeResult{EpisodeNum: episode.AbsoluteNum}
					continue
				}
				results <- episodeResult{EpisodeNum: episode.AbsoluteNum, SourceCount: len(sources)}
			}
		}()
	}
	go func() {
		for _, episode := range episodes {
			jobs <- episode
		}
		close(jobs)
		wg.Wait()
		close(results)
	}()
	done := 0
	synced := 0
	totalSources := 0
	for result := range results {
		done++
		if result.SourceCount > 0 {
			synced++
			totalSources += result.SourceCount
		}
		emitEvent(emit, Event{"type": "episode", "current": done, "total": len(episodes), "overall_total": overallTotal, "skipped": skipped, "ep_num": result.EpisodeNum, "source_count": result.SourceCount})
	}
	return synced, totalSources
}

// fail 记录同步失败。
func (s *Service) fail(ctx context.Context, animeID int64, syncType string, mode string, err error, emit Emitter) Result {
	message := err.Error()
	_ = s.store.AddSyncLog(ctx, animeID, syncType, 0, 0, "error", message)
	emitEvent(emit, Event{"type": "error", "message": message})
	return Result{Success: false, Mode: mode, Message: message, Error: message}
}

// episodeResult 表示单集同步结果。
type episodeResult struct {
	EpisodeNum  int
	SourceCount int
}

// emitEvent 安全发送同步事件。
func emitEvent(emit Emitter, event Event) {
	if emit != nil {
		emit(event)
	}
}

// reverseEpisodes 原地倒序集数列表。
func reverseEpisodes(episodes []*model.Episode) {
	for left, right := 0, len(episodes)-1; left < right; left, right = left+1, right-1 {
		episodes[left], episodes[right] = episodes[right], episodes[left]
	}
}
