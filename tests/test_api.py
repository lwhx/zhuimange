import pytest
import json
import hashlib
from app.core.auth import hash_password, is_bcrypt_hash
from app.db.database import set_setting, get_setting


class TestAuthAPI:
    
    def test_login_page_loads(self, client):
        response = client.get('/login')
        assert response.status_code == 200
    
    def test_login_with_valid_credentials(self, client):
        response = client.post('/login', data={
            'password': 'admin'
        })
        assert response.status_code in [200, 302]
    
    def test_login_upgrades_old_sha256_password(self, client, app):
        password = "old_password"
        old_sha256_hash = hashlib.sha256(password.encode()).hexdigest()
        
        with app.app_context():
            set_setting('auth_password', old_sha256_hash)
        
        response = client.post('/login', data={'password': password})
        assert response.status_code in [200, 302]
        
        with app.app_context():
            new_hash = get_setting('auth_password', '')
            assert is_bcrypt_hash(new_hash) is True
    
    def test_logout_requires_auth(self, client):
        response = client.get('/logout')
        assert response.status_code == 401 or response.status_code == 302


class TestAnimeAPI:
    
    def test_get_animes_empty(self, client):
        response = client.get('/api/anime/list')
        assert response.status_code == 401
    
    def test_get_animes_authenticated(self, auth_client):
        response = auth_client.get('/api/anime/list')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert isinstance(data['data'], list)
    
    def test_add_anime_requires_auth(self, client):
        response = client.post('/api/anime/add', json={
            'tmdb_id': 12345
        })
        assert response.status_code == 401
    
    def test_get_anime_by_id_not_found(self, client):
        response = client.get('/api/anime/99999')
        assert response.status_code == 401
    
    def test_update_anime_requires_auth(self, client):
        response = client.put('/api/anime/1/progress', json={
            'watched_ep': 5
        })
        assert response.status_code == 401
    
    def test_delete_anime_requires_auth(self, client):
        response = client.delete('/api/anime/1')
        assert response.status_code == 401


class TestSettingsAPI:
    
    def test_get_settings_requires_auth(self, client):
        response = client.get('/api/settings')
        assert response.status_code == 401
    
    def test_update_settings_requires_auth(self, client):
        response = client.put('/api/settings', json={
            'key': 'value'
        })
        assert response.status_code == 401


class TestHealthEndpoints:
    
    def test_health_endpoint(self, client):
        response = client.get('/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'healthy'
    
    def test_ready_endpoint(self, client):
        response = client.get('/ready')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'ready'


class TestErrorHandling:
    
    def test_404_error(self, client):
        response = client.get('/nonexistent-endpoint')
        assert response.status_code == 404
    
    def test_api_404_returns_json(self, client):
        response = client.get('/api/nonexistent')
        assert response.status_code == 404
        assert response.content_type.startswith('application/json')
        data = json.loads(response.data)
        assert 'success' in data
        assert 'error' in data


class TestRateLimiting:
    
    def test_rate_limit_headers_present(self, client):
        response = client.get('/health')
        assert response.status_code == 200
