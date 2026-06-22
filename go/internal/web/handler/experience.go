package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// dashboardPage GET /dashboard 追更看板（进度卡片网格）。
func (h *AppHandlers) dashboardPage(w http.ResponseWriter, r *http.Request) {
	body := `
  <div class="page-header">
    <div><h1 class="page-header__title">🧭 追更看板</h1><p class="page-header__subtitle">追更进度一览 · 红色徽章表示该番剧有缺源集数</p></div>
    <div class="page-actions">
      <div class="dash-filters">
        <button class="dash-filter dash-filter--active" data-filter="all" onclick="setDashboardFilter('all')">全部</button>
        <button class="dash-filter" data-filter="missing" onclick="setDashboardFilter('missing')">⚠️ 只看缺源</button>
      </div>
      <button class="btn btn--primary" onclick="loadDashboard()">🔄 刷新</button>
    </div>
  </div>
  <div id="dash-root"></div>`
	renderStandalonePage(w, r, "追更看板", body, "", "dashboard.js")
}

// calendarPage GET /calendar 追更日历（月历网格视图）。
func (h *AppHandlers) calendarPage(w http.ResponseWriter, r *http.Request) {
	body := `
  <div class="page-header">
    <div><h1 class="page-header__title">📅 追更日历</h1><p class="page-header__subtitle">查看动漫开播日期 · 不同颜色代表不同番剧</p></div>
    <div class="page-actions">
      <div class="cal-nav">
        <button class="cal-nav__btn" onclick="prevMonth()" title="上一月">‹</button>
        <span class="cal-nav__title" id="cal-title">-</span>
        <button class="cal-nav__btn" onclick="nextMonth()" title="下一月">›</button>
        <button class="btn btn--secondary btn--sm" onclick="goToday()">今天</button>
      </div>
    </div>
  </div>
  <div class="cal-legend">
    <span class="cal-legend__item"><span class="cal-legend__dot cal-legend__dot--accent"></span> 今天</span>
    <span class="cal-legend__item"><span class="cal-legend__dot"></span> 有开播</span>
    <span class="cal-legend__item"><span class="cal-legend__dot cal-legend__dot--muted"></span> 无更新</span>
  </div>
  <div class="cal-grid" id="cal-grid"></div>`
	renderStandalonePage(w, r, "追更日历", body, "", "calendar.js")
}

// dashboardAPI GET /api/dashboard 返回看板数据。
func (h *AppHandlers) dashboardAPI(w http.ResponseWriter, r *http.Request) {
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	items, err := h.store.ListDashboardItems(r.Context(), limit)
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "查询看板失败", "DASHBOARD_ERROR")
		return
	}
	successResp(w, items, "查询成功")
}

// calendarAPI GET /api/calendar 返回追更日历数据。
func (h *AppHandlers) calendarAPI(w http.ResponseWriter, r *http.Request) {
	today := time.Now()
	start := r.URL.Query().Get("start")
	end := r.URL.Query().Get("end")
	if start == "" {
		start = today.AddDate(0, 0, -7).Format("2006-01-02")
	}
	if end == "" {
		end = today.AddDate(0, 0, 30).Format("2006-01-02")
	}
	items, err := h.store.ListCalendarItems(r.Context(), start, end)
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "查询日历失败", "CALENDAR_ERROR")
		return
	}
	successResp(w, map[string]any{"start": start, "end": end, "items": items}, "查询成功")
}

// favoritesAPI GET|POST /api/favorites 管理收藏夹。
func (h *AppHandlers) favoritesAPI(w http.ResponseWriter, r *http.Request) {
	if r.Method == http.MethodGet {
		items, err := h.store.ListFavorites(r.Context())
		if err != nil {
			errorResp(w, http.StatusInternalServerError, "查询收藏夹失败", "FAVORITES_ERROR")
			return
		}
		successResp(w, items, "查询成功")
		return
	}
	var payload struct {
		Name     string  `json:"name"`
		AnimeIDs []int64 `json:"anime_ids"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil || payload.Name == "" {
		errorResp(w, http.StatusBadRequest, "请求体格式错误", "BAD_REQUEST")
		return
	}
	encoded, _ := json.Marshal(payload.AnimeIDs)
	if err := h.store.CreateFavorite(r.Context(), payload.Name, string(encoded)); err != nil {
		errorResp(w, http.StatusInternalServerError, "创建收藏夹失败", "FAVORITES_ERROR")
		return
	}
	successResp(w, nil, "创建成功")
}

// feedXML GET /feed.xml 输出 RSS 2.0 订阅源（含完整字段，兼容主流阅读器）。
func (h *AppHandlers) feedXML(w http.ResponseWriter, r *http.Request) {
	items, _ := h.store.ListDashboardItems(r.Context(), 50)
	baseURL := schemeFromRequest(r) + "://" + r.Host
	now := time.Now().Format(time.RFC1123Z)

	w.Header().Set("Content-Type", "application/rss+xml; charset=utf-8")
	w.Header().Set("Cache-Control", "no-cache")
	_, _ = fmt.Fprintf(w, `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>追漫阁更新</title>
<link>%s/</link>
<description>追漫阁追更进度订阅</description>
<language>zh-CN</language>
<lastBuildDate>%s</lastBuildDate>`, baseURL, now)
	for _, item := range items {
		pct := 0
		if item.TotalEpisodes > 0 {
			pct = item.WatchedEp * 100 / item.TotalEpisodes
		}
		link := fmt.Sprintf("%s/anime/%d", baseURL, item.AnimeID)
		_, _ = fmt.Fprintf(w, `
<item>
<title>%s — 已看 %d/%d (%d%%)</title>
<link>%s</link>
<guid isPermaLink="true">%s</guid>
<description>已看 %d / %d 集，完成度 %d%%</description>
</item>`,
			htmlEscape(item.TitleCN), item.WatchedEp, item.TotalEpisodes, pct,
			link, link,
			item.WatchedEp, item.TotalEpisodes, pct)
	}
	_, _ = fmt.Fprint(w, "\n</channel></rss>")
}

// schemeFromRequest 推断 http/https scheme。
func schemeFromRequest(r *http.Request) string {
	if r.TLS != nil || r.Header.Get("X-Forwarded-Proto") == "https" {
		return "https"
	}
	return "http"
}

func htmlEscape(value string) string {
	replacer := strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;", `"`, "&quot;", "'", "&apos;")
	return replacer.Replace(value)
}

// manifestJSON GET /manifest.json 输出 PWA manifest。
func (h *AppHandlers) manifestJSON(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/manifest+json; charset=utf-8")
	_ = json.NewEncoder(w).Encode(map[string]any{"name": "追漫阁", "short_name": "追漫阁", "start_url": "/", "display": "standalone", "background_color": "#0f172a", "theme_color": "#0f172a"})
}
