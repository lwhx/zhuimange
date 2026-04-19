"""
追漫阁 - 应用入口
"""
import os
import logging
import secrets
from datetime import date, datetime, timedelta
from functools import wraps
from typing import Any, Callable

from flask import Flask, render_template, jsonify, request, redirect, url_for, session, g, abort
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from app import config
from app.db.database import (
    init_db, get_all_animes_with_stats, get_anime, get_episodes,
    get_sources_for_episode, get_episode_source_counts, get_aliases,
    get_setting, set_setting,
)
from app.core.link_converter import format_duration, format_view_count, invidious_to_youtube
from app.core.auth import hash_password, verify_password, is_bcrypt_hash

AUTH_SESSION_DAYS = 30

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

logger = logging.getLogger(__name__)

REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP Requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP Request Latency', ['method', 'endpoint'])

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per minute"])
cache = Cache()


def create_app(test_config: dict = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), 'web', 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), 'web', 'static'),
    )
    app.config['SECRET_KEY'] = config.SECRET_KEY
    if not os.getenv("SECRET_KEY"):
        logger.warning("⚠️  SECRET_KEY 使用了自动生成的随机值，生产环境请设置 SECRET_KEY 环境变量！")
    app.config['JSON_AS_ASCII'] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=AUTH_SESSION_DAYS)
    app.config['WTF_CSRF_TIME_LIMIT'] = None
    app.config.setdefault('CACHE_TYPE', 'SimpleCache')
    app.config.setdefault('CACHE_DEFAULT_TIMEOUT', 300)

    if test_config:
        app.config.update(test_config)
        if 'DATABASE_PATH' in test_config:
            import app.db.database as db_module
            db_module.DB_PATH = test_config['DATABASE_PATH']

    csrf.init_app(app)
    limiter.init_app(app)
    cache.init_app(app)

    with app.app_context():
        init_db()
        _init_default_password()
        _test_invidious_connection()

    from app.api.routes import api
    app.register_blueprint(api)

    app.jinja_env.filters['format_duration'] = format_duration
    app.jinja_env.filters['format_views'] = format_view_count

    _register_middlewares(app)
    _register_error_handlers(app)
    _register_routes(app)
    _register_health_endpoints(app)

    try:
        from app.core.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.error(f"调度器启动失败: {e}")

    return app


def _init_default_password():
    """初始化默认密码（首次启动时生成随机密码）"""
    stored_hash = get_setting('auth_password', '')
    if not stored_hash:
        default_password = secrets.token_urlsafe(12)
        default_hash = hash_password(default_password)
        set_setting('auth_password', default_hash)
        logger.warning(
            f"⚠️  已生成随机初始密码: {default_password}\n"
            f"    请立即登录并在设置中修改密码！此密码仅显示一次。"
        )
    elif not is_bcrypt_hash(stored_hash):
        logger.info("检测到旧版密码哈希格式，将在下次登录时自动升级")


def _test_invidious_connection():
    try:
        from app.core.invidious_client import get_invidious_client
        client = get_invidious_client()
        logger.info(f"Invidious 实例: {client.current_url}")
        if client.test_connection():
            logger.info("✓ Invidious 连接正常")
        else:
            logger.warning("✗ Invidious 连接失败，视频源同步将无法工作")
    except Exception as e:
        logger.error(f"Invidious 初始化出错: {e}")


def _register_middlewares(app: Flask):
    @app.before_request
    def check_auth():
        allowed = ('login', 'static', 'health', 'ready', 'api.health_check')
        if request.endpoint and request.endpoint in allowed:
            return
        if request.endpoint is None:
            return
        if not session.get('authenticated'):
            if request.path.startswith('/api/'):
                abort(401)
            return redirect(url_for('login'))
        login_time = session.get('login_time')
        if login_time:
            expire = datetime.fromisoformat(login_time) + timedelta(days=AUTH_SESSION_DAYS)
            if datetime.now() > expire:
                session.clear()
                if request.path.startswith('/api/'):
                    abort(401)
                return redirect(url_for('login'))

    @app.after_request
    def record_metrics(response):
        if request.endpoint and not request.endpoint.startswith('static'):
            REQUEST_COUNT.labels(method=request.method, endpoint=request.endpoint or 'unknown', status=response.status_code).inc()
        return response

    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "img-src 'self' https://image.tmdb.org https://img.youtube.com "
            "https://lain.bgm.tv data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )
        return response


def _register_error_handlers(app: Flask):
    @app.errorhandler(400)
    def bad_request(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': '请求参数错误', 'code': 400}), 400
        return render_template('error.html', error='请求参数错误', code=400), 400

    @app.errorhandler(401)
    def unauthorized(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': '需要认证', 'code': 401}), 401
        return render_template('error.html', error='需要认证', code=401), 401

    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': '访问被拒绝', 'code': 403}), 403
        return render_template('error.html', error='访问被拒绝', code=403), 403

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': '资源不存在', 'code': 404}), 404
        return render_template('error.html', error='页面不存在', code=404), 404

    @app.errorhandler(429)
    def rate_limited(e):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': '请求过于频繁，请稍后再试', 'code': 429}), 429
        return render_template('error.html', error='请求过于频繁', code=429), 429

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception(f"服务器内部错误: {e}")
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': '服务器内部错误', 'code': 500}), 500
        return render_template('error.html', error='服务器内部错误', code=500), 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        logger.exception(f"未处理的异常: {e}")
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': '服务器错误', 'code': 500}), 500
        return render_template('error.html', error='服务器错误', code=500), 500


def _register_routes(app: Flask):
    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit("10 per minute")
    def login():
        if request.method == 'POST':
            password = request.form.get('password', '')
            stored_hash = get_setting('auth_password', '')

            if verify_password(password, stored_hash):
                if not is_bcrypt_hash(stored_hash):
                    new_hash = hash_password(password)
                    set_setting('auth_password', new_hash)
                    logger.info("密码哈希已升级为 bcrypt")

                session.permanent = True
                session['authenticated'] = True
                session['login_time'] = datetime.now().isoformat()
                return redirect('/')
            else:
                return render_template('login.html', error='密码错误')

        return render_template('login.html')

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.route('/')
    @cache.cached(timeout=60, key_prefix='index_page')
    def index():
        today = date.today().isoformat()
        animes = get_all_animes_with_stats(today)
        return render_template('index.html', animes=animes)

    @app.route('/anime/<int:anime_id>')
    @cache.cached(timeout=120, key_prefix=lambda: f'anime_detail_{request.view_args.get("anime_id", "")}')
    def anime_detail(anime_id):
        anime = get_anime(anime_id)
        if not anime:
            return render_template('error.html', error="动漫不存在", code=404), 404

        episodes = get_episodes(anime_id)
        aliases = get_aliases(anime_id)
        source_counts = get_episode_source_counts(anime_id)

        today = date.today().isoformat()
        is_tmdb = anime.get("tmdb_id") is not None
        aired_episodes = []
        for ep in episodes:
            if is_tmdb:
                air = ep.get("air_date", "")
                if not air or air > today:
                    continue
            ep["source_count"] = source_counts.get(ep["id"], 0)
            aired_episodes.append(ep)

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

        return render_template('sources_modal.html', anime=anime, episode=episode, sources=sources)

    @app.route('/settings')
    def settings_page():
        from app.db.database import get_all_settings
        settings = get_all_settings()
        return render_template('settings.html', settings=settings)

    @app.route('/stats')
    def stats_page():
        from app.db.database import get_watch_stats
        stats = get_watch_stats()
        return render_template('stats.html', stats=stats)

    @app.route('/theme-preview')
    def theme_preview_page():
        return render_template('theme_preview.html')


def _register_health_endpoints(app: Flask):
    @app.route('/health')
    def health():
        return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

    @app.route('/ready')
    def ready():
        checks = {'database': False, 'invidious': False}

        try:
            from app.db.database import get_db_connection
            conn = get_db_connection()
            conn.execute("SELECT 1")
            conn.close()
            checks['database'] = True
        except Exception as e:
            logger.error(f"数据库健康检查失败: {e}")

        try:
            from app.core.invidious_client import get_invidious_client
            checks['invidious'] = get_invidious_client().test_connection()
        except Exception as e:
            logger.error(f"Invidious 健康检查失败: {e}")

        all_healthy = all(checks.values())
        status_code = 200 if all_healthy else 503
        return jsonify({'status': 'ready' if all_healthy else 'not_ready', 'checks': checks}), status_code

    @app.route('/metrics')
    def metrics():
        expected = config.METRICS_TOKEN
        if expected:
            token = request.args.get('token') or request.headers.get('X-Metrics-Token', '')
            if token != expected:
                abort(403)
        return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}


if __name__ == '__main__':
    app = create_app()
    port = int(os.getenv('PORT', '8000'))
    app.run(host='0.0.0.0', port=port, debug=config.DEBUG)
