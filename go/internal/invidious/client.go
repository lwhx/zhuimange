// Package invidious 实现 Invidious API 客户端与实例负载均衡。
package invidious

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/lwhx/zhuimange/internal/config"
	"github.com/lwhx/zhuimange/internal/store"
)

// Client 封装 Invidious 请求、实例刷新、故障切换和加权轮询。
type Client struct {
	cfg   *config.Config
	store *store.Store
	http  *http.Client
	mu    sync.Mutex
	index int
	state instanceState
}

// instanceState 保存当前 Invidious 实例配置快照。
type instanceState struct {
	PrimaryURL      string
	FallbackURLs    []string
	InstanceWeights map[string]int
	CurrentURL      string
}

// Video 表示 Invidious 搜索或详情接口返回的视频源信息。
type Video struct {
	VideoID            string `json:"video_id"`
	Title              string `json:"title"`
	ChannelID          string `json:"channel_id"`
	ChannelName        string `json:"channel_name"`
	Duration           int    `json:"duration"`
	ViewCount          int64  `json:"view_count"`
	Description        string `json:"description,omitempty"`
	PublishedAt        string `json:"published_at"`
	PublishedTimestamp int64  `json:"published_timestamp,omitempty"`
}

// LoadBalanceSummary 描述当前实例负载均衡策略。
type LoadBalanceSummary struct {
	Strategy        string         `json:"strategy"`
	PrimaryWeight   int            `json:"primary_weight"`
	FallbackWeight  int            `json:"fallback_weight"`
	FallbackCount   int            `json:"fallback_count"`
	InstanceWeights map[string]int `json:"instance_weights"`
	TotalWeight     int            `json:"total_weight"`
	RatioText       string         `json:"ratio_text"`
	Description     string         `json:"description"`
	AvailableCount  int            `json:"available_count"`
	TotalCount      int            `json:"total_count"`
}

// New 创建 Invidious 客户端。
func New(cfg *config.Config, st *store.Store) *Client {
	transport := &http.Transport{Proxy: http.ProxyFromEnvironment, MaxIdleConns: 64, MaxIdleConnsPerHost: 64, IdleConnTimeout: 90 * time.Second}
	client := &Client{
		cfg:   cfg,
		store: st,
		http:  &http.Client{Timeout: time.Duration(cfg.InvidiousAPITimeout) * time.Second, Transport: transport},
		state: instanceState{PrimaryURL: normalizeURL(cfg.InvidiousURL), CurrentURL: normalizeURL(cfg.InvidiousURL), InstanceWeights: map[string]int{}},
	}
	client.refreshWithContext(context.Background())
	slog.Info("Invidious 客户端初始化", "current_url", client.state.CurrentURL)
	return client
}

// TestConnection 测试当前实例是否可用。
func (c *Client) TestConnection(ctx context.Context) bool {
	if err := c.RefreshInstances(ctx); err != nil {
		slog.Warn("刷新 Invidious 实例失败", "error", err)
	}
	currentURL := c.currentURL()
	if currentURL == "" {
		return false
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, currentURL+"/api/v1/stats", nil)
	if err != nil {
		return false
	}
	resp, err := c.http.Do(req)
	if err != nil {
		slog.Warn("Invidious 连接测试失败", "url", currentURL, "error", err)
		return false
	}
	defer resp.Body.Close()
	slog.Info("Invidious 连接测试完成", "url", currentURL, "status", resp.StatusCode)
	return resp.StatusCode == http.StatusOK
}

// RefreshInstances 从数据库 settings 重新加载主实例、备用实例和权重。
func (c *Client) RefreshInstances(ctx context.Context) error {
	return c.refreshWithContext(ctx)
}

// GetInstanceURLs 返回去重后的全部实例 URL。
func (c *Client) GetInstanceURLs() []string {
	c.mu.Lock()
	defer c.mu.Unlock()
	return instanceURLs(c.state.PrimaryURL, c.state.FallbackURLs)
}

// GetLoadBalanceSummary 返回当前负载均衡摘要。
func (c *Client) GetLoadBalanceSummary() LoadBalanceSummary {
	c.mu.Lock()
	defer c.mu.Unlock()

	urls := instanceURLs(c.state.PrimaryURL, c.state.FallbackURLs)
	weights := make(map[string]int, len(urls))
	total := 0
	for _, item := range urls {
		weight := c.state.InstanceWeights[item]
		weights[item] = weight
		total += weight
	}
	primaryWeight := weights[c.state.PrimaryURL]
	fallbackWeight := 0
	ratioParts := []string{fmt.Sprintf("%d", primaryWeight)}
	for _, item := range c.state.FallbackURLs {
		fallbackWeight += weights[item]
		ratioParts = append(ratioParts, fmt.Sprintf("%d", weights[item]))
	}
	description := "仅主实例参与请求"
	if len(c.state.FallbackURLs) > 0 && total > 0 {
		primaryPercent := int(float64(primaryWeight)/float64(total)*100 + 0.5)
		description = fmt.Sprintf("主实例约 %d%%，%d 个备用实例整体约 %d%%", primaryPercent, len(c.state.FallbackURLs), 100-primaryPercent)
	} else if total <= 0 {
		description = "所有实例权重为 0，将仅使用主实例"
	}

	return LoadBalanceSummary{Strategy: "weighted_round_robin", PrimaryWeight: primaryWeight, FallbackWeight: fallbackWeight, FallbackCount: len(c.state.FallbackURLs), InstanceWeights: weights, TotalWeight: total, RatioText: strings.Join(ratioParts, ":"), Description: description}
}

// SearchVideos 搜索视频并转换为统一结构。
func (c *Client) SearchVideos(ctx context.Context, query string, maxResults int, sortBy string) ([]Video, error) {
	if sortBy == "" {
		sortBy = "relevance"
	}
	values := url.Values{}
	values.Set("q", query)
	values.Set("type", "video")
	values.Set("sort_by", sortBy)
	var payload []searchItem
	if err := c.request(ctx, "/api/v1/search?"+values.Encode(), &payload); err != nil {
		return nil, err
	}
	videos := make([]Video, 0, minInt(maxResults, len(payload)))
	for _, item := range payload {
		if item.Type != "video" {
			continue
		}
		videos = append(videos, Video{VideoID: item.VideoID, Title: item.Title, ChannelID: item.AuthorID, ChannelName: item.Author, Duration: item.LengthSeconds, ViewCount: item.ViewCount, PublishedAt: item.PublishedText, PublishedTimestamp: item.Published})
		if maxResults > 0 && len(videos) >= maxResults {
			break
		}
	}
	slog.Info("Invidious 搜索完成", "query", query, "count", len(videos))
	return videos, nil
}

// GetVideoInfo 获取单个视频详情。
func (c *Client) GetVideoInfo(ctx context.Context, videoID string) (*Video, error) {
	var item videoItem
	if err := c.request(ctx, "/api/v1/videos/"+url.PathEscape(videoID), &item); err != nil {
		return nil, err
	}
	return &Video{VideoID: firstNonEmpty(item.VideoID, videoID), Title: item.Title, ChannelID: item.AuthorID, ChannelName: item.Author, Duration: item.LengthSeconds, ViewCount: item.ViewCount, Description: item.Description, PublishedAt: item.PublishedText}, nil
}

// refreshWithContext 执行实例配置热加载。
func (c *Client) refreshWithContext(ctx context.Context) error {
	primaryURL, primaryErr := c.loadPrimaryURL(ctx)
	fallbackURLs, fallbackErr := c.loadFallbackURLs(ctx, primaryURL)
	weights, weightErr := c.loadInstanceWeights(ctx, primaryURL, fallbackURLs)

	c.mu.Lock()
	defer c.mu.Unlock()
	c.state.PrimaryURL = primaryURL
	c.state.FallbackURLs = fallbackURLs
	c.state.InstanceWeights = weights
	if c.state.CurrentURL == "" || !contains(instanceURLs(primaryURL, fallbackURLs), c.state.CurrentURL) {
		c.state.CurrentURL = primaryURL
	}

	if primaryErr != nil {
		return primaryErr
	}
	if fallbackErr != nil {
		return fallbackErr
	}
	return weightErr
}

// request 发送 API 请求，失败时逐个切换实例重试。
func (c *Client) request(ctx context.Context, endpoint string, target any) error {
	if err := c.RefreshInstances(ctx); err != nil {
		slog.Warn("刷新 Invidious 实例失败，继续使用当前快照", "error", err)
	}
	tried := map[string]bool{}
	candidate := c.activeURL()
	var lastErr error
	for candidate != "" {
		tried[candidate] = true
		requestURL := candidate + endpoint
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, requestURL, nil)
		if err != nil {
			return err
		}
		resp, err := c.http.Do(req)
		if err == nil && resp.StatusCode >= 200 && resp.StatusCode < 300 {
			defer resp.Body.Close()
			c.setCurrentURL(candidate)
			return json.NewDecoder(resp.Body).Decode(target)
		}
		if resp != nil {
			resp.Body.Close()
			lastErr = fmt.Errorf("Invidious 请求失败: %s HTTP %d", requestURL, resp.StatusCode)
		} else {
			lastErr = fmt.Errorf("Invidious 请求失败: %s %w", requestURL, err)
		}
		slog.Warn("Invidious 请求失败，尝试切换实例", "url", requestURL, "error", lastErr)
		nextURL := c.switchInstance(ctx, candidate)
		if nextURL == "" || tried[nextURL] {
			break
		}
		candidate = nextURL
	}
	if lastErr != nil {
		return lastErr
	}
	return fmt.Errorf("无可用 Invidious 实例")
}

// activeURL 按权重轮询获取本次请求实例。
func (c *Client) activeURL() string {
	c.mu.Lock()
	defer c.mu.Unlock()
	pool := c.weightedPoolLocked()
	if len(pool) == 0 {
		c.state.CurrentURL = c.state.PrimaryURL
		return c.state.CurrentURL
	}
	selected := pool[c.index%len(pool)]
	c.index = (c.index + 1) % len(pool)
	c.state.CurrentURL = selected
	return selected
}

// switchInstance 从失败实例后方开始探测下一个可用实例。
func (c *Client) switchInstance(ctx context.Context, failedURL string) string {
	urls := c.GetInstanceURLs()
	if len(urls) == 0 {
		return ""
	}
	ordered := make([]string, 0, len(urls))
	failedIndex := indexOf(urls, failedURL)
	if failedIndex >= 0 {
		ordered = append(ordered, urls[failedIndex+1:]...)
		ordered = append(ordered, urls[:failedIndex]...)
	} else {
		for _, item := range urls {
			if item != c.currentURL() {
				ordered = append(ordered, item)
			}
		}
	}
	for _, candidate := range ordered {
		if c.probeStats(ctx, candidate) {
			c.setCurrentURL(candidate)
			slog.Info("Invidious 实例切换完成", "url", candidate)
			return candidate
		}
	}
	slog.Warn("所有 Invidious 实例均不可用")
	return ""
}

// probeStats 探测实例 stats 接口是否可用。
func (c *Client) probeStats(ctx context.Context, instanceURL string) bool {
	probeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(probeCtx, http.MethodGet, instanceURL+"/api/v1/stats", nil)
	if err != nil {
		return false
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

// loadPrimaryURL 从 settings 读取主实例地址。
func (c *Client) loadPrimaryURL(ctx context.Context) (string, error) {
	value, err := c.store.GetSetting(ctx, "invidious_url", c.cfg.InvidiousURL)
	if err != nil {
		return normalizeURL(c.cfg.InvidiousURL), err
	}
	if normalized := normalizeURL(value); normalized != "" {
		return normalized, nil
	}
	return normalizeURL(c.cfg.InvidiousURL), nil
}

// loadFallbackURLs 从 settings 读取备用实例地址。
func (c *Client) loadFallbackURLs(ctx context.Context, primaryURL string) ([]string, error) {
	defaultValue, _ := json.Marshal(c.cfg.InvidiousFallbackURLs)
	value, err := c.store.GetSetting(ctx, "invidious_fallback_urls", string(defaultValue))
	if err != nil {
		return normalizeURLList(c.cfg.InvidiousFallbackURLs, primaryURL), err
	}
	parsed := parseFallbackURLs(value)
	if len(parsed) == 0 && len(c.cfg.InvidiousFallbackURLs) > 0 {
		parsed = c.cfg.InvidiousFallbackURLs
	}
	return normalizeURLList(parsed, primaryURL), nil
}

// loadInstanceWeights 读取实例独立权重并补齐默认权重。
func (c *Client) loadInstanceWeights(ctx context.Context, primaryURL string, fallbackURLs []string) (map[string]int, error) {
	defaults := c.defaultWeights(primaryURL, fallbackURLs)
	value, err := c.store.GetSetting(ctx, "invidious_instance_weights", "{}")
	if err != nil {
		return defaults, err
	}
	custom := parseInstanceWeights(value)
	weights := make(map[string]int, len(defaults))
	for _, item := range instanceURLs(primaryURL, fallbackURLs) {
		if weight, ok := custom[item]; ok {
			weights[item] = maxInt(0, weight)
		} else {
			weights[item] = defaults[item]
		}
	}
	return weights, nil
}

// defaultWeights 按旧逻辑生成默认权重。
func (c *Client) defaultWeights(primaryURL string, fallbackURLs []string) map[string]int {
	weights := map[string]int{primaryURL: maxInt(1, c.cfg.InvidiousPrimaryWeight)}
	fallbackTotal := maxInt(0, c.cfg.InvidiousFallbackWeight)
	if len(fallbackURLs) == 0 {
		return weights
	}
	base := fallbackTotal / len(fallbackURLs)
	extra := fallbackTotal % len(fallbackURLs)
	for index, item := range fallbackURLs {
		weight := base
		if index < extra {
			weight++
		}
		weights[item] = weight
	}
	return weights
}

// weightedPoolLocked 基于权重构造轮询池，调用方必须持有锁。
func (c *Client) weightedPoolLocked() []string {
	urls := instanceURLs(c.state.PrimaryURL, c.state.FallbackURLs)
	pool := []string{}
	for _, item := range urls {
		weight := maxInt(0, c.state.InstanceWeights[item])
		for i := 0; i < weight; i++ {
			pool = append(pool, item)
		}
	}
	if len(pool) == 0 && c.state.PrimaryURL != "" {
		return []string{c.state.PrimaryURL}
	}
	return pool
}

// currentURL 返回当前实例 URL。
func (c *Client) currentURL() string {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.state.CurrentURL
}

// setCurrentURL 更新当前实例 URL。
func (c *Client) setCurrentURL(value string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.state.CurrentURL = value
}

// searchItem 表示搜索接口原始视频字段。
type searchItem struct {
	Type          string `json:"type"`
	VideoID       string `json:"videoId"`
	Title         string `json:"title"`
	AuthorID      string `json:"authorId"`
	Author        string `json:"author"`
	LengthSeconds int    `json:"lengthSeconds"`
	ViewCount     int64  `json:"viewCount"`
	PublishedText string `json:"publishedText"`
	Published     int64  `json:"published"`
}

// videoItem 表示详情接口原始视频字段。
type videoItem struct {
	VideoID       string `json:"videoId"`
	Title         string `json:"title"`
	AuthorID      string `json:"authorId"`
	Author        string `json:"author"`
	LengthSeconds int    `json:"lengthSeconds"`
	ViewCount     int64  `json:"viewCount"`
	Description   string `json:"description"`
	PublishedText string `json:"publishedText"`
}

// parseFallbackURLs 解析 JSON 数组或逗号分隔形式的备用实例。
func parseFallbackURLs(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil
	}
	var items []string
	if err := json.Unmarshal([]byte(raw), &items); err == nil {
		return items
	}
	parts := strings.FieldsFunc(raw, func(r rune) bool { return r == ',' || r == '\n' || r == '\r' })
	result := make([]string, 0, len(parts))
	for _, part := range parts {
		if item := strings.TrimSpace(part); item != "" {
			result = append(result, item)
		}
	}
	return result
}

// parseInstanceWeights 解析实例权重 JSON。
func parseInstanceWeights(raw string) map[string]int {
	var values map[string]int
	if err := json.Unmarshal([]byte(strings.TrimSpace(raw)), &values); err != nil {
		return map[string]int{}
	}
	result := map[string]int{}
	for key, value := range values {
		if normalized := normalizeURL(key); normalized != "" {
			result[normalized] = maxInt(0, value)
		}
	}
	return result
}

// normalizeURL 规范化实例地址。
func normalizeURL(value string) string {
	return strings.TrimRight(strings.TrimSpace(value), "/")
}

// normalizeURLList 规范化并去重 URL 列表。
func normalizeURLList(values []string, primaryURL string) []string {
	result := []string{}
	for _, value := range values {
		normalized := normalizeURL(value)
		if normalized != "" && normalized != primaryURL && !contains(result, normalized) {
			result = append(result, normalized)
		}
	}
	return result
}

// instanceURLs 组合主实例和备用实例。
func instanceURLs(primaryURL string, fallbackURLs []string) []string {
	urls := []string{}
	if primaryURL != "" {
		urls = append(urls, primaryURL)
	}
	for _, item := range fallbackURLs {
		if item != "" && !contains(urls, item) {
			urls = append(urls, item)
		}
	}
	return urls
}

// contains 判断字符串切片是否包含目标值。
func contains(values []string, target string) bool {
	return indexOf(values, target) >= 0
}

// indexOf 返回字符串在切片中的索引。
func indexOf(values []string, target string) int {
	for index, item := range values {
		if item == target {
			return index
		}
	}
	return -1
}

// minInt 返回两个整数中的较小值。
func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// maxInt 返回两个整数中的较大值。
func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// firstNonEmpty 返回第一个非空字符串。
func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}
