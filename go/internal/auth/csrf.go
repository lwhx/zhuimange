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
// 采用双重提交 cookie 模式：cookie 中的 token 必须与 header 中的 token 匹配。
func CSRFMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// 仅写操作需要校验
		if !isWriteMethod(r.Method) {
			next.ServeHTTP(w, r)
			return
		}
		cookieToken, err := r.Cookie(csrfCookieName)
		if err != nil || cookieToken.Value == "" {
			http.Error(w, `{"error":"缺少 CSRF token","code":"CSRF_MISSING"}`, http.StatusForbidden)
			return
		}
		headerToken := r.Header.Get(csrfHeaderName)
		if headerToken == "" || !hmacEqual(cookieToken.Value, headerToken) {
			http.Error(w, `{"error":"CSRF token 不匹配","code":"CSRF_MISMATCH"}`, http.StatusForbidden)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// IssueCSRFCookie 生成并设置 CSRF token cookie（每次 GET 请求刷新，供前端读取）。
func IssueCSRFCookie(w http.ResponseWriter) {
	token := generateCSRFToken()
	http.SetCookie(w, &http.Cookie{
		Name:     csrfCookieName,
		Value:    token,
		Path:     "/",
		MaxAge:   3600 * 24,
		HttpOnly: false, // 前端 JS 需读取
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
