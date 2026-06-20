"""
追漫阁 - API 路由
"""
import logging
from typing import Optional
from datetime import date, datetime
from urllib.parse import urlparse, urlencode
import requests as _requests
from flask import Blueprint, request, jsonify, current_app, Response
from app.db import database as db
from app.core.tmdb_client import get_tmdb_client
from app.core.source_finder import find_sources_for_episode
from app.core.sync_queue import sync_queue
from app.core.source_health import check_episode_sources_health
from app.core.invidious_health import (
    check_invidious_health, get_last_invidious_health,
    is_valid_video_id, DEFAULT_VIDEO_ID,
)
from app.core.link_converter import invidious_to_youtube, format_duration, format_view_count
from app.core.response import success_response, error_response

logger = logging.getLogger(__name__)

api = Blueprint('api', __name__, url_prefix='/api')


def _clear_anime_cache(anime_id: Optional[int] = None):
    """清除相关缓存，使数据变更立即生效"""
    try:
        cache_extension = current_app.extensions.get('cache')
        cache_clients = []
        if hasattr(cache_extension, 'delete'):
            cache_clients.append(cache_extension)
        elif isinstance(cache_extension, dict):
            cache_clients.extend(client for client in cache_extension.keys() if hasattr(client, 'delete'))
            cache_clients.extend(client for client in cache_extension.values() if hasattr(client, 'delete'))

        keys = ['index_page']
        if anime_id:
            keys.extend([
                f'anime_detail_{anime_id}_asc',
                f'anime_detail_{anime_id}_desc',
            ])

        for client in cache_clients:
            for key in keys:
                client.delete(key)
    except Exception as e:
        logger.warning(f"清除缓存失败: {e}")


# ==================== 健康检查 ====================

@api.route('/health')
def health_check():
    """健康检查端点（豁免认证和速率限制）"""
    try:
        db.check_connection()
        return success_response({'status': 'healthy', 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return error_response("服务不健康", code="UNHEALTHY", status_code=503)


@api.route('/diagnostics/invidious', methods=['GET', 'POST'])
def invidious_diagnostics():
    """Invidious 健康诊断"""
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        video_id = (data.get('video_id') or DEFAULT_VIDEO_ID).strip()
        # 校验视频 ID 合法字符集，防止路径游走与注入
        if not is_valid_video_id(video_id):
            return error_response("视频 ID 格式非法，仅允许字母、数字、_、-（6-20 位）", code="INVALID_VIDEO_ID")
        result = check_invidious_health(video_id=video_id)
        return success_response(result, message="Invidious 健康检测完成")
    return success_response(get_last_invidious_health(), message="获取 Invidious 最近健康状态成功")


# ==================== 搜索 ====================

@api.route('/search')
def search_anime():
    """搜索动漫"""
    query = request.args.get('q', '').strip()
    if not query:
        return error_response("请输入搜索关键词")

    results = get_tmdb_client().search_anime(query)
    return success_response(results, message="搜索完成")


# ==================== 动漫管理 ====================

@api.route('/anime/add', methods=['POST'])
def add_anime():
    """从 TMDB 添加动漫"""
    data = request.get_json(silent=True) or {}
    tmdb_id = data.get('tmdb_id')
    if not tmdb_id:
        return error_response("缺少 tmdb_id")

    # 检查是否已添加
    existing = db.get_anime_by_tmdb_id(tmdb_id)
    if existing:
        return error_response("该动漫已添加", code="ANIME_EXISTS")

    # 从 TMDB 获取详情
    detail = get_tmdb_client().get_anime_detail(tmdb_id)
    if not detail:
        return error_response("无法获取动漫信息", code="TMDB_ERROR", status_code=500)

    # 保存动漫
    anime_id = db.add_anime(detail)

    # 获取并保存集数
    if detail.get("seasons"):
        episodes = get_tmdb_client().get_all_episodes(tmdb_id, detail["seasons"])
        if episodes:
            db.add_episodes(anime_id, episodes)

    _clear_anime_cache()
    return success_response({"anime_id": anime_id}, message="动漫添加成功")



@api.route('/anime/add_manual', methods=['POST'])
def add_anime_manual():
    """手动添加动漫"""
    data = request.get_json(silent=True) or {}
    title = data.get('title', '').strip()
    if not title:
        return error_response("缺少动漫名称")

    total_episodes = data.get('total_episodes', 0)

    # 自动搜索封面：如果没提供 poster_url，尝试从 TMDB 搜索
    poster_url = data.get('poster_url', '')
    if not poster_url:
        try:
            tmdb_results = get_tmdb_client().search_anime(title)
            if tmdb_results:
                poster_url = tmdb_results[0].get('poster_url', '')
                logger.info(f"手动添加动漫自动获取封面: {title} → {poster_url[:50]}...")
        except Exception as e:
            logger.warning(f"自动搜索封面失败: {title} - {e}")

    anime_id = db.add_anime({
        "tmdb_id": None,
        "title_cn": title,
        "title_en": "",
        "poster_url": poster_url,
        "overview": "",
        "air_date": "",
        "total_episodes": total_episodes,
        "status": data.get('status', 'Returning Series'),
    })

    # 创建集数记录
    if total_episodes > 0:
        episodes = [
            {"absolute_num": i, "episode_number": i, "season_number": 1}
            for i in range(1, total_episodes + 1)
        ]
        db.add_episodes(anime_id, episodes)

    # 添加别名
    for alias in data.get('aliases', []):
        if alias.strip():
            db.add_alias(anime_id, alias.strip())

    _clear_anime_cache(anime_id)
    return success_response({"anime_id": anime_id}, message="手动添加动漫成功")


@api.route('/anime/<int:anime_id>', methods=['DELETE'])
def delete_anime(anime_id):
    """删除动漫"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)
    db.delete_anime(anime_id)
    _clear_anime_cache()
    return success_response(message="动漫删除成功")


@api.route('/anime/list')
def list_animes():
    """获取所有动漫列表"""
    today = date.today().isoformat()
    animes = db.get_all_animes_with_stats(today)
    return success_response(animes, message="获取动漫列表成功")


@api.route('/anime/<int:anime_id>')
def get_anime(anime_id):
    """获取动漫详情"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    today = date.today().isoformat()
    episodes = db.filter_aired_episodes(anime, db.get_episodes(anime_id), today)
    aliases = db.get_aliases(anime_id)
    rules = db.get_source_rules(anime_id)
    source_counts = db.get_episode_source_counts(anime_id)

    for ep in episodes:
        ep["source_count"] = source_counts.get(ep["id"], 0)

    anime["episodes"] = episodes
    anime["aliases"] = aliases
    anime["rules"] = rules
    anime["watched_ep"] = sum(1 for ep in episodes if ep.get("watched"))
    anime["unwatched_count"] = sum(1 for ep in episodes if not ep.get("watched"))

    return success_response(anime, message="获取动漫详情成功")


# ==================== 进度管理 ====================

@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/watch', methods=['POST'])
def mark_watched(anime_id, ep_num):
    """标记集数已看"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    episode = db.get_episode_by_num(anime_id, ep_num)
    if not episode:
        return error_response("集数不存在", code="EPISODE_NOT_FOUND", status_code=404)
    if not db.episode_is_aired(anime, episode, date.today().isoformat()):
        return error_response("集数尚未开播", code="EPISODE_NOT_AIRED", status_code=400)

    db.mark_episode_watched(anime_id, ep_num, True)
    _clear_anime_cache(anime_id)
    return success_response(message="标记已看成功")


@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/unwatch', methods=['POST'])
def mark_unwatched(anime_id, ep_num):
    """标记集数未看"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    episode = db.get_episode_by_num(anime_id, ep_num)
    if not episode:
        return error_response("集数不存在", code="EPISODE_NOT_FOUND", status_code=404)
    if not db.episode_is_aired(anime, episode, date.today().isoformat()):
        return error_response("集数尚未开播", code="EPISODE_NOT_AIRED", status_code=400)

    db.mark_episode_watched(anime_id, ep_num, False)
    _clear_anime_cache(anime_id)
    return success_response(message="标记未看成功")


@api.route('/anime/<int:anime_id>/progress', methods=['PUT'])
def update_progress(anime_id):
    """更新观看进度"""
    data = request.get_json(silent=True) or {}
    watched_ep = data.get('watched_ep')
    if watched_ep is None:
        return error_response("缺少 watched_ep")

    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)
    try:
        watched_ep = int(watched_ep)
    except (TypeError, ValueError):
        return error_response("watched_ep 必须是数字")

    # 批量标记已看：单次事务完成，避免逐集 UPDATE 的 N 次往返
    today = date.today().isoformat()
    episodes = db.get_episodes(anime_id)
    aired_episodes = db.filter_aired_episodes(anime, episodes, today)
    if aired_episodes:
        watched_ep = min(watched_ep, max(ep["absolute_num"] for ep in aired_episodes))

    watched_count = db.set_watched_up_to(anime_id, watched_ep, today)

    _clear_anime_cache(anime_id)
    return success_response({"watched_count": watched_count}, message=f"更新观看进度成功，已看 {watched_count} 集")


# ==================== 视频源 ====================

@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/sources')
def get_sources(anime_id, ep_num):
    """获取集数的视频源"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    episode = db.get_episode_by_num(anime_id, ep_num)
    if not episode:
        return error_response("集数不存在", code="EPISODE_NOT_FOUND", status_code=404)
    if not db.episode_is_aired(anime, episode, date.today().isoformat()):
        return error_response("集数尚未开播", code="EPISODE_NOT_AIRED", status_code=400)

    sources = db.get_sources_for_episode(episode["id"])

    # 附加链接和格式化信息
    for source in sources:
        source["youtube_url"] = invidious_to_youtube(source["video_id"])
        source["duration_fmt"] = format_duration(source.get("duration", 0))
        source["view_count_fmt"] = format_view_count(source.get("view_count", 0))

    return success_response(sources, message="获取视频源成功")


@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/find_sources', methods=['POST'])
def find_sources(anime_id, ep_num):
    """主动搜索视频源"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    episode = db.get_episode_by_num(anime_id, ep_num)
    if not episode:
        return error_response("集数不存在", code="EPISODE_NOT_FOUND", status_code=404)
    if not db.episode_is_aired(anime, episode, date.today().isoformat()):
        return error_response("集数尚未开播", code="EPISODE_NOT_AIRED", status_code=400)

    force = (request.get_json(silent=True) or {}).get('force', False)
    sources = find_sources_for_episode(anime_id, ep_num, force=force)
    return success_response({"count": len(sources)}, message=f"找到 {len(sources)} 个视频源")


@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/check_sources', methods=['POST'])
def check_sources(anime_id, ep_num):
    """检测集数视频源可用性"""
    result = check_episode_sources_health(anime_id, ep_num)
    if not result.get("success"):
        code = result.get("code", "EPISODE_NOT_FOUND")
        status_code = 400 if code == "EPISODE_NOT_AIRED" else 404
        return error_response(result.get("message", "检测失败"), code=code, status_code=status_code)
    return success_response(result, message=result.get("message", "检测完成"))


# ==================== 同步 ====================

@api.route('/anime/<int:anime_id>/sync', methods=['POST'])
def sync_anime(anime_id):
    """提交动漫视频源同步任务"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'incremental')
    task, created = sync_queue.enqueue(anime_id, mode=mode, sync_type="manual")
    message = "同步任务已加入队列" if created else "该动漫已有同步任务正在执行"
    return success_response(
        {
            "task": task.snapshot(),
            "created": created,
        },
        message=message,
        status_code=202 if created else 200,
    )


@api.route('/sync_tasks/<task_id>')
def get_sync_task(task_id):
    """获取同步任务状态"""
    task = sync_queue.get_task_snapshot(task_id)
    if not task:
        return error_response("同步任务不存在", code="SYNC_TASK_NOT_FOUND", status_code=404)
    return success_response(task, message="获取同步任务状态成功")


@api.route('/sync_tasks/<task_id>/stream')
def sync_task_stream(task_id):
    """SSE 监听同步任务事件"""
    task = sync_queue.get_task(task_id)
    if not task:
        return error_response("同步任务不存在", code="SYNC_TASK_NOT_FOUND", status_code=404)
    return _stream_sync_task(task)


@api.route('/anime/<int:anime_id>/sync_stream')
def sync_anime_stream(anime_id):
    """兼容旧入口：提交/复用同步任务并流式返回进度"""

    mode = request.args.get('mode', 'incremental')
    if mode not in {'incremental', 'full'}:
        mode = 'incremental'

    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    task, _created = sync_queue.enqueue(anime_id, mode=mode, sync_type="manual")
    return _stream_sync_task(task)


def _stream_sync_task(task):
    """把任务事件缓冲区转换成 SSE 响应。"""
    import json as _json
    from flask import Response, stream_with_context

    def generate():
        last_seq = 0
        terminal_status = {"success", "error"}
        while True:
            with task.condition:
                events = [event for event in task.events if event.get("_seq", 0) > last_seq]
                while not events and task.status not in terminal_status:
                    notified = task.condition.wait(timeout=15)
                    events = [event for event in task.events if event.get("_seq", 0) > last_seq]
                    if not notified and not events:
                        break

            if not events and task.status not in terminal_status:
                yield f"data: {_json.dumps({'type': 'heartbeat', 'task_id': task.id}, ensure_ascii=False)}\n\n"
                continue

            for event in events:
                last_seq = max(last_seq, int(event.get("_seq", 0)))
                yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"

            if task.status in terminal_status:
                break

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )


# ==================== 设置 ====================

@api.route('/settings')
def get_settings():
    """获取所有设置"""
    settings = db.get_all_settings()
    return success_response(settings, message="获取设置成功")


# 允许通过 /api/settings 写入的字段白名单。
# 敏感字段（如 auth_password）必须走专用接口，防止绕过旧密码校验。
_SETTINGS_WHITELIST = frozenset({
    "auto_sync_enabled", "auto_sync_interval",
    "match_threshold", "match_recommend_threshold",
    "invidious_url", "invidious_fallback_urls", "invidious_instance_weights",
    "tg_bot_token", "tg_chat_id",
    "tg_notify_enabled", "tg_backup_enabled", "tg_backup_interval_days",
    "episode_sort_order",
})


@api.route('/settings', methods=['PUT'])
def update_settings():
    """更新设置"""
    data = request.get_json(silent=True) or {}
    ignored = []
    for key, value in data.items():
        if key in _SETTINGS_WHITELIST:
            db.set_setting(key, str(value))
        else:
            ignored.append(key)
    if ignored:
        logger.warning(f"update_settings 忽略非白名单字段: {ignored}")

    # 如果更新了同步间隔，动态调整调度器
    if 'auto_sync_interval' in data:
        from app.core.scheduler import update_sync_interval
        try:
            update_sync_interval(int(data['auto_sync_interval']))
        except Exception as e:
            logger.error(f"更新调度器间隔失败: {e}")

    # 如果更新了 TG 备份设置，动态调整定时任务
    if 'tg_backup_enabled' in data or 'tg_backup_interval_days' in data:
        from app.core.scheduler import update_tg_backup_schedule
        try:
            enabled = db.get_setting("tg_backup_enabled", "false") == "true"
            days = int(db.get_setting("tg_backup_interval_days", "1"))
            update_tg_backup_schedule(enabled, days)
        except Exception as e:
            logger.error(f"更新 TG 备份计划失败: {e}")

    # 如果更新了 Invidious 设置，重置客户端以便立即加载新实例配置
    if 'invidious_url' in data or 'invidious_fallback_urls' in data or 'invidious_instance_weights' in data:
        from app.core.invidious_client import reset_invidious_client
        reset_invidious_client()

    return success_response(message="更新设置成功")


@api.route('/change_password', methods=['POST'])
def change_password():
    """修改访问密码"""
    from app.core.auth import hash_password, verify_password
    data = request.get_json(silent=True) or {}
    old_pwd = data.get('old_password', '')
    new_pwd = data.get('new_password', '')

    if not old_pwd or not new_pwd:
        return error_response("请填写完整")
    if len(new_pwd) < 8:
        return error_response("新密码至少8位", code="PASSWORD_TOO_SHORT")

    stored_hash = db.get_setting('auth_password', '')

    if not verify_password(old_pwd, stored_hash):
        return error_response("当前密码错误", code="INVALID_PASSWORD")

    new_hash = hash_password(new_pwd)
    db.set_setting('auth_password', new_hash)
    return success_response(message="密码修改成功")


# ==================== 搜索规则 ====================

@api.route('/anime/<int:anime_id>/rules', methods=['PUT'])
def update_rules(anime_id):
    """更新动漫搜索规则"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    data = request.get_json(silent=True) or {}
    db.set_source_rules(anime_id, data)
    _clear_anime_cache(anime_id)
    return success_response(message="更新搜索规则成功")


# ==================== 别名管理 ====================

@api.route('/anime/<int:anime_id>/aliases', methods=['POST'])
def add_anime_alias(anime_id):
    """添加动漫别名"""
    data = request.get_json(silent=True) or {}
    alias = data.get('alias', '').strip()
    if not alias:
        return error_response("缺少别名")

    db.add_alias(anime_id, alias)
    _clear_anime_cache(anime_id)
    return success_response(message="添加别名成功")


# ==================== 同步日志 ====================

@api.route('/sync_logs')
def get_sync_logs():
    """获取同步日志"""
    anime_id = request.args.get('anime_id', type=int)
    limit = request.args.get('limit', 20, type=int)
    logs = db.get_sync_logs(anime_id, limit)
    return success_response(logs, message="获取同步日志成功")


# ==================== 备份与恢复 ====================

@api.route('/backup/export')
def backup_export():
    """导出备份 JSON 文件"""
    from app.core.backup import export_json
    from flask import Response
    from datetime import datetime

    json_str = export_json()
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"zhuimange_backup_{now}.json"

    return Response(
        json_str,
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@api.route('/backup/import', methods=['POST'])
def backup_import():
    """导入备份 JSON"""
    from app.core.backup import import_data

    file = request.files.get('file')
    if not file:
        # 尝试从 JSON body 读取
        data = request.get_json(silent=True)
        if not data:
            return error_response("请上传备份文件")
    else:
        try:
            import json as _json
            data = _json.loads(file.read().decode('utf-8'))
        except Exception as e:
            return error_response(f"文件解析失败: {e}", code="FILE_PARSE_ERROR")

    if data.get("app") != "追漫阁":
        return error_response("无效的备份文件", code="INVALID_BACKUP_FILE")
    if not isinstance(data.get("animes"), list):
        return error_response("备份文件格式错误：缺少 animes 列表", code="INVALID_BACKUP_FILE")

    stats = import_data(data)
    return success_response(stats, message="备份导入成功")


@api.route('/backup/telegram', methods=['POST'])
def backup_telegram():
    """发送备份到 Telegram"""
    from app.core.backup import send_backup_to_telegram
    result = send_backup_to_telegram()
    if result["success"]:
        return success_response(result, message="备份发送成功")
    return error_response(result.get("error", "备份发送失败"), status_code=400)


@api.route('/backup/local', methods=['POST'])
def backup_local():
    """发送备份到本地文件"""
    from app.core.backup import save_backup_local
    result = save_backup_local()
    if result["success"]:
        return success_response(result, message="本地备份成功")
    return error_response(result.get("error", "本地备份失败"), status_code=400)


@api.route('/backup/logs')
def backup_logs():
    """获取备份日志"""
    backup_type = request.args.get('type')
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int) or 50

    logs = db.get_backup_logs(backup_type=backup_type, status=status, limit=limit)
    return success_response(logs)


@api.route('/backup/stats')
def backup_stats():
    """获取备份统计信息"""
    days = request.args.get('days', 30, type=int) or 30
    stats = db.get_backup_stats(days=days)
    return success_response(stats)


@api.route('/backup/scheduler/status')
def scheduler_status():
    """获取调度器状态"""
    from app.core.scheduler import scheduler
    
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": str(job.next_run_time) if job.next_run_time else None
        })
    
    return success_response({
        "running": scheduler.running,
        "jobs": jobs
    })


@api.route('/backup/storage/check')
def storage_check():
    """检查存储空间可用性"""
    import os
    import shutil
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backup_dir = os.path.join(base_dir, "data", "backups")
    
    # 检查备份目录
    backup_dir_exists = os.path.exists(backup_dir)
    backup_dir_writable = False
    
    if backup_dir_exists:
        try:
            test_file = os.path.join(backup_dir, ".write_test")
            with open(test_file, "w") as f:
                f.write("test")
            os.unlink(test_file)
            backup_dir_writable = True
        except Exception:
            backup_dir_writable = False
    
    # 获取磁盘空间
    total_space = 0
    free_space = 0
    used_space = 0
    
    try:
        total, used, free = shutil.disk_usage(base_dir)
        total_space = total
        used_space = used
        free_space = free
    except Exception as e:
        return error_response(f"获取磁盘空间失败: {str(e)}")
    
    # 统计备份文件数量和总大小
    backup_files = []
    backup_count = 0
    backup_size = 0
    
    if backup_dir_exists:
        try:
            for filename in os.listdir(backup_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(backup_dir, filename)
                    file_size = os.path.getsize(filepath)
                    backup_count += 1
                    backup_size += file_size
                    backup_files.append({
                        "filename": filename,
                        "size": file_size,
                        "created_at": datetime.fromtimestamp(os.path.getctime(filepath)).isoformat()
                    })
        except Exception as e:
            logger.warning(f"统计备份文件失败: {e}")
    
    return success_response({
        "backup_dir": {
            "exists": backup_dir_exists,
            "writable": backup_dir_writable
        },
        "disk": {
            "total_bytes": total_space,
            "used_bytes": used_space,
            "free_bytes": free_space,
            "total_gb": round(total_space / 1024 / 1024 / 1024, 2),
            "used_gb": round(used_space / 1024 / 1024 / 1024, 2),
            "free_gb": round(free_space / 1024 / 1024 / 1024, 2),
            "usage_percent": round(used_space / total_space * 100, 2) if total_space > 0 else 0
        },
        "backups": {
            "count": backup_count,
            "total_space_bytes": backup_size,
            "total_size_mb": round(backup_size / 1024 / 1024, 2),
            "files": backup_files
        }
    })


# ==================== 图片代理（解决 HTTPS 混合内容） ====================

# 固定白名单域名，加上用户配置的 Invidious 实例域名
_PROXY_HOST_WHITELIST = {
    'image.tmdb.org', 'img.youtube.com', 'i.ytimg.com', 'lain.bgm.net',
}


def _get_proxy_whitelist_hosts():
    """合并固定白名单与当前配置的 Invidious 实例域名"""
    hosts = set(_PROXY_HOST_WHITELIST)
    try:
        from app.core.invidious_client import get_invidious_client
        client = get_invidious_client()
        client.refresh_instances()
        for url in [client.primary_url, *client.fallback_urls]:
            host = urlparse(url).hostname
            if host:
                hosts.add(host)
    except Exception:
        pass
    return hosts


@api.route('/proxy_image')
def proxy_image():
    """图片代理：同源转发外部图片，解决 HTTPS 站点加载 HTTP 图片的混合内容拦截。

    仅代理白名单域名（Invidious 实例 + TMDB/YouTube），防止 SSRF 滥用。
    浏览器请求本接口（同源 HTTPS），后端拉取外部图片并流式返回。
    """
    target_url = request.args.get('url', '').strip()
    if not target_url:
        return error_response('缺少 url 参数', code='MISSING_URL', status_code=400)

    parsed = urlparse(target_url)
    # SSRF 防护：仅允许 http/https 且主机在白名单
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return error_response('非法的图片地址', code='INVALID_URL', status_code=400)
    if parsed.hostname not in _get_proxy_whitelist_hosts():
        return error_response('该图片域名不在允许列表内', code='HOST_NOT_ALLOWED', status_code=403)

    try:
        upstream = _requests.get(target_url, stream=True, timeout=10,
                                 headers={'User-Agent': 'zhuimange-image-proxy/1.0'})
        if upstream.status_code != 200:
            return error_response(f'上游返回 {upstream.status_code}', code='UPSTREAM_ERROR', status_code=502)

        content_type = upstream.headers.get('Content-Type', 'image/jpeg')
        # 仅允许图片类型透传
        if not content_type.startswith('image/'):
            return error_response('非图片内容', code='NOT_IMAGE', status_code=415)

        def generate():
            try:
                for chunk in upstream.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        resp = Response(generate(), content_type=content_type)
        # 代理图片可长期缓存（海报/缩略图稳定），减轻重复代理开销
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        return resp
    except _requests.RequestException as e:
        logger.warning(f'图片代理失败: {target_url} -> {e}')
        return error_response('图片代理请求失败', code='PROXY_ERROR', status_code=502)
