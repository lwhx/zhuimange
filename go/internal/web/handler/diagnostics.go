package handler

import (
	"encoding/json"
	"net/http"
	"strconv"
)

// checkInvidiousDiagnostics GET|POST /api/diagnostics/invidious 检测 Invidious 实例健康。
// 支持 ?video_id= 或 body.video_id 自定义探针视频（对齐 Python）。
func (h *AppHandlers) checkInvidiousDiagnostics(w http.ResponseWriter, r *http.Request) {
	videoID := r.URL.Query().Get("video_id")
	if videoID == "" && r.Method == http.MethodPost {
		var req struct {
			VideoID string `json:"video_id"`
		}
		_ = json.NewDecoder(r.Body).Decode(&req)
		videoID = req.VideoID
	}
	result := h.healthChecker.CheckInvidiousWithVideo(r.Context(), videoID)
	successResp(w, result, "诊断完成")
}

// checkSourcesDiagnostics POST /api/diagnostics/sources 批量检测视频源健康。
func (h *AppHandlers) checkSourcesDiagnostics(w http.ResponseWriter, r *http.Request) {
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit <= 0 {
		limit = 20
	}
	result, err := h.healthChecker.CheckSourcesBatch(r.Context(), limit)
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "视频源健康检测失败", "SOURCE_HEALTH_ERROR")
		return
	}
	successResp(w, result, "检测完成")
}

// statsSummary GET /api/stats 返回统计概要。
func (h *AppHandlers) statsSummary(w http.ResponseWriter, r *http.Request) {
	result, err := h.store.GetStatsSummary(r.Context())
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "统计查询失败", "STATS_ERROR")
		return
	}
	successResp(w, result, "查询成功")
}

// diagnosticsPage GET /diagnostics Invidious 健康诊断面板。
func (h *AppHandlers) diagnosticsPage(w http.ResponseWriter, r *http.Request) {
	body := `
  <div class="page-header">
    <div>
      <h1 class="page-header__title">🔍 Invidious 健康面板</h1>
      <p class="page-header__subtitle">监控自部署视频搜索服务的连通性、视频详情链路和实例切换状态</p>
    </div>
    <div class="page-actions">
      <input type="text" id="diag-video-id" class="diag-video-input" value="dQw4w9WgXcQ" placeholder="YouTube 视频 ID"
             onkeydown="if(event.key==='Enter'){event.preventDefault();checkInvidiousHealth()}">
      <button class="btn btn--primary" onclick="checkInvidiousHealth()">🔎 立即检测</button>
    </div>
  </div>

  <div class="diag-grid">
    <section class="diag-card diag-card--status" id="diag-overall">
      <div class="diag-card__label">整体状态</div>
      <div class="diag-card__value" id="diag-overall-text">未检测</div>
      <div class="diag-card__hint" id="diag-checked-at">等待首次健康检测</div>
    </section>
    <section class="diag-card">
      <div class="diag-card__label">探针目标实例</div>
      <div class="diag-card__value diag-card__value--url" id="diag-active-url">-</div>
      <div class="diag-card__hint">视频详情探测选用的实例（主实例优先）</div>
    </section>
    <section class="diag-card">
      <div class="diag-card__label">负载均衡</div>
      <div class="diag-card__value" id="diag-lb-ratio">-</div>
      <div class="diag-card__hint" id="diag-lb-detail">各实例按权重轮询</div>
    </section>
    <section class="diag-card">
      <div class="diag-card__label">视频详情链路</div>
      <div class="diag-card__value" id="diag-video-status">未检测</div>
      <div class="diag-card__hint" id="diag-video-detail">使用默认公开视频 ID 探测</div>
    </section>
  </div>

  <section class="diag-section">
    <div class="diag-section__header">
      <div><h2>实例连通性</h2><p>依次检测主实例与备用实例的 <code>/api/v1/stats</code> 接口</p></div>
      <span class="diag-chip" id="diag-timeout">超时配置：-</span>
    </div>
    <div class="diag-instance-list" id="diag-instance-list">
      <div class="diag-empty">暂无检测数据，点击上方"立即检测"开始</div>
    </div>
  </section>

  <section class="diag-section diag-section--video">
    <div class="diag-section__header">
      <div><h2>视频详情探针</h2><p>逐个检测可连通实例的 <code>/api/v1/videos/{video_id}</code>，定位视频详情链路异常</p></div>
    </div>
    <div class="diag-instance-list" id="diag-video-probe-list">
      <div class="diag-empty">暂无视频详情检测数据</div>
    </div>
  </section>`
	renderStandalonePage(w, r, "诊断", body, "", "diagnostics.js")
}

// statsPage GET /stats 观看统计页。
func (h *AppHandlers) statsPage(w http.ResponseWriter, r *http.Request) {
	body := `
  <div class="page-header">
    <div><h1 class="page-header__title">📊 观看统计</h1><p class="page-header__subtitle">追番数据一览</p></div>
    <div class="page-actions"><button class="btn btn--primary" onclick="loadStats()">🔄 刷新</button></div>
  </div>
  <div id="stats-root"></div>`
	renderStandalonePage(w, r, "统计", body, "", "stats.js")
}
