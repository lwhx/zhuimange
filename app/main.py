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
from flask_compress import Compress
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from werkzeug.middleware.proxy_fix import ProxyFix

from app import config
from app.db.database import (
    init_db, get_all_animes_with_stats, get_anime, get_episodes,
    get_sources_for_episode, get_episode_source_counts, get_aliases,
    get_setting, set_setting, filter_aired_episodes, episode_is_aired,
)
from app.core.link_converter import format_duration, format_view_count, invidious_to_youtube
from app.core.auth import hash_password, verify_password, is_bcrypt_hash

AUTH_SESSION_DAYS = 30

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# 可选：设置 LOG_FILE 环境变量后，日志额外写入轮转文件（非容器部署兜底）。
# 容器部署依赖 docker logs，可不设。
_log_file = os.getenv("LOG_FILE", "")
if _log_file:
    from logging.handlers import RotatingFileHandler
    _file_handler = RotatingFileHandler(
        _log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    _file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S',
    ))
    _file_handler.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))
    logging.getLogger().addHandler(_file_handler)

logger = logging.getLogger(__name__)

REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP Requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP Request Latency', ['method', 'endpoint'])

csrf = CSRFProtect()
# 启用限流响应头，便于反代/客户端感知 429。
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per minute"], headers_enabled=True)
cache = Cache()
# gzip 传输压缩：CSS/JS/HTML 等文本资源自动压缩，显著减小传输体积
compress = Compress()


def create_app(test_config: dict = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), 'web', 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), 'web', 'static'),
    )
    # 反向代理（Nginx/Caddy/Docker）后，REMOTE_ADDR 全是代理 IP，
    # 会让按 IP 的限流（如登录 10/min）误伤所有用户。ProxyFix 从
    # X-Forwarded-For 还原真实客户端 IP。仅在部署于可信反代后生效，
    # 通过 PROXY_FIX_TRUSTED_HOPS 控制信任的代理跳数（默认 1）。
    trusted_hops = int(os.getenv("PROXY_FIX_TRUSTED_HOPS", "1"))
    if trusted_hops > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=trusted_hops, x_proto=1, x_host=1, x_prefix=1)

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
    compress.init_app(app)

    with app.app_context():
        init_db()
        _init_default_password()
        if not app.config.get('TESTING') and not app.config.get('SKIP_EXTERNAL_CHECKS', False):
            _test_invidious_connection()

    from app.api.routes import api
    app.register_blueprint(api)

    app.jinja_env.filters['format_duration'] = format_duration
    app.jinja_env.filters['format_views'] = format_view_count
    app.jinja_env.filters['proxy_img'] = _proxy_img_filter

    _register_middlewares(app)
    _register_error_handlers(app)
    _register_routes(app)
    _register_health_endpoints(app)

    if not app.config.get('TESTING') and not app.config.get('DISABLE_SCHEDULER', False):
        try:
            from app.core.sync_queue import sync_queue
            from app.core.scheduler import start_scheduler
            sync_queue.start()
            start_scheduler()
        except Exception as e:
            logger.error(f"调度器启动失败: {e}")

    return app


def _init_default_password():
    """初始化默认密码（首次启动时生成随机密码）

    密码同时打印到日志并写入 data/.initial_password（仅属主可读），
    作为日志丢失时的兜底取回途径。用户首次登录后自动删除该文件。
    """
    stored_hash = get_setting('auth_password', '')
    if not stored_hash:
        default_password = secrets.token_urlsafe(12)
        default_hash = hash_password(default_password)
        set_setting('auth_password', default_hash)
        logger.warning(
            f"⚠️  已生成随机初始密码: {default_password}\n"
            f"    请立即登录并在设置中修改密码！此密码仅显示一次。"
        )
        # 兜底留存：日志可能被轮转/丢失，写入文件便于取回
        try:
            secret_file = os.path.join(config.BASE_DIR, "data", ".initial_password")
            os.makedirs(os.path.dirname(secret_file), exist_ok=True)
            fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(default_password)
            logger.warning(f"    初始密码已留存到 {secret_file}，登录后将自动删除")
        except OSError as e:
            logger.warning(f"无法留存初始密码文件: {e}")
    elif not is_bcrypt_hash(stored_hash):
        logger.info("检测到旧版密码哈希格式，将在下次登录时自动升级")


def _consume_initial_password_file():
    """首次登录成功后删除初始密码留存文件，避免明文泄露。"""
    try:
        secret_file = os.path.join(config.BASE_DIR, "data", ".initial_password")
        if os.path.isfile(secret_file):
            os.remove(secret_file)
            logger.info("初始密码留存文件已删除")
    except OSError as e:
        logger.warning(f"删除初始密码留存文件失败: {e}")


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


def _get_invidious_thumb_base() -> str:
    """取 Invidious 主实例地址用于拼接视频缩略图（/vi/<id>/...），避免直连 YouTube"""
    try:
        from app.core.invidious_client import get_invidious_client
        client = get_invidious_client()
        client.refresh_instances()
        return (client.primary_url or "").rstrip("/")
    except Exception:
        return ""


def _is_https_request():
    """判断当前请求是否为 HTTPS（含反向代理透传的 X-Forwarded-Proto）"""
    from flask import request
    if request.is_secure:
        return True
    # 反代场景：nginx/cloudflare 用 http 转发到 Flask，但带 X-Forwarded-Proto: https
    return request.headers.get('X-Forwarded-Proto', '').lower() == 'https'


def _proxy_img_filter(url):
    """Jinja filter：HTTPS 站点下把 http:// 外部图片改写为同源代理 URL，避免混合内容拦截。

    - https:// 图片：原样返回（无混合内容问题）
    - http:// 图片且当前请求是 HTTPS：改写为 /api/proxy_image?url=...
    - 本地 HTTP 部署：原样返回（无代理开销）
    """
    if not url:
        return url
    if not url.startswith('http://'):
        return url
    # 仅在 HTTPS 页面才需要代理
    try:
        if not _is_https_request():
            return url
    except Exception:
        # 非请求上下文（如后台任务）时原样返回
        return url
    from urllib.parse import quote
    return f'/api/proxy_image?url={quote(url, safe="")}'


def _register_middlewares(app: Flask):
    @app.before_request
    def check_auth():
        # health/ready/metrics 供探针与 Prometheus 抓取，不能要求登录；
        # proxy_image 是页面海报/缩略图的同源代理，浏览器 <img> 加载，白名单已限域名防 SSRF
        allowed = ('login', 'static', 'health', 'ready', 'metrics', 'api.health_check', 'api.proxy_image')
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
            # img-src 放宽：海报/缩略图来源含用户配置的 Invidious 实例（自部署，域名/IP 不固定），
            # img 标签无法执行脚本，放宽协议头风险可控而功能必要
            "img-src 'self' https: http: data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'"
        )
        return response

    @app.after_request
    def add_cache_headers(response):
        # 静态资源（CSS/JS/字体）带 ?v= 版本指纹，可长期强缓存；
        # 文件内容变更时版本号随之更新，天然失效。
        if request.endpoint == 'static':
            response.headers['Cache-Control'] = 'public, max-age=31536000'
        # HTML 页面与 API 响应默认不缓存，避免改版/数据更新后拿到旧内容
        elif response.content_type and 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-cache'
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

                _consume_initial_password_file()
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
    @cache.cached(
        timeout=120,
        key_prefix=lambda: (
            f'anime_detail_{request.view_args.get("anime_id", "")}_'
            f'{get_setting("episode_sort_order", "desc")}'
        ),
    )
    def anime_detail(anime_id):
        anime = get_anime(anime_id)
        if not anime:
            return render_template('error.html', error="动漫不存在", code=404), 404

        episodes = get_episodes(anime_id)
        aliases = get_aliases(anime_id)
        source_counts = get_episode_source_counts(anime_id)

        aired_episodes = filter_aired_episodes(anime, episodes, date.today().isoformat())
        for ep in aired_episodes:
            ep["source_count"] = source_counts.get(ep["id"], 0)

        sort_order = get_setting("episode_sort_order", "desc")
        if sort_order == "desc":
            aired_episodes.reverse()

        anime["episodes"] = aired_episodes
        anime["aliases"] = aliases
        anime["sort_order"] = sort_order
        anime["watched_ep"] = sum(1 for ep in aired_episodes if ep.get("watched"))
        anime["unwatched_count"] = sum(1 for ep in aired_episodes if not ep.get("watched"))

        return render_template('anime_detail.html', anime=anime)

    @app.route('/anime/<int:anime_id>/episode/<int:ep_num>/sources')
    def episode_sources(anime_id, ep_num):
        from app.db.database import get_episode_by_num
        anime = get_anime(anime_id)
        episode = get_episode_by_num(anime_id, ep_num)
        if not episode:
            return "集数不存在", 404
        if not episode_is_aired(anime, episode, date.today().isoformat()):
            return "集数尚未开播", 404

        sources = get_sources_for_episode(episode["id"], include_invalid=True)
        invidious_base = _get_invidious_thumb_base()
        for source in sources:
            source["youtube_url"] = invidious_to_youtube(source["video_id"])
            # 缩略图优先用 Invidious 代理路径（国内可访问），避免 img.youtube.com 不可达
            vid = source.get("video_id", "")
            if vid and invidious_base:
                source["thumb_url"] = f"{invidious_base}/vi/{vid}/mqdefault.jpg"
            else:
                source["thumb_url"] = f"https://img.youtube.com/vi/{vid}/mqdefault.jpg"
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

    @app.route('/diagnostics')
    def diagnostics_page():
        return render_template('diagnostics.html')




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
