package syncsvc

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"sync"
	"time"

	"github.com/lwhx/zhuimange/internal/model"
	"github.com/lwhx/zhuimange/internal/store"
)

const eventBufferSize = 300

// Task 表示内存中的同步任务状态。
type Task struct {
	ID         string        `json:"id"`
	AnimeID    int64         `json:"anime_id"`
	Mode       string        `json:"mode"`
	SyncType   string        `json:"sync_type"`
	Status     string        `json:"status"`
	Progress   int           `json:"progress"`
	Message    string        `json:"message"`
	Error      string        `json:"error"`
	Result     *Result       `json:"result,omitempty"`
	CreatedAt  time.Time     `json:"created_at"`
	StartedAt  *time.Time    `json:"started_at,omitempty"`
	FinishedAt *time.Time    `json:"finished_at,omitempty"`
	Events     []QueuedEvent `json:"-"`
	Seq        int64         `json:"-"`
	Cond       *sync.Cond    `json:"-"`
}

// QueuedEvent 表示带序号的任务事件。
type QueuedEvent struct {
	Seq  int64 `json:"_seq"`
	Data Event `json:"data"`
}

// Queue 管理同步任务队列。
type Queue struct {
	store         *store.Store
	service       *Service
	jobs          chan string
	mu            sync.Mutex
	tasks         map[string]*Task
	activeByAnime map[int64]string
}

// NewQueue 创建并启动同步队列。
func NewQueue(st *store.Store, service *Service) *Queue {
	q := &Queue{store: st, service: service, jobs: make(chan string, 100), tasks: map[string]*Task{}, activeByAnime: map[int64]string{}}
	go q.worker()
	go q.gc() // 定时清理已完成任务，防止内存单调增长
	return q
}

// gc 定时清理已完成且超过保留期的任务，释放内存。
func (q *Queue) gc() {
	ticker := time.NewTicker(5 * time.Minute)
	defer ticker.Stop()
	const retention = 30 * time.Minute // 完成任务保留 30 分钟供 SSE 续传
	for range ticker.C {
		cutoff := time.Now().Add(-retention)
		q.mu.Lock()
		for id, task := range q.tasks {
			if (task.Status == "success" || task.Status == "error") && task.CreatedAt.Before(cutoff) {
				// 从 activeByAnime 移除（若是当前活跃任务）
				if active, ok := q.activeByAnime[task.AnimeID]; ok && active == id {
					delete(q.activeByAnime, task.AnimeID)
				}
				delete(q.tasks, id)
			}
		}
		q.mu.Unlock()
	}
}

// Enqueue 入队同步任务，同动漫已有任务时复用。
func (q *Queue) Enqueue(ctx context.Context, animeID int64, mode string, syncType string) (*Task, bool, error) {
	mode = NormalizeMode(mode)
	q.mu.Lock()
	if id := q.activeByAnime[animeID]; id != "" {
		if task := q.tasks[id]; task != nil && (task.Status == "queued" || task.Status == "running") {
			q.mu.Unlock()
			return task, false, nil
		}
	}
	task := &Task{ID: newTaskID(), AnimeID: animeID, Mode: mode, SyncType: syncType, Status: "queued", Progress: 0, Message: "同步任务已加入队列", CreatedAt: time.Now()}
	task.Cond = sync.NewCond(&q.mu)
	q.tasks[task.ID] = task
	q.activeByAnime[animeID] = task.ID
	q.addEventLocked(task, Event{"type": "queued", "message": task.Message})
	q.mu.Unlock()
	if err := q.store.CreateSyncJob(ctx, &model.SyncJob{TaskID: task.ID, AnimeID: animeID, Status: task.Status, Mode: mode, SyncType: syncType, Progress: task.Progress, Message: task.Message}); err != nil {
		q.mu.Lock()
		delete(q.tasks, task.ID)
		if q.activeByAnime[animeID] == task.ID {
			delete(q.activeByAnime, animeID)
		}
		q.mu.Unlock()
		return nil, false, err
	}
	q.jobs <- task.ID
	return task, true, nil
}

// GetTask 查询任务。
func (q *Queue) GetTask(id string) *Task {
	q.mu.Lock()
	defer q.mu.Unlock()
	return q.tasks[id]
}

// EventsAfter 返回指定序号之后的事件。
func (q *Queue) EventsAfter(id string, seq int64) ([]QueuedEvent, bool) {
	q.mu.Lock()
	defer q.mu.Unlock()
	task := q.tasks[id]
	if task == nil {
		return nil, false
	}
	items := []QueuedEvent{}
	for _, event := range task.Events {
		if event.Seq > seq {
			items = append(items, event)
		}
	}
	return items, true
}

// Wait 等待任务产生事件或结束。
func (q *Queue) Wait(id string, seq int64, timeout time.Duration) bool {
	q.mu.Lock()
	defer q.mu.Unlock()
	task := q.tasks[id]
	if task == nil {
		return false
	}
	deadline := time.Now().Add(timeout)
	for !hasEventAfter(task, seq) && task.Status != "success" && task.Status != "error" && time.Now().Before(deadline) {
		task.Cond.Wait()
	}
	return true
}

// worker 消费同步任务。
func (q *Queue) worker() {
	for id := range q.jobs {
		q.run(id)
	}
}

// run 执行单个同步任务。
func (q *Queue) run(id string) {
	ctx := context.Background()
	q.mu.Lock()
	task := q.tasks[id]
	if task == nil {
		q.mu.Unlock()
		return
	}
	now := time.Now()
	task.Status = "running"
	task.StartedAt = &now
	task.Message = "同步任务开始执行"
	q.addEventLocked(task, Event{"type": "task_start", "message": task.Message})
	q.mu.Unlock()
	_ = q.store.UpdateSyncJob(ctx, id, map[string]any{"status": "running", "message": "同步任务开始执行"})
	emit := func(event Event) {
		q.mu.Lock()
		defer q.mu.Unlock()
		current := q.tasks[id]
		if current == nil {
			return
		}
		if progress, ok := eventProgress(event); ok {
			current.Progress = progress
		}
		if message, ok := event["message"].(string); ok {
			current.Message = message
		}
		q.addEventLocked(current, event)
	}
	result := q.service.RunAnimeSync(ctx, task.AnimeID, task.Mode, task.SyncType, emit)
	q.mu.Lock()
	finished := time.Now()
	task.Status = "success"
	if !result.Success {
		task.Status = "error"
		task.Error = result.Message
	}
	task.Progress = 100
	task.Result = &result
	task.FinishedAt = &finished
	task.Message = result.Message
	q.addEventLocked(task, Event{"type": "task_done", "task_status": task.Status, "message": result.Message})
	delete(q.activeByAnime, task.AnimeID)
	q.mu.Unlock()
	_ = q.store.UpdateSyncJob(ctx, id, map[string]any{"status": task.Status, "progress": 100, "message": task.Message, "finished_at": finished})
}

// addEventLocked 添加任务事件，调用方必须持有锁。
func (q *Queue) addEventLocked(task *Task, event Event) {
	task.Seq++
	event["task_id"] = task.ID
	event["status"] = task.Status
	event["timestamp"] = time.Now().Format(time.RFC3339)
	queued := QueuedEvent{Seq: task.Seq, Data: event}
	task.Events = append(task.Events, queued)
	if len(task.Events) > eventBufferSize {
		task.Events = task.Events[len(task.Events)-eventBufferSize:]
	}
	task.Cond.Broadcast()
}

// hasEventAfter 判断是否有新事件。
func hasEventAfter(task *Task, seq int64) bool {
	for _, event := range task.Events {
		if event.Seq > seq {
			return true
		}
	}
	return false
}

// eventProgress 从事件中计算任务进度。
func eventProgress(event Event) (int, bool) {
	current, currentOK := toInt(event["current"])
	total, totalOK := toInt(event["total"])
	if currentOK && totalOK && total > 0 {
		return current * 100 / total, true
	}
	return 0, false
}

// toInt 转换任意整数类型。
func toInt(value any) (int, bool) {
	switch item := value.(type) {
	case int:
		return item, true
	case int64:
		return int(item), true
	case float64:
		return int(item), true
	default:
		return 0, false
	}
}

// newTaskID 生成任务 ID。
func newTaskID() string {
	bytes := make([]byte, 16)
	_, _ = rand.Read(bytes)
	return hex.EncodeToString(bytes)
}
