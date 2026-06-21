package handler

import (
	"html/template"
	"net/http"

	"github.com/lwhx/zhuimange/internal/auth"
	"github.com/lwhx/zhuimange/internal/web/middleware"
)

// loginPage 渲染登录页。GET 请求发放 CSRF token cookie。
func (h *AppHandlers) loginPage(w http.ResponseWriter, r *http.Request) {
	// 已登录则跳转首页
	if _, err := h.auth.ValidateRequest(r); err == nil {
		http.Redirect(w, r, "/", http.StatusFound)
		return
	}

	auth.IssueCSRFCookie(w)

	tmpl := template.Must(template.New("login").Parse(loginTemplateHTML))
	errParam := r.URL.Query().Get("error")
	errMsg := ""
	if errParam == "1" {
		errMsg = "密码错误"
	}
	_ = tmpl.Execute(w, map[string]string{
		"Error": errMsg,
	})
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

	if err := h.auth.Login(r.Context(), w, password); err != nil {
		http.Redirect(w, r, "/login?error=1", http.StatusFound)
		return
	}
	http.Redirect(w, r, "/", http.StatusFound)
}

// logout 登出并重定向到登录页。
func (h *AppHandlers) logout(w http.ResponseWriter, r *http.Request) {
	h.auth.Logout(w)
	http.Redirect(w, r, "/login", http.StatusFound)
}

// index 首页（阶段 1 占位，阶段 2 实现完整列表）。
func (h *AppHandlers) index(w http.ResponseWriter, r *http.Request) {
	// 发放/刷新 CSRF token
	auth.IssueCSRFCookie(w)

	session := middleware.SessionFromContext(r.Context())
	user := "访客"
	if session != nil {
		user = "已登录"
	}

	tmpl := template.Must(template.New("index").Parse(indexTemplateHTML))
	_ = tmpl.Execute(w, map[string]string{
		"User": user,
	})
}

// health 健康检查端点。
func (h *AppHandlers) health(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

// loginTemplateHTML 登录页内联模板（阶段 1 简化版，阶段 2 迁移完整样式）。
const loginTemplateHTML = `<!DOCTYPE html>
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
    <p class="subtitle">个人追更管理平台</p>
    {{if .Error}}<div class="error">{{.Error}}</div>{{end}}
    <form method="POST" action="/login">
      <div class="form-group">
        <label>访问密码</label>
        <input type="password" name="password" placeholder="输入访问密码" autofocus>
      </div>
      <button type="submit" class="btn">登录</button>
    </form>
  </div>
</body>
</html>`

// indexTemplateHTML 首页占位模板（阶段 2 实现完整卡片网格）。
const indexTemplateHTML = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>追漫阁 - 首页</title>
<style>
  body { font-family: -apple-system, "Noto Sans SC", sans-serif; background: #0f172a; color: #e2e8f0; padding: 40px; }
  .card { background: #1e293b; padding: 30px; border-radius: 12px; max-width: 600px; margin: 40px auto; }
  h1 { margin-bottom: 16px; }
  .status { color: #4ade80; }
  .info { color: #94a3b8; margin-top: 12px; line-height: 1.6; }
</style>
</head>
<body>
  <div class="card">
    <h1>📚 追漫阁 Go 版</h1>
    <p>状态：<span class="status">{{.User}}</span> ✅</p>
    <div class="info">
      阶段 1 地基已完成：配置加载、数据库初始化、认证守卫、CSRF 防护、安全头。<br>
      后续阶段将实现完整功能：动漫列表、详情、同步引擎、追更日历等。
    </div>
  </div>
</body>
</html>`
