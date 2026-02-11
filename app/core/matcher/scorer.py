"""
追漫阁 - 综合评分系统
"""
import logging
import time
from typing import Optional
from app import config
from app.core.matcher.preprocessor import normalize_text, extract_episode_number
from app.core.matcher.fuzzy_matcher import fuzzy_match_score
from app.core.matcher.collection_filter import should_filter
from app.db import database as db

logger = logging.getLogger(__name__)

# 画质关键词 → 加分值（出现即加分，优先排序）
QUALITY_BONUS_KEYWORDS = {
    "4k": 10, "4K": 10,
    "2160p": 10, "2160P": 10,
    "蓝光": 8,
    "1080p": 6, "1080P": 6,
    "超清": 5,
    "高清": 4,
    "720p": 2, "720P": 2,
}


def score_video(
    video: dict,
    anime_title: str,
    target_episode: int,
    aliases: Optional[list[str]] = None,
) -> dict:
    """
    为视频源进行综合评分

    评分维度:
    - 标题匹配 (40%): 动漫名称与视频标题的匹配度
    - 集数匹配 (30%): 目标集数与视频中检测到的集数
    - 频道信任 (15%): 频道是否在信任列表中
    - 时效性   (15%): 发布时间越近分数越高

    Args:
        video: 视频信息字典
        anime_title: 动漫名称
        target_episode: 目标集数
        aliases: 动漫别名列表

    Returns:
        评分结果字典，包含 total_score 和各维度分数
    """
    video_title = video.get("title", "")
    duration = video.get("duration", 0)

    # 前置过滤：合集/非正片
    if should_filter(video_title, duration):
        return {
            "total_score": 0,
            "title_score": 0,
            "episode_score": 0,
            "channel_score": 0,
            "recency_score": 0,
            "filtered": True,
            "filter_reason": "合集/非正片内容",
        }

    # 文本预处理
    normalized_video_title = normalize_text(video_title)
    normalized_anime_title = normalize_text(anime_title)

    # 1. 标题匹配分 (0-100)
    title_score = fuzzy_match_score(
        normalized_video_title,
        normalized_anime_title,
        aliases
    )

    # 2. 集数匹配分 (0-100)
    episode_score = 0.0
    detected_ep = extract_episode_number(video_title)
    if detected_ep is not None:
        if detected_ep == target_episode:
            episode_score = 100.0
        elif abs(detected_ep - target_episode) <= 1:
            episode_score = 30.0
        else:
            episode_score = 0.0
    else:
        # 无法检测集数，给一个中等分
        episode_score = 20.0

    # 3. 频道信任分 (0-100)
    channel_score = 0.0
    channel_id = video.get("channel_id", "")
    if channel_id and db.is_trusted_channel(channel_id):
        channel_score = 100.0
    else:
        # 根据观看量给一定分数
        view_count = video.get("view_count", 0)
        if view_count > 100000:
            channel_score = 60.0
        elif view_count > 10000:
            channel_score = 40.0
        elif view_count > 1000:
            channel_score = 20.0

    # 4. 时效性分 (0-100)
    recency_score = 50.0  # 默认中等分
    published_ts = video.get("published_timestamp", 0)
    if published_ts > 0:
        now = int(time.time())
        age_days = (now - published_ts) / 86400
        if age_days <= 7:
            recency_score = 100.0
        elif age_days <= 30:
            recency_score = 80.0
        elif age_days <= 90:
            recency_score = 60.0
        elif age_days <= 365:
            recency_score = 40.0
        else:
            recency_score = 20.0

    # 画质加分
    quality_bonus = 0.0
    video_title_lower = video_title.lower()
    for kw, bonus in QUALITY_BONUS_KEYWORDS.items():
        if kw.lower() in video_title_lower:
            quality_bonus = max(quality_bonus, bonus)

    # 综合评分（加权 + 画质加分）
    total_score = (
        title_score * config.SCORE_WEIGHT_TITLE +
        episode_score * config.SCORE_WEIGHT_EPISODE +
        channel_score * config.SCORE_WEIGHT_CHANNEL +
        recency_score * config.SCORE_WEIGHT_RECENCY +
        quality_bonus
    )

    result = {
        "total_score": round(total_score, 2),
        "title_score": round(title_score, 2),
        "episode_score": round(episode_score, 2),
        "channel_score": round(channel_score, 2),
        "recency_score": round(recency_score, 2),
        "filtered": False,
        "filter_reason": "",
        "detected_episode": detected_ep,
        "quality_bonus": quality_bonus,
    }

    logger.debug(
        f"评分: '{video_title}' → 总分={result['total_score']} "
        f"(标题={title_score:.1f}, 集数={episode_score:.1f}, "
        f"频道={channel_score:.1f}, 时效={recency_score:.1f})"
    )

    return result
