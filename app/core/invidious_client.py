"""
追漫阁 - Invidious API 客户端
"""
import logging
from typing import Any, Optional
import requests
from app import config

logger = logging.getLogger(__name__)


class InvidiousClient:
    """Invidious API 客户端，支持多实例故障切换"""

    def __init__(self):
        self.primary_url = config.INVIDIOUS_URL.rstrip("/")
        self.fallback_urls = [
            url.rstrip("/") for url in config.INVIDIOUS_FALLBACK_URLS
        ]
        self.timeout = config.INVIDIOUS_API_TIMEOUT
        self.current_url = self.primary_url
        self.session = requests.Session()
        logger.info(f"Invidious 客户端初始化，当前实例: {self.current_url}")

    def update_url(self, new_url: str):
        """动态更新 Invidious 实例 URL"""
        new_url = new_url.rstrip("/")
        if new_url != self.current_url:
            self.current_url = new_url
            self.primary_url = new_url
            logger.info(f"Invidious 实例 URL 已更新: {new_url}")

    def test_connection(self) -> bool:
        """测试当前实例是否可用"""
        try:
            url = f"{self.current_url}/api/v1/stats"
            resp = self.session.get(url, timeout=10)
            logger.info(f"Invidious 连接测试: {url} → HTTP {resp.status_code}")
            return resp.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Invidious 连接测试失败: {self.current_url} → {e}")
            return False

    def _get_active_url(self) -> str:
        """获取当前活跃的实例 URL"""
        return self.current_url

    def _switch_instance(self):
        """切换到下一个可用实例"""
        current_index = -1
        all_urls = [self.primary_url] + self.fallback_urls
        try:
            current_index = all_urls.index(self.current_url)
        except ValueError:
            pass

        for i in range(1, len(all_urls)):
            next_index = (current_index + i) % len(all_urls)
            next_url = all_urls[next_index]
            try:
                resp = self.session.get(
                    f"{next_url}/api/v1/stats",
                    timeout=5
                )
                if resp.status_code == 200:
                    self.current_url = next_url
                    logger.info(f"Invidious 实例切换至: {next_url}")
                    return
            except requests.RequestException:
                continue

        logger.warning("所有 Invidious 实例均不可用")

    def _request(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """发送 API 请求，失败时尝试切换实例"""
        url = f"{self._get_active_url()}{endpoint}"
        try:
            resp = self.session.get(url, params=params or {}, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning(f"Invidious 请求失败: {url} - {e}，尝试切换实例")
            self._switch_instance()
            # 使用新实例重试一次
            url = f"{self._get_active_url()}{endpoint}"
            try:
                resp = self.session.get(url, params=params or {}, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e2:
                logger.error(f"Invidious 重试失败: {url} - {e2}")
                raise

    def search_videos(self, query: str, max_results: int = 20) -> list[dict]:
        """
        搜索视频

        Args:
            query: 搜索关键词
            max_results: 最大结果数

        Returns:
            视频列表
        """
        try:
            logger.info(f"搜索视频: '{query}' (实例: {self.current_url})")
            results = self._request("/api/v1/search", {
                "q": query,
                "type": "video",
                "sort_by": "relevance",
            })

            if not isinstance(results, list):
                logger.warning(f"Invidious 返回非列表结果: {type(results)} → {str(results)[:200]}")
                return []

            videos = []
            for item in results[:max_results]:
                if item.get("type") != "video":
                    continue
                videos.append({
                    "video_id": item.get("videoId", ""),
                    "title": item.get("title", ""),
                    "channel_id": item.get("authorId", ""),
                    "channel_name": item.get("author", ""),
                    "duration": item.get("lengthSeconds", 0),
                    "view_count": item.get("viewCount", 0),
                    "published_at": item.get("publishedText", ""),
                    "published_timestamp": item.get("published", 0),
                })
            logger.info(f"搜索完成: '{query}' → {len(videos)} 个视频")
            return videos
        except Exception as e:
            logger.error(f"视频搜索失败: {query} - {type(e).__name__}: {e}")
            return []

    def get_video_info(self, video_id: str) -> Optional[dict]:
        """
        获取视频详情

        Args:
            video_id: YouTube 视频 ID

        Returns:
            视频详情
        """
        try:
            item = self._request(f"/api/v1/videos/{video_id}")
            return {
                "video_id": item.get("videoId", video_id),
                "title": item.get("title", ""),
                "channel_id": item.get("authorId", ""),
                "channel_name": item.get("author", ""),
                "duration": item.get("lengthSeconds", 0),
                "view_count": item.get("viewCount", 0),
                "description": item.get("description", ""),
                "published_at": item.get("publishedText", ""),
            }
        except Exception as e:
            logger.error(f"获取视频详情失败: {video_id} - {e}")
            return None


# 全局单例
invidious_client = InvidiousClient()
