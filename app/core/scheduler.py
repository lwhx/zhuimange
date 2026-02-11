"""
追漫阁 - 任务调度器
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.db import database as db

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def check_and_sync():
    """
    检查并同步需要更新的动漫

    根据全局同步间隔和个别动漫的独立同步间隔，
    自动查找需要同步的动漫并执行同步。
    """
    from app.core.source_finder import sync_anime_sources

    try:
        settings = db.get_all_settings()
        auto_enabled = settings.get("auto_sync_enabled", "true") == "true"
        if not auto_enabled:
            logger.info("自动同步已禁用")
            return

        animes = db.get_all_animes()
        global_interval = int(settings.get("auto_sync_interval", "360"))

        synced_count = 0
        for anime in animes:
            # 跳过已完结且已看完的动漫
            if (anime.get("status") == "Ended" and
                    anime.get("watched_ep", 0) >= anime.get("total_episodes", 0) > 0):
                continue

            try:
                result = sync_anime_sources(anime["id"])
                if result.get("success"):
                    synced_count += 1
                    logger.info(
                        f"同步完成: {anime['title_cn']} - "
                        f"{result.get('synced_episodes', 0)} 集"
                    )
            except Exception as e:
                logger.error(f"同步异常: {anime['title_cn']} - {e}")
                db.add_sync_log(
                    anime_id=anime["id"],
                    sync_type="auto",
                    episodes_synced=0,
                    sources_found=0,
                    status="error",
                    message=str(e),
                )

        # 清理过期日志
        db.cleanup_old_sync_logs()

        logger.info(f"自动同步完成: {synced_count}/{len(animes)} 部动漫")

    except Exception as e:
        logger.exception(f"自动同步任务异常: {e}")


def start_scheduler():
    """启动调度器"""
    try:
        settings = db.get_all_settings()
        interval_minutes = int(settings.get("auto_sync_interval", "360"))

        scheduler.add_job(
            check_and_sync,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="auto_sync",
            name="自动同步视频源",
            replace_existing=True,
        )

        # 定时 TG 备份
        tg_enabled = settings.get("tg_backup_enabled", "false") == "true"
        tg_days = int(settings.get("tg_backup_interval_days", "1"))
        if tg_enabled:
            scheduler.add_job(
                _tg_backup_task,
                trigger=IntervalTrigger(days=tg_days),
                id="tg_backup",
                name="定时 Telegram 备份",
                replace_existing=True,
            )
            logger.info(f"定时 TG 备份已启用，间隔: {tg_days} 天")

        scheduler.start()
        logger.info(f"调度器已启动，同步间隔: {interval_minutes} 分钟")
    except Exception as e:
        logger.error(f"调度器启动失败: {e}")


def _tg_backup_task():
    """定时 TG 备份任务"""
    try:
        from app.core.backup import send_backup_to_telegram
        result = send_backup_to_telegram()
        if result.get("success"):
            logger.info(f"定时 TG 备份成功: {result.get('filename')}")
        else:
            logger.error(f"定时 TG 备份失败: {result.get('error')}")
    except Exception as e:
        logger.error(f"定时 TG 备份异常: {e}")


def stop_scheduler():
    """停止调度器"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("调度器已停止")


def update_sync_interval(minutes: int):
    """
    更新同步间隔

    Args:
        minutes: 新的同步间隔（分钟）
    """
    try:
        scheduler.reschedule_job(
            "auto_sync",
            trigger=IntervalTrigger(minutes=minutes),
        )
        logger.info(f"同步间隔已更新: {minutes} 分钟")
    except Exception as e:
        logger.error(f"更新同步间隔失败: {e}")


def update_tg_backup_schedule(enabled: bool, days: int = 1):
    """更新定时 TG 备份计划"""
    try:
        if enabled:
            scheduler.add_job(
                _tg_backup_task,
                trigger=IntervalTrigger(days=days),
                id="tg_backup",
                name="定时 Telegram 备份",
                replace_existing=True,
            )
            logger.info(f"定时 TG 备份已启用，间隔: {days} 天")
        else:
            try:
                scheduler.remove_job("tg_backup")
            except Exception:
                pass
            logger.info("定时 TG 备份已禁用")
    except Exception as e:
        logger.error(f"更新 TG 备份计划失败: {e}")
