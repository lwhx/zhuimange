"""
追漫阁 - 综合评分系统
"""
import logging
import time
from typing import Optional
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

TITLE_STRONG_THRESHOLD = 75.0
TITLE_ACCEPT_THRESHOLD = 30.0

CONFIDENCE_TIERS = {
    "S": {
        "rank": 4,
        "base_score": 90.0,
        "label": "高置信：标题/集数/可信频道均命中",
    },
    "A": {
        "rank": 3,
        "base_score": 80.0,
        "label": "高置信：标题和集数命中",
    },
    "B": {
        "rank": 2,
        "base_score": 65.0,
        "label": "中置信：标题命中但未识别集数",
    },
    "C": {
        "rank": 1,
        "base_score": 35.0,
        "label": "低置信：弱匹配候选",
    },
}

HEALTH_RANK = {
    "available": 3,
    "unknown": 2,
    "error": 1,
    "invalid": 0,
}


def _to_int(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _get_quality_bonus(video_title: str) -> float:
    quality_bonus = 0.0
    video_title_lower = video_title.lower()
    for kw, bonus in QUALITY_BONUS_KEYWORDS.items():
        if kw.lower() in video_title_lower:
            quality_bonus = max(quality_bonus, bonus)
    return quality_bonus


def _get_channel_score(video: dict, trusted_channel: bool) -> float:
    if trusted_channel:
        return 100.0

    view_count = _to_int(video.get("view_count"))
    if view_count > 100000:
        return 60.0
    if view_count > 10000:
        return 40.0
    if view_count > 1000:
        return 20.0
    return 0.0


def _get_view_score(video: dict) -> float:
    view_count = _to_int(video.get("view_count"))
    if view_count > 1000000:
        return 100.0
    if view_count > 100000:
        return 80.0
    if view_count > 10000:
        return 60.0
    if view_count > 1000:
        return 40.0
    if view_count > 0:
        return 20.0
    return 0.0


def _get_recency_score(video: dict) -> float:
    recency_score = 50.0
    published_ts = _to_int(video.get("published_timestamp"))
    if published_ts > 0:
        now = int(time.time())
        age_days = max(0, (now - published_ts) / 86400)
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
    return recency_score


def _resolve_confidence_tier(
    title_score: float,
    detected_episode: Optional[int],
    trusted_channel: bool,
) -> str:
    if detected_episode is None:
        return "B" if title_score >= TITLE_STRONG_THRESHOLD else "C"
    if title_score >= TITLE_STRONG_THRESHOLD and trusted_channel:
        return "S"
    if title_score >= TITLE_STRONG_THRESHOLD:
        return "A"
    return "C"


def _get_tiered_score(
    tier: str,
    title_score: float,
    episode_score: float,
    channel_score: float,
    recency_score: float,
    view_score: float,
    quality_bonus: float,
) -> float:
    tie_score = (
        title_score * 0.35 +
        episode_score * 0.20 +
        channel_score * 0.15 +
        recency_score * 0.15 +
        view_score * 0.10 +
        quality_bonus * 0.50
    )
    tie_breaker = min(9.99, tie_score / 10)
    return round(CONFIDENCE_TIERS[tier]["base_score"] + tie_breaker, 2)


def source_sort_key(video: dict) -> tuple:
    """视频源排序键：置信等级优先，同级内再看质量、时效和播放量。"""
    detail = video.get("score_detail") or {}
    return (
        detail.get("confidence_rank", 0),
        detail.get("episode_score", 0),
        detail.get("title_score", 0),
        1 if detail.get("trusted_channel") else 0,
        HEALTH_RANK.get((video.get("health_status") or "unknown").lower(), 2),
        _to_int(video.get("published_timestamp")),
        _to_int(video.get("view_count")),
        detail.get("quality_bonus", 0),
        video.get("match_score", detail.get("total_score", 0)),
    )


def score_video(
    video: dict,
    anime_title: str,
    target_episode: int,
    aliases: Optional[list[str]] = None,
) -> dict:
    """
    为视频源进行综合评分

    评分策略:
    - 硬过滤：合集、非正片、标题弱匹配、明确错集数直接出局
    - 置信等级：S/A/B/C 分层，集数精确命中的源天然排在未识别集数前
    - 同级排序：标题、可信频道、时效、播放量、画质只在同等级内影响顺序

    Args:
        video: 视频信息字典
        anime_title: 动漫名称
        target_episode: 目标集数
        aliases: 动漫别名列表

    Returns:
        评分结果字典，包含 total_score、confidence_tier 和各维度分数
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
            "detected_episode": None,
            "confidence_tier": "",
            "confidence_rank": 0,
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

    if title_score < TITLE_ACCEPT_THRESHOLD:
        return {
            "total_score": 0,
            "title_score": round(title_score, 2),
            "episode_score": 0,
            "channel_score": 0,
            "recency_score": 0,
            "filtered": True,
            "filter_reason": "标题匹配度过低",
            "detected_episode": None,
            "confidence_tier": "",
            "confidence_rank": 0,
        }

    detected_ep = extract_episode_number(video_title)
    if detected_ep is not None:
        if detected_ep != target_episode:
            return {
                "total_score": 0,
                "title_score": round(title_score, 2),
                "episode_score": 0,
                "channel_score": 0,
                "recency_score": 0,
                "filtered": True,
                "filter_reason": f"集数不匹配：检测到第{detected_ep}集",
                "detected_episode": detected_ep,
                "confidence_tier": "",
                "confidence_rank": 0,
            }
        episode_score = 100.0
    else:
        episode_score = 20.0

    channel_id = video.get("channel_id", "")
    trusted_channel = bool(channel_id and db.is_trusted_channel(channel_id))
    channel_score = _get_channel_score(video, trusted_channel)
    recency_score = _get_recency_score(video)
    view_score = _get_view_score(video)
    quality_bonus = _get_quality_bonus(video_title)
    confidence_tier = _resolve_confidence_tier(
        title_score,
        detected_ep,
        trusted_channel,
    )

    total_score = _get_tiered_score(
        confidence_tier,
        title_score,
        episode_score,
        channel_score,
        recency_score,
        view_score,
        quality_bonus,
    )
    confidence = CONFIDENCE_TIERS[confidence_tier]

    result = {
        "total_score": total_score,
        "title_score": round(title_score, 2),
        "episode_score": round(episode_score, 2),
        "channel_score": round(channel_score, 2),
        "recency_score": round(recency_score, 2),
        "view_score": round(view_score, 2),
        "filtered": False,
        "filter_reason": "",
        "detected_episode": detected_ep,
        "quality_bonus": quality_bonus,
        "trusted_channel": trusted_channel,
        "confidence_tier": confidence_tier,
        "confidence_rank": confidence["rank"],
        "confidence_label": confidence["label"],
    }

    logger.debug(
        f"评分: '{video_title}' → {confidence_tier}级 总分={result['total_score']} "
        f"(标题={title_score:.1f}, 集数={episode_score:.1f}, "
        f"频道={channel_score:.1f}, 时效={recency_score:.1f}, "
        f"播放={view_score:.1f}, 画质+{quality_bonus:.1f})"
    )

    return result
