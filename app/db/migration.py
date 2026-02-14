"""
追漫阁 - 数据库迁移管理模块
"""
import os
import subprocess
import sys
from pathlib import Path
from app import config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
ALEMBIC_INI = os.path.join(BASE_DIR, "alembic.ini")
MIGRATIONS_DIR = os.path.join(BASE_DIR, "migrations")


def run_alembic_command(args: list[str]) -> bool:
    """运行 Alembic 命令"""
    cmd = [sys.executable, "-m", "alembic"] + args
    env = os.environ.copy()
    env["DATABASE_PATH"] = config.DATABASE_PATH
    
    try:
        result = subprocess.run(
            cmd,
            cwd=BASE_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"迁移命令执行失败: {e}")
        print(f"错误输出: {e.stderr}")
        return False


def upgrade_database(revision: str = "head") -> bool:
    """升级数据库到指定版本"""
    return run_alembic_command(["upgrade", revision])


def downgrade_database(revision: str = "-1") -> bool:
    """降级数据库到指定版本"""
    return run_alembic_command(["downgrade", revision])


def create_migration(message: str) -> bool:
    """创建新的迁移文件"""
    return run_alembic_command(["revision", "--autogenerate", "-m", message])


def show_migrations() -> bool:
    """显示迁移历史"""
    return run_alembic_command(["history"])


def show_current_revision() -> bool:
    """显示当前数据库版本"""
    return run_alembic_command(["current"])


def stamp_database(revision: str) -> bool:
    """标记数据库为指定版本（不执行迁移）"""
    return run_alembic_command(["stamp", revision])
