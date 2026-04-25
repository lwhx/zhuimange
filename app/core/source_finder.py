"""
追漫阁 - 视频源查找器
"""
import json
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from app import config
from app.core.invidious_client import get_invidious_client
from app.core.tmdb_client import get_tmdb_client
from app.core.matcher.scorer import score_video
from app.core.matcher.preprocessor import normalize_text, extract_episode_number
from app.db import database as db

logger = logging.getLogger(__name__)

# 手动添加动漫的匹配阈值（更宽松）
MANUAL_MATCH_THRESHOLD = 30


def _get_search_keywords(anime: dict, episode_num: int, aliases: list[str] = None) -> list[str]:
    """
    生成搜索关键词列表

    Args:
        anime: 动漫信息
        episode_num: 目标集数
        aliases: 已获取的别名列表（避免重复查询）

    Returns:
        关键词列表
    """
    title = anime.get("title_cn", "")

    if aliases is None:
        aliases = db.get_aliases(anime["id"])
        aliases.extend(db.get_global_aliases_by_title(title))

    all_names = [title] + aliases
    # 去重
    seen = set()
    unique_names = []
    for name in all_names:
        if name and name.lower() not in seen:
            seen.add(name.lower())
            unique_names.append(name)

    keywords = []
    for name in unique_names[:config.SEARCH_KEYWORDS_LIMIT]:
        keywords.append(f"{name} 第{episode_num}集")
        keywords.append(f"{name} EP{episode_num}")

    return keywords


def _apply_source_rules(videos: list[dict], anime_id: int) -> list[dict]:
    """
    应用搜索规则过滤

    Args:
        videos: 视频列表
        anime_id: 动漫 ID

    Returns:
        过滤后的视频列表
    """
    rules = db.get_source_rules(anime_id)
    if not rules:
        return videos

    allow_keywords = json.loads(rules.get("allow_keywords", "[]"))
    deny_keywords = json.loads(rules.get("deny_keywords", "[]"))
    allow_channels = json.loads(rules.get("allow_channels", "[]"))
    deny_channels = json.loads(rules.get("deny_channels", "[]"))

    filtered = []
    for video in videos:
        title_lower = video.get("title", "").lower()
        channel_id = video.get("channel_id", "")

        # 黑名单频道
        if deny_channels and channel_id in deny_channels:
            continue

        # 黑名单关键词
        if deny_keywords and any(kw.lower() in title_lower for kw in deny_keywords):
            continue

        # 白名单频道（如有设置，则只保留白名单频道）
        if allow_channels and channel_id not in allow_channels:
            continue

        # 白名单关键词（如有设置，必须包含至少一个）
        if allow_keywords and not any(kw.lower() in title_lower for kw in allow_keywords):
            continue

        filtered.append(video)

    return filtered


def find_sources_for_episode(
    anime_id: int,
    episode_num: int,
    force: bool = False,
) -> list[dict]:
    """
    查找指定集数的视频源

    Args:
        anime_id: 动漫 ID
        episode_num: 集数
        force: 是否强制搜索（忽略缓存）

    Returns:
        视频源列表
    """
    anime = db.get_anime(anime_id)
    if not anime:
        logger.error(f"动漫不存在: anime_id={anime_id}")
        return []

    # 获取对应集数记录
    episode = db.get_episode_by_num(anime_id, episode_num)
    if not episode:
        logger.error(f"集数不存在: anime_id={anime_id}, ep={episode_num}")
        return []

    # 检查缓存（非强制模式下）
    if not force:
        existing_sources = db.get_sources_for_episode(episode["id"])
        if existing_sources:
            logger.info(f"使用缓存视频源: {anime['title_cn']} 第{episode_num}集 ({len(existing_sources)}个)")
            return existing_sources

    # 获取别名列表（一次查询，复用于关键词和评分）
    aliases = db.get_aliases(anime_id)
    aliases.extend(db.get_global_aliases_by_title(anime["title_cn"]))

    # 生成搜索关键词
    keywords = _get_search_keywords(anime, episode_num, aliases)
    logger.info(f"搜索关键词: {keywords}")

    # 并发搜索并收集所有结果
    all_videos = []
    seen_ids = set()
    max_workers = min(max(1, config.SOURCE_SEARCH_WORKERS), len(keywords)) if keywords else 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_search_keyword_videos, keyword): keyword for keyword in keywords}
        for future in as_completed(futures):
            keyword = futures[future]
            try:
                videos = future.result()
                logger.info(f"关键词 '{keyword}' 搜索到 {len(videos)} 个视频")
                for video in videos:
                    vid = video.get("video_id", "")
                    if vid and vid not in seen_ids:
                        seen_ids.add(vid)
                        all_videos.append(video)
            except Exception as e:
                logger.error(f"搜索关键词 '{keyword}' 出错: {type(e).__name__}: {e}")

    logger.info(f"去重后找到 {len(all_videos)} 个候选视频")

    # 应用搜索规则
    all_videos = _apply_source_rules(all_videos, anime_id)
    logger.info(f"规则过滤后: {len(all_videos)} 个视频")

    # 判断是否为手动添加的动漫（使用更低阈值）
    is_manual = anime.get("tmdb_id") is None
    threshold = MANUAL_MATCH_THRESHOLD if is_manual else config.MATCH_THRESHOLD
    if is_manual:
        logger.info(f"手动添加动漫，使用宽松阈值: {threshold}")

    # 评分并排序
    scored_videos = []
    filtered_count = 0
    below_threshold_count = 0
    for video in all_videos:
        score_result = score_video(
            video, anime["title_cn"], episode_num, aliases
        )

        if score_result["filtered"]:
            filtered_count += 1
            logger.debug(f"过滤: '{video.get('title', '')}' - {score_result.get('filter_reason', '')}")
            continue

        if score_result["total_score"] >= threshold:
            video["match_score"] = score_result["total_score"]
            video["score_detail"] = score_result
            scored_videos.append(video)
        else:
            below_threshold_count += 1
            logger.debug(
                f"低分: '{video.get('title', '')}' = {score_result['total_score']:.1f} "
                f"(阈值: {threshold})"
            )

    logger.info(
        f"评分结果: {len(scored_videos)} 通过, {filtered_count} 被过滤, "
        f"{below_threshold_count} 低于阈值({threshold})"
    )

    # 按分数排序
    scored_videos.sort(key=lambda x: x["match_score"], reverse=True)

    # 强制重新搜索时，搜索流程已完成，此时用新结果替换该集旧视频源
    if force:
        deleted_count = db.delete_sources_for_episode(episode["id"])
        logger.info(
            f"强制搜索清理旧视频源: {anime['title_cn']} 第{episode_num}集 "
            f"({deleted_count}个)"
        )

    # 保存到数据库
    max_sources = config.MAX_SOURCES_PER_EPISODE
    for video in scored_videos[:max_sources]:
        db.add_source({
            "episode_id": episode["id"],
            "video_id": video["video_id"],
            "title": video.get("title", ""),
            "channel_id": video.get("channel_id", ""),
            "channel_name": video.get("channel_name", ""),
            "duration": video.get("duration", 0),
            "view_count": video.get("view_count", 0),
            "published_at": video.get("published_at", ""),
            "match_score": video["match_score"],
        })

    # 循环结束后统一查询一次
    saved_sources = db.get_sources_for_episode(episode["id"])

    logger.info(
        f"保存 {len(scored_videos[:max_sources])} 个视频源: "
        f"{anime['title_cn']} 第{episode_num}集"
    )

    return saved_sources


def _search_keyword_videos(keyword: str) -> list[dict]:
    """
    搜索单个关键词的视频列表

    Args:
        keyword: 搜索关键词

    Returns:
        视频列表
    """
    return get_invidious_client().search_videos(keyword, max_results=config.MAX_SEARCH_RESULTS)


def should_sync_episode(episode: dict, mode: str = "incremental") -> tuple[bool, str]:
    """
    判断单集是否需要同步视频源

    Args:
        episode: 集数记录
        mode: 同步模式，incremental 表示增量，full 表示全量

    Returns:
        是否同步和原因
    """
    if mode == "full":
        return True, "full"

    sources = db.get_sources_for_episode(episode["id"])
    if not sources:
        return True, "missing"

    return False, "cached"


def discover_latest_episode(anime_id: int) -> int:
    """
    搜索动漫最新集数

    通过搜索动漫名称，从搜索结果中提取最大集数号

    Args:
        anime_id: 动漫 ID

    Returns:
        发现的最新集数，未发现返回 0
    """
    anime = db.get_anime(anime_id)
    if not anime:
        return 0

    title = anime.get("title_cn", "")
    aliases = db.get_aliases(anime_id)
    aliases.extend(db.get_global_aliases_by_title(title))

    # 搜索名称（不带集数）
    search_terms = [title] + aliases[:3]
    max_ep = 0

    for term in search_terms:
        if not term:
            continue
        try:
            # 按相关性搜索
            videos = get_invidious_client().search_videos(term, max_results=50)
            for video in videos:
                ep = extract_episode_number(video.get("title", ""))
                if ep is not None and ep > max_ep:
                    max_ep = ep

            # 按日期搜索（更容易找到最新集数）
            videos_by_date = get_invidious_client().search_videos(term, max_results=30, sort_by="date")
            for video in videos_by_date:
                ep = extract_episode_number(video.get("title", ""))
                if ep is not None and ep > max_ep:
                    max_ep = ep
        except Exception as e:
            logger.error(f"探测集数搜索失败: {term} - {e}")

    # 针对性搜索更高集数（max_ep+1 到 max_ep+10）
    if max_ep > 0:
        for offset in range(1, 11):
            target_ep = max_ep + offset
            try:
                keyword = f"{title} 第{target_ep}集"
                videos = get_invidious_client().search_videos(keyword, max_results=5)
                found = False
                for video in videos:
                    ep = extract_episode_number(video.get("title", ""))
                    if ep is not None and ep == target_ep:
                        max_ep = target_ep
                        found = True
                        break
                if not found:
                    break
            except Exception as e:
                logger.error(f"探测集数搜索失败: 第{target_ep}集 - {e}")
                break

    if max_ep > 0:
        logger.info(f"探测到最新集数: {title} → 第{max_ep}集")

        # 自动创建缺少的集数记录
        existing_episodes = db.get_episodes(anime_id)
        existing_nums = {ep["absolute_num"] for ep in existing_episodes}

        new_episodes = []
        for i in range(1, max_ep + 1):
            if i not in existing_nums:
                new_episodes.append({
                    "absolute_num": i,
                    "episode_number": i,
                    "season_number": 1,
                })

        if new_episodes:
            db.add_episodes(anime_id, new_episodes)
            logger.info(f"自动创建 {len(new_episodes)} 个集数记录")

        # 更新 total_episodes
        db.update_anime(anime_id, {"total_episodes": max_ep})

    return max_ep


def sync_anime_sources(anime_id: int, mode: str = "incremental") -> dict:
    """
    同步整部动漫的视频源

    Args:
        anime_id: 动漫 ID
        mode: 同步模式，incremental 表示增量同步，full 表示全量刷新

    Returns:
        同步结果
    """
    anime = db.get_anime(anime_id)
    if not anime:
        return {"success": False, "error": "动漫不存在"}

    if mode not in {"incremental", "full"}:
        mode = "incremental"

    # TMDB 添加的动漫：先从 TMDB 更新集数
    tmdb_id = anime.get("tmdb_id")
    if tmdb_id:
        try:
            detail = get_tmdb_client().get_anime_detail(tmdb_id)
            if detail and detail.get("seasons"):
                episodes = get_tmdb_client().get_all_episodes(tmdb_id, detail["seasons"])
                if episodes:
                    existing_episodes = db.get_episodes(anime_id)
                    existing_nums = {ep["absolute_num"] for ep in existing_episodes}
                    new_episodes = []
                    for ep in episodes:
                        if ep.get("absolute_num", 0) not in existing_nums:
                            new_episodes.append(ep)
                    if new_episodes:
                        db.add_episodes(anime_id, new_episodes)
                        logger.info(f"TMDB 更新: 新增 {len(new_episodes)} 个集数记录")
                    db.update_anime(anime_id, {"total_episodes": detail.get("total_episodes", 0)})
        except Exception as e:
            logger.warning(f"TMDB 集数更新失败: {e}")

    # 探测最新集数（补充 TMDB 未收录的集数）
    discovered_ep = 0
    try:
        discovered_ep = discover_latest_episode(anime_id)
        if discovered_ep > 0:
            logger.info(f"探测到最新集数: {discovered_ep} 集")
    except Exception as e:
        logger.warning(f"探测最新集数失败: {e}")

    episodes = db.get_episodes(anime_id)
    sync_items = []
    skipped = 0
    skip_reasons = {"cached": 0}
    for ep in episodes:
        should_sync, reason = should_sync_episode(ep, mode)
        if should_sync:
            sync_items.append((ep, reason))
        else:
            skipped += 1
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    synced = 0
    total_sources = 0
    lock = threading.Lock()

    logger.info(
        f"同步并发配置: 模式={mode}, 集数并发={config.EPISODE_SYNC_WORKERS}, "
        f"关键词并发={config.SOURCE_SEARCH_WORKERS}, 待同步={len(sync_items)}, 跳过={skipped}"
    )

    def _sync_one(ep, reason):
        """同步单集（线程任务）"""
        try:
            sources = find_sources_for_episode(anime_id, ep["absolute_num"], force=(mode == "full"))
            return (ep["absolute_num"], sources, reason)
        except Exception as e:
            logger.error(f"同步失败: {anime['title_cn']} 第{ep['absolute_num']}集 - {e}")
            return (ep["absolute_num"], None, reason)

    # 多线程并发同步，线程数由配置控制，避免叠加单集关键词并发后压垮实例
    max_workers = min(max(1, config.EPISODE_SYNC_WORKERS), len(sync_items)) if sync_items else 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_sync_one, ep, reason): ep for ep, reason in sync_items}
        for future in as_completed(futures):
            ep_num, sources, reason = future.result()
            if sources:
                with lock:
                    synced += 1
                    total_sources += len(sources)

    # 更新最后同步时间
    db.touch_anime_sync(anime_id)

    # 手动动漫无封面时，尝试用视频缩略图作为封面
    anime = db.get_anime(anime_id)  # 重新读取
    is_manual = anime.get("tmdb_id") is None
    if is_manual and not anime.get("poster_url"):
        # 从已保存的视频源中取最高分的缩略图
        for ep in episodes:
            sources = db.get_sources_for_episode(ep.get("id", 0))
            if sources:
                best_vid = sources[0].get("video_id", "")
                if best_vid:
                    thumb_url = f"https://img.youtube.com/vi/{best_vid}/hqdefault.jpg"
                    db.update_anime(anime_id, {"poster_url": thumb_url})
                    logger.info(f"自动设置封面(视频缩略图): {thumb_url}")
                    break

    # 记录同步日志
    db.add_sync_log(
        anime_id=anime_id,
        sync_type="manual",
        episodes_synced=synced,
        sources_found=total_sources,
        status="success",
        message=f"同步完成: 模式={mode}, 同步 {synced}/{len(sync_items)} 集，跳过 {skipped}/{len(episodes)} 集"
    )

    return {
        "success": True,
        "mode": mode,
        "synced_episodes": synced,
        "skipped_episodes": skipped,
        "total_episodes": len(episodes),
        "target_episodes": len(sync_items),
        "total_sources": total_sources,
        "skip_reasons": skip_reasons,
    }
