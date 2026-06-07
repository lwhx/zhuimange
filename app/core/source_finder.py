"""
追漫阁 - 视频源查找器
"""
import json
import logging
import re
from datetime import date
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from app import config
from app.core.invidious_client import get_invidious_client
from app.core.matcher.scorer import score_video, source_sort_key
from app.core.matcher.preprocessor import extract_episode_number
from app.db import database as db

logger = logging.getLogger(__name__)

# 手动添加动漫的匹配阈值（更宽松）
MANUAL_MATCH_THRESHOLD = 30


def _dedupe_keep_order(items: list[str]) -> list[str]:
    """按顺序去重，避免重复关键词浪费搜索配额。"""
    seen = set()
    unique_items = []
    for item in items:
        value = item.strip()
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            unique_items.append(value)
    return unique_items


def _is_generic_episode_title(title: str) -> bool:
    """过滤 TMDB 中常见的无信息量单集名，如 Episode 1 / 第1集。"""
    normalized = title.strip()
    if not normalized:
        return True
    return bool(re.fullmatch(
        r"(?:episode|ep|e|第)\s*\d+\s*(?:集|话|話)?",
        normalized,
        flags=re.IGNORECASE,
    ))


def _get_search_keywords(
    anime: dict,
    episode_num: int,
    aliases: list[str] = None,
    episode: Optional[dict] = None,
) -> list[str]:
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

    search_names = unique_names[:config.SEARCH_KEYWORDS_LIMIT]
    keywords = []

    episode_title = (episode or {}).get("title", "").strip()
    if anime.get("tmdb_id") is not None and episode_title and not _is_generic_episode_title(episode_title):
        for name in search_names:
            keywords.append(f"{name} {episode_title}")

    for name in search_names:
        keywords.append(f"{name} 第{episode_num}集")
        keywords.append(f"{name} EP{episode_num}")

    return _dedupe_keep_order(keywords)


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
    if not db.episode_is_aired(anime, episode, date.today().isoformat()):
        logger.info(
            f"跳过未开播集数的视频源搜索: {anime['title_cn']} 第{episode_num}集 "
            f"(air_date={episode.get('air_date', '')})"
        )
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
    keywords = _get_search_keywords(anime, episode_num, aliases, episode)
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

    # 评分并排序：先硬过滤，再按置信等级和同级质量排序
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

    # 置信等级优先；发布时间/播放量/画质只作为同级内排序因素
    scored_videos.sort(key=source_sort_key, reverse=True)

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

    if anime.get("tmdb_id") is not None:
        logger.info(
            "TMDB 动漫跳过网页最新集数探测，使用 TMDB 集数作为准确信息源: "
            f"{anime.get('title_cn', anime_id)}"
        )
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
    from app.core.sync_service import run_anime_sync

    return run_anime_sync(anime_id, mode=mode, sync_type="manual")
