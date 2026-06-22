package matcher

import (
	"math"
	"sort"
	"strings"
	"time"

	"github.com/lwhx/zhuimange/internal/config"
	"github.com/lwhx/zhuimange/internal/invidious"
)

// ScoreDetail 保存视频源综合评分明细。
type ScoreDetail struct {
	TotalScore      float64 `json:"total_score"`
	TitleScore      float64 `json:"title_score"`
	EpisodeScore    float64 `json:"episode_score"`
	ChannelScore    float64 `json:"channel_score"`
	RecencyScore    float64 `json:"recency_score"`
	ViewScore       float64 `json:"view_score"`
	Filtered        bool    `json:"filtered"`
	FilterReason    string  `json:"filter_reason"`
	DetectedEpisode int     `json:"detected_episode,omitempty"`
	QualityBonus    float64 `json:"quality_bonus"`
	TrustedChannel  bool    `json:"trusted_channel"`
	ConfidenceTier  string  `json:"confidence_tier"`
	ConfidenceRank  int     `json:"confidence_rank"`
	ConfidenceLabel string  `json:"confidence_label"`
}

// ScoredVideo 保存视频与评分明细。
type ScoredVideo struct {
	Video invidious.Video `json:"video"`
	Score ScoreDetail     `json:"score"`
}

// TrustedChannelFunc 判断频道是否可信。
type TrustedChannelFunc func(channelID string) bool

var confidenceTiers = map[string]struct {
	Rank      int
	BaseScore float64
	Label     string
}{
	"S": {Rank: 4, BaseScore: 90, Label: "高置信：标题/集数/可信频道均命中"},
	"A": {Rank: 3, BaseScore: 80, Label: "高置信：标题和集数命中"},
	"B": {Rank: 2, BaseScore: 65, Label: "中置信：标题命中但未识别集数"},
	"C": {Rank: 1, BaseScore: 35, Label: "低置信：弱匹配候选"},
}

var healthRank = map[string]int{"available": 3, "unknown": 2, "error": 1, "invalid": 0}

// ScoreVideo 对单个视频进行综合评分。
func ScoreVideo(video invidious.Video, animeTitle string, targetEpisode int, aliases []string, trusted TrustedChannelFunc, cfg *config.Config) ScoreDetail {
	if ShouldFilter(video.Title, video.Duration, cfg) {
		return filteredScore("合集/非正片内容", 0, 0)
	}
	normalizedVideoTitle := NormalizeText(video.Title)
	normalizedAnimeTitle := NormalizeText(animeTitle)
	normalizedAliases := make([]string, 0, len(aliases))
	for _, alias := range aliases {
		normalizedAliases = append(normalizedAliases, NormalizeText(alias))
	}
	titleScore := FuzzyMatchScore(normalizedVideoTitle, normalizedAnimeTitle, normalizedAliases, cfg.FuzzyNGramSize)
	if titleScore < cfg.TitleAcceptThreshold {
		return filteredScore("标题匹配度过低", titleScore, 0)
	}
	detectedEpisode, hasEpisode := ExtractEpisodeNumber(video.Title)
	episodeScore := 20.0
	if hasEpisode {
		if detectedEpisode != targetEpisode {
			result := filteredScore("集数不匹配", titleScore, detectedEpisode)
			return result
		}
		episodeScore = 100
	}
	trustedChannel := trusted != nil && video.ChannelID != "" && trusted(video.ChannelID)
	channelScore := getChannelScore(trustedChannel)
	recencyScore := getRecencyScore(video.PublishedTimestamp)
	viewScore := getViewScore(video.ViewCount)
	qualityBonus := getQualityBonus(video.Title)
	tier := resolveConfidenceTier(titleScore, hasEpisode, trustedChannel, cfg)
	totalScore := getTieredScore(tier, titleScore, episodeScore, channelScore, recencyScore, viewScore, qualityBonus, cfg)
	confidence := confidenceTiers[tier]
	return ScoreDetail{TotalScore: totalScore, TitleScore: round2(titleScore), EpisodeScore: round2(episodeScore), ChannelScore: round2(channelScore), RecencyScore: round2(recencyScore), ViewScore: round2(viewScore), Filtered: false, DetectedEpisode: detectedEpisode, QualityBonus: qualityBonus, TrustedChannel: trustedChannel, ConfidenceTier: tier, ConfidenceRank: confidence.Rank, ConfidenceLabel: confidence.Label}
}

// SortScoredVideos 按置信等级和多维度排序。
func SortScoredVideos(videos []ScoredVideo) {
	sort.SliceStable(videos, func(i int, j int) bool {
		left := videos[i]
		right := videos[j]
		return sourceSortKey(left) > sourceSortKey(right)
	})
}

// filteredScore 创建过滤结果。
func filteredScore(reason string, titleScore float64, detectedEpisode int) ScoreDetail {
	return ScoreDetail{TotalScore: 0, TitleScore: round2(titleScore), Filtered: true, FilterReason: reason, DetectedEpisode: detectedEpisode}
}

// getQualityBonus 计算画质加分。
func getQualityBonus(title string) float64 {
	lower := strings.ToLower(title)
	bonus := 0.0
	for keyword, value := range config.QualityBonusKeywords {
		if strings.Contains(lower, strings.ToLower(keyword)) {
			bonus = math.Max(bonus, value)
		}
	}
	return bonus
}

// getChannelScore 计算频道可信度分。
func getChannelScore(trusted bool) float64 {
	if trusted {
		return 100
	}
	return 0
}

// getViewScore 计算播放量分。
func getViewScore(viewCount int64) float64 {
	switch {
	case viewCount > 1000000:
		return 100
	case viewCount > 100000:
		return 80
	case viewCount > 10000:
		return 60
	case viewCount > 1000:
		return 40
	case viewCount > 0:
		return 20
	default:
		return 0
	}
}

// getRecencyScore 计算发布时间新鲜度分。
func getRecencyScore(publishedTimestamp int64) float64 {
	if publishedTimestamp <= 0 {
		return 50
	}
	ageDays := time.Since(time.Unix(publishedTimestamp, 0)).Hours() / 24
	switch {
	case ageDays <= 7:
		return 100
	case ageDays <= 30:
		return 80
	case ageDays <= 90:
		return 60
	case ageDays <= 365:
		return 40
	default:
		return 20
	}
}

// resolveConfidenceTier 解析置信等级。
func resolveConfidenceTier(titleScore float64, hasEpisode bool, trustedChannel bool, cfg *config.Config) string {
	if !hasEpisode {
		if titleScore >= cfg.TitleStrongThreshold {
			return "B"
		}
		return "C"
	}
	if titleScore >= cfg.TitleStrongThreshold && trustedChannel {
		return "S"
	}
	if titleScore >= cfg.TitleStrongThreshold {
		return "A"
	}
	return "C"
}

// getTieredScore 计算分层总分，tie-breaker 不跨层。
func getTieredScore(tier string, titleScore float64, episodeScore float64, channelScore float64, recencyScore float64, viewScore float64, qualityBonus float64, cfg *config.Config) float64 {
	tieScore := titleScore*cfg.TieWeightTitle + episodeScore*cfg.TieWeightEpisode + channelScore*cfg.TieWeightChannel + recencyScore*cfg.TieWeightRecency + viewScore*cfg.TieWeightView + qualityBonus*cfg.TieWeightQuality
	tieBreaker := math.Min(9.99, tieScore/10)
	return round2(confidenceTiers[tier].BaseScore + tieBreaker)
}

// sourceSortKey 返回可比较的排序权重。
func sourceSortKey(video ScoredVideo) float64 {
	score := video.Score
	health := healthRank["unknown"]
	return float64(score.ConfidenceRank)*1e12 + score.EpisodeScore*1e9 + score.TitleScore*1e7 + boolWeight(score.TrustedChannel)*1e6 + float64(health)*1e5 + float64(video.Video.PublishedTimestamp) + float64(video.Video.ViewCount)/1e6 + score.QualityBonus*10 + score.TotalScore
}

// boolWeight 将布尔值转为排序权重。
func boolWeight(value bool) float64 {
	if value {
		return 1
	}
	return 0
}

// round2 保留两位小数。
func round2(value float64) float64 {
	return math.Round(value*100) / 100
}

// atoi 解析整数，失败返回 0。
func atoi(value string) int {
	result := 0
	for _, item := range value {
		if item < '0' || item > '9' {
			return 0
		}
		result = result*10 + int(item-'0')
	}
	return result
}

// minInt 返回两个整数中的较小值。
func minInt(left int, right int) int {
	if left < right {
		return left
	}
	return right
}

// maxIntRuneLen 返回两个字符串 rune 长度的较大值。
func maxIntRuneLen(left string, right string) int {
	leftLength := len([]rune(left))
	rightLength := len([]rune(right))
	if leftLength > rightLength {
		return leftLength
	}
	return rightLength
}

// contains 判断字符串是否包含子串。
func contains(text string, sub string) bool {
	return strings.Contains(text, sub)
}
