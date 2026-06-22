package handler

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
)

// findSources POST /api/anime/{id}/episode/{ep}/find_sources 主动搜索单集视频源。
func (h *AppHandlers) findSources(w http.ResponseWriter, r *http.Request) {
	animeID, ok := parseIDParam(w, r, "id")
	if !ok {
		return
	}
	epNum, ok := parseEpisodeParam(w, r)
	if !ok {
		return
	}

	force := false
	var payload struct {
		Force bool `json:"force"`
	}
	_ = json.NewDecoder(r.Body).Decode(&payload)
	force = payload.Force

	sources, err := h.finder.FindSourcesForEpisode(r.Context(), animeID, epNum, force)
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "搜索失败: "+err.Error(), "FIND_SOURCES_ERROR")
		return
	}
	successResp(w, map[string]any{"count": len(sources)}, "找到 "+strconv.Itoa(len(sources))+" 个视频源")
}

// checkEpisodeSources POST /api/anime/{id}/episode/{ep}/check_sources 检测单集视频源健康。
func (h *AppHandlers) checkEpisodeSources(w http.ResponseWriter, r *http.Request) {
	animeID, ok := parseIDParam(w, r, "id")
	if !ok {
		return
	}
	epNum, ok := parseEpisodeParam(w, r)
	if !ok {
		return
	}

	episode, err := h.store.GetEpisodeByNum(r.Context(), animeID, epNum)
	if err != nil || episode == nil {
		errorResp(w, http.StatusNotFound, "集数不存在", "EPISODE_NOT_FOUND")
		return
	}
	sources, err := h.store.GetSourcesForEpisode(r.Context(), episode.ID)
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "查询视频源失败", "SOURCE_QUERY_ERROR")
		return
	}

	results := make([]map[string]any, 0, len(sources))
	summary := map[string]int{"available": 0, "error": 0, "unknown": 0}
	for _, src := range sources {
		result := h.healthChecker.CheckSourceHealth(r.Context(), src.ID, src.VideoID)
		status, _ := result["health_status"].(string)
		if _, exists := summary[status]; !exists {
			status = "unknown"
		}
		summary[status]++
		results = append(results, result)
	}
	successResp(w, map[string]any{
		"checked": len(results),
		"summary": summary,
		"sources": results,
	}, "检测完成")
}

// metricsEndpoint GET /metrics 简化版 Prometheus 指标端点。
// 若配置了 METRICS_TOKEN，需通过 ?token= 或 X-Metrics-Token 头校验。
func (h *AppHandlers) metricsEndpoint(w http.ResponseWriter, r *http.Request) {
	// token 校验（若配置了 MetricsToken）
	if h.config.MetricsToken != "" {
		token := r.URL.Query().Get("token")
		if token == "" {
			token = r.Header.Get("X-Metrics-Token")
		}
		if token != h.config.MetricsToken {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
	}
	w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
	// 基础进程指标
	stats, _ := h.store.GetStatsSummary(r.Context())
	animeCount := 0
	if stats != nil {
		animeCount = stats.AnimeCount
	}
	body := "# HELP zhuimange_animes_total 追踪的动漫总数\n" +
		"# TYPE zhuimange_animes_total gauge\n" +
		"zhuimange_animes_total " + strconv.Itoa(animeCount) + "\n"
	_, _ = w.Write([]byte(body))
}

// readyEndpoint GET /ready 就绪探针，校验数据库与 Invidious 连通性。
func (h *AppHandlers) readyEndpoint(w http.ResponseWriter, r *http.Request) {
	checks := map[string]bool{"database": false, "invidious": false}

	// 数据库检查（执行一次轻量查询）
	if _, err := h.store.GetAllSettings(r.Context()); err == nil {
		checks["database"] = true
	}
	// Invidious 检查（test_connection，失败不致命）
	if h.invidious.TestConnection(r.Context()) {
		checks["invidious"] = true
	}

	allReady := checks["database"] // 仅要求数据库就绪即可服务
	status := "ready"
	code := http.StatusOK
	if !allReady {
		status = "not_ready"
		code = http.StatusServiceUnavailable
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]any{"status": status, "checks": checks})
}

// parseIDParam 解析路由参数 {id} 为 int64，失败返回 400。
func parseIDParam(w http.ResponseWriter, r *http.Request, name string) (int64, bool) {
	raw := chi.URLParam(r, name)
	id, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || id <= 0 {
		errorResp(w, http.StatusBadRequest, "无效的 ID 参数", "BAD_REQUEST")
		return 0, false
	}
	return id, true
}

// parseEpisodeParam 解析路由参数 {ep} 为 int，失败返回 400。
func parseEpisodeParam(w http.ResponseWriter, r *http.Request) (int, bool) {
	raw := chi.URLParam(r, "ep")
	ep, err := strconv.Atoi(raw)
	if err != nil || ep <= 0 {
		errorResp(w, http.StatusBadRequest, "无效的集数参数", "BAD_REQUEST")
		return 0, false
	}
	return ep, true
}
