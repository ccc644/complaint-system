# 0728 SMTP 邮件配置 — DB 优先、.env 兜底，运行时热刷新
"""SMTP 邮件发送配置。
0811 改造：DB 优先（system_settings 表），.env 兜底，reload_smtp_config() 供运行时刷新。
SMTP 未配置时降级为仅生成邮件草稿。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 模块级变量：由 reload_smtp_config() 统一填充
SMTP_HOST = ""
SMTP_PORT = 587
SMTP_USER = ""
SMTP_PASSWORD = ""
SMTP_FROM = ""

# .env 路径（兜底用）
_env_path = Path(__file__).resolve().parent.parent / ".env"
_ENV_LOADED = False


def _ensure_env_loaded():
    """延迟加载 .env（确保 dotenv 只在首次需要时加载）。"""
    global _ENV_LOADED
    if not _ENV_LOADED and _env_path.exists():
        load_dotenv(_env_path)
        _ENV_LOADED = True


def reload_smtp_config():
    """从 DB 重新加载 SMTP 配置（DB 优先，.env 兜底）。
    供 system_settings 变更后运行时热刷新调用。
    """
    global SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM

    _ensure_env_loaded()

    # .env 兜底值
    env_defaults = {
        "smtp_host": os.environ.get("SMTP_HOST", ""),
        "smtp_port": os.environ.get("SMTP_PORT", "587"),
        "smtp_user": os.environ.get("SMTP_USER", ""),
        "smtp_password": os.environ.get("SMTP_PASSWORD", ""),
        "smtp_from": os.environ.get("SMTP_FROM", ""),
    }

    # 尝试从 DB 读取（DB 优先）
    try:
        from data.database import get_settings
        db_settings = get_settings(
            "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from"
        )
    except Exception:
        db_settings = {}

    def _val(key: str) -> str:
        return db_settings.get(key, "") or env_defaults.get(key, "")

    SMTP_HOST = _val("smtp_host")
    try:
        SMTP_PORT = int(_val("smtp_port")) if _val("smtp_port") else 587
    except ValueError:
        SMTP_PORT = 587
    SMTP_USER = _val("smtp_user")
    SMTP_PASSWORD = _val("smtp_password")
    SMTP_FROM = _val("smtp_from")


def is_smtp_configured() -> bool:
    """SMTP 是否已配置（所有字段非空）。"""
    return all([SMTP_HOST, bool(SMTP_PORT), SMTP_USER, SMTP_PASSWORD, SMTP_FROM])


# 模块首次加载时自动初始化
reload_smtp_config()
