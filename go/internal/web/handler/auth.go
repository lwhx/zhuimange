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

// loginPageHTML 登录页（引用主题系统 + app.css，与主站视觉统一）。
const loginPageHTML = `<!DOCTYPE html>
<html lang="zh-CN" data-theme="midnight">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>登录 - 追漫阁</title>
<link rel="stylesheet" href="/static/app.css?v=8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script>(function(){var s=localStorage.getItem('zmg-theme');if(s)document.documentElement.setAttribute('data-theme',s);})();</script>
<style>
  body {
    display: flex; align-items: center; justify-content: center; min-height: 100vh;
    background: var(--bg-primary); position: relative; overflow: hidden;
  }
  body::before {
    content: ''; position: absolute; top: -20%; left: -10%; width: 60%; height: 60%;
    background: radial-gradient(circle, var(--accent-glow) 0%, transparent 70%);
    filter: blur(60px); pointer-events: none;
  }
  body::after {
    content: ''; position: absolute; bottom: -20%; right: -10%; width: 50%; height: 50%;
    background: radial-gradient(circle, rgba(139,92,246,0.15) 0%, transparent 70%);
    filter: blur(60px); pointer-events: none;
  }
  .login-card {
    position: relative; z-index: 1;
    background: var(--glass-bg); backdrop-filter: blur(20px) saturate(180%);
    -webkit-backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid var(--glass-border);
    padding: 44px 36px; border-radius: var(--radius-lg); width: 380px;
    box-shadow: var(--shadow-lg);
    animation: fadeInUp 0.5s ease;
  }
  .login-card h1 {
    text-align: center; margin-bottom: 6px; font-size: 1.6rem; font-weight: 800;
    letter-spacing: -0.02em;
  }
  .login-card h1 span {
    background: var(--gradient-accent); -webkit-background-clip: text;
    background-clip: text; -webkit-text-fill-color: transparent;
  }
  .login-card .subtitle {
    text-align: center; color: var(--text-muted); margin-bottom: 32px; font-size: 0.9rem;
  }
  .login-card .form-group { margin-bottom: 18px; }
  .login-card label {
    display: block; margin-bottom: 8px; font-size: 0.85rem;
    color: var(--text-secondary); font-weight: 500;
  }
  .login-card input {
    width: 100%; padding: 12px 16px; font-size: 0.95rem;
    background: var(--bg-input); border: 1px solid var(--border-color);
    border-radius: var(--radius-sm); color: var(--text-primary);
    transition: all var(--transition-fast);
  }
  .login-card input:focus {
    outline: none; border-color: var(--accent);
    box-shadow: 0 0 0 4px var(--accent-soft);
  }
  .login-card .btn {
    width: 100%; padding: 13px; font-size: 1rem; font-weight: 700;
    background: var(--gradient-accent); color: white; border: none;
    border-radius: var(--radius-sm); cursor: pointer; margin-top: 8px;
    box-shadow: 0 4px 14px var(--accent-glow);
    transition: all var(--transition-fast);
  }
  .login-card .btn:hover {
    box-shadow: 0 6px 22px var(--accent-glow);
    transform: translateY(-1px);
  }
  .login-card .btn:active { transform: scale(0.97); }
  .login-card .error {
    background: rgba(239,68,68,0.15); color: var(--danger);
    border: 1px solid rgba(239,68,68,0.3);
    padding: 12px 16px; border-radius: var(--radius-sm);
    margin-bottom: 18px; font-size: 0.85rem; text-align: center;
  }
</style>
</head>
<body>
  <div class="login-card">
    <h1>📚 <span>追漫阁</span></h1>
    <p class="subtitle">个人追更管理平台</p>{{ERROR_BLOCK}}
    <form method="POST" action="/login" onsubmit="return fillCsrfToken()">
      <input type="hidden" id="csrf_token" name="csrf_token" value="">
      <div class="form-group">
        <label>访问密码</label>
        <input type="password" name="password" placeholder="输入访问密码" autofocus>
      </div>
      <button type="submit" class="btn">登 录</button>
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
