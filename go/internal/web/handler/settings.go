package handler

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"strings"

	tmplpkg "github.com/lwhx/zhuimange/internal/web/template"
)

// settingsWhitelist 允许通过 /api/settings 写入的字段。
// 敏感字段（如 auth_password）必须走专用接口，防止绕过旧密码校验。
var settingsWhitelist = map[string]bool{
	"auto_sync_enabled":          true,
	"auto_sync_interval":         true,
	"match_threshold":            true,
	"match_recommend_threshold":  true,
	"invidious_url":              true,
	"invidious_fallback_urls":    true,
	"invidious_instance_weights": true,
	"tmdb_api_key":               true,
	"tg_bot_token":               true,
	"tg_chat_id":                 true,
	"tg_notify_enabled":          true,
	"tg_backup_enabled":          true,
	"tg_backup_interval_days":    true,
	"episode_sort_order":         true,
}

// settingsPage GET /settings 渲染设置页（模板化页面）。
func (h *AppHandlers) settingsPage(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	renderPage(w, r, "settings.html", &tmplpkg.RenderData{Title: "设置"})
}

// settingsAPI GET /api/settings 返回全部设置（敏感字段脱敏）。
func (h *AppHandlers) settingsAPI(w http.ResponseWriter, r *http.Request) {
	settings, err := h.store.GetAllSettings(r.Context())
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "读取设置失败", "SETTINGS_ERROR")
		return
	}
	if settings == nil {
		settings = map[string]string{}
	}
	delete(settings, "auth_password") // 脱敏
	// 敏感密钥脱敏：保留是否已配置的信息，不返回明文值（防 XSS/共享浏览器泄露）
	for _, key := range []string{"tg_bot_token", "tmdb_api_key"} {
		if v, ok := settings[key]; ok && v != "" {
			settings[key] = "********" // 前端显示 ******** 表示已配置
		}
	}
	successResp(w, settings, "获取设置成功")
}

// updateSettings PUT /api/settings 更新设置（白名单字段）。
func (h *AppHandlers) updateSettings(w http.ResponseWriter, r *http.Request) {
	var payload map[string]any
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		errorResp(w, http.StatusBadRequest, "请求体格式错误", "BAD_REQUEST")
		return
	}

	applied := map[string]string{}
	ignored := []string{}
	refreshInvidious := false
	refreshTMDB := false
	for key, value := range payload {
		if !settingsWhitelist[key] {
			ignored = append(ignored, key)
			continue
		}
		strVal := stringifySetting(value)
		// 脱敏占位符：用户未修改密钥时提交 ********，跳过不覆盖原值
		if strVal == "********" && (key == "tg_bot_token" || key == "tmdb_api_key") {
			continue
		}
		if err := h.store.SetSetting(r.Context(), key, strVal); err != nil {
			errorResp(w, http.StatusInternalServerError, "保存设置失败", "SETTINGS_ERROR")
			return
		}
		applied[key] = strVal
		if key == "invidious_url" || key == "invidious_fallback_urls" || key == "invidious_instance_weights" {
			refreshInvidious = true
		}
		if key == "tmdb_api_key" {
			refreshTMDB = true
		}
	}

	if refreshInvidious && h.invidious != nil {
		if err := h.invidious.RefreshInstances(r.Context()); err != nil {
			slog.Warn("刷新 Invidious 实例配置失败", "error", err)
		}
	}
	if refreshTMDB && h.tmdb != nil {
		h.tmdb.SetAPIKey(applied["tmdb_api_key"])
	}

	successResp(w, map[string]any{"applied": applied, "ignored": ignored}, "设置已保存")
}

// changePassword POST /api/change_password 修改访问密码。
func (h *AppHandlers) changePassword(w http.ResponseWriter, r *http.Request) {
	var payload struct {
		OldPassword string `json:"old_password"`
		NewPassword string `json:"new_password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		errorResp(w, http.StatusBadRequest, "请求体格式错误", "BAD_REQUEST")
		return
	}
	if payload.OldPassword == "" || payload.NewPassword == "" {
		errorResp(w, http.StatusBadRequest, "请填写完整", "BAD_REQUEST")
		return
	}
	if len(payload.NewPassword) < 8 {
		errorResp(w, http.StatusBadRequest, "新密码至少 8 位", "PASSWORD_TOO_SHORT")
		return
	}

	if err := h.auth.ChangePassword(r.Context(), payload.OldPassword, payload.NewPassword); err != nil {
		if err.Error() == "当前密码错误" {
			errorResp(w, http.StatusBadRequest, "当前密码错误", "INVALID_PASSWORD")
			return
		}
		errorResp(w, http.StatusInternalServerError, "修改密码失败", "PASSWORD_ERROR")
		return
	}
	successResp(w, nil, "密码修改成功")
}

// stringifySetting 将设置值统一转为字符串（兼容 JSON 数字/布尔）。
func stringifySetting(value any) string {
	switch v := value.(type) {
	case string:
		return v
	case bool:
		if v {
			return "true"
		}
		return "false"
	case float64:
		if v == float64(int64(v)) {
			return formatInt(int64(v))
		}
		return formatFloat(v)
	case nil:
		return ""
	default:
		bytes, err := json.Marshal(v)
		if err != nil {
			return ""
		}
		return strings.TrimSpace(string(bytes))
	}
}

// formatInt 整数转字符串（不引入 strconv 保持文件依赖精简）。
func formatInt(v int64) string {
	if v == 0 {
		return "0"
	}
	neg := v < 0
	if neg {
		v = -v
	}
	var buf [20]byte
	i := len(buf)
	for v > 0 {
		i--
		buf[i] = byte('0' + v%10)
		v /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}

// formatFloat 浮点数转字符串。
func formatFloat(v float64) string {
	bytes, _ := json.Marshal(v)
	return string(bytes)
}
