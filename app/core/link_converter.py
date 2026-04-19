"""
追漫阁 - 链接转换器
"""


def invidious_to_youtube(video_id: str) -> str:
    """
    将视频 ID 转换为 YouTube 链接

    Args:
        video_id: YouTube 视频 ID

    Returns:
        YouTube 链接
    """
    return f"https://www.youtube.com/watch?v={video_id}"


def invidious_to_embed(video_id: str) -> str:
    """
    将视频 ID 转换为嵌入链接

    Args:
        video_id: YouTube 视频 ID

    Returns:
        嵌入链接
    """
    return f"https://www.youtube.com/embed/{video_id}"


def get_invidious_link(video_id: str, invidious_url: str) -> str:
    """
    生成 Invidious 观看链接

    Args:
        video_id: 视频 ID
        invidious_url: Invidious 实例地址

    Returns:
        Invidious 链接
    """
    return f"{invidious_url.rstrip('/')}/watch?v={video_id}"


def format_duration(seconds: int) -> str:
    """
    格式化时长

    Args:
        seconds: 秒数

    Returns:
        格式化后的时长字符串 (HH:MM:SS 或 MM:SS)
    """
    if seconds <= 0:
        return "0:00"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_view_count(count: int) -> str:
    """
    格式化观看数

    Args:
        count: 观看次数

    Returns:
        格式化后的字符串 (如 1.2万)
    """
    if count >= 100000000:
        return f"{count / 100000000:.1f}亿"
    if count >= 10000:
        return f"{count / 10000:.1f}万"
    if count >= 1000:
        return f"{count / 1000:.1f}千"
    return str(count)
