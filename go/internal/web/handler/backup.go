package handler

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"time"
)

// backupExport GET /api/backup/export 导出 JSON 备份文件。
func (h *AppHandlers) backupExport(w http.ResponseWriter, r *http.Request) {
	data, err := h.backupService.ExportJSON(r.Context())
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "导出失败", "BACKUP_ERROR")
		return
	}
	filename := "zhuimange_backup_" + time.Now().Format("20060102_150405") + ".json"
	w.Header().Set("Content-Disposition", "attachment; filename="+filename)
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_, _ = w.Write(data)
}

// backupImport POST /api/backup/import 导入 JSON 备份（合并模式）。
func (h *AppHandlers) backupExportCSV(w http.ResponseWriter, r *http.Request) {
	data, err := h.backupService.ExportCSV(r.Context())
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "导出 CSV 失败", "BACKUP_ERROR")
		return
	}
	w.Header().Set("Content-Disposition", "attachment; filename=zhuimange_watchlist.csv")
	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	_, _ = w.Write(data)
}

func (h *AppHandlers) backupExportBangumi(w http.ResponseWriter, r *http.Request) {
	data, err := h.backupService.ExportBangumi(r.Context())
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "导出 Bangumi 失败", "BACKUP_ERROR")
		return
	}
	w.Header().Set("Content-Disposition", "attachment; filename=zhuimange_bangumi.json")
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_, _ = w.Write(data)
}

// backupImport POST /api/backup/import 导入 JSON 备份（合并模式）。
// 限制上传大小为 50MB，防止 OOM。
func (h *AppHandlers) backupImport(w http.ResponseWriter, r *http.Request) {
	const maxBackupSize = 50 << 20 // 50 MB
	// 优先读取上传文件，其次读取 JSON body
	var payload []byte
	if file, _, err := r.FormFile("file"); err == nil {
		defer file.Close()
		payload, err = io.ReadAll(io.LimitReader(file, maxBackupSize+1))
		if err != nil {
			errorResp(w, http.StatusBadRequest, "文件读取失败", "FILE_PARSE_ERROR")
			return
		}
	} else {
		payload, _ = io.ReadAll(io.LimitReader(r.Body, maxBackupSize+1))
	}
	if len(payload) > maxBackupSize {
		errorResp(w, http.StatusRequestEntityTooLarge, "备份文件超过 50MB 限制", "FILE_TOO_LARGE")
		return
	}
	if len(payload) == 0 {
		errorResp(w, http.StatusBadRequest, "请上传备份文件", "BAD_REQUEST")
		return
	}

	// 校验基本结构
	var probe struct {
		App    string            `json:"app"`
		Animes []json.RawMessage `json:"animes"`
	}
	if err := json.Unmarshal(payload, &probe); err != nil {
		errorResp(w, http.StatusBadRequest, "文件解析失败", "FILE_PARSE_ERROR")
		return
	}
	if probe.App != "追漫阁" {
		errorResp(w, http.StatusBadRequest, "无效的备份文件", "INVALID_BACKUP_FILE")
		return
	}

	stats, err := h.backupService.ImportJSON(r.Context(), payload)
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "导入失败: "+err.Error(), "BACKUP_ERROR")
		return
	}
	successResp(w, stats, "备份导入成功")
}

// backupTelegram POST /api/backup/telegram 发送备份到 Telegram。
func (h *AppHandlers) backupTelegram(w http.ResponseWriter, r *http.Request) {
	result, err := h.backupService.SendBackupToTelegram(r.Context())
	if err != nil {
		errorResp(w, http.StatusBadRequest, err.Error(), "TG_BACKUP_ERROR")
		return
	}
	successResp(w, result, "备份发送成功")
}

// backupLocal POST /api/backup/local 保存备份到本地文件。
func (h *AppHandlers) backupLocal(w http.ResponseWriter, r *http.Request) {
	result, err := h.backupService.SaveBackupLocal(r.Context())
	if err != nil {
		errorResp(w, http.StatusBadRequest, err.Error(), "LOCAL_BACKUP_ERROR")
		return
	}
	successResp(w, result, "本地备份成功")
}

// backupLogs GET /api/backup/logs 获取备份日志。
func (h *AppHandlers) backupLogs(w http.ResponseWriter, r *http.Request) {
	backupType := r.URL.Query().Get("type")
	status := r.URL.Query().Get("status")
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit <= 0 {
		limit = 50
	}
	logs, err := h.store.GetBackupLogs(r.Context(), backupType, status, limit)
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "查询备份日志失败", "BACKUP_LOG_ERROR")
		return
	}
	successResp(w, logs, "查询成功")
}

// backupStats GET /api/backup/stats 获取备份统计。
func (h *AppHandlers) backupStats(w http.ResponseWriter, r *http.Request) {
	days, _ := strconv.Atoi(r.URL.Query().Get("days"))
	if days <= 0 {
		days = 30
	}
	stats, err := h.store.GetBackupStats(r.Context(), days)
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "查询备份统计失败", "BACKUP_STATS_ERROR")
		return
	}
	successResp(w, stats, "查询成功")
}
