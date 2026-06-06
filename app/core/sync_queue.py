"""
追漫阁 - 同步任务队列

轻量级进程内队列，解决同一部动漫重复同步和手动请求阻塞问题。
"""
import copy
import logging
import queue
import threading
import uuid
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Optional

from app import config
from app.core.sync_service import normalize_sync_mode, run_anime_sync

logger = logging.getLogger(__name__)

EVENT_BUFFER_SIZE = 300


class SyncTask:
    """单个同步任务的内存状态。"""

    def __init__(self, anime_id: int, mode: str, sync_type: str = "manual"):
        self.id = uuid.uuid4().hex
        self.anime_id = anime_id
        self.mode = normalize_sync_mode(mode)
        self.sync_type = sync_type
        self.status = "queued"
        self.created_at = datetime.now().isoformat(timespec="seconds")
        self.started_at = ""
        self.finished_at = ""
        self.error = ""
        self.result: Optional[dict[str, Any]] = None
        self.events: deque[dict[str, Any]] = deque(maxlen=EVENT_BUFFER_SIZE)
        self._event_seq = 0
        self.condition = threading.Condition()

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "anime_id": self.anime_id,
            "mode": self.mode,
            "sync_type": self.sync_type,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "result": copy.deepcopy(self.result),
        }

    def add_event(self, event: dict[str, Any]) -> dict[str, Any]:
        item = dict(event)
        item.setdefault("task_id", self.id)
        item.setdefault("status", self.status)
        item.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
        with self.condition:
            self._event_seq += 1
            item["_seq"] = self._event_seq
            self.events.append(item)
            self.condition.notify_all()
        return item


class SyncQueue:
    """线程安全的同步队列。"""

    def __init__(
        self,
        worker_count: int = 1,
        autostart: bool = True,
        task_retention_seconds: Optional[int] = None,
    ):
        self._queue: queue.Queue[str] = queue.Queue()
        self._tasks: dict[str, SyncTask] = {}
        self._active_by_anime: dict[int, str] = {}
        self._lock = threading.Lock()
        self._started = False
        self._worker_count = max(1, worker_count)
        self._autostart = autostart
        self._task_retention_seconds = (
            config.SYNC_TASK_RETENTION_SECONDS
            if task_retention_seconds is None
            else max(0, task_retention_seconds)
        )

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True

        for index in range(self._worker_count):
            thread = threading.Thread(
                target=self._worker_loop,
                name=f"sync-queue-worker-{index + 1}",
                daemon=True,
            )
            thread.start()
        logger.info(f"同步任务队列已启动，worker_count={self._worker_count}")

    def enqueue(self, anime_id: int, mode: str = "incremental", sync_type: str = "manual") -> tuple[SyncTask, bool]:
        """提交任务；同一动漫已有排队/运行任务时返回现有任务。"""
        if self._autostart:
            self.start()
        normalized_mode = normalize_sync_mode(mode)
        with self._lock:
            self._cleanup_completed_tasks_locked()
            existing_id = self._active_by_anime.get(anime_id)
            if existing_id:
                existing = self._tasks.get(existing_id)
                if existing and existing.status in {"queued", "running"}:
                    return existing, False

            task = SyncTask(anime_id=anime_id, mode=normalized_mode, sync_type=sync_type)
            self._tasks[task.id] = task
            self._active_by_anime[anime_id] = task.id
            self._queue.put(task.id)
            task.add_event({"type": "queued", "message": "同步任务已加入队列"})
            return task, True

    def get_task(self, task_id: str) -> Optional[SyncTask]:
        with self._lock:
            self._cleanup_completed_tasks_locked()
            return self._tasks.get(task_id)

    def get_task_snapshot(self, task_id: str) -> Optional[dict[str, Any]]:
        task = self.get_task(task_id)
        return task.snapshot() if task else None

    def wait_for_completion(self, task_id: str, timeout: Optional[float] = None) -> Optional[dict[str, Any]]:
        """等待任务结束，返回任务快照；主要供后台调度器复用队列。"""
        task = self.get_task(task_id)
        if not task:
            return None
        terminal_status = {"success", "error"}
        with task.condition:
            if task.status not in terminal_status:
                task.condition.wait_for(lambda: task.status in terminal_status, timeout=timeout)
        return task.snapshot()

    def cleanup_completed_tasks(self) -> int:
        """清理超过保留期的已完成任务，返回清理数量。"""
        with self._lock:
            return self._cleanup_completed_tasks_locked()

    def _worker_loop(self) -> None:
        while True:
            task_id = self._queue.get()
            task = self.get_task(task_id)
            if not task:
                self._queue.task_done()
                continue

            try:
                self._run_task(task)
            finally:
                self._queue.task_done()

    def _run_task(self, task: SyncTask) -> None:
        task.status = "running"
        task.started_at = datetime.now().isoformat(timespec="seconds")
        task.add_event({"type": "task_start", "message": "同步任务开始执行"})

        def emit(event: dict[str, Any]) -> None:
            task.add_event(event)

        try:
            result = run_anime_sync(
                task.anime_id,
                mode=task.mode,
                sync_type=task.sync_type,
                emit=emit,
            )
            task.result = result
            task.status = "success" if result.get("success") else "error"
            if not result.get("success"):
                task.error = result.get("message") or result.get("error") or "同步失败"
                task.add_event({"type": "error", "message": task.error})
        except Exception as e:
            logger.exception(f"同步任务异常: task_id={task.id}, anime_id={task.anime_id}, error={e}")
            task.status = "error"
            task.error = str(e)
            task.add_event({"type": "error", "message": str(e)})
        finally:
            task.finished_at = datetime.now().isoformat(timespec="seconds")
            task.add_event({
                "type": "task_done",
                "task_status": task.status,
                "message": "同步任务结束",
            })
            with self._lock:
                if self._active_by_anime.get(task.anime_id) == task.id:
                    self._active_by_anime.pop(task.anime_id, None)
                self._cleanup_completed_tasks_locked()

    def _cleanup_completed_tasks_locked(self) -> int:
        terminal_status = {"success", "error"}
        cutoff = datetime.now() - timedelta(seconds=self._task_retention_seconds)
        expired_ids = [
            task_id
            for task_id, task in self._tasks.items()
            if task.status in terminal_status
            and task.finished_at
            and datetime.fromisoformat(task.finished_at) <= cutoff
        ]
        for task_id in expired_ids:
            self._tasks.pop(task_id, None)
        return len(expired_ids)


sync_queue = SyncQueue(worker_count=1)
