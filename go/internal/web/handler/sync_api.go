package handler

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
)

// enqueueSync POST /api/anime/{id}/sync 将动漫同步任务加入队列。
func (h *AppHandlers) enqueueSync(w http.ResponseWriter, r *http.Request) {
	animeID, _ := strconv.ParseInt(chi.URLParam(r, "id"), 10, 64)
	var req struct {
		Mode string `json:"mode"`
	}
	_ = json.NewDecoder(r.Body).Decode(&req)
	if req.Mode == "" {
		req.Mode = r.URL.Query().Get("mode")
	}
	task, created, err := h.syncQueue.Enqueue(r.Context(), animeID, req.Mode, "manual")
	if err != nil {
		errorResp(w, http.StatusInternalServerError, "创建同步任务失败", "SYNC_ENQUEUE_ERROR")
		return
	}
	successResp(w, map[string]any{"task": taskSnapshot(task), "created": created}, "同步任务已提交")
}

// syncTaskSnapshot GET /api/sync_tasks/{task_id} 返回同步任务快照。
func (h *AppHandlers) syncTaskSnapshot(w http.ResponseWriter, r *http.Request) {
	taskID := chi.URLParam(r, "task_id")
	task := h.syncQueue.GetTask(taskID)
	if task == nil {
		errorResp(w, http.StatusNotFound, "同步任务不存在", "TASK_NOT_FOUND")
		return
	}
	successResp(w, taskSnapshot(task), "查询成功")
}

// syncTaskStream GET /api/sync_tasks/{task_id}/stream 推送同步任务 SSE 事件。
func (h *AppHandlers) syncTaskStream(w http.ResponseWriter, r *http.Request) {
	taskID := chi.URLParam(r, "task_id")
	flusher, ok := w.(http.Flusher)
	if !ok {
		errorResp(w, http.StatusInternalServerError, "当前响应不支持流式推送", "SSE_UNSUPPORTED")
		return
	}
	w.Header().Set("Content-Type", "text/event-stream; charset=utf-8")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")
	lastSeq := int64(0)
	if value := r.Header.Get("Last-Event-ID"); value != "" {
		if parsed, err := strconv.ParseInt(value, 10, 64); err == nil {
			lastSeq = parsed
		}
	}
	ticker := time.NewTicker(15 * time.Second)
	defer ticker.Stop()
	for {
		events, exists := h.syncQueue.EventsAfter(taskID, lastSeq)
		if !exists {
			fmt.Fprintf(w, "event: error\ndata: {\"message\":\"同步任务不存在\"}\n\n")
			flusher.Flush()
			return
		}
		for _, event := range events {
			payload, _ := json.Marshal(event.Data)
			fmt.Fprintf(w, "id: %d\nevent: message\ndata: %s\n\n", event.Seq, payload)
			lastSeq = event.Seq
		}
		flusher.Flush()
		select {
		case <-r.Context().Done():
			return
		case <-ticker.C:
			fmt.Fprintf(w, ": heartbeat\n\n")
			flusher.Flush()
		default:
			h.syncQueue.Wait(taskID, lastSeq, 10*time.Second)
		}
	}
}

// taskSnapshot 返回任务对外快照。
func taskSnapshot(task any) any {
	return task
}
