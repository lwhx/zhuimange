"""
测试固件和公共工具
"""
import os
import tempfile
import pytest
from app.main import create_app


@pytest.fixture
def app():
    """创建测试用 Flask 应用"""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    test_config = {
        "TESTING": True,
        "DATABASE_PATH": db_path,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
        "CACHE_TYPE": "NullCache",
        "USE_MIGRATIONS": False,
    }
    app = create_app(test_config)
    yield app
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return app.test_client()


@pytest.fixture
def auth_client(client, app):
    """已认证的测试客户端"""
    from app.db import database as db
    from app.core.auth import hash_password

    with app.app_context():
        db.set_setting("auth_password", hash_password("testpassword"))

    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["login_time"] = "2099-12-31T00:00:00"

    return client
