"""
追漫阁 - Invidious 健康诊断
"""
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
import requests
from app import config
from app.core.invidious_client import get_invidious_client

DEFAULT_VIDEO_ID = "dQw4w9WgXcQ"

# YouTube 视频 ID 合法字符集与长度（11 位标准 ID，放宽到 6-20 容错）
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
# stats 接口为轻量探测，使用更短的超时，避免长尾实例拖慢整轮检测
STATS_PROBE_TIMEOUT = 10
# 探测各实例时并发上限，防止实例数较多时建立过多连接
PROBE_WORKERS = 4

# 同一时刻仅允许一次健康检测执行，避免并发请求重复探测耗尽 worker
_health_run_lock = threading.Lock()
# 保护 _last_health_result 的读写，避免读到半填充数据
_cache_lock = threading.Lock()

_last_health_result: dict[str, Any] = {
    "checked_at": "",
    "overall_status": "unknown",
    "primary_url": config.INVIDIOUS_URL.rstrip("/"),
    "active_url": config.INVIDIOUS_URL.rstrip("/"),
    "instances": [],
    "video_probe": {},
    "video_probes": [],
    "load_balance": {},
}


def is_valid_video_id(video_id: str) -> bool:
    """校验视频 ID 是否为合法字符集，防止路径游走与注入"""
    return bool(video_id and VIDEO_ID_PATTERN.match(video_id))


def check_invidious_health(video_id: str = DEFAULT_VIDEO_ID) -> dict[str, Any]:
    """检测 Invidious 实例健康状态

    通过 _health_run_lock 保证同一时刻仅有一个检测在执行：若已有检测进行中，
    直接返回其完成后写入的最近一次结果，避免并发请求重复探测。
    """
    if not _health_run_lock.acquire(blocking=False):
        # 已有检测进行中，返回最近一次结果，避免重复探测耗尽 worker
        return get_last_invidious_health()
    try:
        return _run_health_check(video_id)
    finally:
        _health_run_lock.release()


def _run_health_check(video_id: str) -> dict[str, Any]:
    """执行一轮完整的实例与视频链路检测"""
    client = get_invidious_client()
    client.refresh_instances()
    instance_items = _build_instance_items(client)
    with requests.Session() as session:
        # 并发探测各实例，缩短多实例场景下的整体耗时
        with ThreadPoolExecutor(max_workers=min(PROBE_WORKERS, len(instance_items) or 1)) as pool:
            instance_results = list(pool.map(
                lambda item: _check_instance(session, item), instance_items
            ))
        available_instances = [item for item in instance_results if item["available"]]
        probe_url = _resolve_probe_url(client.primary_url, available_instances)
        with ThreadPoolExecutor(max_workers=min(PROBE_WORKERS, len(available_instances) or 1)) as pool:
            video_probes = list(pool.map(
                lambda item: _check_video_detail(session, item["url"], video_id, item),
                available_instances,
            ))
    video_probe = _resolve_primary_video_probe(probe_url, video_probes) if video_probes else _empty_video_probe(video_id)
    overall_status = _resolve_overall_status(available_instances, video_probe)

    result = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "overall_status": overall_status,
        "primary_url": client.primary_url,
        # active_url 为本次视频详情探针选用的目标实例，并非客户端实际分发流量的实例
        "active_url": probe_url,
        "timeout": config.INVIDIOUS_API_TIMEOUT,
        "instances": instance_results,
        "video_probe": video_probe,
        "video_probes": video_probes,
        "load_balance": client.get_load_balance_summary() | {
            "available_count": len(available_instances),
            "total_count": len(instance_results),
        },
    }
    _save_last_health_result(result)
    return result


def get_last_invidious_health() -> dict[str, Any]:
    """获取最近一次 Invidious 健康检测结果（深拷贝，避免外部修改污染缓存）"""
    import copy
    with _cache_lock:
        return copy.deepcopy(_last_health_result)


def _build_instance_items(client) -> list[dict[str, Any]]:
    """构建带角色和权重的实例列表（权重取各实例独立配置）"""
    weights = client.instance_weights
    items = [{
        "url": client.primary_url,
        "role": "primary",
        "role_text": "主实例",
        "weight": weights.get(client.primary_url, client.primary_weight),
    }]
    for url in client.fallback_urls:
        items.append({
            "url": url,
            "role": "fallback",
            "role_text": "备用实例",
            "weight": weights.get(url, 0),
        })
    return items


def _check_instance(session: requests.Session, item: dict[str, Any]) -> dict[str, Any]:
    """检测单个 Invidious 实例连通性"""
    started_at = time.perf_counter()
    url = item["url"]
    result = {
        "url": url,
        "role": item.get("role", "fallback"),
        "role_text": item.get("role_text", "备用实例"),
        "weight": item.get("weight", 0),
        "endpoint": f"{url}/api/v1/stats",
        "available": False,
        "status_code": None,
        "latency_ms": None,
        "software": "",
        "version": "",
        "error": "",
    }
    try:
        response = session.get(result["endpoint"], timeout=min(config.INVIDIOUS_API_TIMEOUT, STATS_PROBE_TIMEOUT))
        result["status_code"] = response.status_code
        result["latency_ms"] = round((time.perf_counter() - started_at) * 1000)
        result["available"] = response.status_code == 200
        if response.headers.get("content-type", "").startswith("application/json"):
            payload = response.json()
            software = payload.get("software") or {}
            result["software"] = software.get("name", "")
            result["version"] = software.get("version", "")
        if not result["available"]:
            result["error"] = f"HTTP {response.status_code}"
    except Exception as e:
        result["latency_ms"] = round((time.perf_counter() - started_at) * 1000)
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def _resolve_probe_url(primary_url: str, available_instances: list[dict[str, Any]]) -> str:
    """选择健康检测的视频详情探针目标实例（主实例优先，否则首个可用）"""
    for item in available_instances:
        if item.get("url") == primary_url:
            return item["url"]
    return available_instances[0]["url"] if available_instances else primary_url


def _resolve_primary_video_probe(active_url: str, video_probes: list[dict[str, Any]]) -> dict[str, Any]:
    """选择汇总卡片展示的视频详情探针结果"""
    for probe in video_probes:
        if probe.get("url") == active_url:
            return probe
    return video_probes[0]


def _check_video_detail(session: requests.Session, url: str, video_id: str, item: dict[str, Any] | None = None) -> dict[str, Any]:
    """检测视频详情链路可用性"""
    started_at = time.perf_counter()
    endpoint = f"{url}/api/v1/videos/{video_id}"
    result = {
        "video_id": video_id,
        "url": url,
        "role": (item or {}).get("role", ""),
        "role_text": (item or {}).get("role_text", ""),
        "weight": (item or {}).get("weight", 0),
        "endpoint": endpoint,
        "available": False,
        "status_code": None,
        "latency_ms": None,
        "title": "",
        "channel_name": "",
        "error": "",
    }
    try:
        response = session.get(endpoint, timeout=config.INVIDIOUS_API_TIMEOUT)
        result["status_code"] = response.status_code
        result["latency_ms"] = round((time.perf_counter() - started_at) * 1000)
        result["available"] = response.status_code == 200
        if result["available"]:
            payload = response.json()
            result["title"] = payload.get("title", "")
            result["channel_name"] = payload.get("author", "")
        else:
            result["error"] = f"HTTP {response.status_code}"
    except Exception as e:
        result["latency_ms"] = round((time.perf_counter() - started_at) * 1000)
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def _empty_video_probe(video_id: str) -> dict[str, Any]:
    """构建未执行视频链路检测结果"""
    return {
        "video_id": video_id,
        "endpoint": "",
        "available": False,
        "status_code": None,
        "latency_ms": None,
        "title": "",
        "channel_name": "",
        "error": "无可用实例，已跳过视频详情链路检测",
    }


def _resolve_overall_status(available_instances: list[dict[str, Any]], video_probe: dict[str, Any]) -> str:
    """计算整体健康状态"""
    if not available_instances:
        return "down"
    if not video_probe.get("available"):
        return "degraded"
    return "healthy"


def _save_last_health_result(result: dict[str, Any]) -> None:
    """保存最近一次健康检测结果（加锁，保证读取方不会看到半填充数据）"""
    with _cache_lock:
        _last_health_result.clear()
        _last_health_result.update(result)
