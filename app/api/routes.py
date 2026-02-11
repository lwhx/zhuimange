"""
追漫阁 - API 路由
"""
import logging
from flask import Blueprint, request, jsonify
from app.db import database as db
from app.core.tmdb_client import tmdb_client
from app.core.source_finder import find_sources_for_episode, sync_anime_sources
from app.core.link_converter import invidious_to_youtube, format_duration, format_view_count

logger = logging.getLogger(__name__)

api = Blueprint('api', __name__, url_prefix='/api')


# ==================== 搜索 ====================

@api.route('/search')
def search_anime():
    """搜索动漫 (TMDB)"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"error": "请输入搜索关键词"}), 400

    results = tmdb_client.search_anime(query)
    return jsonify(results)


# ==================== 动漫管理 ====================

@api.route('/anime/add', methods=['POST'])
def add_anime():
    """从 TMDB 添加动漫"""
    data = request.json or {}
    tmdb_id = data.get('tmdb_id')
    if not tmdb_id:
        return jsonify({"error": "缺少 tmdb_id"}), 400

    # 检查是否已添加
    existing = db.get_anime_by_tmdb_id(tmdb_id)
    if existing:
        return jsonify({"error": "该动漫已添加", "anime_id": existing["id"]}), 400

    # 从 TMDB 获取详情
    detail = tmdb_client.get_anime_detail(tmdb_id)
    if not detail:
        return jsonify({"error": "无法获取动漫信息"}), 500

    # 保存动漫
    anime_id = db.add_anime(detail)

    # 获取并保存集数
    if detail.get("seasons"):
        episodes = tmdb_client.get_all_episodes(tmdb_id, detail["seasons"])
        if episodes:
            db.add_episodes(anime_id, episodes)

    return jsonify({"success": True, "anime_id": anime_id})


@api.route('/anime/add_manual', methods=['POST'])
def add_anime_manual():
    """手动添加动漫"""
    data = request.json or {}
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "缺少动漫名称"}), 400

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

    return jsonify({"success": True, "anime_id": anime_id})


@api.route('/anime/<int:anime_id>', methods=['DELETE'])
def delete_anime(anime_id):
    """删除动漫"""
    anime = db.get_anime(anime_id)
    if not anime:
        return jsonify({"error": "动漫不存在"}), 404
    db.delete_anime(anime_id)
    return jsonify({"success": True})


@api.route('/anime/list')
def list_animes():
    """获取所有动漫列表"""
    animes = db.get_all_animes()
    # 为每个动漫附加未看集数统计
    for anime in animes:
        episodes = db.get_episodes(anime["id"])
        anime["unwatched_count"] = sum(1 for ep in episodes if not ep.get("watched"))
        anime["episode_count"] = len(episodes)
    return jsonify(animes)


@api.route('/anime/<int:anime_id>')
def get_anime(anime_id):
    """获取动漫详情"""
    anime = db.get_anime(anime_id)
    if not anime:
        return jsonify({"error": "动漫不存在"}), 404

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

    return jsonify(anime)


# ==================== 进度管理 ====================

@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/watch', methods=['POST'])
def mark_watched(anime_id, ep_num):
    """标记集数已看"""
    anime = db.get_anime(anime_id)
    if not anime:
        return jsonify({"error": "动漫不存在"}), 404

    db.mark_episode_watched(anime_id, ep_num, True)
    return jsonify({"success": True})


@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/unwatch', methods=['POST'])
def mark_unwatched(anime_id, ep_num):
    """标记集数未看"""
    anime = db.get_anime(anime_id)
    if not anime:
        return jsonify({"error": "动漫不存在"}), 404

    db.mark_episode_watched(anime_id, ep_num, False)
    return jsonify({"success": True})


@api.route('/anime/<int:anime_id>/progress', methods=['PUT'])
def update_progress(anime_id):
    """更新观看进度"""
    data = request.json or {}
    watched_ep = data.get('watched_ep')
    if watched_ep is None:
        return jsonify({"error": "缺少 watched_ep"}), 400

    anime = db.get_anime(anime_id)
    if not anime:
        return jsonify({"error": "动漫不存在"}), 404

    # 批量标记已看
    episodes = db.get_episodes(anime_id)
    for ep in episodes:
        if ep["absolute_num"] <= watched_ep:
            db.mark_episode_watched(anime_id, ep["absolute_num"], True)
        else:
            db.mark_episode_watched(anime_id, ep["absolute_num"], False)

    db.update_anime(anime_id, {"watched_ep": watched_ep})
    return jsonify({"success": True})


# ==================== 视频源 ====================

@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/sources')
def get_sources(anime_id, ep_num):
    """获取集数的视频源"""
    episode = db.get_episode_by_num(anime_id, ep_num)
    if not episode:
        return jsonify({"error": "集数不存在"}), 404

    sources = db.get_sources_for_episode(episode["id"])

    # 附加链接和格式化信息
    for source in sources:
        source["youtube_url"] = invidious_to_youtube(source["video_id"])
        source["duration_fmt"] = format_duration(source.get("duration", 0))
        source["view_count_fmt"] = format_view_count(source.get("view_count", 0))

    return jsonify(sources)


@api.route('/anime/<int:anime_id>/episode/<int:ep_num>/find_sources', methods=['POST'])
def find_sources(anime_id, ep_num):
    """主动搜索视频源"""
    force = request.json.get('force', False) if request.json else False
    sources = find_sources_for_episode(anime_id, ep_num, force=force)
    return jsonify({"success": True, "count": len(sources)})


# ==================== 同步 ====================

@api.route('/anime/<int:anime_id>/sync', methods=['POST'])
def sync_anime(anime_id):
    """同步动漫视频源"""
    anime = db.get_anime(anime_id)
    if not anime:
        return jsonify({"error": "动漫不存在"}), 404

    result = sync_anime_sources(anime_id)
    return jsonify(result)


@api.route('/anime/<int:anime_id>/sync_stream')
def sync_anime_stream(anime_id):
    """SSE 流式同步动漫视频源（实时进度）"""
    import json as _json
    from flask import Response, stream_with_context

    anime = db.get_anime(anime_id)
    if not anime:
        return jsonify({"error": "动漫不存在"}), 404

    def generate():
        from app.core.source_finder import find_sources_for_episode, discover_latest_episode
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 手动动漫先探测集数
        is_manual = anime.get("tmdb_id") is None
        if is_manual:
            discover_latest_episode(anime_id)

        episodes = db.get_episodes(anime_id)
        episodes.reverse()  # 从最新集开始同步
        total = len(episodes)

        yield f"data: {_json.dumps({'type': 'start', 'total': total}, ensure_ascii=False)}\n\n"

        synced = 0
        total_sources = 0
        done_count = 0
        BATCH_SIZE = 4  # 每批并发 4 集

        def _sync_ep(ep):
            ep_num = ep["absolute_num"]
            try:
                sources = find_sources_for_episode(anime_id, ep_num, force=True)
                return ep_num, len(sources) if sources else 0
            except Exception as e:
                logger.error(f"同步失败: {anime['title_cn']} 第{ep_num}集 - {e}")
                return ep_num, 0

        # 分批并发处理
        for batch_start in range(0, total, BATCH_SIZE):
            batch = episodes[batch_start:batch_start + BATCH_SIZE]

            with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
                futures = {executor.submit(_sync_ep, ep): ep for ep in batch}
                results = []
                for future in as_completed(futures):
                    results.append(future.result())

            # 按集数排序后逐个汇报
            results.sort(key=lambda x: x[0])
            for ep_num, count in results:
                done_count += 1
                if count > 0:
                    synced += 1
                    total_sources += count
                yield f"data: {_json.dumps({'type': 'episode', 'current': done_count, 'total': total, 'ep_num': ep_num, 'source_count': count}, ensure_ascii=False)}\n\n"

        # 更新最后同步时间
        db.update_anime(anime_id, {"last_sync_at": "CURRENT_TIMESTAMP"})

        # 手动动漫无封面兜底
        if is_manual:
            a = db.get_anime(anime_id)
            if not a.get("poster_url"):
                for ep in episodes:
                    srcs = db.get_sources_for_episode(ep.get("id", 0))
                    if srcs:
                        vid = srcs[0].get("video_id", "")
                        if vid:
                            db.update_anime(anime_id, {"poster_url": f"https://img.youtube.com/vi/{vid}/0.jpg"})
                            break

        db.add_sync_log(
            anime_id=anime_id, sync_type="manual",
            episodes_synced=synced, sources_found=total_sources,
            status="success",
            message=f"同步完成: {synced}/{total} 集找到视频源"
        )

        yield f"data: {_json.dumps({'type': 'done', 'synced': synced, 'total_sources': total_sources}, ensure_ascii=False)}\n\n"

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
    return jsonify(settings)


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

    return jsonify({"success": True})


@api.route('/change_password', methods=['POST'])
def change_password():
    """修改访问密码"""
    import hashlib
    data = request.json or {}
    old_pwd = data.get('old_password', '')
    new_pwd = data.get('new_password', '')

    if not old_pwd or not new_pwd:
        return jsonify({"error": "请填写完整"}), 400
    if len(new_pwd) < 4:
        return jsonify({"error": "新密码至少4位"}), 400

    old_hash = hashlib.sha256(old_pwd.encode()).hexdigest()
    stored_hash = db.get_setting('auth_password', '')

    if old_hash != stored_hash:
        return jsonify({"error": "当前密码错误"}), 400

    new_hash = hashlib.sha256(new_pwd.encode()).hexdigest()
    db.set_setting('auth_password', new_hash)
    return jsonify({"success": True})


# ==================== 搜索规则 ====================

@api.route('/anime/<int:anime_id>/rules', methods=['PUT'])
def update_rules(anime_id):
    """更新动漫搜索规则"""
    anime = db.get_anime(anime_id)
    if not anime:
        return jsonify({"error": "动漫不存在"}), 404

    data = request.json or {}
    db.set_source_rules(anime_id, data)
    return jsonify({"success": True})


# ==================== 别名管理 ====================

@api.route('/anime/<int:anime_id>/aliases', methods=['POST'])
def add_anime_alias(anime_id):
    """添加动漫别名"""
    data = request.json or {}
    alias = data.get('alias', '').strip()
    if not alias:
        return jsonify({"error": "缺少别名"}), 400

    db.add_alias(anime_id, alias)
    return jsonify({"success": True})


# ==================== 同步日志 ====================

@api.route('/sync_logs')
def get_sync_logs():
    """获取同步日志"""
    anime_id = request.args.get('anime_id', type=int)
    limit = request.args.get('limit', 20, type=int)
    logs = db.get_sync_logs(anime_id, limit)
    return jsonify(logs)


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
            return jsonify({"error": "请上传备份文件"}), 400
    else:
        try:
            import json as _json
            data = _json.loads(file.read().decode('utf-8'))
        except Exception as e:
            return jsonify({"error": f"文件解析失败: {e}"}), 400

    if data.get("app") != "追漫阁":
        return jsonify({"error": "无效的备份文件"}), 400

    stats = import_data(data)
    return jsonify({"success": True, **stats})


@api.route('/backup/telegram', methods=['POST'])
def backup_telegram():
    """发送备份到 Telegram"""
    from app.core.backup import send_backup_to_telegram
    result = send_backup_to_telegram()
    if result["success"]:
        return jsonify(result)
    else:
        return jsonify(result), 400
