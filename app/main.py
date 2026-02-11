"""
追漫阁 - 应用入口
"""
import os
import hashlib
from datetime import date, datetime, timedelta
import logging
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from app import config
from app.db.database import init_db, get_all_animes, get_anime, get_episodes, get_sources_for_episode, get_aliases, get_setting, set_setting
from app.core.link_converter import format_duration, format_view_count, invidious_to_youtube

AUTH_SESSION_DAYS = 30  # 登录有效期

# 配置日志
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """创建 Flask 应用"""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), 'web', 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), 'web', 'static'),
    )
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['JSON_AS_ASCII'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=AUTH_SESSION_DAYS)

    # 初始化数据库
    init_db()

    # 初始化默认密码（首次运行）
    if not get_setting('auth_password', ''):
        default_hash = hashlib.sha256('admin'.encode()).hexdigest()
        set_setting('auth_password', default_hash)

    # 测试 Invidious 连接
    try:
        from app.core.invidious_client import invidious_client
        logger.info(f"Invidious 实例: {invidious_client.current_url}")
        if invidious_client.test_connection():
            logger.info("✓ Invidious 连接正常")
        else:
            logger.warning("✗ Invidious 连接失败，视频源同步将无法工作")
    except Exception as e:
        logger.error(f"Invidious 初始化出错: {e}")

    # 注册 API 蓝图
    from app.api.routes import api
    app.register_blueprint(api)

    # 注册模板过滤器
    app.jinja_env.filters['format_duration'] = format_duration
    app.jinja_env.filters['format_views'] = format_view_count

    # ==================== 认证 ====================

    @app.before_request
    def check_auth():
        """所有页面需要登录"""
        allowed = ('login', 'static')
        if request.endpoint and request.endpoint in allowed:
            return
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        # 检查会话是否过期
        login_time = session.get('login_time')
        if login_time:
            expire = datetime.fromisoformat(login_time) + timedelta(days=AUTH_SESSION_DAYS)
            if datetime.now() > expire:
                session.clear()
                return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """登录页面"""
        if request.method == 'POST':
            password = request.form.get('password', '')
            pwd_hash = hashlib.sha256(password.encode()).hexdigest()
            stored_hash = get_setting('auth_password', '')

            if pwd_hash == stored_hash:
                session.permanent = True
                session['authenticated'] = True
                session['login_time'] = datetime.now().isoformat()
                return redirect('/')
            else:
                return render_template('login.html', error='密码错误')

        return render_template('login.html')

    @app.route('/logout')
    def logout():
        """退出登录"""
        session.clear()
        return redirect(url_for('login'))

    # ==================== Web 路由 ====================

    @app.route('/')
    def index():
        """首页 - 动漫列表"""
        animes = get_all_animes()
        today = date.today().isoformat()
        for anime in animes:
            episodes = get_episodes(anime["id"])
            # 过滤未播出的集数（与详情页一致）
            is_tmdb = anime.get("tmdb_id") is not None
            aired = []
            for ep in episodes:
                if is_tmdb:
                    air = ep.get("air_date", "")
                    if not air or air > today:
                        continue
                aired.append(ep)
            anime["unwatched_count"] = sum(1 for ep in aired if not ep.get("watched"))
            anime["episode_count"] = len(aired)
        return render_template('index.html', animes=animes)

    @app.route('/anime/<int:anime_id>')
    def anime_detail(anime_id):
        """动漫详情页"""
        anime = get_anime(anime_id)
        if not anime:
            return render_template('index.html', animes=get_all_animes(), error="动漫不存在"), 404

        episodes = get_episodes(anime_id)
        aliases = get_aliases(anime_id)

        # 过滤未播出的集数（TMDB 刮削的有 air_date）
        today = date.today().isoformat()
        is_tmdb = anime.get("tmdb_id") is not None
        aired_episodes = []
        for ep in episodes:
            if is_tmdb:
                air = ep.get("air_date", "")
                if not air or air > today:
                    continue
            sources = get_sources_for_episode(ep["id"])
            ep["source_count"] = len(sources)
            aired_episodes.append(ep)

        # 排序（默认倒序）
        from app.db.database import get_setting
        sort_order = get_setting("episode_sort_order", "desc")
        if sort_order == "desc":
            aired_episodes.reverse()

        anime["episodes"] = aired_episodes
        anime["aliases"] = aliases
        anime["sort_order"] = sort_order
        anime["unwatched_count"] = sum(1 for ep in aired_episodes if not ep.get("watched"))

        return render_template('anime_detail.html', anime=anime)

    @app.route('/anime/<int:anime_id>/episode/<int:ep_num>/sources')
    def episode_sources(anime_id, ep_num):
        """视频源模态框"""
        from app.db.database import get_episode_by_num
        anime = get_anime(anime_id)
        episode = get_episode_by_num(anime_id, ep_num)
        if not episode:
            return "集数不存在", 404

        sources = get_sources_for_episode(episode["id"])
        for source in sources:
            source["youtube_url"] = invidious_to_youtube(source["video_id"])
            source["duration_fmt"] = format_duration(source.get("duration", 0))
            source["view_count_fmt"] = format_view_count(source.get("view_count", 0))

        return render_template(
            'sources_modal.html',
            anime=anime,
            episode=episode,
            sources=sources,
        )

    @app.route('/settings')
    def settings_page():
        """设置页面"""
        from app.db.database import get_all_settings
        settings = get_all_settings()
        return render_template('settings.html', settings=settings)

    # 启动调度器
    @app.before_request
    def _start_scheduler_once():
        """首次请求时启动调度器"""
        if not hasattr(app, '_scheduler_started'):
            app._scheduler_started = True
            try:
                from app.core.scheduler import start_scheduler
                start_scheduler()
            except Exception as e:
                logger.error(f"调度器启动失败: {e}")

    return app


if __name__ == '__main__':
    app = create_app()
    port = int(os.getenv('PORT', '8000'))
    app.run(host='0.0.0.0', port=port, debug=(config.LOG_LEVEL == 'DEBUG'))
