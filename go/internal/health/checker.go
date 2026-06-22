// Package health 实现 Invidious 和视频源健康诊断。
package health

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/lwhx/zhuimange/internal/invidious"
	"github.com/lwhx/zhuimange/internal/store"
)

const defaultProbeVideoID = "dQw4w9WgXcQ"

// Checker 封装健康诊断依赖。
type Checker struct {
	store     *store.Store
	invidious *invidious.Client
	http      *http.Client
}

// NewChecker 创建健康诊断器。
func NewChecker(st *store.Store, client *invidious.Client) *Checker {
	return &Checker{store: st, invidious: client, http: &http.Client{Timeout: 10 * time.Second}}
}

// InvidiousHealth 表示 Invidious 健康诊断结果。
type InvidiousHealth struct {
	CheckedAt     string                       `json:"checked_at"`
	OverallStatus string                       `json:"overall_status"`
	PrimaryURL    string                       `json:"primary_url"`
	ActiveURL     string                       `json:"active_url"`
	Timeout       int                          `json:"timeout"`
	Instances     []InstanceHealth             `json:"instances"`
	VideoProbe    VideoProbe                   `json:"video_probe"`
	VideoProbes   []VideoProbe                 `json:"video_probes"`
	LoadBalance   invidious.LoadBalanceSummary `json:"load_balance"`
}

// InstanceHealth 表示单个实例健康状态。
type InstanceHealth struct {
	URL        string `json:"url"`
	Available  bool   `json:"available"`
	StatusCode int    `json:"status_code"`
	LatencyMS  int64  `json:"latency_ms"`
	Error      string `json:"error"`
}

// VideoProbe 表示视频详情探针结果。
type VideoProbe struct {
	URL        string `json:"url"`
	VideoID    string `json:"video_id"`
	Available  bool   `json:"available"`
	StatusCode int    `json:"status_code"`
	LatencyMS  int64  `json:"latency_ms"`
	Error      string `json:"error"`
	Title      string `json:"title"`
}

// CheckInvidious 检测所有 Invidious 实例 stats 接口及视频详情链路。
func (c *Checker) CheckInvidious(ctx context.Context) InvidiousHealth {
	return c.CheckInvidiousWithVideo(ctx, defaultProbeVideoID)
}

// CheckInvidiousWithVideo 用指定视频 ID 检测实例连通性与视频详情链路（对齐 Python _run_health_check）。
func (c *Checker) CheckInvidiousWithVideo(ctx context.Context, videoID string) InvidiousHealth {
	if videoID == "" {
		videoID = defaultProbeVideoID
	}
	urls := c.invidious.GetInstanceURLs()
	items := make([]InstanceHealth, 0, len(urls))
	available := 0
	for _, item := range urls {
		result := c.checkInstance(ctx, item)
		if result.Available {
			available++
		}
		items = append(items, result)
	}

	// 视频详情探针：仅对可用实例探测 /api/v1/videos/{video_id}
	videoProbes := make([]VideoProbe, 0, available)
	activeURL := ""
	for _, inst := range items {
		if !inst.Available {
			continue
		}
		probe := c.checkVideoDetail(ctx, inst.URL, videoID)
		videoProbes = append(videoProbes, probe)
		if activeURL == "" && probe.Available {
			activeURL = inst.URL // 第一个可用的作为 active_url
		}
	}

	videoProbe := VideoProbe{VideoID: videoID}
	if len(videoProbes) > 0 {
		videoProbe = videoProbes[0]
	}

	status := "healthy"
	if available == 0 {
		status = "down"
	} else if available < len(urls) || !videoProbe.Available {
		status = "degraded"
	}

	lb := c.invidious.GetLoadBalanceSummary()
	lb.AvailableCount = available
	lb.TotalCount = len(items)

	return InvidiousHealth{
		CheckedAt:     time.Now().Format(time.RFC3339),
		OverallStatus: status,
		PrimaryURL:    c.primaryURL(),
		ActiveURL:     activeURL,
		Timeout:       int(c.http.Timeout.Seconds()),
		Instances:     items,
		VideoProbe:    videoProbe,
		VideoProbes:   videoProbes,
		LoadBalance:   lb,
	}
}

func (c *Checker) primaryURL() string {
	urls := c.invidious.GetInstanceURLs()
	if len(urls) > 0 {
		return urls[0]
	}
	return ""
}

// CheckSourceHealth 检测指定视频源是否可用。
func (c *Checker) CheckSourceHealth(ctx context.Context, sourceID int64, videoID string) map[string]any {
	_, err := c.invidious.GetVideoInfo(ctx, videoID)
	if err == nil {
		_ = c.store.UpdateSourceHealth(ctx, sourceID, "available", 0, "")
		return map[string]any{"source_id": sourceID, "video_id": videoID, "health_status": "available", "error": ""}
	}
	_ = c.store.UpdateSourceHealth(ctx, sourceID, "error", 1, err.Error())
	return map[string]any{"source_id": sourceID, "video_id": videoID, "health_status": "error", "error": err.Error()}
}

// CheckSourcesBatch 批量检测视频源健康状态。
func (c *Checker) CheckSourcesBatch(ctx context.Context, limit int) (map[string]any, error) {
	sources, err := c.store.ListAllSources(ctx, limit)
	if err != nil {
		return nil, err
	}
	results := make([]map[string]any, 0, len(sources))
	summary := map[string]int{"available": 0, "error": 0, "unknown": 0}
	for _, source := range sources {
		result := c.CheckSourceHealth(ctx, source.ID, source.VideoID)
		status, _ := result["health_status"].(string)
		if _, ok := summary[status]; !ok {
			status = "unknown"
		}
		summary[status]++
		results = append(results, result)
	}
	return map[string]any{"checked": len(results), "summary": summary, "sources": results}, nil
}

// checkInstance 检测单个实例 stats 接口。
func (c *Checker) checkInstance(ctx context.Context, instanceURL string) InstanceHealth {
	started := time.Now()
	result := InstanceHealth{URL: instanceURL}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, instanceURL+"/api/v1/stats", nil)
	if err != nil {
		result.Error = err.Error()
		return result
	}
	resp, err := c.http.Do(req)
	result.LatencyMS = time.Since(started).Milliseconds()
	if err != nil {
		result.Error = err.Error()
		return result
	}
	defer resp.Body.Close()
	result.StatusCode = resp.StatusCode
	result.Available = resp.StatusCode == http.StatusOK
	if !result.Available {
		result.Error = fmt.Sprintf("HTTP %d", resp.StatusCode)
	}
	return result
}

// checkVideoDetail 检测单实例的视频详情链路 /api/v1/videos/{video_id}。
func (c *Checker) checkVideoDetail(ctx context.Context, instanceURL, videoID string) VideoProbe {
	started := time.Now()
	probe := VideoProbe{URL: instanceURL, VideoID: videoID}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, instanceURL+"/api/v1/videos/"+videoID, nil)
	if err != nil {
		probe.Error = err.Error()
		return probe
	}
	resp, err := c.http.Do(req)
	probe.LatencyMS = time.Since(started).Milliseconds()
	if err != nil {
		probe.Error = err.Error()
		return probe
	}
	defer resp.Body.Close()
	probe.StatusCode = resp.StatusCode
	probe.Available = resp.StatusCode == http.StatusOK
	if !probe.Available {
		probe.Error = fmt.Sprintf("HTTP %d", resp.StatusCode)
	}
	return probe
}
