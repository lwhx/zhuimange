package auth

import (
	"crypto/rand"
	"encoding/hex"
	"net/http"
	"strings"
)

// csrfCookieName / csrfHeaderName 双重提交 cookie 模式的命名。
const (
	csrfCookieName = "zmg_csrf"
	csrfHeaderName = "X-CSRF-Token"
)

// CSRFMiddleware 验证写操作（POST/PUT/PATCH/DELETE）的 CSRF token。
// 兼容双重提交 cookie 模式：优先读取 header，其次读取表单字段 csrf_token。
// 对 /login POST 请求跳过检查，因为登录页本身是公开的，密码才是安全机制。
func CSRFMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// 仅写操作需要校验
		if !isWriteMethod(r.Method) {
			next.ServeHTTP(w, r)
			return
		}
		// 登录/登出请求跳过 CSRF 检查：
		// /login 是公开的，密码本身是安全机制；/logout 不涉及数据保护
		if r.Method == http.MethodPost && (r.URL.Path == "/login" || r.URL.Path == "/logout") {
			next.ServeHTTP(w, r)
			return
		}
		cookieToken, err := r.Cookie(csrfCookieName)
		if err != nil || cookieToken.Value == "" {
			respondCSRFError(w, r, http.StatusForbidden, "CSRF token 缺失", "CSRF_MISSING")
			return
		}
		headerToken := strings.TrimSpace(r.Header.Get(csrfHeaderName))
		if headerToken == "" {
			_ = r.ParseForm() // 必须先解析表单才能读取 FormValue
			headerToken = strings.TrimSpace(r.FormValue("csrf_token"))
		}
		if headerToken == "" || !hmacEqual(cookieToken.Value, headerToken) {
			respondCSRFError(w, r, http.StatusForbidden, "CSRF token 不匹配", "CSRF_MISMATCH")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func respondCSRFError(w http.ResponseWriter, r *http.Request, status int, msg, code string) {
	// 判断是否是 API 请求：检查 Content-Type 头或 X-Requested-With 头
	contentType := r.Header.Get("Content-Type")
	isXHR := r.Header.Get("X-Requested-With") == "XMLHttpRequest"
	isAPI := strings.Contains(contentType, "application/json") || isXHR || strings.HasPrefix(r.URL.Path, "/api/")

	if isAPI {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_, _ = w.Write([]byte(`{"error":"` + msg + `","code":"` + code + `"}`))
		return
	}
	// 页面请求：重定向回登录页
	http.Redirect(w, r, "/login?error=csrf", http.StatusFound)
}

// IssueCSRFCookie 生成并设置 CSRF token cookie。
// r 用于判断是否 HTTPS（设置 Secure 标志）。
func IssueCSRFCookie(w http.ResponseWriter, r *http.Request) {
	token := generateCSRFToken()
	http.SetCookie(w, &http.Cookie{
		Name:     csrfCookieName,
		Value:    token,
		Path:     "/",
		MaxAge:   3600 * 24,
		HttpOnly: false,    // 前端 JS 需读取
		Secure:   isSecureRequest(r),
		SameSite: http.SameSiteLaxMode,
	})
}

func isWriteMethod(method string) bool {
	switch strings.ToUpper(method) {
	case http.MethodPost, http.MethodPut, http.MethodPatch, http.MethodDelete:
		return true
	}
	return false
}

// hmacEqual 常量时间比较，防止时序攻击。
func hmacEqual(a, b string) bool {
	if len(a) != len(b) {
		return false
	}
	var result byte
	for i := 0; i < len(a); i++ {
		result |= a[i] ^ b[i]
	}
	return result == 0
}

// generateCSRFToken 生成 32 字节随机 token（hex 编码）。
func generateCSRFToken() string {
	b := make([]byte, 32)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}
