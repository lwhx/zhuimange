import pytest
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import create_app
import app.db.database as db_module


@pytest.fixture(scope='function')
def app():
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    test_config = {
        'TESTING': True,
        'DATABASE_PATH': db_path,
        'SECRET_KEY': 'test-secret-key-for-testing-only',
        'WTF_CSRF_ENABLED': False,
        'RATELIMIT_ENABLED': False,
        'CACHE_TYPE': 'NullCache',
        'USE_MIGRATIONS': False,
    }
    
    _app = create_app(test_config)
    
    yield _app
    
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


@pytest.fixture
def auth_client(client):
    from app.core.auth import hash_password
    from app.db.database import set_setting
    with client.application.app_context():
        set_setting('auth_password', hash_password('test_password'))
    
    client.post('/login', data={'password': 'test_password'})
    return client
