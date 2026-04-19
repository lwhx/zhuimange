"""
追漫阁 - 认证工具模块
使用 bcrypt 进行安全的密码哈希
"""
import bcrypt


def hash_password(password: str) -> str:
    """
    使用 bcrypt 哈希密码
    
    Args:
        password: 明文密码
        
    Returns:
        哈希后的密码字符串
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """
    验证密码是否匹配，支持 bcrypt 和旧的 SHA-256 哈希
    
    Args:
        password: 明文密码
        hashed: 存储的哈希密码
        
    Returns:
        密码是否匹配
    """
    import hashlib
    
    if not hashed:
        return False
    
    try:
        if is_bcrypt_hash(hashed):
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        else:
            old_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
            return old_hash == hashed
    except Exception:
        return False


def is_bcrypt_hash(hashed: str) -> bool:
    """
    检查是否为 bcrypt 哈希格式
    
    Args:
        hashed: 待检查的字符串
        
    Returns:
        是否为 bcrypt 哈希
    """
    if not hashed:
        return False
    return hashed.startswith('$2b$') or hashed.startswith('$2a$')
