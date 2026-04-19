"""
追漫阁 - Bangumi.tv API 客户端

Bangumi API 文档: https://bangumi.github.io/api/
"""
import logging
from typing import Optional, TYPE_CHECKING
from urllib.parse import quote
import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "追漫阁/1.0 (https://github.com/lwhx/zhuimange)",
    "Accept": "application/json",
}
_BASE = "https://api.bgm.tv"
_IMG_BASE = "https://lain.bgm.tv"
_TIMEOUT = 10


def _fix_img(url: str) -> str:
    """将 http 图片 URL 改为 https"""
    if not url:
        return ""
    return url.replace("http://", "https://")


class BangumiClient:
    """Bangumi.tv API 客户端（单例）"""

    def search_anime(self, keyword: str, limit: int = 15) -> list[dict]:
        """
        搜索动漫

        Args:
            keyword: 搜索关键词
            limit: 最大结果数

        Returns:
            标准化的动漫信息列表
        """
        url = f"{_BASE}/search/subject/{quote(keyword)}"
        params = {"type": 2, "responseGroup": "medium", "max_results": limit}
        try:
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("list") or []
            return [self._normalize(item) for item in items if item.get("type") == 2]
        except Exception as e:
            logger.error(f"Bangumi 搜索失败: {keyword} - {e}")
            return []

    def get_anime_detail(self, subject_id: int) -> Optional[dict]:
        """
        获取动漫详情

        Args:
            subject_id: Bangumi subject ID

        Returns:
            标准化的动漫信息，或 None
        """
        url = f"{_BASE}/subject/{subject_id}"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            return self._normalize(resp.json())
        except Exception as e:
            logger.error(f"Bangumi 详情获取失败: {subject_id} - {e}")
            return None

    def get_episodes(self, subject_id: int) -> list[dict]:
        """
        获取集数列表（仅正片，type=0）

        Args:
            subject_id: Bangumi subject ID

        Returns:
            集数列表
        """
        url = f"{_BASE}/subject/{subject_id}/ep"
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            episodes = data.get("eps") or []
            result = []
            for i, ep in enumerate(episodes):
                if ep.get("type") != 0:  # 只要正片
                    continue
                result.append({
                    "absolute_num": ep.get("sort") or (i + 1),
                    "episode_number": ep.get("sort") or (i + 1),
                    "season_number": 1,
                    "title": ep.get("name_cn") or ep.get("name", ""),
                    "air_date": ep.get("airdate", ""),
                    "overview": "",
                    "still_path": "",
                })
            return result
        except Exception as e:
            logger.error(f"Bangumi 集数获取失败: {subject_id} - {e}")
            return []

    def _normalize(self, item: dict) -> dict:
        """将 Bangumi 数据格式化为与 TMDB 一致的结构"""
        images = item.get("images") or {}
        poster = (
            images.get("large") or images.get("medium") or images.get("common") or ""
        )
        name_cn = item.get("name_cn") or item.get("name", "")
        name_en = ""
        # 如果 name_cn 为空但 name 是中文，用 name 作为中文名
        if not name_cn and item.get("name"):
            name_cn = item["name"]
        # 如果有日文名且中文名不同，将日文名存为英文名（用于搜索）
        if item.get("name") and item["name"] != name_cn:
            name_en = item["name"]

        return {
            "bangumi_id": item.get("id"),
            "tmdb_id": None,
            "title_cn": name_cn,
            "title_en": name_en,
            "poster_url": _fix_img(poster),
            "overview": item.get("summary", ""),
            "air_date": item.get("air_date", ""),
            "total_episodes": item.get("eps_count") or item.get("eps") or 0,
            "status": "Returning Series",
            "source": "bangumi",
        }


# 延迟初始化：避免模块级实例化，方便测试 mock
_bangumi_client_instance: Optional["BangumiClient"] = None


def get_bangumi_client() -> "BangumiClient":
    """获取 Bangumi 客户端单例（延迟初始化）

    Returns:
        BangumiClient 实例
    """
    global _bangumi_client_instance
    if _bangumi_client_instance is None:
        _bangumi_client_instance = BangumiClient()
    return _bangumi_client_instance


def reset_bangumi_client() -> None:
    """重置 Bangumi 客户端实例（仅用于测试）"""
    global _bangumi_client_instance
    _bangumi_client_instance = None
