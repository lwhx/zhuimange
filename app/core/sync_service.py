"""
追漫阁 - 动漫同步服务

这里集中承载同步流程，普通同步、SSE 流式同步和后台队列都复用这一套逻辑。
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Callable, Optional

from app import config
from app.core.source_finder import (
    discover_latest_episode,
    find_sources_for_episode,
    should_sync_episode,
)
from app.core.tmdb_client import get_tmdb_client
from app.db import database as db

logger = logging.getLogger(__name__)

SyncEvent = dict[str, Any]
SyncEmitter = Callable[[SyncEvent], None]


def normalize_sync_mode(mode: str) -> str:
    """规范化同步模式。"""
    return mode if mode in {"incremental", "full"} else "incremental"


def run_anime_sync(
    anime_id: int,
    mode: str = "incremental",
    sync_type: str = "manual",
    emit: Optional[SyncEmitter] = None,
) -> dict[str, Any]:
    """
    同步一部动漫的视频源。

    Args:
        anime_id: 动漫 ID
        mode: incremental 或 full
        sync_type: manual / auto 等同步来源，用于日志
        emit: 可选事件回调，SSE 和队列用它推送实时进度

    Returns:
        同步结果字典
    """
    mode = normalize_sync_mode(mode)
    anime = db.get_anime(anime_id)
    if not anime:
        result = {"success": False, "message": "动漫不存在", "error": "动漫不存在"}
        _emit(emit, {"type": "error", "message": "动漫不存在"})
        return result

    try:
        is_manual = anime.get("tmdb_id") is None

        _refresh_tmdb_episodes(anime_id, anime, emit)
        if is_manual:
            _discover_latest_episodes(anime_id, anime, emit)
        elif config.DISCOVER_TMDB_LATEST_EPISODES:
            logger.info(
                "已忽略 DISCOVER_TMDB_LATEST_EPISODES：TMDB 动漫仅使用 TMDB 集数源，"
                f"anime_id={anime_id}"
            )

        today = date.today().isoformat()
        episodes = db.filter_aired_episodes(anime, db.get_episodes(anime_id), today)
        episodes.reverse()  # 从最新集开始，更符合追更场景
        total = len(episodes)

        _emit(emit, {"type": "start", "total": total, "mode": mode})

        sync_items: list[tuple[dict, str]] = []
        skipped = 0
        skip_reasons: dict[str, int] = {"cached": 0}
        for ep in episodes:
            should_sync, reason = should_sync_episode(ep, mode)
            if should_sync:
                sync_items.append((ep, reason))
            else:
                skipped += 1
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

        _emit(emit, {
            "type": "plan",
            "mode": mode,
            "total": total,
            "target": len(sync_items),
            "skipped": skipped,
            "skip_reasons": skip_reasons,
        })

        synced = 0
        total_sources = 0
        done_count = 0
        first_video_id = ""

        logger.info(
            f"同步并发配置: 模式={mode}, 集数并发={config.EPISODE_SYNC_WORKERS}, "
            f"待同步={len(sync_items)}, 跳过={skipped}"
        )

        def _sync_one(ep: dict, reason: str) -> tuple[int, int, str]:
            ep_num = ep["absolute_num"]
            try:
                sources = find_sources_for_episode(
                    anime_id,
                    ep_num,
                    force=(mode == "full"),
                )
                return ep_num, len(sources) if sources else 0, reason
            except Exception as e:
                logger.error(f"同步失败: {anime['title_cn']} 第{ep_num}集 - {e}")
                return ep_num, 0, reason

        max_workers = min(max(1, config.EPISODE_SYNC_WORKERS), len(sync_items)) if sync_items else 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_sync_one, ep, reason): ep for ep, reason in sync_items}
            for future in as_completed(futures):
                ep_num, source_count, reason = future.result()
                done_count += 1
                if source_count > 0:
                    synced += 1
                    total_sources += source_count
                    if not first_video_id:
                        ep_obj = next((e for e in episodes if e["absolute_num"] == ep_num), None)
                        first_video_id = _first_source_video_id(ep_obj)

                _emit(emit, {
                    "type": "episode",
                    "current": done_count,
                    "total": len(sync_items),
                    "overall_total": total,
                    "skipped": skipped,
                    "ep_num": ep_num,
                    "source_count": source_count,
                    "reason": reason,
                })

        db.touch_anime_sync(anime_id)

        poster_url = ""
        if is_manual:
            poster_url = _ensure_manual_poster(anime_id, first_video_id, episodes)
            if poster_url:
                _emit(emit, {"type": "poster", "poster_url": poster_url})

        message = f"同步完成: 模式={mode}, 同步 {synced}/{len(sync_items)} 集，跳过 {skipped}/{total} 集"
        db.add_sync_log(
            anime_id=anime_id,
            sync_type=sync_type,
            episodes_synced=synced,
            sources_found=total_sources,
            status="success",
            message=message,
        )

        result = {
            "success": True,
            "mode": mode,
            "synced_episodes": synced,
            "skipped_episodes": skipped,
            "total_episodes": total,
            "target_episodes": len(sync_items),
            "total_sources": total_sources,
            "skip_reasons": skip_reasons,
            "poster_url": poster_url,
        }
        _emit(emit, {
            "type": "done",
            "mode": mode,
            "synced": synced,
            "skipped": skipped,
            "target": len(sync_items),
            "total": total,
            "total_sources": total_sources,
        })
        return result
    except Exception as e:
        logger.exception(f"同步流程发生错误: anime_id={anime_id}, mode={mode}, error={e}")
        db.add_sync_log(
            anime_id=anime_id,
            sync_type=sync_type,
            episodes_synced=0,
            sources_found=0,
            status="error",
            message=str(e),
        )
        result = {"success": False, "message": str(e), "error": str(e), "mode": mode}
        _emit(emit, {"type": "error", "message": str(e)})
        return result


def _refresh_tmdb_episodes(anime_id: int, anime: dict, emit: Optional[SyncEmitter]) -> None:
    """从 TMDB 刷新已添加动漫的集数。"""
    tmdb_id = anime.get("tmdb_id")
    if not tmdb_id:
        return

    _emit(emit, {"type": "discovering", "message": "正在从 TMDB 更新集数..."})
    try:
        detail = get_tmdb_client().get_anime_detail(tmdb_id)
        if not detail or not detail.get("seasons"):
            return

        tmdb_episodes = get_tmdb_client().get_all_episodes(tmdb_id, detail["seasons"])
        if not tmdb_episodes:
            return

        tmdb_nums = {
            ep.get("absolute_num", 0)
            for ep in tmdb_episodes
            if ep.get("absolute_num", 0) > 0
        }
        deleted_count, existing_nums = db.delete_episodes_not_in_absolute_nums(anime_id, tmdb_nums)
        if deleted_count:
            logger.info(
                f"TMDB 更新: 清理 {deleted_count} 个非 TMDB 集数记录，anime_id={anime_id}"
            )

        new_episodes = [
            ep for ep in tmdb_episodes
            if ep.get("absolute_num", 0) not in existing_nums
        ]
        if new_episodes:
            db.add_episodes(anime_id, new_episodes)
            logger.info(f"TMDB 更新: 新增 {len(new_episodes)} 个集数记录")

        db.update_anime(anime_id, {"total_episodes": detail.get("total_episodes", 0)})
        today = date.today().isoformat()
        aired_new_episodes = db.filter_aired_episodes(anime, new_episodes, today)
        aired_total = len(db.filter_aired_episodes(anime, db.get_episodes(anime_id), today))
        new_ep_nums = [
            ep.get("absolute_num", 0)
            for ep in aired_new_episodes
            if ep.get("absolute_num", 0) > 0
        ]
        _emit(emit, {
            "type": "discover",
            "new_episodes": new_ep_nums,
            "total": aired_total,
        })
    except Exception as e:
        logger.warning(f"TMDB 集数更新失败: {e}")


def _discover_latest_episodes(anime_id: int, anime: dict, emit: Optional[SyncEmitter]) -> None:
    """通过视频搜索补充探测最新集数。"""
    _emit(emit, {"type": "discovering", "message": "正在探测最新集数..."})
    existing_nums_before = {ep["absolute_num"] for ep in db.get_episodes(anime_id)}
    try:
        discovered = discover_latest_episode(anime_id)
    except Exception as e:
        logger.warning(f"探测最新集数失败: {anime.get('title_cn', anime_id)} - {e}")
        return

    if discovered <= 0:
        return

    all_eps_after = db.get_episodes(anime_id)
    new_ep_nums = [
        ep["absolute_num"]
        for ep in all_eps_after
        if ep["absolute_num"] not in existing_nums_before
    ]
    _emit(emit, {
        "type": "discover",
        "new_episodes": new_ep_nums,
        "total": len(all_eps_after),
    })


def _ensure_manual_poster(anime_id: int, first_video_id: str, episodes: list[dict]) -> str:
    """手动添加动漫没有封面时，用最高分视频缩略图补一个封面。"""
    anime = db.get_anime(anime_id)
    if not anime or anime.get("poster_url"):
        return ""

    video_id = first_video_id
    if not video_id:
        for ep in episodes:
            video_id = _first_source_video_id(ep)
            if video_id:
                break

    if not video_id:
        return ""

    poster_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    db.update_anime(anime_id, {"poster_url": poster_url})
    logger.info(f"自动设置封面(视频缩略图): {poster_url}")
    return poster_url


def _first_source_video_id(ep: Optional[dict]) -> str:
    if not ep:
        return ""
    sources = db.get_sources_for_episode(ep.get("id", 0))
    if not sources:
        return ""
    return sources[0].get("video_id", "")


def _emit(emit: Optional[SyncEmitter], event: SyncEvent) -> None:
    if emit:
        emit(event)
