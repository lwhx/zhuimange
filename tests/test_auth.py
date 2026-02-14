import pytest
import hashlib
from app.core.auth import hash_password, verify_password, is_bcrypt_hash


class TestPasswordHashing:
    
    def test_hash_password_returns_bcrypt_hash(self):
        password = "test_password_123"
        hashed = hash_password(password)
        
        assert hashed is not None
        assert hashed != password
        assert is_bcrypt_hash(hashed) is True
    
    def test_hash_password_creates_different_salts(self):
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        assert hash1 != hash2
    
    def test_verify_password_correct(self):
        password = "correct_password"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_password_incorrect(self):
        password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(password)
        
        assert verify_password(wrong_password, hashed) is False
    
    def test_is_bcrypt_hash_valid(self):
        valid_hash = "$2b$12$abcdefghijklmnopqrstuvwxABCDEFGHIJ"
        assert is_bcrypt_hash(valid_hash) is True
        
        valid_hash_2a = "$2a$12$abcdefghijklmnopqrstuvwxABCDEFGHIJ"
        assert is_bcrypt_hash(valid_hash_2a) is True
    
    def test_is_bcrypt_hash_invalid(self):
        invalid_hash = "sha256:abcdef123456"
        assert is_bcrypt_hash(invalid_hash) is False
        
        assert is_bcrypt_hash("") is False
        assert is_bcrypt_hash(None) is False
    
    def test_verify_password_with_invalid_hash(self):
        result = verify_password("password", "invalid_hash")
        assert result is False


class TestPasswordMigration:
    
    def test_is_bcrypt_hash_identifies_old_sha256(self):
        old_sha256_hash = hashlib.sha256("old_password".encode()).hexdigest()
        assert is_bcrypt_hash(old_sha256_hash) is False
    
    def test_verify_password_with_old_sha256_hash(self):
        password = "old_password"
        old_hash = hashlib.sha256(password.encode()).hexdigest()
        
        assert verify_password(password, old_hash) is True
    
    def test_verify_password_with_wrong_old_sha256_hash(self):
        password = "old_password"
        old_hash = hashlib.sha256("different_password".encode()).hexdigest()
        
        assert verify_password(password, old_hash) is False
    
    def test_verify_password_with_bcrypt_hash(self):
        password = "new_password"
        bcrypt_hash = hash_password(password)
        
        assert verify_password(password, bcrypt_hash) is True
