"""
追漫阁 - API 路由
"""
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from app.db import database as db
from app.core.tmdb_client import tmdb_client
from app.core.source_finder import find_sources_for_episode, sync_anime_sources
from app.core.link_converter import invidious_to_youtube, format_duration, format_view_count
from app.core.response import success_response, error_response

logger = logging.getLogger(__name__)

api = Blueprint('api', __name__, url_prefix='/api')


def _clear_index_cache():
    """清除首页缓存，使数据变更立即生效"""
    try:
        from flask import current_app
        cache = current_app.extensions.get('cache')
        if cache:
            cache.delete('index_page')
    except Exception:
        pass


# ==================== 健康检查 ====================

@api.route('/health')
def health_check():
    """健康检查端点（豁免认证和速率限制）"""
    try:
        db.check_connection()
        return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 503


# ==================== 搜索 ====================

@api.route('/search')
def search_anime():
    """搜索动漫 (TMDB)"""
    query = request.args.get('q', '').strip()
    if not query:
        return error_response("请输入搜索关键词")

    results = tmdb_client.search_anime(query)
    return jsonify(results)


# ==================== 动漫管理 ====================

@api.route('/anime/add', methods=['POST'])
def add_anime():
    """从 TMDB 添加动漫"""
    data = request.json or {}
    tmdb_id = data.get('tmdb_id')
    if not tmdb_id:
        return error_response("缺少 tmdb_id")

    # 检查是否已添加
    existing = db.get_anime_by_tmdb_id(tmdb_id)
    if existing:
        return error_response("该动漫已添加", code="ANIME_EXISTS")

    # 从 TMDB 获取详情
    detail = tmdb_client.get_anime_detail(tmdb_id)
    if not detail:
        return error_response("无法获取动漫信息", code="TMDB_ERROR", status_code=500)

    # 保存动漫
    anime_id = db.add_anime(detail)

    # 获取并保存集数
    if detail.get("seasons"):
        episodes = tmdb_client.get_all_episodes(tmdb_id, detail["seasons"])
        if episodes:
            db.add_episodes(anime_id, episodes)

    return success_response({"anime_id": anime_id}, message="动漫添加成功")



@api.route('/anime/add_manual', methods=['POST'])
def add_anime_manual():
    """手动添加动漫"""
    data = request.json or {}
    title = data.get('title', '').strip()
    if not title:
        return error_response("缺少动漫名称")

    total_episodes = data.get('total_episodes', 0)

    # 自动搜索封面：如果没提供 poster_url，尝试从 TMDB 搜索
    poster_url = data.get('poster_url', '')
    if not poster_url:
        try:
            tmdb_results = tmdb_client.search_anime(title)
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

    _clear_index_cache()
    return success_response({"anime_id": anime_id}, message="手动添加动漫成功")


@api.route('/anime/<int:anime_id>', methods=['DELETE'])
def delete_anime(anime_id):
    """删除动漫"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)
    db.delete_anime(anime_id)
    _clear_index_cache()
    return success_response(message="动漫删除成功")


@api.route('/anime/list')
def list_animes():
    """获取所有动漫列表"""
    animes = db.get_all_animes()
    # 为每个动漫附加未看集数统计
    for anime in animes:
        episodes = db.get_episodes(anime["id"])
        anime["unwatched_count"] = sum(1 for ep in episodes if not ep.get("watched"))
        anime["episode_count"] = len(episodes)
    return success_response(animes, message="获取动漫列表成功")


@api.route('/anime/<int:anime_id>')
def get_anime(anime_id):
    """获取动漫详情"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    episodes = db.get_episodes(anime_id)
    aliases = db.get_aliases(anime_id)
    rules = db.get_source_rules(anime_id)

    # 为每集附加视频源数量
    for ep in episodes:
        sources = db.get_sources_for_episode(ep["id"])
        ep["source_count"] = len(sources)

    anime["episodes"] = episodes
    anime["aliases"] = aliases
    anime["rules"] = rules
    anime["unwatched_count"] = sum(1 for ep in episodes if not ep.get("watched"))

    return success_response(anime, message="获取动漫详情成功")


# ==================== 进度管理 ====================

@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/watch', methods=['POST'])
def mark_watched(anime_id, ep_num):
    """标记集数已看"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    db.mark_episode_watched(anime_id, ep_num, True)
    _clear_index_cache()
    return success_response(message="标记已看成功")


@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/unwatch', methods=['POST'])
def mark_unwatched(anime_id, ep_num):
    """标记集数未看"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    db.mark_episode_watched(anime_id, ep_num, False)
    _clear_index_cache()
    return success_response(message="标记未看成功")


@api.route('/anime/<int:anime_id>/progress', methods=['PUT'])
def update_progress(anime_id):
    """更新观看进度"""
    data = request.json or {}
    watched_ep = data.get('watched_ep')
    if watched_ep is None:
        return error_response("缺少 watched_ep")

    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    # 批量标记已看
    episodes = db.get_episodes(anime_id)
    for ep in episodes:
        if ep["absolute_num"] <= watched_ep:
            db.mark_episode_watched(anime_id, ep["absolute_num"], True)
        else:
            db.mark_episode_watched(anime_id, ep["absolute_num"], False)

    db.update_anime(anime_id, {"watched_ep": watched_ep})
    _clear_index_cache()
    return success_response(message="更新观看进度成功")


# ==================== 视频源 ====================

@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/sources')
def get_sources(anime_id, ep_num):
    """获取集数的视频源"""
    episode = db.get_episode_by_num(anime_id, ep_num)
    if not episode:
        return error_response("集数不存在", code="EPISODE_NOT_FOUND", status_code=404)

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
    force = request.json.get('force', False) if request.json else False
    sources = find_sources_for_episode(anime_id, ep_num, force=force)
    return success_response({"count": len(sources)}, message=f"找到 {len(sources)} 个视频源")


# ==================== 同步 ====================

@api.route('/anime/<int:anime_id>/sync', methods=['POST'])
def sync_anime(anime_id):
    """同步动漫视频源"""
    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    result = sync_anime_sources(anime_id)
    if result.get("success"):
        return success_response(result, message="同步完成")
    return error_response(result.get("message", "同步失败"), status_code=500)


@api.route('/anime/<int:anime_id>/sync_stream')
def sync_anime_stream(anime_id):
    """SSE 流式同步动漫视频源（实时进度）"""
    import json as _json
    from flask import Response, stream_with_context

    anime = db.get_anime(anime_id)
    if not anime:
        return error_response("动漫不存在", code="ANIME_NOT_FOUND", status_code=404)

    def generate():
        from app.core.source_finder import find_sources_for_episode
        from app.core.matcher.preprocessor import extract_episode_number
        from app.core.invidious_client import invidious_client
        from concurrent.futures import ThreadPoolExecutor, as_completed

        try:
            is_manual = anime.get("tmdb_id") is None

            # ===== 阶段 1: 手动动漫实时探测集数 =====
            if is_manual:
                yield f"data: {_json.dumps({'type': 'discovering', 'message': '正在探测集数...'}, ensure_ascii=False)}\n\n"

                title = anime.get("title_cn", "")
                aliases_list = db.get_aliases(anime_id)
                search_terms = [title] + aliases_list[:3]
                max_ep = 0

                for term in search_terms:
                    if not term:
                        continue
                    try:
                        videos = invidious_client.search_videos(term, max_results=50)
                        for video in videos:
                            ep = extract_episode_number(video.get("title", ""))
                            if ep is not None and ep > max_ep:
                                max_ep = ep
                    except Exception as e:
                        logger.error(f"探测集数搜索失败: {term} - {e}")

                if max_ep > 0:
                    # 创建缺少的集数记录
                    existing_episodes = db.get_episodes(anime_id)
                    existing_nums = {ep["absolute_num"] for ep in existing_episodes}

                    new_episodes = []
                    for i in range(1, max_ep + 1):
                        if i not in existing_nums:
                            new_episodes.append({
                                "absolute_num": i,
                                "episode_number": i,
                                "season_number": 1,
                            })

                    if new_episodes:
                        db.add_episodes(anime_id, new_episodes)
                        db.update_anime(anime_id, {"total_episodes": max_ep})
                        logger.info(f"自动创建 {len(new_episodes)} 个集数记录")

                    # 推送 discover 事件，前端实时创建集数 DOM
                    new_ep_nums = [ep["absolute_num"] for ep in new_episodes]
                    yield f"data: {_json.dumps({'type': 'discover', 'new_episodes': new_ep_nums, 'total': max_ep}, ensure_ascii=False)}\n\n"

            # ===== 阶段 2: 同步视频源 =====
            episodes = db.get_episodes(anime_id)
            episodes.reverse()  # 从最新集开始同步
            total = len(episodes)

            yield f"data: {_json.dumps({'type': 'start', 'total': total}, ensure_ascii=False)}\n\n"

            synced = 0
            total_sources = 0
            done_count = 0
            first_video_id = None
            BATCH_SIZE = 4

            def _sync_ep(ep):
                ep_num = ep["absolute_num"]
                try:
                    sources = find_sources_for_episode(anime_id, ep_num, force=True)
                    return ep_num, len(sources) if sources else 0
                except Exception as e:
                    logger.error(f"同步失败: {anime['title_cn']} 第{ep_num}集 - {e}")
                    return ep_num, 0

            with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
                futures = {executor.submit(_sync_ep, ep): ep for ep in episodes}
                for future in as_completed(futures):
                    ep_num, count = future.result()
                    done_count += 1
                    if count > 0:
                        synced += 1
                        total_sources += count
                        # 记录第一个有源的视频 ID（用于封面）
                        if first_video_id is None:
                            ep_obj = next((e for e in episodes if e["absolute_num"] == ep_num), None)
                            if ep_obj:
                                srcs = db.get_sources_for_episode(ep_obj.get("id", 0))
                                if srcs:
                                    first_video_id = srcs[0].get("video_id", "")
                    yield f"data: {_json.dumps({'type': 'episode', 'current': done_count, 'total': total, 'ep_num': ep_num, 'source_count': count}, ensure_ascii=False)}\n\n"

            # ===== 阶段 3: 封面和收尾 =====
            db.touch_anime_sync(anime_id)

            # 手动动漫自动设置封面（高清缩略图）
            poster_url = None
            if is_manual:
                a = db.get_anime(anime_id)
                if not a.get("poster_url") and first_video_id:
                    poster_url = f"https://img.youtube.com/vi/{first_video_id}/hqdefault.jpg"
                    db.update_anime(anime_id, {"poster_url": poster_url})
                    logger.info(f"自动设置封面(高清缩略图): {poster_url}")
                    # 推送封面更新事件
                    yield f"data: {_json.dumps({'type': 'poster', 'poster_url': poster_url}, ensure_ascii=False)}\n\n"

            db.add_sync_log(
                anime_id=anime_id, sync_type="manual",
                episodes_synced=synced, sources_found=total_sources,
                status="success",
                message=f"同步完成: {synced}/{total} 集找到视频源"
            )

            yield f"data: {_json.dumps({'type': 'done', 'synced': synced, 'total_sources': total_sources}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception(f"同步流发生错误: {e}")
            yield f"data: {_json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

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


@api.route('/settings', methods=['PUT'])
def update_settings():
    """更新设置"""
    data = request.json or {}
    for key, value in data.items():
        db.set_setting(key, str(value))

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

    return success_response(message="更新设置成功")


@api.route('/change_password', methods=['POST'])
def change_password():
    """修改访问密码"""
    from app.core.auth import hash_password, verify_password
    data = request.json or {}
    old_pwd = data.get('old_password', '')
    new_pwd = data.get('new_password', '')

    if not old_pwd or not new_pwd:
        return error_response("请填写完整")
    if len(new_pwd) < 4:
        return error_response("新密码至少4位", code="PASSWORD_TOO_SHORT")

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

    data = request.json or {}
    db.set_source_rules(anime_id, data)
    return success_response(message="更新搜索规则成功")


# ==================== 别名管理 ====================

@api.route('/anime/<int:anime_id>/aliases', methods=['POST'])
def add_anime_alias(anime_id):
    """添加动漫别名"""
    data = request.json or {}
    alias = data.get('alias', '').strip()
    if not alias:
        return error_response("缺少别名")

    db.add_alias(anime_id, alias)
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
        data = request.json
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
    limit = int(request.args.get('limit', 50))
    
    logs = db.get_backup_logs(backup_type=backup_type, status=status, limit=limit)
    return success_response(logs)


@api.route('/backup/stats')
def backup_stats():
    """获取备份统计信息"""
    days = int(request.args.get('days', 30))
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
            "path": backup_dir,
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
            "total_size_bytes": backup_size,
            "total_size_mb": round(backup_size / 1024 / 1024, 2),
            "files": backup_files
        }
    })
