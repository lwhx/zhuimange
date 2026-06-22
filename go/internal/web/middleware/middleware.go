// Package middleware 实现 HTTP 中间件：认证守卫、安全头、限流、请求日志。
package middleware

import (
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/lwhx/zhuimange/internal/auth"
)

// AuthMiddleware 强制认证，未登录的 API 请求返回 401，页面请求重定向到登录页。
// allowedPaths 是豁免认证的路径前缀（如 /login、/static、/health）。
func AuthMiddleware(a *auth.Authenticator, allowedPaths []string) func(http.Handler) http.Handler {
	allow := func(path string) bool {
		for _, p := range allowedPaths {
			if strings.HasPrefix(path, p) {
				return true
			}
		}
		return false
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// 豁免路径直接放行
			if allow(r.URL.Path) {
				next.ServeHTTP(w, r)
				return
			}
			// 精确匹配登录/登出
			if r.URL.Path == "/login" || r.URL.Path == "/logout" {
				next.ServeHTTP(w, r)
				return
			}

			session, err := a.ValidateRequest(r)
			if err != nil {
				if strings.HasPrefix(r.URL.Path, "/api/") {
					w.Header().Set("Content-Type", "application/json")
					w.WriteHeader(http.StatusUnauthorized)
					_, _ = w.Write([]byte(`{"error":"未登录或会话已过期","code":"UNAUTHORIZED"}`))
				} else {
					http.Redirect(w, r, "/login", http.StatusFound)
				}
				return
			}
			_ = session // 认证通过即可，session 数据当前 handler 未读取
			next.ServeHTTP(w, r)
		})
	}
}

// SecurityHeaders 设置安全响应头（与 Python 版 CSP 等价）。
func SecurityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		h := w.Header()
		h.Set("X-Content-Type-Options", "nosniff")
		h.Set("X-Frame-Options", "SAMEORIGIN")
		h.Set("X-XSS-Protection", "1; mode=block")
		// img-src 放宽：海报/缩略图来源含用户配置的 Invidious 实例（自部署，域名/IP 不固定）
		h.Set("Content-Security-Policy",
			"default-src 'self'; "+
				"img-src 'self' https: http: data:; "+
				"style-src 'self' 'unsafe-inline'; "+
				"script-src 'self' 'unsafe-inline'; "+
				"connect-src 'self'; "+
				"font-src 'self'; "+
				"form-action 'self'; "+
				"frame-ancestors 'none'")
		next.ServeHTTP(w, r)
	})
}

// RateLimiter 简单的内存滑动窗口限流器（按 IP）。
// 适用于个人项目，无需引入 Redis 等外部依赖。
type RateLimiter struct {
	mu       sync.Mutex
	visitors map[string]*bucket
	rate     int           // 时间窗口内最大请求数
	window   time.Duration // 时间窗口
}

type bucket struct {
	count    int
	startAt  time.Time // 当前窗口起点（不随请求漂移）
	lastSeen time.Time
}

// NewRateLimiter 创建限流器。rate 为窗口内允许的请求数，window 为窗口时长。
func NewRateLimiter(rate int, window time.Duration) *RateLimiter {
	rl := &RateLimiter{
		visitors: make(map[string]*bucket),
		rate:     rate,
		window:   window,
	}
	// 后台清理过期桶
	go rl.cleanup()
	return rl
}

// Allow 判断 IP 是否被允许（超出则返回 false）。
// 使用固定窗口起点：窗口从首次请求开始计时，窗口内累计计数；
// 窗口过期后才重置——避免每次请求更新起点导致窗口永不滚动。
func (rl *RateLimiter) Allow(ip string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	b, exists := rl.visitors[ip]
	// 窗口已过期（或首次）：重置为全新窗口
	if !exists || now.Sub(b.startAt) > rl.window {
		rl.visitors[ip] = &bucket{count: 1, startAt: now, lastSeen: now}
		return true
	}
	b.count++
	b.lastSeen = now
	return b.count <= rl.rate
}

func (rl *RateLimiter) cleanup() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()
	for range ticker.C {
		rl.mu.Lock()
		for ip, b := range rl.visitors {
			if time.Since(b.lastSeen) > rl.window {
				delete(rl.visitors, ip)
			}
		}
		rl.mu.Unlock()
	}
}

// RateLimitMiddleware 限流中间件工厂。
func RateLimitMiddleware(rl *RateLimiter) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			ip := clientIP(r)
			if !rl.Allow(ip) {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusTooManyRequests)
				_, _ = w.Write([]byte(`{"error":"请求过于频繁，请稍后再试","code":"RATE_LIMITED"}`))
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// clientIP 提取客户端 IP（优先 X-Forwarded-For，兼容反向代理）。
func clientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		if idx := strings.Index(xff, ","); idx > 0 {
			return strings.TrimSpace(xff[:idx])
		}
		return strings.TrimSpace(xff)
	}
	// 去掉端口
	if idx := strings.LastIndex(r.RemoteAddr, ":"); idx > 0 {
		return r.RemoteAddr[:idx]
	}
	return r.RemoteAddr
}
