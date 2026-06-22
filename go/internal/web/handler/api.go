package handler

import (
	"context"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/lwhx/zhuimange/internal/model"
)

// ==================== 统一 JSON 响应 ====================

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func successResp(w http.ResponseWriter, data any, msg string) {
	writeJSON(w, http.StatusOK, map[string]any{
		"success": true,
		"message": msg,
		"data":    data,
	})
}

func errorResp(w http.ResponseWriter, status int, msg, code string) {
	writeJSON(w, status, map[string]any{
		"success": false,
		"error":   msg,
		"code":    code,
	})
}

// ==================== 搜索 API ====================

// searchAnime GET /api/search?q=
func (h *AppHandlers) searchAnime(w http.ResponseWriter, r *http.Request) {
	q := strings.TrimSpace(r.URL.Query().Get("q"))
	if len(q) < 2 {
		successResp(w, []any{}, "搜索词至少 2 个字符")
		return
	}
	if h.tmdb == nil {
		errorResp(w, http.StatusServiceUnavailable, "TMDB 未配置", "TMDB_UNAVAILABLE")
		return
	}
	results, err := h.tmdb.SearchAnime(r.Context(), q)
	if err != nil {
		slog.Warn("搜索动漫失败", "query", q, "error", err)
		successResp(w, []any{}, "搜索完成")
		return
	}
	successResp(w, results, "搜索成功")
}

// ==================== 添加动漫 API ====================

// addAnime POST /api/anime/add （从 TMDB 添加）
func (h *AppHandlers) addAnime(w http.ResponseWriter, r *http.Request) {
	var req struct {
		TMDBID int64 `json:"tmdb_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		errorResp(w, http.StatusBadRequest, "请求格式错误", "INVALID_BODY")
		return
	}
	if req.TMDBID == 0 {
		errorResp(w, http.StatusBadRequest, "缺少 tmdb_id", "MISSING_TMDB_ID")
		return
	}
	if h.tmdb == nil {
		errorResp(w, http.StatusServiceUnavailable, "TMDB 未配置", "TMDB_UNAVAILABLE")
		return
	}

	detail, err := h.tmdb.GetAnimeDetail(r.Context(), req.TMDBID)
	if err != nil || detail == nil {
		errorResp(w, http.StatusBadGateway, "获取动漫详情失败", "TMDB_ERROR")
		return
	}

	episodes, err := h.tmdb.GetAllEpisodes(r.Context(), req.TMDBID, detail.Seasons)
	if err != nil {
		slog.Warn("拉取集数失败", "tmdb_id", req.TMDBID, "error", err)
	}

	anime := &model.Anime{
		TMDBID:        &detail.TMDBID,
		TitleCN:       detail.TitleCN,
		TitleEN:       detail.TitleEN,
		PosterURL:     detail.PosterURL,
		Overview:      detail.Overview,
		AirDate:       detail.AirDate,
		TotalEpisodes: detail.TotalEpisodes,
		Status:        detail.Status,
	}
	created, err := h.store.CreateAnime(r.Context(), anime)
	if err != nil {
		errorResp(w, http.StatusConflict, "添加失败（可能已存在）", "DUPLICATE")
		return
	}

	if len(episodes) > 0 {
		eps := make([]model.Episode, 0, len(episodes))
		for _, e := range episodes {
			eps = append(eps, model.Episode{
				AnimeID:       created.ID,
				SeasonNumber:  e.SeasonNumber,
				EpisodeNumber: e.EpisodeNumber,
				AbsoluteNum:   e.AbsoluteNum,
				Title:         e.Title,
				Overview:      e.Overview,
				AirDate:       e.AirDate,
				StillPath:     e.StillPath,
			})
		}
		if _, err := h.store.AddEpisodes(r.Context(), eps); err != nil {
			slog.Warn("批量插入集数失败", "anime_id", created.ID, "error", err)
		}
	}

	successResp(w, map[string]any{"anime_id": created.ID}, "添加成功")
}

// addAnimeManual POST /api/anime/add_manual （手动添加）
func (h *AppHandlers) addAnimeManual(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Title         string   `json:"title"`
		TotalEpisodes int      `json:"total_episodes"`
		Aliases       []string `json:"aliases"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		errorResp(w, http.StatusBadRequest, "请求格式错误", "INVALID_BODY")
		return
	}
	if strings.TrimSpace(req.Title) == "" {
		errorResp(w, http.StatusBadRequest, "标题不能为空", "MISSING_TITLE")
		return
	}

	// 自动搜索封面：从 TMDB 匹配首个结果（与 Python 版 add_anime_manual 一致）
	posterURL := ""
	overview := ""
	if h.tmdb != nil {
		results, err := h.tmdb.SearchAnime(r.Context(), strings.TrimSpace(req.Title))
		if err == nil && len(results) > 0 {
			posterURL = results[0].PosterURL
			overview = results[0].Overview
		} else if err != nil {
			slog.Warn("手动添加自动搜索封面失败", "title", req.Title, "error", err)
		}
	}

	anime := &model.Anime{
		TitleCN:       strings.TrimSpace(req.Title),
		TotalEpisodes: req.TotalEpisodes,
		PosterURL:     posterURL,
		Overview:      overview,
	}
	created, err := h.store.CreateAnime(r.Context(), anime)
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "创建失败", "CREATE_ERROR")
		return
	}

	for _, alias := range req.Aliases {
		alias = strings.TrimSpace(alias)
		if alias != "" {
			if err := h.store.AddAlias(r.Context(), created.ID, alias); err != nil {
				slog.Warn("添加别名失败", "anime_id", created.ID, "alias", alias, "error", err)
			}
		}
	}

	// 按 total_episodes 自动创建集数记录（与 Python 版一致）
	if req.TotalEpisodes > 0 {
		eps := make([]model.Episode, 0, req.TotalEpisodes)
		for i := 1; i <= req.TotalEpisodes; i++ {
			eps = append(eps, model.Episode{
				AnimeID:       created.ID,
				SeasonNumber:  1,
				EpisodeNumber: i,
				AbsoluteNum:   i,
			})
		}
		if _, err := h.store.AddEpisodes(r.Context(), eps); err != nil {
			slog.Warn("批量插入集数失败", "anime_id", created.ID, "error", err)
		}
	}

	successResp(w, map[string]any{"anime_id": created.ID}, "添加成功")
}

// deleteAnime DELETE /api/anime/{id} 删除动漫（级联删除集数/源/别名）。
func (h *AppHandlers) deleteAnime(w http.ResponseWriter, r *http.Request) {
	id, ok := parseIDParam(w, r, "id")
	if !ok {
		return
	}
	anime, err := h.store.GetAnime(r.Context(), id)
	if err != nil || anime == nil {
		errorResp(w, http.StatusNotFound, "动漫不存在", "ANIME_NOT_FOUND")
		return
	}
	if err := h.store.DeleteAnime(r.Context(), id); err != nil {
		errorResp(w, http.StatusInternalServerError, "删除失败", "DELETE_ERROR")
		return
	}
	successResp(w, nil, "动漫删除成功")
}

// ==================== 进度 API ====================

// markWatched POST /api/anime/{id}/episode/{ep}/watch
func (h *AppHandlers) markWatched(w http.ResponseWriter, r *http.Request) {
	animeID, _ := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	epNum, _ := strconv.Atoi(chi.URLParam(r, "ep"))

	aired, err := h.store.EpisodeIsAired(r.Context(), animeID, epNum, time.Now().Format("2006-01-02"))
	if err == nil && !aired {
		errorResp(w, http.StatusBadRequest, "该集数尚未开播", "NOT_AIRED")
		return
	}

	episode, err := h.store.GetEpisodeByNum(r.Context(), animeID, epNum)
	if err != nil || episode == nil {
		errorResp(w, http.StatusNotFound, "集数不存在", "EP_NOT_FOUND")
		return
	}
	if err := h.store.SetEpisodeWatched(r.Context(), episode.ID, true); err != nil {
		errorResp(w, http.StatusInternalServerError, "更新失败", "UPDATE_ERROR")
		return
	}
	h.updateAnimeProgress(r.Context(), animeID)
	successResp(w, nil, "已标记为已看")
}

// markUnwatched POST /api/anime/{id}/episode/{ep}/unwatch
func (h *AppHandlers) markUnwatched(w http.ResponseWriter, r *http.Request) {
	animeID, _ := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	epNum, _ := strconv.Atoi(chi.URLParam(r, "ep"))

	episode, err := h.store.GetEpisodeByNum(r.Context(), animeID, epNum)
	if err != nil || episode == nil {
		errorResp(w, http.StatusNotFound, "集数不存在", "EP_NOT_FOUND")
		return
	}
	if err := h.store.SetEpisodeWatched(r.Context(), episode.ID, false); err != nil {
		errorResp(w, http.StatusInternalServerError, "更新失败", "UPDATE_ERROR")
		return
	}
	h.updateAnimeProgress(r.Context(), animeID)
	successResp(w, nil, "已标记为未看")
}

// updateProgress PUT /api/anime/{id}/progress
func (h *AppHandlers) updateProgress(w http.ResponseWriter, r *http.Request) {
	animeID, _ := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	var req struct {
		WatchedEp int `json:"watched_ep"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		errorResp(w, http.StatusBadRequest, "请求格式错误", "INVALID_BODY")
		return
	}
	if err := h.store.SetWatchedUpTo(r.Context(), animeID, req.WatchedEp); err != nil {
		errorResp(w, http.StatusInternalServerError, "更新失败", "UPDATE_ERROR")
		return
	}
	h.updateAnimeProgress(r.Context(), animeID)
	successResp(w, nil, "进度已更新")
}

// updateAnimeProgress 根据集数 watched 状态更新动漫的 watched_ep 计数。
func (h *AppHandlers) updateAnimeProgress(ctx context.Context, animeID int64) {
	_, watched, err := h.store.EpisodeStats(ctx, animeID)
	if err != nil {
		return
	}
	if err := h.store.UpdateAnime(ctx, animeID, map[string]any{"watched_ep": watched}); err != nil {
		slog.Warn("更新 watched_ep 计数失败", "anime_id", animeID, "watched", watched, "error", err)
	}
}

// ==================== 图片代理 ====================

var proxyWhitelistHosts = map[string]bool{
	"image.tmdb.org":  true,
	"img.youtube.com": true,
	"i.ytimg.com":     true,
	"lain.bgm.net":    true,
	"lain.bgm.tv":     true,
}

// proxyImage GET /api/proxy_image?url=
func (h *AppHandlers) proxyImage(w http.ResponseWriter, r *http.Request) {
	target := strings.TrimSpace(r.URL.Query().Get("url"))
	if target == "" {
		errorResp(w, http.StatusBadRequest, "缺少 url 参数", "MISSING_URL")
		return
	}
	parsed, err := url.Parse(target)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Hostname() == "" {
		errorResp(w, http.StatusBadRequest, "非法的图片地址", "INVALID_URL")
		return
	}
	hostname := strings.ToLower(parsed.Hostname())
	allowed := h.proxyAllowedHosts(r.Context())
	if !allowed[hostname] {
		errorResp(w, http.StatusForbidden, "该图片域名不在允许列表内", "HOST_NOT_ALLOWED")
		return
	}

	client := &http.Client{Timeout: 15 * time.Second, CheckRedirect: func(req *http.Request, via []*http.Request) error {
		// 重定向后重新校验 hostname（小写归一）和 scheme
		if req.URL.Scheme != "http" && req.URL.Scheme != "https" {
			return http.ErrUseLastResponse
		}
		if !allowed[strings.ToLower(req.URL.Hostname())] {
			return http.ErrUseLastResponse
		}
		return nil
	}}
	resp, err := client.Get(target)
	if err != nil {
		slog.Warn("图片代理失败", "url", target, "error", err)
		errorResp(w, http.StatusBadGateway, "图片代理请求失败", "PROXY_ERROR")
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		errorResp(w, http.StatusBadGateway, "图片代理请求失败", "PROXY_ERROR")
		return
	}
	contentType := resp.Header.Get("Content-Type")
	if !strings.HasPrefix(contentType, "image/") {
		errorResp(w, http.StatusUnsupportedMediaType, "非图片内容", "NOT_IMAGE")
		return
	}

	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Cache-Control", "public, max-age=86400")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	_, _ = io.Copy(w, io.LimitReader(resp.Body, 10<<20))
}

// proxyAllowedHosts 合并固定白名单与当前 Invidious 实例域名。
func (h *AppHandlers) proxyAllowedHosts(ctx context.Context) map[string]bool {
	hosts := make(map[string]bool, len(proxyWhitelistHosts)+3)
	for k := range proxyWhitelistHosts {
		hosts[k] = true
	}
	primaryURL, _ := h.store.GetSetting(ctx, "invidious_url", "")
	if u, err := url.Parse(primaryURL); err == nil && u.Hostname() != "" {
		hosts[u.Hostname()] = true
	}
	fallbacks, _ := h.store.GetSetting(ctx, "invidious_fallback_urls", "[]")
	var urls []string
	if err := json.Unmarshal([]byte(fallbacks), &urls); err == nil {
		for _, u := range urls {
			if parsed, err := url.Parse(u); err == nil && parsed.Hostname() != "" {
				hosts[parsed.Hostname()] = true
			}
		}
	}
	return hosts
}

