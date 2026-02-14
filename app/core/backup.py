"""
追漫阁 - 数据备份与恢复
"""
import json
import logging
import os
import tempfile
import hashlib
from datetime import datetime
import requests
from app import config
from app.db import database as db

logger = logging.getLogger(__name__)


def export_data() -> dict:
    """
    导出所有数据为字典

    Returns:
        包含所有追更数据的字典
    """
    animes = db.get_all_animes()
    result = {
        "version": "1.0",
        "exported_at": datetime.now().isoformat(),
        "app": "追漫阁",
        "animes": [],
        "settings": db.get_all_settings(),
    }

    for anime in animes:
        aid = anime["id"]
        episodes = db.get_episodes(aid)
        aliases = db.get_aliases(aid)
        rules = db.get_source_rules(aid)

        # 每集附带视频源
        ep_list = []
        for ep in episodes:
            sources = db.get_sources_for_episode(ep["id"])
            ep["sources"] = sources
            ep_list.append(ep)

        anime_data = {
            "anime": anime,
            "episodes": ep_list,
            "aliases": aliases,
            "rules": rules,
        }
        result["animes"].append(anime_data)

    return result


def export_json() -> str:
    """导出为 JSON 字符串"""
    data = export_data()
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def import_data(data: dict) -> dict:
    """
    从字典导入数据（合并模式，不会删除现有数据）

    Args:
        data: export_data() 格式的字典

    Returns:
        导入结果统计
    """
    stats = {"animes_imported": 0, "episodes_imported": 0, "sources_imported": 0, "skipped": 0}

    for anime_entry in data.get("animes", []):
        anime_info = anime_entry.get("anime", {})
        tmdb_id = anime_info.get("tmdb_id")

        # 检查是否已存在
        existing = None
        if tmdb_id:
            existing = db.get_anime_by_tmdb_id(tmdb_id)

        if existing:
            anime_id = existing["id"]
            stats["skipped"] += 1
            # 更新观看进度（取较大值）
            if (anime_info.get("watched_ep") or 0) > (existing.get("watched_ep") or 0):
                db.update_anime(anime_id, {"watched_ep": anime_info["watched_ep"]})
        else:
            # 新增动漫
            anime_id = db.add_anime({
                "title_cn": anime_info.get("title_cn", ""),
                "title_en": anime_info.get("title_en", ""),
                "tmdb_id": tmdb_id,
                "poster_url": anime_info.get("poster_url", ""),
                "overview": anime_info.get("overview", ""),
                "air_date": anime_info.get("air_date", ""),
                "status": anime_info.get("status", ""),
                "total_episodes": anime_info.get("total_episodes", 0),
                "watched_ep": anime_info.get("watched_ep", 0),
            })
            stats["animes_imported"] += 1

        # 导入集数
        episodes_data = anime_entry.get("episodes", [])
        if episodes_data:
            existing_eps = {ep["absolute_num"] for ep in db.get_episodes(anime_id)}
            new_eps = []
            for ep in episodes_data:
                if ep.get("absolute_num") not in existing_eps:
                    new_eps.append({
                        "season_number": ep.get("season_number", 1),
                        "episode_number": ep.get("episode_number", 0),
                        "absolute_num": ep.get("absolute_num", 0),
                        "title": ep.get("title", ""),
                        "overview": ep.get("overview", ""),
                        "air_date": ep.get("air_date", ""),
                    })
            if new_eps:
                db.add_episodes(anime_id, new_eps)
                stats["episodes_imported"] += len(new_eps)

            # 恢复已看状态
            for ep in episodes_data:
                if ep.get("watched"):
                    db.mark_episode_watched(anime_id, ep["absolute_num"], True)

            # 导入视频源
            for ep in episodes_data:
                for src in ep.get("sources", []):
                    episode_obj = db.get_episode_by_num(anime_id, ep["absolute_num"])
                    if episode_obj:
                        try:
                            db.add_source({
                                "episode_id": episode_obj["id"],
                                "video_id": src.get("video_id", ""),
                                "title": src.get("title", ""),
                                "channel_name": src.get("channel_name", ""),
                                "channel_id": src.get("channel_id", ""),
                                "duration": src.get("duration", 0),
                                "view_count": src.get("view_count", 0),
                                "published_at": src.get("published_at", ""),
                                "match_score": src.get("match_score", 0),
                            })
                            stats["sources_imported"] += 1
                        except Exception:
                            pass  # 重复的视频源跳过

        # 导入别名
        for alias in anime_entry.get("aliases", []):
            try:
                db.add_alias(anime_id, alias)
            except Exception:
                pass

        # 导入规则
        rules = anime_entry.get("rules")
        if rules:
            db.set_source_rules(anime_id, rules)

    # 导入设置
    for key, value in data.get("settings", {}).items():
        db.set_setting(key, str(value))

    return stats


def send_backup_to_telegram() -> dict:
    """
    将备份 JSON 通过 Telegram Bot 发送

    Returns:
        发送结果
    """
    # 优先从设置读取（UI 配置），回退到 config（环境变量）
    token = db.get_setting("tg_bot_token", "") or config.TG_BOT_TOKEN
    chat_id = db.get_setting("tg_chat_id", "") or config.TG_CHAT_ID

    if not token or not chat_id:
        error_msg = "未配置 TG_BOT_TOKEN 或 TG_CHAT_ID"
        logger.warning(error_msg)
        db.add_backup_log("telegram", "error", error_msg, 0, "", "NO_CONFIG")
        return {"success": False, "error": error_msg}

    tmp_path = None
    file_size = 0
    
    try:
        json_str = export_json()
        file_size = len(json_str.encode('utf-8'))
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"zhuimange_backup_{now}.json"

        # 通过 sendDocument API 发送文件
        url = f"https://api.telegram.org/bot{token}/sendDocument"

        # 写入临时文件
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        tmp.write(json_str)
        tmp.close()
        tmp_path = tmp.name

        with open(tmp.name, "rb") as f:
            resp = requests.post(
                url,
                data={"chat_id": chat_id, "caption": f"📦 追漫阁备份 {now}"},
                files={"document": (filename, f, "application/json")},
                timeout=30,
            )

        if resp.status_code == 200 and resp.json().get("ok"):
            logger.info(f"Telegram 备份发送成功: {filename}")
            db.add_backup_log("telegram", "success", "备份发送成功", file_size, filename)
            return {"success": True, "filename": filename}
        else:
            error = resp.json().get("description", resp.text)
            error_code = resp.json().get("error_code", "TG_API_ERROR")
            logger.error(f"Telegram 备份发送失败: {error}")
            db.add_backup_log("telegram", "error", error, 0, filename, error_code)
            return {"success": False, "error": error}

    except requests.exceptions.Timeout:
        error_msg = "Telegram API 请求超时"
        logger.error(error_msg)
        db.add_backup_log("telegram", "error", error_msg, 0, "", "TIMEOUT")
        return {"success": False, "error": error_msg}
    except requests.exceptions.RequestException as e:
        error_msg = f"网络请求失败: {str(e)}"
        logger.error(f"Telegram 备份异常: {e}")
        db.add_backup_log("telegram", "error", error_msg, 0, "", "NETWORK_ERROR")
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"备份异常: {str(e)}"
        logger.error(f"Telegram 备份异常: {e}")
        db.add_backup_log("telegram", "error", error_msg, 0, "", "UNKNOWN_ERROR")
        return {"success": False, "error": str(e)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception as e:
                logger.warning(f"临时文件清理失败: {e}")


def calculate_backup_checksum(data: dict) -> str:
    """计算备份数据的校验和
    
    Args:
        data: 备份数据字典
    
    Returns:
        SHA256 哈希值
    """
    json_str = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(json_str.encode('utf-8')).hexdigest()


def verify_backup_integrity(data: dict, expected_checksum: str = None) -> dict:
    """验证备份数据的完整性
    
    Args:
        data: 备份数据字典
        expected_checksum: 期望的校验和（可选）
    
    Returns:
        验证结果字典
    """
    result = {
        "valid": True,
        "checksum": "",
        "checksum_match": False,
        "animes_count": 0,
        "episodes_count": 0,
        "sources_count": 0,
        "errors": []
    }
    
    # 检查基本结构
    if data.get("app") != "追漫阁":
        result["valid"] = False
        result["errors"].append("无效的备份文件标识")
    
    if "animes" not in data:
        result["valid"] = False
        result["errors"].append("缺少 animes 数据")
    else:
        result["animes_count"] = len(data["animes"])
    
    # 统计数据量
    episodes_count = 0
    sources_count = 0
    for anime_entry in data.get("animes", []):
        episodes = anime_entry.get("episodes", [])
        episodes_count += len(episodes)
        for ep in episodes:
            sources_count += len(ep.get("sources", []))
    
    result["episodes_count"] = episodes_count
    result["sources_count"] = sources_count
    
    # 计算校验和
    result["checksum"] = calculate_backup_checksum(data)
    
    # 验证校验和
    if expected_checksum:
        result["checksum_match"] = result["checksum"] == expected_checksum
        if not result["checksum_match"]:
            result["valid"] = False
            result["errors"].append("校验和不匹配")
    
    return result


def save_backup_local(backup_dir: str = None) -> dict:
    """保存备份到本地文件
    
    Args:
        backup_dir: 备份目录路径，默认为 data/backups
    
    Returns:
        备份结果
    """
    import os
    
    if not backup_dir:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        backup_dir = os.path.join(base_dir, "data", "backups")
    
    try:
        os.makedirs(backup_dir, exist_ok=True)
        
        data = export_data()
        json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        checksum = calculate_backup_checksum(data)
        
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"zhuimange_backup_{now}.json"
        filepath = os.path.join(backup_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(json_str)
        
        file_size = os.path.getsize(filepath)
        
        logger.info(f"本地备份成功: {filename}, 大小: {file_size} 字节")
        db.add_backup_log("local", "success", "备份保存成功", file_size, filename)
        
        return {
            "success": True,
            "filename": filename,
            "filepath": filepath,
            "file_size": file_size,
            "checksum": checksum
        }
        
    except OSError as e:
        error_msg = f"文件系统错误: {str(e)}"
        logger.error(f"本地备份失败: {error_msg}")
        db.add_backup_log("local", "error", error_msg, 0, "", "FILESYSTEM_ERROR")
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"本地备份异常: {str(e)}"
        logger.error(f"本地备份异常: {e}")
        db.add_backup_log("local", "error", error_msg, 0, "", "UNKNOWN_ERROR")
        return {"success": False, "error": error_msg}
