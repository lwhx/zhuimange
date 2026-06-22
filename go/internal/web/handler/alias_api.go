package handler

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"

	"github.com/lwhx/zhuimange/internal/model"
)

// listAnimeAliases GET /api/anime/{id}/aliases 返回当前动漫的别名列表。
func (h *AppHandlers) listAnimeAliases(w http.ResponseWriter, r *http.Request) {
	animeID, _ := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	aliases, err := h.store.GetAliases(r.Context(), animeID)
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "读取别名失败", "ALIAS_QUERY_ERROR")
		return
	}
	successResp(w, map[string]any{"aliases": aliases}, "获取成功")
}

// updateAnimeAliases PUT /api/anime/{id}/aliases 保存当前动漫的别名列表。
func (h *AppHandlers) updateAnimeAliases(w http.ResponseWriter, r *http.Request) {
	animeID, _ := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	var req struct {
		Aliases []string `json:"aliases"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		errorResp(w, http.StatusBadRequest, "请求格式错误", "INVALID_BODY")
		return
	}
	for _, alias := range req.Aliases {
		alias = strings.TrimSpace(alias)
		if alias == "" {
			continue
		}
		if err := h.store.AddAlias(r.Context(), animeID, alias); err != nil {
			errorResp(w, http.StatusInternalServerError, "保存别名失败", "ALIAS_SAVE_ERROR")
			return
		}
	}
	successResp(w, nil, "别名已保存")
}

// updateSourceRules PUT /api/anime/{id}/rules 保存动漫的搜索规则（黑白名单关键词/频道）。
// 对齐 Python update_rules，字段：allow_keywords/deny_keywords/allow_channels/deny_channels（JSON 数组）。
func (h *AppHandlers) updateSourceRules(w http.ResponseWriter, r *http.Request) {
	id, ok := parseIDParam(w, r, "id")
	if !ok {
		return
	}
	anime, err := h.store.GetAnime(r.Context(), id)
	if err != nil || anime == nil {
		errorResp(w, http.StatusNotFound, "动漫不存在", "ANIME_NOT_FOUND")
		return
	}

	var req struct {
		AllowKeywords []string `json:"allow_keywords"`
		DenyKeywords  []string `json:"deny_keywords"`
		AllowChannels []string `json:"allow_channels"`
		DenyChannels  []string `json:"deny_channels"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		errorResp(w, http.StatusBadRequest, "请求格式错误", "INVALID_BODY")
		return
	}

	// 规范化：去空白、去空串
	trim := func(in []string) []string {
		out := make([]string, 0, len(in))
		for _, s := range in {
			if s = strings.TrimSpace(s); s != "" {
				out = append(out, s)
			}
		}
		return out
	}
	rule := &model.SourceRule{
		AnimeID:       id,
		AllowKeywords: trim(req.AllowKeywords),
		DenyKeywords:  trim(req.DenyKeywords),
		AllowChannels: trim(req.AllowChannels),
		DenyChannels:  trim(req.DenyChannels),
	}
	if err := h.store.UpsertSourceRule(r.Context(), rule); err != nil {
		errorResp(w, http.StatusInternalServerError, "保存规则失败", "RULE_SAVE_ERROR")
		return
	}
	successResp(w, nil, "搜索规则已保存")
}
