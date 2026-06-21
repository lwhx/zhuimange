// Package handler 实现 HTTP 路由处理器。
package handler

import (
	"net/http"
	"os"
	"path/filepath"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"

	"github.com/lwhx/zhuimange/internal/auth"
	"github.com/lwhx/zhuimange/internal/config"
	"github.com/lwhx/zhuimange/internal/store"
	"github.com/lwhx/zhuimange/internal/tmdb"
	tmplpkg "github.com/lwhx/zhuimange/internal/web/template"
	"github.com/lwhx/zhuimange/internal/web/middleware"
)

// AppHandlers 持有所有 handler 的共享依赖。
type AppHandlers struct {
	store  *store.Store
	auth   *auth.Authenticator
	config *config.Config
	tmdb   *tmdb.Client
}

// globalTmplMgr 全局模板管理器（在 NewRouter 时初始化）。
var globalTmplMgr *tmplpkg.Manager

// NewRouter 创建并配置 HTTP 路由树。
func NewRouter(st *store.Store, a *auth.Authenticator, limiter *middleware.RateLimiter, cfg *config.Config) http.Handler {
	// 初始化模板管理器
	tmplDir := resolveTemplateDir()
	if tmplDir != "" {
		mgr, err := tmplpkg.New(tmplDir)
		if err != nil {
			panic("初始化模板管理器失败: " + err.Error())
		}
		globalTmplMgr = mgr
	}

	h := &AppHandlers{
		store:  st,
		auth:   a,
		config: cfg,
		tmdb:   tmdb.New(cfg),
	}
	r := chi.NewRouter()

	// 全局中间件（必须在注册任何路由之前 Use）
	r.Use(chimw.RequestID)
	r.Use(chimw.RealIP)
	r.Use(middleware.SecurityHeaders)
	r.Use(middleware.RateLimitMiddleware(limiter))
	r.Use(auth.CSRFMiddleware)
	r.Use(middleware.AuthMiddleware(a, []string{"/static/", "/health", "/ready", "/api/health", "/api/proxy_image"}))

	// 公开路由
	r.Get("/login", h.loginPage)
	r.Post("/login", h.loginSubmit)
	r.Get("/logout", h.logout)

	// API 路由
	r.Get("/api/search", h.searchAnime)
	r.Post("/api/anime/add", h.addAnime)
	r.Post("/api/anime/add_manual", h.addAnimeManual)
	r.Post("/api/anime/{id}/episode/{ep}/watch", h.markWatched)
	r.Post("/api/anime/{id}/episode/{ep}/unwatch", h.markUnwatched)
	r.Put("/api/anime/{id}/progress", h.updateProgress)
	r.Get("/api/proxy_image", h.proxyImage)

	// 页面路由
	r.Get("/", h.index)
	r.Get("/anime/{id}", h.animeDetail)
	r.Get("/anime/{id}/episode/{ep}/sources", h.episodeSources)
	r.Get("/health", h.health)

	// 静态文件
	staticDir := resolveStaticDir()
	if staticDir != "" {
		fs := http.StripPrefix("/static/", http.FileServer(http.Dir(staticDir)))
		r.Handle("/static/*", fs)
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
