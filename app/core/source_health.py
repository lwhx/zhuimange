"""
追漫阁 - 视频源健康检测
"""
import logging
from typing import Any
from app.core.invidious_client import get_invidious_client
from app.db import database as db

logger = logging.getLogger(__name__)

SOURCE_HEALTH_FAIL_THRESHOLD = 2


def check_source_health(source: dict[str, Any]) -> dict[str, Any]:
    """检测单个视频源健康状态"""
    source_id = int(source.get("id") or 0)
    video_id = str(source.get("video_id") or "").strip()
    if not source_id or not video_id:
        return {
            "source_id": source_id,
            "video_id": video_id,
            "health_status": "error",
            "is_valid": 1,
            "error": "视频源数据不完整",
        }

    try:
        video_info = get_invidious_client().get_video_info(video_id)
        if video_info:
            updated_source = db.update_source_health(
                source_id,
                "available",
                fail_threshold=SOURCE_HEALTH_FAIL_THRESHOLD,
            )
            logger.info(f"视频源检测可用: source_id={source_id}, video_id={video_id}")
            return _build_result(updated_source, "")

        updated_source = db.update_source_health(
            source_id,
            "error",
            "视频详情不可访问，可能已下架或实例暂时异常",
            fail_threshold=SOURCE_HEALTH_FAIL_THRESHOLD,
        )
        logger.warning(f"视频源检测失败: source_id={source_id}, video_id={video_id}")
        return _build_result(updated_source, "视频详情不可访问，可能已下架或实例暂时异常")
    except Exception as e:
        error_message = f"检测异常: {type(e).__name__}: {e}"
        updated_source = db.update_source_health(
            source_id,
            "error",
            error_message,
            fail_threshold=SOURCE_HEALTH_FAIL_THRESHOLD,
        )
        logger.error(f"视频源检测异常: source_id={source_id}, video_id={video_id}, error={e}")
        return _build_result(updated_source, error_message)


def check_episode_sources_health(anime_id: int, episode_num: int) -> dict[str, Any]:
    """检测指定集数全部视频源健康状态"""
    episode = db.get_episode_by_num(anime_id, episode_num)
    if not episode:
        return {
            "success": False,
            "message": "集数不存在",
            "checked": 0,
            "available": 0,
            "invalid": 0,
            "error": 0,
            "unknown": 0,
            "sources": [],
        }

    sources = db.get_sources_for_episode(episode["id"], include_invalid=True)
    results = [check_source_health(source) for source in sources]
    summary = {
        "success": True,
        "checked": len(results),
        "available": 0,
        "invalid": 0,
        "error": 0,
        "unknown": 0,
        "sources": results,
    }
    for result in results:
        status = result.get("health_status") or "unknown"
        if status not in {"available", "invalid", "error", "unknown"}:
            status = "unknown"
        summary[status] += 1
    summary["message"] = f"检测完成：可用 {summary['available']} 个，失效 {summary['invalid']} 个，异常 {summary['error']} 个"
    return summary


def _build_result(source: dict[str, Any] | None, error_message: str) -> dict[str, Any]:
    """构建视频源检测结果"""
    if not source:
        return {
            "source_id": 0,
            "video_id": "",
            "health_status": "error",
            "is_valid": 1,
            "error": error_message or "视频源不存在",
        }
    return {
        "source_id": source.get("id"),
        "video_id": source.get("video_id"),
        "health_status": source.get("health_status") or "unknown",
        "is_valid": int(source.get("is_valid") or 0),
        "fail_count": int(source.get("fail_count") or 0),
        "last_checked_at": source.get("last_checked_at"),
        "error": error_message or source.get("last_check_error") or "",
    }
