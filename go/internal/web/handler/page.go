package handler

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/lwhx/zhuimange/internal/auth"
	"github.com/lwhx/zhuimange/internal/model"
	tmplpkg "github.com/lwhx/zhuimange/internal/web/template"
)

// indexData 首页渲染数据。
type indexData struct {
	Animes        []*animeCardView
	TotalCount    int
	TotalSources  int
	ContinuingCount int
	UnwatchedTotal  int
	Now           time.Time
}

// animeCardView 首页卡片视图（含计算字段）。
type animeCardView struct {
	*model.Anime
	UnwatchedCount int
	EpisodeCount   int
}

// animeDetailData 详情页渲染数据。
type animeDetailData struct {
	Anime          *model.Anime
	Episodes       []*model.Episode
	EpisodeCount   int
	SourceCount    int
	IsHTTPS        bool
	Aliases        []string
	Rules          *model.SourceRule
	NextEpisode    int // 下一集未看集号，0 表示已追完
	UnwatchedCount int
}

// index 首页：动漫卡片网格。
func (h *AppHandlers) index(w http.ResponseWriter, r *http.Request) {
	auth.IssueCSRFCookie(w, r)

	animes, err := h.store.ListAnimes(r.Context())
	if err != nil {
		http.Error(w, "加载列表失败", http.StatusInternalServerError)
		return
	}

	// 批量查询所有动漫的集数/源数（单次 JOIN，替代 N+1）
	cardStats, _ := h.store.ListAnimeCardStats(r.Context())

	cards := make([]*animeCardView, 0, len(animes))
	totalSources := 0
	continueCount := 0
	unwatchedTotal := 0
	for _, a := range animes {
		stats := cardStats[a.ID]
		epCount := stats.EpisodeCount
		unwatched := 0
		if epCount > a.WatchedEp {
			unwatched = epCount - a.WatchedEp
		}
		totalSources += stats.SourceCount
		unwatchedTotal += unwatched
		if a.Status == "Returning Series" || a.Status == "Continuing" {
			continueCount++
		}
		cards = append(cards, &animeCardView{
			Anime:          a,
			UnwatchedCount: unwatched,
			EpisodeCount:   epCount,
		})
	}

	renderPage(w, r, "index.html", &tmplpkg.RenderData{
		Title:     "首页",
		ActiveNav: "home",
		Data: &indexData{
			Animes:          cards,
			TotalCount:      len(animes),
			TotalSources:    totalSources,
			ContinuingCount: continueCount,
			UnwatchedTotal:  unwatchedTotal,
			Now:          time.Now(),
		},
	})
}

// animeDetail 详情页。
func (h *AppHandlers) animeDetail(w http.ResponseWriter, r *http.Request) {
	auth.IssueCSRFCookie(w, r)

	id, err := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	if err != nil {
		http.NotFound(w, r)
		return
	}

	anime, err := h.store.GetAnime(r.Context(), id)
	if err != nil || anime == nil {
		http.NotFound(w, r)
		return
	}

	// 集数可见性：手动添加（无 TMDB）全部可见；TMDB 作品仅显示已开播集数。
	// 与 Python 版 filter_aired_episodes 保持一致。
	today := time.Now().Format("2006-01-02")
	var episodes []*model.Episode
	if anime.IsManual() {
		episodes, _ = h.store.ListEpisodes(r.Context(), id)
	} else {
		episodes, _ = h.store.FilterAiredEpisodes(r.Context(), id, today)
	}
	epCount, watchedCount, _ := h.store.EpisodeStats(r.Context(), id)
	srcCount, _ := h.countAnimeSources(r.Context(), id)
	aliases, _ := h.store.GetAliases(r.Context(), id)
	rules, _ := h.store.GetSourceRule(r.Context(), id)
	// 保证 Rules 非 nil，避免模板访问 nil 指针
	if rules == nil {
		rules = &model.SourceRule{}
	}

	// 批量填充每集视频源数量（单次 GROUP BY，替代 N+1 循环）
	sourceCounts, _ := h.store.EpisodeSourceCounts(r.Context(), id)
	for _, ep := range episodes {
		ep.SourceCount = sourceCounts[ep.ID]
	}

	// 计算下一集未看 + 未看总数（在升序上遍历，保证取到最小未看集号）
	nextEpisode := 0
	unwatched := 0
	for _, ep := range episodes {
		if !ep.Watched {
			unwatched++
			if nextEpisode == 0 {
				nextEpisode = ep.AbsoluteNum
			}
		}
	}

	// 集数列表倒序排列（最新集在前），方便追更场景查看
	for i, j := 0, len(episodes)-1; i < j; i, j = i+1, j-1 {
		episodes[i], episodes[j] = episodes[j], episodes[i]
	}
	// 若 store 的 EpisodeStats 给出的 watchedCount 不可靠则用 epCount 兜底
	_ = watchedCount

	renderPage(w, r, "anime_detail.html", &tmplpkg.RenderData{
		Title:     anime.TitleCN,
		ActiveNav: "home",
		Data: &animeDetailData{
			Anime:          anime,
			Episodes:       episodes,
			EpisodeCount:   epCount,
			SourceCount:    srcCount,
			IsHTTPS:        tmplpkg.IsHTTPSRequest(r),
			Aliases:        aliases,
			Rules:          rules,
			NextEpisode:    nextEpisode,
			UnwatchedCount: unwatched,
		},
	})
}

// countAnimeSources 统计某动漫的全部视频源数（跨集），委托给 store。
func (h *AppHandlers) countAnimeSources(ctx context.Context, animeID int64) (int, error) {
	return h.store.CountAnimeSources(ctx, animeID)
}

// episodeSources 视频源模态（HTMX 局部加载，返回 HTML 片段）。
func (h *AppHandlers) episodeSources(w http.ResponseWriter, r *http.Request) {
	animeID, _ := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	epNum, _ := strconv.Atoi(chi.URLParam(r, "ep"))

	anime, _ := h.store.GetAnime(r.Context(), animeID)
	episode, err := h.store.GetEpisodeByNum(r.Context(), animeID, epNum)
	if err != nil || episode == nil {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte(`<div class="source-empty-state"><div class="source-empty-state__icon">⏳</div><div class="source-empty-state__title">该集数暂不可用</div><div class="source-empty-state__desc">可能尚未开播</div></div>`))
		return
	}

	// TMDB 作品未开播集数不可访问（与 Python episode_is_aired 一致）；手动作品全部可见
	if anime != nil && !anime.IsManual() {
		today := time.Now().Format("2006-01-02")
		if episode.AirDate != "" && episode.AirDate > today {
			w.WriteHeader(http.StatusNotFound)
			w.Write([]byte(`<div class="source-empty-state"><div class="source-empty-state__icon">⏳</div><div class="source-empty-state__title">该集数尚未开播</div><div class="source-empty-state__desc">首播日期 ` + episode.AirDate + `</div></div>`))
			return
		}
	}

	sources, _ := h.store.GetSourcesForEpisode(r.Context(), episode.ID)
	if sources == nil {
		sources = []*model.Source{}
	}

	animeTitle := ""
	if anime != nil {
		animeTitle = anime.TitleCN
	}

	data := struct {
		Sources    []*model.Source
		EpNum      int
		AnimeID    int64
		AnimeTitle string
		IsHTTPS    bool
	}{
		Sources:    sources,
		EpNum:      epNum,
		AnimeID:    animeID,
		AnimeTitle: animeTitle,
		IsHTTPS:    tmplpkg.IsHTTPSRequest(r),
	}

	// 直接渲染片段（不走 base 布局）
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := globalTmplMgr.RenderPartial(w, "sources_modal.html", data); err != nil {
		http.Error(w, "渲染失败", http.StatusInternalServerError)
	}
}

// notFoundHandler 渲染美观的 404 页面（API 路径返回 JSON）。
func (h *AppHandlers) notFoundHandler(w http.ResponseWriter, r *http.Request) {
	if strings.HasPrefix(r.URL.Path, "/api/") {
		errorResp(w, http.StatusNotFound, "资源不存在", "NOT_FOUND")
		return
	}
	renderErrorPage(w, r, http.StatusNotFound, "🔍", "页面不存在", "你访问的页面可能已被移除或地址有误")
}

// methodNotAllowedHandler 渲染 405 页面。
func (h *AppHandlers) methodNotAllowedHandler(w http.ResponseWriter, r *http.Request) {
	if strings.HasPrefix(r.URL.Path, "/api/") {
		errorResp(w, http.StatusMethodNotAllowed, "请求方法不被允许", "METHOD_NOT_ALLOWED")
		return
	}
	renderErrorPage(w, r, http.StatusMethodNotAllowed, "🚫", "请求方法不被允许", "该页面不支持当前的请求方式")
}

// renderErrorPage 渲染错误页（用 base 布局）。
func renderErrorPage(w http.ResponseWriter, r *http.Request, code int, icon, title, message string) {
	data := &tmplpkg.RenderData{
		Title: fmt.Sprintf("%d %s", code, title),
		Data: map[string]any{
			"Code":    fmt.Sprintf("%d", code),
			"Icon":    icon,
			"Title":   title,
			"Message": message,
		},
	}
	w.WriteHeader(code)
	if err := globalTmplMgr.RenderPage(w, "error.html", data); err != nil {
		http.Error(w, title, code)
	}
}

// renderPage 渲染完整页面（base 布局）。
func renderPage(w http.ResponseWriter, r *http.Request, page string, data *tmplpkg.RenderData) {
	data.IsHTTPS = tmplpkg.IsHTTPSRequest(r)
	if cookie, err := r.Cookie("zmg-theme"); err == nil && cookie.Value != "" {
		data.Theme = cookie.Value
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := globalTmplMgr.RenderPage(w, page, data); err != nil {
		http.Error(w, "渲染失败: "+err.Error(), http.StatusInternalServerError)
	}
}

// renderStandalonePage 渲染独立页面（不走 base.html 模板）。
// 用于统计/诊断/看板/日历等轻量页面，保证它们与主站共享主题系统、
// navbar 和主题下拉选择器（避免跨页面主题不一致）。
// activeNav 用于高亮当前页（home/dashboard/calendar/stats/diagnostics/settings）。
// extraScripts 为需要额外引入的 /static/*.js 文件名列表（按顺序加载）。
func renderStandalonePage(w http.ResponseWriter, r *http.Request, title, bodyHTML, scriptHTML, activeNav string, extraScripts ...string) {
	theme := "midnight"
	if cookie, err := r.Cookie("zmg-theme"); err == nil && cookie.Value != "" {
		theme = cookie.Value
	}
	scriptTags := ""
	for _, s := range extraScripts {
		if s == "" {
			continue
		}
		scriptTags += fmt.Sprintf(`<script src="/static/%s?v=2"></script>`, s)
	}
	navLink := func(href, icon, name, nav string) string {
		active := ""
		if nav == activeNav {
			active = " navbar__link--active"
		}
		return fmt.Sprintf(`<a href="%s" class="navbar__link%s">%s %s</a>`, href, active, icon, name)
	}
	navbar := `<nav class="navbar">` +
		`<a href="/" class="navbar__brand">📚 <span>追漫阁</span></a>` +
		`<div class="navbar__links">` +
		navLink("/", "🏠", "首页", "home") +
		navLink("/dashboard", "🧭", "看板", "dashboard") +
		navLink("/calendar", "🗓️", "日历", "calendar") +
		navLink("/stats", "📊", "统计", "stats") +
		navLink("/diagnostics", "🔧", "诊断", "diagnostics") +
		navLink("/settings", "⚙️", "设置", "settings") +
		`<div class="navbar__theme-selector">` +
		`<button type="button" class="navbar__theme-btn" onclick="toggleThemeDropdown()" title="切换主题">🎨</button>` +
		`<div class="theme-dropdown" id="theme-dropdown">` +
		`<div class="theme-dropdown__header"><span>🎨 配色方案</span><button type="button" class="theme-dropdown__close" onclick="toggleThemeDropdown()">&times;</button></div>` +
		`<div class="theme-dropdown__list">` +
		`<button type="button" class="theme-option" data-theme="midnight" onclick="setTheme('midnight')"><span class="theme-option__color" style="background:linear-gradient(135deg,#0b1120,#5b8cff)"></span><span class="theme-option__name">午夜蓝</span></button>` +
		`<button type="button" class="theme-option" data-theme="ocean" onclick="setTheme('ocean')"><span class="theme-option__color" style="background:linear-gradient(135deg,#08102f,#4a9eff)"></span><span class="theme-option__name">深海</span></button>` +
		`<button type="button" class="theme-option" data-theme="forest" onclick="setTheme('forest')"><span class="theme-option__color" style="background:linear-gradient(135deg,#0a1a12,#2dd4a0)"></span><span class="theme-option__name">森林</span></button>` +
		`<button type="button" class="theme-option" data-theme="sunset" onclick="setTheme('sunset')"><span class="theme-option__color" style="background:linear-gradient(135deg,#1a0a1a,#f0509e)"></span><span class="theme-option__name">日落</span></button>` +
		`<button type="button" class="theme-option" data-theme="light" onclick="setTheme('light')"><span class="theme-option__color" style="background:linear-gradient(135deg,#f1f4f9,#3b6eff)"></span><span class="theme-option__name">浅色</span></button>` +
		`</div></div></div>` +
		`<form method="POST" action="/logout" style="display:inline;">` +
		`<button type="submit" class="navbar__link navbar__link--muted" style="background:none;border:none;cursor:pointer;font:inherit;padding:8px 10px;">退出</button>` +
		`</form></div></nav>`

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	fmt.Fprintf(w, `<!doctype html>
<html lang="zh-CN" data-theme="%s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s - 追漫阁</title>
<link rel="stylesheet" href="/static/app.css?v=8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script>(function(){var s=localStorage.getItem('zmg-theme');if(s)document.documentElement.setAttribute('data-theme',s);})();</script>
</head>
<body>
%s
<main class="main-content fade-in">%s</main>
<div id="toast-container" class="toast-container"></div>
<script src="/static/common.js?v=3"></script>
<script src="/static/app.js?v=6"></script>
%s
<script>%s</script>
</body>
</html>`, theme, title, navbar, bodyHTML, scriptTags, scriptHTML)
}
