# 0724 依赖注入 — get_current_user, get_db
"""FastAPI 依赖注入工具。"""

from data.database import get_conn


def get_db():
    """获取数据库连接（作为 FastAPI 依赖）。"""
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()
