package handler

import (
	"net/http"
	"strings"

	"github.com/lwhx/zhuimange/internal/auth"
)

// loginPage 渲染登录页。
func (h *AppHandlers) loginPage(w http.ResponseWriter, r *http.Request) {
	if _, err := h.auth.ValidateRequest(r); err == nil {
		http.Redirect(w, r, "/", http.StatusFound)
		return
	}
	auth.IssueCSRFCookie(w, r)
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	errorBlock := ""
	switch r.URL.Query().Get("error") {
	case "1":
		errorBlock = `<div class="error">密码错误</div>`
	case "csrf":
		errorBlock = `<div class="error">会话已失效，请重新登录</div>`
	}
	page := strings.Replace(loginPageHTML, "{{ERROR_BLOCK}}", errorBlock, 1)
	_, _ = w.Write([]byte(page))
}

// loginSubmit 处理登录表单提交。
func (h *AppHandlers) loginSubmit(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseForm(); err != nil {
		http.Redirect(w, r, "/login?error=1", http.StatusFound)
		return
	}
	password := r.FormValue("password")
	if password == "" {
		http.Redirect(w, r, "/login?error=1", http.StatusFound)
		return
	}
	if err := h.auth.Login(r.Context(), w, r, password); err != nil {
		http.Redirect(w, r, "/login?error=1", http.StatusFound)
		return
	}
	http.Redirect(w, r, "/", http.StatusFound)
}

// logout 登出并重定向到登录页。改为 POST 防 CSRF 登出 DoS。
func (h *AppHandlers) logout(w http.ResponseWriter, r *http.Request) {
	h.auth.Logout(w, r)
	http.Redirect(w, r, "/login", http.StatusFound)
}

// health 健康检查端点。
func (h *AppHandlers) health(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

// loginPageHTML 登录页（独立样式，不依赖 base 布局）。
const loginPageHTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>登录 - 追漫阁</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, "Noto Sans SC", sans-serif; background: #0f172a; color: #e2e8f0; display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .login-card { background: #1e293b; padding: 40px; border-radius: 12px; width: 360px; box-shadow: 0 8px 32px rgba(0,0,0,0.3); }
  h1 { text-align: center; margin-bottom: 8px; font-size: 1.5rem; }
  .subtitle { text-align: center; color: #94a3b8; margin-bottom: 28px; font-size: 0.9rem; }
  .form-group { margin-bottom: 16px; }
  label { display: block; margin-bottom: 6px; font-size: 0.85rem; color: #cbd5e1; }
  input { width: 100%; padding: 10px 12px; background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #e2e8f0; font-size: 0.95rem; }
  input:focus { outline: none; border-color: #3b82f6; }
  .btn { width: 100%; padding: 11px; background: #3b82f6; color: white; border: none; border-radius: 6px; font-size: 1rem; cursor: pointer; margin-top: 8px; }
  .btn:hover { background: #2563eb; }
  .error { background: #7f1d1d; color: #fecaca; padding: 10px; border-radius: 6px; margin-bottom: 16px; font-size: 0.85rem; text-align: center; }
</style>
</head>
<body>
  <div class="login-card">
    <h1>📚 追漫阁</h1>
    <p class="subtitle">个人追更管理平台</p>{{ERROR_BLOCK}}
    <form method="POST" action="/login" onsubmit="return fillCsrfToken()">
      <input type="hidden" id="csrf_token" name="csrf_token" value="">
      <div class="form-group">
        <label>访问密码</label>
        <input type="password" name="password" placeholder="输入访问密码" autofocus>
      </div>
      <button type="submit" class="btn">登录</button>
    </form>
  </div>
<script>
function getCookie(name) {
  const value = '; ' + document.cookie;
  const parts = value.split('; ' + name + '=');
  if (parts.length === 2) return parts.pop().split(';').shift();
  return '';
}
function fillCsrfToken() {
  const token = getCookie('zmg_csrf');
  const el = document.getElementById('csrf_token');
  if (el) el.value = token;
  return true;
}
document.addEventListener('DOMContentLoaded', fillCsrfToken);
</script>
</body>
</html>`
