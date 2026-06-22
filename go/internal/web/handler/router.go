// Package handler 实现 HTTP 路由处理器。
package handler

import (
	"io/fs"
	"net/http"
	"os"
	"path/filepath"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"

	"github.com/lwhx/zhuimange/internal/auth"
	"github.com/lwhx/zhuimange/internal/backup"
	"github.com/lwhx/zhuimange/internal/config"
	"github.com/lwhx/zhuimange/internal/health"
	"github.com/lwhx/zhuimange/internal/invidious"
	"github.com/lwhx/zhuimange/internal/source"
	"github.com/lwhx/zhuimange/internal/store"
	"github.com/lwhx/zhuimange/internal/syncsvc"
	"github.com/lwhx/zhuimange/internal/tmdb"
	"github.com/lwhx/zhuimange/internal/web/middleware"
	tmplpkg "github.com/lwhx/zhuimange/internal/web/template"
	webassets "github.com/lwhx/zhuimange/web"
)

// AppHandlers 持有所有 handler 的共享依赖。
type AppHandlers struct {
	store         *store.Store
	auth          *auth.Authenticator
	config        *config.Config
	tmdb          *tmdb.Client
	invidious     *invidious.Client
	finder        *source.Finder
	syncQueue     *syncsvc.Queue
	healthChecker *health.Checker
	backupService *backup.Service
}

// globalTmplMgr 全局模板管理器（在 NewRouter 时初始化）。
var globalTmplMgr *tmplpkg.Manager

// NewRouter 创建并配置 HTTP 路由树。
func NewRouter(st *store.Store, a *auth.Authenticator, limiter *middleware.RateLimiter, cfg *config.Config) http.Handler {
	tmplDir := resolveTemplateDir()
	if tmplDir != "" {
		mgr, err := tmplpkg.New(tmplDir)
		if err != nil {
			panic("初始化模板管理器失败: " + err.Error())
		}
		globalTmplMgr = mgr
	} else {
		mgr, err := tmplpkg.NewFS(webassets.Templates)
		if err != nil {
			panic("初始化嵌入模板管理器失败: " + err.Error())
		}
		globalTmplMgr = mgr
	}

	tmdbClient := tmdb.New(cfg)
	invidiousClient := invidious.New(cfg, st)
	finder := source.NewFinder(cfg, st, invidiousClient)
	syncService := syncsvc.NewService(cfg, st, tmdbClient, finder)

	h := &AppHandlers{
		store:         st,
		auth:          a,
		config:        cfg,
		tmdb:          tmdbClient,
		invidious:     invidiousClient,
		finder:        finder,
		syncQueue:     syncsvc.NewQueue(st, syncService),
		healthChecker: health.NewChecker(st, invidiousClient),
		backupService: backup.NewService(st),
	}
	r := chi.NewRouter()

	r.Use(chimw.RequestID)
	r.Use(chimw.RealIP)
	r.Use(chimw.Recoverer) // panic 恢复 + 日志
	r.Use(chimw.Compress(5)) // gzip 压缩（CSS/JS/HTML/JSON）
	r.Use(middleware.SecurityHeaders)
	r.Use(middleware.RateLimitMiddleware(limiter))
	r.Use(auth.CSRFMiddleware)
	r.Use(middleware.AuthMiddleware(a, []string{"/static/", "/health", "/ready", "/metrics", "/api/health", "/api/proxy_image"}))

	r.Get("/login", h.loginPage)
	r.Post("/login", h.loginSubmit)
	r.Post("/logout", h.logout)

	r.Get("/api/search", h.searchAnime)
	r.Post("/api/anime/add", h.addAnime)
	r.Post("/api/anime/add_manual", h.addAnimeManual)
	r.Delete("/api/anime/{id}", h.deleteAnime)
	r.Post("/api/anime/{id}/aliases", h.updateAnimeAliases)
	r.Get("/api/anime/{id}/aliases", h.listAnimeAliases)
	r.Put("/api/anime/{id}/rules", h.updateSourceRules)
	r.Post("/api/anime/{id}/episode/{ep}/watch", h.markWatched)
	r.Post("/api/anime/{id}/episode/{ep}/unwatch", h.markUnwatched)
	r.Put("/api/anime/{id}/progress", h.updateProgress)
	r.Post("/api/anime/{id}/episode/{ep}/find_sources", h.findSources)
	r.Post("/api/anime/{id}/episode/{ep}/check_sources", h.checkEpisodeSources)
	r.Post("/api/anime/{id}/sync", h.enqueueSync)
	r.Get("/api/sync_tasks/{task_id}", h.syncTaskSnapshot)
	r.Get("/api/sync_tasks/{task_id}/stream", h.syncTaskStream)
	r.Get("/api/diagnostics/invidious", h.checkInvidiousDiagnostics)
	r.Post("/api/diagnostics/invidious", h.checkInvidiousDiagnostics)
	r.Post("/api/diagnostics/sources", h.checkSourcesDiagnostics)
	r.Get("/api/stats", h.statsSummary)
	r.Get("/api/dashboard", h.dashboardAPI)
	r.Get("/api/calendar", h.calendarAPI)
	r.Get("/api/favorites", h.favoritesAPI)
	r.Post("/api/favorites", h.favoritesAPI)
	r.Get("/api/proxy_image", h.proxyImage)
	r.Get("/api/settings", h.settingsAPI)
	r.Put("/api/settings", h.updateSettings)
	r.Post("/api/change_password", h.changePassword)
	r.Get("/api/backup/export", h.backupExport)
	r.Get("/api/backup/export_csv", h.backupExportCSV)
	r.Get("/api/backup/export_bangumi", h.backupExportBangumi)
	r.Post("/api/backup/import", h.backupImport)
	r.Post("/api/backup/telegram", h.backupTelegram)
	r.Post("/api/backup/local", h.backupLocal)
	r.Get("/api/backup/logs", h.backupLogs)
	r.Get("/api/backup/stats", h.backupStats)

	r.Get("/", h.index)
	r.Get("/anime/{id}", h.animeDetail)
	r.Get("/anime/{id}/episode/{ep}/sources", h.episodeSources)
	r.Get("/diagnostics", h.diagnosticsPage)
	r.Get("/stats", h.statsPage)
	r.Get("/dashboard", h.dashboardPage)
	r.Get("/calendar", h.calendarPage)
	r.Get("/settings", h.settingsPage)
	r.Get("/feed.xml", h.feedXML)
	r.Get("/manifest.json", h.manifestJSON)
	r.Get("/health", h.health)
	r.Get("/metrics", h.metricsEndpoint)
	r.Get("/ready", h.readyEndpoint)

	// 错误页：未匹配路由返回美观的 404 页面（API 路径返回 JSON）
	r.NotFound(h.notFoundHandler)
	r.MethodNotAllowed(h.methodNotAllowedHandler)

	// 静态资源：长缓存（配合 ?v= 指纹，安全上 immutable）
	staticCache := func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
			next.ServeHTTP(w, r)
		})
	}
	staticDir := resolveStaticDir()
	if staticDir != "" {
		fs := http.StripPrefix("/static/", http.FileServer(http.Dir(staticDir)))
		r.Handle("/static/*", staticCache(fs))
	} else {
		// embed FS 路径含 "static/" 前缀，用 fs.Sub 剥离后 FileServer 可正确查找
		staticSub, _ := fs.Sub(webassets.Static, "static")
		r.Handle("/static/*", staticCache(http.StripPrefix("/static/", http.FileServer(http.FS(staticSub)))))
	}

	return r
}

// resolveTemplateDir 解析模板目录。
func resolveTemplateDir() string {
	if _, err := os.Stat("web/templates"); err == nil {
		return "web/templates"
	}
	if cwd, err := os.Getwd(); err == nil {
		candidate := filepath.Join(cwd, "web", "templates")
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	return ""
}

// resolveStaticDir 解析静态资源目录。
func resolveStaticDir() string {
	if _, err := os.Stat("web/static"); err == nil {
		return "web/static"
	}
	if cwd, err := os.Getwd(); err == nil {
		candidate := filepath.Join(cwd, "web", "static")
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	return ""
}
