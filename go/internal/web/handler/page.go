package handler

import (
	"context"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/lwhx/zhuimange/internal/auth"
	"github.com/lwhx/zhuimange/internal/model"
	tmplpkg "github.com/lwhx/zhuimange/internal/web/template"
)

// indexData 首页渲染数据。
type indexData struct {
	Animes       []*animeCardView
	TotalCount   int
	TotalSources int
	Now          time.Time
}

// animeCardView 首页卡片视图（含计算字段）。
type animeCardView struct {
	*model.Anime
	UnwatchedCount int
	EpisodeCount   int
}

// animeDetailData 详情页渲染数据。
type animeDetailData struct {
	Anime        *model.Anime
	Episodes     []*model.Episode
	EpisodeCount int
	SourceCount  int
	IsHTTPS      bool
}

// index 首页：动漫卡片网格。
func (h *AppHandlers) index(w http.ResponseWriter, r *http.Request) {
	auth.IssueCSRFCookie(w)

	animes, err := h.store.ListAnimes(r.Context())
	if err != nil {
		http.Error(w, "加载列表失败", http.StatusInternalServerError)
		return
	}

	cards := make([]*animeCardView, 0, len(animes))
	totalSources := 0
	for _, a := range animes {
		epCount, _, _ := h.store.EpisodeStats(r.Context(), a.ID)
		unwatched := 0
		if epCount > a.WatchedEp {
			unwatched = epCount - a.WatchedEp
		}
		srcCount, _ := h.countAnimeSources(r.Context(), a.ID)
		totalSources += srcCount
		cards = append(cards, &animeCardView{
			Anime:          a,
			UnwatchedCount: unwatched,
			EpisodeCount:   epCount,
		})
	}

	renderPage(w, r, "index.html", &tmplpkg.RenderData{
		Title: "首页",
		Data: &indexData{
			Animes:       cards,
			TotalCount:   len(animes),
			TotalSources: totalSources,
			Now:          time.Now(),
		},
	})
}

// animeDetail 详情页。
func (h *AppHandlers) animeDetail(w http.ResponseWriter, r *http.Request) {
	auth.IssueCSRFCookie(w)

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

	episodes, _ := h.store.ListEpisodes(r.Context(), id)
	epCount, _, _ := h.store.EpisodeStats(r.Context(), id)
	srcCount, _ := h.countAnimeSources(r.Context(), id)

	renderPage(w, r, "anime_detail.html", &tmplpkg.RenderData{
		Title: anime.TitleCN,
		Data: &animeDetailData{
			Anime:        anime,
			Episodes:     episodes,
			EpisodeCount: epCount,
			SourceCount:  srcCount,
			IsHTTPS:      tmplpkg.IsHTTPSRequest(r),
		},
	})
}

// countAnimeSources 统计某动漫的全部视频源数（跨集）。
func (h *AppHandlers) countAnimeSources(ctx context.Context, animeID int64) (int, error) {
	var count int
	err := h.store.DB().QueryRowContext(ctx, `
		SELECT COUNT(*) FROM sources s
		JOIN episodes e ON s.episode_id = e.id
		WHERE e.anime_id = ?`, animeID).Scan(&count)
	return count, err
}

// episodeSources 视频源模态（HTMX 局部加载，返回 HTML 片段）。
func (h *AppHandlers) episodeSources(w http.ResponseWriter, r *http.Request) {
	animeID, _ := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	epNum, _ := strconv.Atoi(chi.URLParam(r, "ep"))

	episode, err := h.store.GetEpisodeByNum(r.Context(), animeID, epNum)
	if err != nil || episode == nil {
		w.WriteHeader(http.StatusNotFound)
		w.Write([]byte(`<div class="empty-state"><div class="empty-state__icon">⏳</div><div class="empty-state__title">该集数暂不可用</div><p>可能尚未开播</p></div>`))
		return
	}

	sources, _ := h.store.GetSourcesForEpisode(r.Context(), episode.ID)
	if sources == nil {
		sources = []*model.Source{}
	}

	data := struct {
		Sources []*model.Source
		EpNum   int
		IsHTTPS bool
	}{Sources: sources, EpNum: epNum, IsHTTPS: tmplpkg.IsHTTPSRequest(r)}

	// 直接渲染片段（不走 base 布局）
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	if err := globalTmplMgr.RenderPartial(w, "sources_modal.html", data); err != nil {
		http.Error(w, "渲染失败", http.StatusInternalServerError)
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
