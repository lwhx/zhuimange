"""
追漫阁 - Invidious API 客户端
"""
import json
import logging
import threading
from typing import Any, Optional
import requests
from requests.adapters import HTTPAdapter
from app import config

logger = logging.getLogger(__name__)


class InvidiousClient:
    """Invidious API 客户端，支持用户配置实例与权重负载均衡"""

    def __init__(self):
        self.timeout = config.INVIDIOUS_API_TIMEOUT
        self.primary_weight = max(1, config.INVIDIOUS_PRIMARY_WEIGHT)
        self.fallback_weight = max(0, config.INVIDIOUS_FALLBACK_WEIGHT)
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=64, pool_maxsize=64)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self._lb_index = 0
        self._lb_lock = threading.Lock()
        self.primary_url = self._load_primary_url()
        self.fallback_urls = self._load_fallback_urls(self.primary_url)
        self.current_url = self.primary_url
        logger.info(f"Invidious 客户端初始化，当前实例: {self.current_url}")

    def update_url(self, new_url: str):
        """动态更新 Invidious 主实例 URL"""
        new_url = _normalize_url(new_url)
        if new_url and new_url != self.current_url:
            self.current_url = new_url
            self.primary_url = new_url
            self.fallback_urls = self._load_fallback_urls(self.primary_url)
            logger.info(f"Invidious 实例 URL 已更新: {new_url}")

    def test_connection(self) -> bool:
        """测试当前实例是否可用"""
        self.refresh_instances()
        try:
            url = f"{self.current_url}/api/v1/stats"
            resp = self.session.get(url, timeout=10)
            logger.info(f"Invidious 连接测试: {url} → HTTP {resp.status_code}")
            return resp.status_code == 200
        except requests.RequestException as e:
            logger.error(f"Invidious 连接测试失败: {self.current_url} → {e}")
            return False

    def refresh_instances(self) -> None:
        """从设置重新加载主实例和备用实例"""
        primary_url = self._load_primary_url()
        fallback_urls = self._load_fallback_urls(primary_url)
        if primary_url != self.primary_url or fallback_urls != self.fallback_urls:
            self.primary_url = primary_url
            self.fallback_urls = fallback_urls
            if self.current_url not in self.get_instance_urls():
                self.current_url = self.primary_url
            logger.info(
                f"Invidious 实例配置已刷新: 主实例={self.primary_url}, "
                f"备用实例数量={len(self.fallback_urls)}"
            )

    def get_instance_urls(self) -> list[str]:
        """获取去重后的全部实例地址"""
        urls = [self.primary_url]
        for url in self.fallback_urls:
            if url and url not in urls:
                urls.append(url)
        return urls

    def get_load_balance_summary(self) -> dict[str, Any]:
        """获取当前负载均衡策略摘要"""
        return {
            "strategy": "weighted_round_robin",
            "primary_weight": self.primary_weight,
            "fallback_weight": self.fallback_weight,
            "fallback_count": len(self.fallback_urls),
            "ratio_text": f"{self.primary_weight}:{self.fallback_weight}",
            "description": "主实例约 70%，备用实例整体约 30%" if self.fallback_urls else "仅主实例参与请求",
        }

    def _get_active_url(self) -> str:
        """按权重获取本次请求使用的实例 URL"""
        self.refresh_instances()
        pool = self._build_weighted_pool()
        if not pool:
            self.current_url = self.primary_url
            return self.current_url
        with self._lb_lock:
            selected_url = pool[self._lb_index % len(pool)]
            self._lb_index = (self._lb_index + 1) % len(pool)
        self.current_url = selected_url
        return selected_url

    def _switch_instance(self, failed_url: str = "") -> Optional[str]:
        """从失败实例切换到下一个候选实例"""
        self.refresh_instances()
        urls = self.get_instance_urls()
        if failed_url and failed_url in urls:
            failed_index = urls.index(failed_url)
            ordered_urls = urls[failed_index + 1:] + urls[:failed_index]
        else:
            ordered_urls = [url for url in urls if url != self.current_url]

        for next_url in ordered_urls:
            try:
                resp = self.session.get(f"{next_url}/api/v1/stats", timeout=5)
                if resp.status_code == 200:
                    self.current_url = next_url
                    logger.info(f"Invidious 实例切换至: {next_url}")
                    return next_url
            except requests.RequestException:
                continue

        logger.warning("所有 Invidious 实例均不可用")
        return None

    def _request(self, endpoint: str, params: Optional[dict] = None) -> Any:
        """发送 API 请求，失败时尝试切换实例重试"""
        selected_url = self._get_active_url()
        request_urls = [selected_url]
        last_error: Optional[requests.RequestException] = None

        for index, base_url in enumerate(request_urls):
            url = f"{base_url}{endpoint}"
            try:
                logger.debug(f"Invidious 请求: {url}")
                resp = self.session.get(url, params=params or {}, timeout=self.timeout)
                resp.raise_for_status()
                self.current_url = base_url
                return resp.json()
            except requests.RequestException as e:
                last_error = e
                logger.warning(f"Invidious 请求失败: {url} - {e}")
                if index == 0:
                    switched_url = self._switch_instance(base_url)
                    if switched_url and switched_url not in request_urls:
                        request_urls.append(switched_url)

        if last_error:
            raise last_error
        raise requests.RequestException("无可用 Invidious 实例")

    def search_videos(self, query: str, max_results: int = 20, sort_by: str = "relevance") -> list[dict]:
        """
        搜索视频

        Args:
            query: 搜索关键词
            max_results: 最大结果数
            sort_by: 排序方式 (relevance, date, view_count, rating)

        Returns:
            视频列表
        """
        try:
            results = self._request("/api/v1/search", {
                "q": query,
                "type": "video",
                "sort_by": sort_by,
            })
            logger.info(f"搜索视频: '{query}' (实例: {self.current_url})")

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

    def _build_weighted_pool(self) -> list[str]:
        """构建主 7 备用 3 的权重实例池"""
        pool = [self.primary_url] * self.primary_weight
        if self.fallback_urls and self.fallback_weight > 0:
            for index in range(self.fallback_weight):
                pool.append(self.fallback_urls[index % len(self.fallback_urls)])
        return pool

    @staticmethod
    def _load_primary_url() -> str:
        """从数据库设置加载主实例地址"""
        try:
            from app.db import database as db
            return _normalize_url(db.get_setting("invidious_url", config.INVIDIOUS_URL)) or config.INVIDIOUS_URL.rstrip("/")
        except Exception as e:
            logger.warning(f"读取 Invidious 主实例设置失败，使用配置文件默认值: {e}")
            return config.INVIDIOUS_URL.rstrip("/")

    @staticmethod
    def _load_fallback_urls(primary_url: str) -> list[str]:
        """从数据库设置加载备用实例地址"""
        try:
            from app.db import database as db
            raw_value = db.get_setting("invidious_fallback_urls", "[]")
        except Exception as e:
            logger.warning(f"读取 Invidious 备用实例设置失败，使用环境变量默认值: {e}")
            raw_value = json.dumps(config.INVIDIOUS_FALLBACK_URLS, ensure_ascii=False)

        fallback_urls = _parse_fallback_urls(raw_value)
        if not fallback_urls and config.INVIDIOUS_FALLBACK_URLS:
            fallback_urls = config.INVIDIOUS_FALLBACK_URLS

        urls = []
        for url in fallback_urls:
            normalized_url = _normalize_url(url)
            if normalized_url and normalized_url != primary_url and normalized_url not in urls:
                urls.append(normalized_url)
        return urls


def _parse_fallback_urls(raw_value: Any) -> list[str]:
    """解析备用实例设置值"""
    if isinstance(raw_value, list):
        return [str(item) for item in raw_value]
    raw_text = str(raw_value or "").strip()
    if not raw_text:
        return []
    try:
        parsed_value = json.loads(raw_text)
        if isinstance(parsed_value, list):
            return [str(item) for item in parsed_value]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in raw_text.replace("\n", ",").split(",") if item.strip()]


def _normalize_url(url: str) -> str:
    """规范化实例地址"""
    return str(url or "").strip().rstrip("/")


_invidious_client_instance: Optional["InvidiousClient"] = None


def get_invidious_client() -> "InvidiousClient":
    """获取 Invidious 客户端单例（延迟初始化）

    Returns:
        InvidiousClient 实例
    """
    global _invidious_client_instance
    if _invidious_client_instance is None:
        _invidious_client_instance = InvidiousClient()
    return _invidious_client_instance


def reset_invidious_client() -> None:
    """重置 Invidious 客户端实例（仅用于测试或配置更新）"""
    global _invidious_client_instance
    _invidious_client_instance = None
