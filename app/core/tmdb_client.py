"""
追漫阁 - TMDB API 客户端
"""
import logging
from typing import Any, Optional
import requests
from app import config

logger = logging.getLogger(__name__)


class TMDBClient:
    """TMDB API 客户端"""

    def __init__(self):
        self.api_key = config.TMDB_API_KEY
        self.base_url = config.TMDB_BASE_URL
        self.language = config.TMDB_LANGUAGE
        self.image_base = config.TMDB_IMAGE_BASE
        self.session = requests.Session()
        self.session.params = {
            "api_key": self.api_key,
            "language": self.language,
        }

    def _request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """发送 API 请求"""
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self.session.get(url, params=params or {}, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"TMDB API 请求失败: {endpoint} - {e}")
            raise

    def search_anime(self, query: str) -> list[dict]:
        """
        搜索动漫

        Args:
            query: 搜索关键词

        Returns:
            动漫列表
        """
        try:
            data = self._request("/search/tv", {
                "query": query,
                "with_genres": "16",
                "include_adult": "false",
            })
            results = []
            for item in data.get("results", []):
                results.append({
                    "tmdb_id": item["id"],
                    "title_cn": item.get("name", ""),
                    "title_en": item.get("original_name", ""),
                    "poster_url": (
                        f"{self.image_base}{item['poster_path']}"
                        if item.get("poster_path")
                        else ""
                    ),
                    "overview": item.get("overview", ""),
                    "air_date": item.get("first_air_date", ""),
                    "vote_average": item.get("vote_average", 0),
                    "total_episodes": item.get("number_of_episodes", 0),
                })
            return results
        except Exception as e:
            logger.error(f"搜索动漫失败: {query} - {e}")
            return []

    def get_anime_detail(self, tmdb_id: int) -> Optional[dict]:
        """
        获取动漫详情

        Args:
            tmdb_id: TMDB ID

        Returns:
            动漫详情字典
        """
        try:
            item = self._request(f"/tv/{tmdb_id}")
            seasons = item.get("seasons", [])
            # 过滤掉特别篇(season_number=0)
            regular_seasons = [s for s in seasons if s.get("season_number", 0) > 0]

            total_episodes = sum(s.get("episode_count", 0) for s in regular_seasons)

            return {
                "tmdb_id": item["id"],
                "title_cn": item.get("name", ""),
                "title_en": item.get("original_name", ""),
                "poster_url": (
                    f"{self.image_base}{item['poster_path']}"
                    if item.get("poster_path")
                    else ""
                ),
                "overview": item.get("overview", ""),
                "air_date": item.get("first_air_date", ""),
                "total_episodes": total_episodes,
                "status": item.get("status", "Unknown"),
                "seasons": [
                    {
                        "season_number": s["season_number"],
                        "episode_count": s.get("episode_count", 0),
                        "name": s.get("name", ""),
                    }
                    for s in regular_seasons
                ],
            }
        except Exception as e:
            logger.error(f"获取动漫详情失败: tmdb_id={tmdb_id} - {e}")
            return None

    def get_all_episodes(self, tmdb_id: int, seasons: list[dict]) -> list[dict]:
        """
        获取所有集数信息

        Args:
            tmdb_id: TMDB ID
            seasons: 季信息列表

        Returns:
            集数列表，带 absolute_num
        """
        episodes = []
        absolute_num = 0

        for season in seasons:
            season_num = season["season_number"]
            try:
                data = self._request(f"/tv/{tmdb_id}/season/{season_num}")
                for ep in data.get("episodes", []):
                    absolute_num += 1
                    episodes.append({
                        "season_number": season_num,
                        "episode_number": ep.get("episode_number", 0),
                        "absolute_num": absolute_num,
                        "title": ep.get("name", ""),
                        "overview": ep.get("overview", ""),
                        "air_date": ep.get("air_date", ""),
                        "still_path": (
                            f"{self.image_base}{ep['still_path']}"
                            if ep.get("still_path")
                            else ""
                        ),
                    })
            except Exception as e:
                logger.error(f"获取季 {season_num} 集数失败: {e}")
                continue

        return episodes


# 全局单例
tmdb_client = TMDBClient()
