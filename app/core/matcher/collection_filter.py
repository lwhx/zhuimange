"""
追漫阁 - 合集过滤器
"""
import re
import logging
from app import config

logger = logging.getLogger(__name__)

# 合集/非正片关键词
COLLECTION_KEYWORDS = [
    '合集', '全集', '连续播放', '一口气看完', '1-', '1～',
    '大合集', '合辑', '联播', '马拉松', '连播',
]

CLIP_KEYWORDS = [
    '混剪', '剪辑', 'cut', '名场面', '高能', '高燃',
    '高光', '催泪', '感动', '燃向', '踩点',
]

COMMENTARY_KEYWORDS = [
    '解说', '解析', '详解', '评价', '吐槽', '盘点', '分析',
    '科普', '讲解', '拉片', 'react', 'reaction', '反应',
]

PREVIEW_KEYWORDS = [
    '预告', 'PV', 'CM', '宣传', '先行', '预热',
    '片花', 'trailer', 'preview', 'teaser',
]

MUSIC_KEYWORDS = [
    'OP', 'ED', 'OST', 'BGM', '片头曲', '片尾曲',
    '主题曲', '插曲', 'AMV', 'MAD', '同人',
]

# 合集标题模式
COLLECTION_RANGE_PATTERN = re.compile(
    r'(\d+)\s*[-~～到至]\s*(\d+)\s*[集话話期回]'
)
COLLECTION_ALL_PATTERN = re.compile(
    r'[全共]\s*(\d+)\s*[集话話期回]'
)


def is_collection(title: str, duration: int = 0) -> bool:
    """
    检测是否为合集视频

    改进：增加上下文判断，避免误过滤
    - 标题同时包含具体集数（如"第5集"）时不过滤
    - 仅当"合集"附近有范围词才过滤

    Args:
        title: 视频标题
        duration: 视频时长（秒）

    Returns:
        是否为合集
    """
    title_lower = title.lower()

    # 检测是否包含具体集数信息（如 "第5集"、"EP05"）
    has_specific_ep = bool(re.search(
        r'第\s*\d+\s*[集话話期回]|[Ee][Pp]?\s*\d+(?!\s*[-~～到至])',
        title
    ))

    # 1. 关键词检测（但如果有具体集数则放行）
    for keyword in COLLECTION_KEYWORDS:
        if keyword.lower() in title_lower:
            # "合集" "全集" 但同时有具体集数 → 可能是频道名带"合集"
            if has_specific_ep and keyword in ('合集', '大合集', '合辑'):
                logger.debug(f"合集关键词 '{keyword}' 命中但有具体集数，放行: '{title}'")
                continue
            logger.debug(f"合集关键词命中: '{keyword}' in '{title}'")
            return True

    # 2. 范围模式检测（如 "1-10集"）
    match = COLLECTION_RANGE_PATTERN.search(title)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        if end - start >= 2:
            logger.debug(f"合集范围命中: {start}-{end} in '{title}'")
            return True

    # 3. 全集模式检测（如 "全24集"）
    if COLLECTION_ALL_PATTERN.search(title):
        logger.debug(f"全集模式命中: '{title}'")
        return True

    # 4. 时长检测（超过阈值视为合集）
    if duration > 0 and duration > config.COLLECTION_MAX_DURATION:
        # 如果有具体集数且时长不是特别夸张（<1.5倍阈值），放行
        if has_specific_ep and duration < config.COLLECTION_MAX_DURATION * 1.5:
            logger.debug(f"时长偏长但有具体集数，放行: '{title}' ({duration}s)")
            return False
        logger.debug(f"时长过长 ({duration}s > {config.COLLECTION_MAX_DURATION}s): '{title}'")
        return True

    return False


def is_non_episode_content(title: str) -> bool:
    """
    检测是否为非正片内容（剪辑、解说、预告等）

    Args:
        title: 视频标题

    Returns:
        是否为非正片
    """
    title_lower = title.lower()

    all_keyword_groups = [
        ("剪辑", CLIP_KEYWORDS),
        ("解说", COMMENTARY_KEYWORDS),
        ("预告", PREVIEW_KEYWORDS),
        ("音乐", MUSIC_KEYWORDS),
    ]

    for category, keywords in all_keyword_groups:
        for keyword in keywords:
            if keyword.lower() in title_lower:
                logger.debug(f"非正片[{category}]关键词命中: '{keyword}' in '{title}'")
                return True

    # 额外检查全局排除关键词
    for keyword in config.EXCLUDE_KEYWORDS:
        if keyword.lower() in title_lower:
            return True

    return False


def should_filter(title: str, duration: int = 0) -> bool:
    """
    综合判断是否应过滤该视频

    Args:
        title: 视频标题
        duration: 视频时长（秒）

    Returns:
        是否应过滤
    """
    return is_collection(title, duration) or is_non_episode_content(title)
