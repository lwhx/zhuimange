"""
追漫阁 - Invidious 健康诊断
"""
import time
from datetime import datetime
from typing import Any
import requests
from app import config
from app.core.invidious_client import get_invidious_client

DEFAULT_VIDEO_ID = "dQw4w9WgXcQ"

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


def check_invidious_health(video_id: str = DEFAULT_VIDEO_ID) -> dict[str, Any]:
    """检测 Invidious 实例健康状态"""
    client = get_invidious_client()
    client.refresh_instances()
    instance_items = _build_instance_items(client)
    session = requests.Session()
    instance_results = [_check_instance(session, item) for item in instance_items]
    available_instances = [item for item in instance_results if item["available"]]
    active_url = _resolve_active_url(client.primary_url, available_instances)
    video_probes = [_check_video_detail(session, item["url"], video_id, item) for item in instance_results if item["available"]]
    video_probe = _resolve_primary_video_probe(active_url, video_probes) if video_probes else _empty_video_probe(video_id)
    overall_status = _resolve_overall_status(available_instances, video_probe)

    result = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "overall_status": overall_status,
        "primary_url": client.primary_url,
        "active_url": active_url,
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
    """获取最近一次 Invidious 健康检测结果"""
    return dict(_last_health_result)


def _build_instance_items(client) -> list[dict[str, Any]]:
    """构建带角色和权重的实例列表"""
    items = [{
        "url": client.primary_url,
        "role": "primary",
        "role_text": "主实例",
        "weight": client.primary_weight,
    }]
    fallback_count = len(client.fallback_urls)
    fallback_share = round(client.fallback_weight / fallback_count, 2) if fallback_count else 0
    for url in client.fallback_urls:
        items.append({
            "url": url,
            "role": "fallback",
            "role_text": "备用实例",
            "weight": fallback_share,
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
        response = session.get(result["endpoint"], timeout=min(config.INVIDIOUS_API_TIMEOUT, 10))
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


def _resolve_active_url(primary_url: str, available_instances: list[dict[str, Any]]) -> str:
    """选择健康检测的视频详情探针实例"""
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
    """保存最近一次健康检测结果"""
    _last_health_result.clear()
    _last_health_result.update(result)
