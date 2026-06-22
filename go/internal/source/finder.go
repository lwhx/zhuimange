// Package source 实现视频源发现、评分、缓存和入库流程。
package source

import (
	"context"
	"fmt"
	"log/slog"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/lwhx/zhuimange/internal/config"
	"github.com/lwhx/zhuimange/internal/invidious"
	"github.com/lwhx/zhuimange/internal/matcher"
	"github.com/lwhx/zhuimange/internal/model"
	"github.com/lwhx/zhuimange/internal/store"
)

// Finder 封装视频源发现依赖。
type Finder struct {
	cfg       *config.Config
	store     *store.Store
	invidious *invidious.Client
}

// NewFinder 创建视频源发现服务。
func NewFinder(cfg *config.Config, st *store.Store, client *invidious.Client) *Finder {
	return &Finder{cfg: cfg, store: st, invidious: client}
}

// FindSourcesForEpisode 查找指定动漫单集的视频源。
func (f *Finder) FindSourcesForEpisode(ctx context.Context, animeID int64, episodeNum int, force bool) ([]*model.Source, error) {
	anime, err := f.store.GetAnime(ctx, animeID)
	if err != nil {
		return nil, err
	}
	if anime == nil {
		return nil, fmt.Errorf("动漫不存在: %d", animeID)
	}
	episode, err := f.store.GetEpisodeByNum(ctx, animeID, episodeNum)
	if err != nil {
		return nil, err
	}
	if episode == nil {
		return nil, fmt.Errorf("集数不存在: anime_id=%d ep=%d", animeID, episodeNum)
	}
	if !isAired(episode) {
		slog.Info("跳过未开播集数的视频源搜索", "anime", anime.TitleCN, "episode", episodeNum, "air_date", episode.AirDate)
		return nil, nil
	}
	if !force {
		existing, err := f.store.GetSourcesForEpisode(ctx, episode.ID)
		if err != nil {
			return nil, err
		}
		if len(existing) > 0 {
			return existing, nil
		}
	}
	aliases, err := f.aliases(ctx, anime)
	if err != nil {
		return nil, err
	}
	keywords := f.searchKeywords(anime, episode, aliases)
	videos := f.searchKeywordsVideos(ctx, keywords)
	videos = applySourceRules(videos, f.loadSourceRule(ctx, animeID))
	scored := f.scoreVideos(ctx, videos, anime, episodeNum, aliases)
	if force {
		if err := f.store.DeleteSourcesForEpisode(ctx, episode.ID); err != nil {
			return nil, err
		}
	}
	limit := f.cfg.MaxSourcesPerEpisode
	if limit <= 0 || limit > len(scored) {
		limit = len(scored)
	}
	for _, item := range scored[:limit] {
		video := item.Video
		if err := f.store.AddSource(ctx, &model.Source{EpisodeID: episode.ID, VideoID: video.VideoID, Title: video.Title, ChannelID: video.ChannelID, ChannelName: video.ChannelName, Duration: video.Duration, ViewCount: video.ViewCount, PublishedAt: video.PublishedAt, MatchScore: item.Score.TotalScore}); err != nil {
			return nil, err
		}
	}
	slog.Info("视频源发现完成", "anime", anime.TitleCN, "episode", episodeNum, "saved", limit, "candidates", len(videos))
	return f.store.GetSourcesForEpisode(ctx, episode.ID)
}

// ShouldSyncEpisode 判断单集是否需要同步视频源。
func (f *Finder) ShouldSyncEpisode(ctx context.Context, episode *model.Episode, mode string) (bool, string, error) {
	if mode == "full" {
		return true, "full", nil
	}
	count, err := f.store.CountSourcesForEpisode(ctx, episode.ID)
	if err != nil {
		return false, "", err
	}
	if count == 0 {
		return true, "missing", nil
	}
	return false, "cached", nil
}

// DiscoverLatestEpisode 探测手动添加动漫的最新集数并补齐集数记录。
// 注意：正则可能误提取年份/分辨率等数字，故设置合理上界（500 集）避免创建过多空集。
func (f *Finder) DiscoverLatestEpisode(ctx context.Context, animeID int64) (int, error) {
	anime, err := f.store.GetAnime(ctx, animeID)
	if err != nil {
		return 0, err
	}
	if anime == nil {
		return 0, nil // 动漫不存在，静默跳过（不返回 err 避免误报）
	}
	if !anime.IsManual() {
		return 0, nil
	}
	aliases, err := f.aliases(ctx, anime)
	if err != nil {
		return 0, err
	}
	terms := append([]string{anime.TitleCN}, aliases...)
	terms = dedupeKeepOrder(limitStrings(terms, 4))
	const maxReasonableEpisode = 500 // 合理上界：防正则误提年份/分辨率导致创建几千空集
	maxEpisode := 0
	for _, term := range terms {
		for _, sortBy := range []string{"relevance", "date"} {
			videos, err := f.invidious.SearchVideos(ctx, term, f.cfg.MaxSearchResults, sortBy)
			if err != nil {
				slog.Warn("探测集数搜索失败", "term", term, "error", err)
				continue
			}
			for _, video := range videos {
				if episode, ok := matcher.ExtractEpisodeNumber(video.Title); ok {
					// 过滤明显不合理的集数（年份/分辨率误匹配）
					if episode > maxReasonableEpisode {
						slog.Debug("探测到异常集数，跳过", "video", video.Title, "episode", episode)
						continue
					}
					if episode > maxEpisode {
						maxEpisode = episode
					}
				}
			}
		}
	}
	if maxEpisode <= 0 {
		return 0, nil
	}
	existing, err := f.store.ListEpisodes(ctx, animeID)
	if err != nil {
		return 0, err
	}
	existingNums := map[int]bool{}
	for _, episode := range existing {
		existingNums[episode.AbsoluteNum] = true
	}
	newEpisodes := make([]model.Episode, 0)
	for number := 1; number <= maxEpisode; number++ {
		if !existingNums[number] {
			newEpisodes = append(newEpisodes, model.Episode{AnimeID: animeID, SeasonNumber: 1, EpisodeNumber: number, AbsoluteNum: number})
		}
	}
	if _, err := f.store.AddEpisodes(ctx, newEpisodes); err != nil {
		return maxEpisode, err
	}
	if err := f.store.UpdateAnime(ctx, animeID, map[string]any{"total_episodes": maxEpisode}); err != nil {
		return maxEpisode, err
	}
	return maxEpisode, nil
}

// aliases 获取自定义别名和全局别名。
func (f *Finder) aliases(ctx context.Context, anime *model.Anime) ([]string, error) {
	custom, err := f.store.GetAliases(ctx, anime.ID)
	if err != nil {
		return nil, err
	}
	global, err := f.store.GetGlobalAliasesByTitle(ctx, anime.TitleCN)
	if err != nil {
		return nil, err
	}
	return dedupeKeepOrder(append(custom, global...)), nil
}

// searchKeywords 生成单集搜索关键词。
func (f *Finder) searchKeywords(anime *model.Anime, episode *model.Episode, aliases []string) []string {
	names := dedupeKeepOrder(append([]string{anime.TitleCN}, aliases...))
	names = limitStrings(names, f.cfg.SearchKeywordsLimit)
	keywords := []string{}
	if !anime.IsManual() && episode.Title != "" && !isGenericEpisodeTitle(episode.Title) {
		for _, name := range names {
			keywords = append(keywords, name+" "+episode.Title)
		}
	}
	for _, name := range names {
		keywords = append(keywords, fmt.Sprintf("%s 第%d集", name, episode.AbsoluteNum))
		keywords = append(keywords, fmt.Sprintf("%s EP%d", name, episode.AbsoluteNum))
	}
	return dedupeKeepOrder(keywords)
}

// searchKeywordsVideos 并发搜索关键词并按 video_id 去重。
func (f *Finder) searchKeywordsVideos(ctx context.Context, keywords []string) []invidious.Video {
	if len(keywords) == 0 {
		return nil
	}
	workers := f.cfg.SourceSearchWorkers
	if workers <= 0 || workers > len(keywords) {
		workers = len(keywords)
	}
	jobs := make(chan string)
	results := make(chan []invidious.Video, len(keywords))
	var wg sync.WaitGroup
	for worker := 0; worker < workers; worker++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for keyword := range jobs {
				videos, err := f.invidious.SearchVideos(ctx, keyword, f.cfg.MaxSearchResults, "relevance")
				if err != nil {
					slog.Warn("关键词搜索失败", "keyword", keyword, "error", err)
					continue
				}
				results <- videos
			}
		}()
	}
	go func() {
		for _, keyword := range keywords {
			jobs <- keyword
		}
		close(jobs)
		wg.Wait()
		close(results)
	}()
	seen := map[string]bool{}
	all := []invidious.Video{}
	for batch := range results {
		for _, video := range batch {
			if video.VideoID != "" && !seen[video.VideoID] {
				seen[video.VideoID] = true
				all = append(all, video)
			}
		}
	}
	return all
}

// scoreVideos 过滤、评分并排序候选视频。
func (f *Finder) scoreVideos(ctx context.Context, videos []invidious.Video, anime *model.Anime, episodeNum int, aliases []string) []matcher.ScoredVideo {
	threshold := float64(f.cfg.MatchThreshold)
	if anime.IsManual() {
		threshold = float64(f.cfg.ManualMatchThreshold)
	}
	scored := []matcher.ScoredVideo{}
	trusted := f.store.TrustedChannelChecker(ctx)
	for _, video := range videos {
		score := matcher.ScoreVideo(video, anime.TitleCN, episodeNum, aliases, trusted, f.cfg)
		if score.Filtered || score.TotalScore < threshold {
			continue
		}
		scored = append(scored, matcher.ScoredVideo{Video: video, Score: score})
	}
	matcher.SortScoredVideos(scored)
	return scored
}

// loadSourceRule 加载搜索规则，失败时返回 nil 并记录警告。
func (f *Finder) loadSourceRule(ctx context.Context, animeID int64) *model.SourceRule {
	rule, err := f.store.GetSourceRule(ctx, animeID)
	if err != nil {
		slog.Warn("读取搜索规则失败", "anime_id", animeID, "error", err)
		return nil
	}
	return rule
}

// applySourceRules 应用动漫级搜索规则。
func applySourceRules(videos []invidious.Video, rule *model.SourceRule) []invidious.Video {
	if rule == nil {
		return videos
	}
	filtered := make([]invidious.Video, 0, len(videos))
	for _, video := range videos {
		lower := strings.ToLower(video.Title)
		if len(rule.DenyChannels) > 0 && containsString(rule.DenyChannels, video.ChannelID) {
			continue
		}
		if hasAnyKeyword(lower, rule.DenyKeywords) {
			continue
		}
		if len(rule.AllowChannels) > 0 && !containsString(rule.AllowChannels, video.ChannelID) {
			continue
		}
		if len(rule.AllowKeywords) > 0 && !hasAnyKeyword(lower, rule.AllowKeywords) {
			continue
		}
		filtered = append(filtered, video)
	}
	return filtered
}

var genericEpisodeTitlePattern = regexp.MustCompile(`(?i)^(?:episode|ep|e|第)\s*\d+\s*(?:集|话|話)?$`)

// isGenericEpisodeTitle 判断 TMDB 单集标题是否无信息量。
func isGenericEpisodeTitle(title string) bool {
	return strings.TrimSpace(title) == "" || genericEpisodeTitlePattern.MatchString(strings.TrimSpace(title))
}

// isAired 判断集数是否已开播。
func isAired(episode *model.Episode) bool {
	return episode.AirDate == "" || episode.AirDate <= time.Now().Format("2006-01-02")
}

// dedupeKeepOrder 按顺序去重字符串。
func dedupeKeepOrder(items []string) []string {
	seen := map[string]bool{}
	result := []string{}
	for _, item := range items {
		value := strings.TrimSpace(item)
		key := strings.ToLower(value)
		if value != "" && !seen[key] {
			seen[key] = true
			result = append(result, value)
		}
	}
	return result
}

// limitStrings 限制字符串切片长度。
func limitStrings(items []string, limit int) []string {
	if limit <= 0 || len(items) <= limit {
		return items
	}
	return items[:limit]
}

// containsString 判断切片是否包含字符串。
func containsString(items []string, target string) bool {
	for _, item := range items {
		if item == target {
			return true
		}
	}
	return false
}

// hasAnyKeyword 判断文本是否包含任一关键词。
func hasAnyKeyword(text string, keywords []string) bool {
	for _, keyword := range keywords {
		if strings.Contains(text, strings.ToLower(keyword)) {
			return true
		}
	}
	return false
}

// PrimaryInstanceURL 返回当前 Invidious 主实例地址（去尾斜杠），
// 用于拼接视频缩略图代理路径（手动动漫封面兜底场景）。无可用实例返回空串。
func (f *Finder) PrimaryInstanceURL() string {
	if f.invidious == nil {
		return ""
	}
	urls := f.invidious.GetInstanceURLs()
	if len(urls) == 0 {
		return ""
	}
	return strings.TrimRight(urls[0], "/")
}
