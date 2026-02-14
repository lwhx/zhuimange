import pytest
import os
import tempfile
from app.main import create_app


@pytest.fixture(scope='function')
def app_with_csrf():
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    test_config = {
        'TESTING': True,
        'DATABASE_PATH': db_path,
        'SECRET_KEY': 'test-secret-key-for-csrf-testing',
        'WTF_CSRF_ENABLED': True,
        'WTF_CSRF_TIME_LIMIT': None,
        'RATELIMIT_ENABLED': False,
        'CACHE_TYPE': 'NullCache',
        'USE_MIGRATIONS': False,
    }
    
    _app = create_app(test_config)
    
    yield _app
    
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def client_with_csrf(app_with_csrf):
    return app_with_csrf.test_client()


class TestCSRFProtection:
    
    def test_login_page_contains_csrf_token(self, client_with_csrf):
        response = client_with_csrf.get('/login')
        assert response.status_code == 200
        assert b'csrf_token' in response.data
    
    def test_login_without_csrf_token_fails(self, client_with_csrf):
        with client_with_csrf.application.app_context():
            from app.db.database import set_setting
            from app.core.auth import hash_password
            set_setting('auth_password', hash_password('admin'))
        
        response = client_with_csrf.post('/login', data={'password': 'admin'})
        assert response.status_code in [400, 403]
    
    def test_login_with_valid_csrf_token_succeeds(self, client_with_csrf):
        with client_with_csrf.application.app_context():
            from app.db.database import set_setting
            from app.core.auth import hash_password
            set_setting('auth_password', hash_password('admin'))
        
        response = client_with_csrf.get('/login')
        assert response.status_code == 200
        
        import re
        csrf_match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        assert csrf_match
        
        csrf_token = csrf_match.group(1).decode()
        
        response = client_with_csrf.post('/login', data={
            'password': 'admin',
            'csrf_token': csrf_token
        }, follow_redirects=False)
        assert response.status_code == 302
    
    def test_api_json_requests_not_affected_by_csrf(self, client_with_csrf):
        response = client_with_csrf.get('/api/anime/list')
        assert response.status_code == 401
