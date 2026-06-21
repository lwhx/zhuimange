// Package handler 实现 HTTP 路由处理器。
//
// 阶段 1 只实现登录/登出与认证守卫，后续阶段逐步补充其他页面与 API。
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
	"github.com/lwhx/zhuimange/internal/web/middleware"
)

// AppHandlers 持有所有 handler 的共享依赖。
type AppHandlers struct {
	store  *store.Store
	auth   *auth.Authenticator
	config *config.Config
}

// NewRouter 创建并配置 HTTP 路由树。
func NewRouter(st *store.Store, a *auth.Authenticator, limiter *middleware.RateLimiter, cfg *config.Config) http.Handler {
	h := &AppHandlers{store: st, auth: a, config: cfg}
	r := chi.NewRouter()

	// 全局中间件（必须在注册任何路由之前 Use）
	r.Use(chimw.RequestID)
	r.Use(chimw.RealIP)
	r.Use(middleware.SecurityHeaders)
	r.Use(middleware.RateLimitMiddleware(limiter))
	// CSRF 保护（登录提交等写操作需要）
	r.Use(auth.CSRFMiddleware)
	// 认证守卫：豁免登录/静态/健康检查
	r.Use(middleware.AuthMiddleware(a, []string{"/static/", "/health", "/ready", "/api/health", "/api/proxy_image"}))

	// 公开路由
	r.Get("/login", h.loginPage)
	r.Post("/login", h.loginSubmit)
	r.Get("/logout", h.logout)

	// 受保护路由（需登录）
	r.Get("/", h.index)
	r.Get("/health", h.health)

	// 静态文件服务（CSS/JS/字体）—— 认证中间件已豁免 /static/ 前缀
	staticDir := resolveStaticDir()
	if staticDir != "" {
		fs := http.StripPrefix("/static/", http.FileServer(http.Dir(staticDir)))
		r.Handle("/static/*", fs)
	}

	return r
}

// resolveStaticDir 解析静态资源目录（兼容 go run 开发模式与编译后运行）。
func resolveStaticDir() string {
	// 开发模式：go/ 目录下的 web/static
	if _, err := os.Stat("web/static"); err == nil {
		return "web/static"
	}
	// 编译后：二进制同级 web/static
	if cwd, err := os.Getwd(); err == nil {
		candidate := filepath.Join(cwd, "web", "static")
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	return ""
}
