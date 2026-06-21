// Package tmdb 封装 TMDB API 客户端，提供动漫搜索与详情获取。
//
// 迁移自 Python tmdb_client.py，保持字段映射与跨季 absolute_num 连续编号语义一致。
package tmdb

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strconv"
	"time"

	"github.com/lwhx/zhuimange/internal/config"
)

// ImageBase 是 TMDB 海报/剧照的基础 URL。
const ImageBase = "https://image.tmdb.org/t/p/w500"

// SearchResult TMDB 搜索结果项。
type SearchResult struct {
	TMDBID        int64   `json:"tmdb_id"`
	TitleCN       string  `json:"title_cn"`
	TitleEN       string  `json:"title_en"`
	PosterURL     string  `json:"poster_url"`
	Overview      string  `json:"overview"`
	AirDate       string  `json:"air_date"`
	VoteAverage   float64 `json:"vote_average"`
	TotalEpisodes int     `json:"total_episodes"`
}

// SeasonDetail 季信息。
type SeasonDetail struct {
	SeasonNumber int    `json:"season_number"`
	EpisodeCount int    `json:"episode_count"`
	Name         string `json:"name"`
}

// AnimeDetail 动漫详情。
type AnimeDetail struct {
	TMDBID        int64         `json:"tmdb_id"`
	TitleCN       string        `json:"title_cn"`
	TitleEN       string        `json:"title_en"`
	PosterURL     string        `json:"poster_url"`
	Overview      string        `json:"overview"`
	AirDate       string        `json:"air_date"`
	TotalEpisodes int           `json:"total_episodes"`
	Status        string        `json:"status"`
	Seasons       []SeasonDetail `json:"seasons"`
}

// Episode 集数信息（带跨季连续 absolute_num）。
type Episode struct {
	SeasonNumber  int    `json:"season_number"`
	EpisodeNumber int    `json:"episode_number"`
	AbsoluteNum   int    `json:"absolute_num"`
	Title         string `json:"title"`
	Overview      string `json:"overview"`
	AirDate       string `json:"air_date"`
	StillPath     string `json:"still_path"`
}

// Client TMDB API 客户端。
type Client struct {
	apiKey   string
	baseURL  string
	language string
	http     *http.Client
}

// New 创建 TMDB 客户端。
func New(cfg *config.Config) *Client {
	return &Client{
		apiKey:   cfg.TMDBAPIKey,
		baseURL:  cfg.TMDBBaseURL,
		language: cfg.TMDBLanguage,
		http: &http.Client{
			Timeout: 15 * time.Second,
			Transport: &http.Transport{
				MaxIdleConns:        10,
				MaxIdleConnsPerHost: 5,
				IdleConnTimeout:     90 * time.Second,
			},
		},
	}
}

// request 发送 TMDB API 请求并解析 JSON。
func (c *Client) request(ctx context.Context, endpoint string, params map[string]string) (map[string]any, error) {
	u, err := url.Parse(c.baseURL + endpoint)
	if err != nil {
		return nil, err
	}
	q := u.Query()
	q.Set("api_key", c.apiKey)
	q.Set("language", c.language)
	for k, v := range params {
		q.Set(k, v)
	}
	u.RawQuery = q.Encode()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, err
	}

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("TMDB 请求失败 %s: %w", endpoint, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("TMDB 返回 %d: %s", resp.StatusCode, string(body))
	}

	var result map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("解析 TMDB 响应失败: %w", err)
	}
	return result, nil
}

// SearchAnime 搜索动漫（with_genres=16 动画过滤）。
func (c *Client) SearchAnime(ctx context.Context, query string) ([]SearchResult, error) {
	data, err := c.request(ctx, "/search/tv", map[string]string{
		"query":       query,
		"with_genres": "16",
		"include_adult": "false",
	})
	if err != nil {
		return nil, err
	}

	rawResults, _ := data["results"].([]any)
	results := make([]SearchResult, 0, len(rawResults))
	for _, r := range rawResults {
		item, ok := r.(map[string]any)
		if !ok {
			continue
		}
		tmdbID := toInt64(item["id"])
		results = append(results, SearchResult{
			TMDBID:        tmdbID,
			TitleCN:       toString(item["name"]),
			TitleEN:       toString(item["original_name"]),
			PosterURL:     toPosterURL(item["poster_path"]),
			Overview:      toString(item["overview"]),
			AirDate:       toString(item["first_air_date"]),
			VoteAverage:   toFloat64(item["vote_average"]),
			TotalEpisodes: toInt(item["number_of_episodes"]),
		})
	}
	return results, nil
}

// GetAnimeDetail 获取动漫详情（过滤 season_number=0 特别篇）。
func (c *Client) GetAnimeDetail(ctx context.Context, tmdbID int64) (*AnimeDetail, error) {
	data, err := c.request(ctx, fmt.Sprintf("/tv/%d", tmdbID), nil)
	if err != nil {
		return nil, err
	}

	rawSeasons, _ := data["seasons"].([]any)
	var regularSeasons []SeasonDetail
	totalEpisodes := 0
	for _, s := range rawSeasons {
		season, ok := s.(map[string]any)
		if !ok {
			continue
		}
		seasonNum := toInt(season["season_number"])
		if seasonNum <= 0 {
			continue // 跳过特别篇
		}
		ec := toInt(season["episode_count"])
		totalEpisodes += ec
		regularSeasons = append(regularSeasons, SeasonDetail{
			SeasonNumber: seasonNum,
			EpisodeCount: ec,
			Name:         toString(season["name"]),
		})
	}

	return &AnimeDetail{
		TMDBID:        toInt64(data["id"]),
		TitleCN:       toString(data["name"]),
		TitleEN:       toString(data["original_name"]),
		PosterURL:     toPosterURL(data["poster_path"]),
		Overview:      toString(data["overview"]),
		AirDate:       toString(data["first_air_date"]),
		TotalEpisodes: totalEpisodes,
		Status:        toString(data["status"]),
		Seasons:       regularSeasons,
	}, nil
}

// GetAllEpisodes 获取所有季的集数，按季顺序累加 absolute_num（跨季连续编号）。
// 这是追更场景的核心：无论第几季，集数从 1 连续递增。
func (c *Client) GetAllEpisodes(ctx context.Context, tmdbID int64, seasons []SeasonDetail) ([]Episode, error) {
	var episodes []Episode
	absoluteNum := 0

	for _, season := range seasons {
		data, err := c.request(ctx, fmt.Sprintf("/tv/%d/season/%d", tmdbID, season.SeasonNumber), nil)
		if err != nil {
			slog.Warn("获取季集数失败，跳过", "tmdb_id", tmdbID, "season", season.SeasonNumber, "error", err)
			continue
		}
		rawEps, _ := data["episodes"].([]any)
		for _, e := range rawEps {
			ep, ok := e.(map[string]any)
			if !ok {
				continue
			}
			absoluteNum++
			episodes = append(episodes, Episode{
				SeasonNumber:  season.SeasonNumber,
				EpisodeNumber: toInt(ep["episode_number"]),
				AbsoluteNum:   absoluteNum,
				Title:         toString(ep["name"]),
				Overview:      toString(ep["overview"]),
				AirDate:       toString(ep["air_date"]),
				StillPath:     toPosterURL(ep["still_path"]),
			})
		}
	}
	return episodes, nil
}

// ==================== 类型转换辅助 ====================

func toInt64(v any) int64 {
	switch n := v.(type) {
	case float64:
		return int64(n)
	case int:
		return int64(n)
	case int64:
		return n
	case string:
		i, _ := strconv.ParseInt(n, 10, 64)
		return i
	}
	return 0
}

func toInt(v any) int {
	return int(toInt64(v))
}

func toFloat64(v any) float64 {
	switch n := v.(type) {
	case float64:
		return n
	case int:
		return float64(n)
	case int64:
		return float64(n)
	}
	return 0
}

func toString(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

func toPosterURL(v any) string {
	if path, ok := v.(string); ok && path != "" {
		return ImageBase + path
	}
	return ""
}
