# 0824 钉钉通知配置 — DB 优先、.env 兜底，运行时热刷新
"""钉钉工作通知配置。
仿 smtp_config.py：DB 优先（system_settings 表），.env 兜底，reload_dingtalk_config() 供运行时刷新。
未配置/未启用时钉钉通知完全静默跳过，站内通知不受影响。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 模块级变量：由 reload_dingtalk_config() 统一填充
DINGTALK_ENABLED = False
DINGTALK_APP_KEY = ""
DINGTALK_APP_SECRET = ""
DINGTALK_AGENT_ID = ""
PUBLIC_BASE_URL = ""
DINGTALK_DRY_RUN = False

# .env 路径（兜底用）
_env_path = Path(__file__).resolve().parent.parent / ".env"
_ENV_LOADED = False


def _ensure_env_loaded():
    """延迟加载 .env（确保 dotenv 只在首次需要时加载）。"""
    global _ENV_LOADED
    if not _ENV_LOADED and _env_path.exists():
        load_dotenv(_env_path)
        _ENV_LOADED = True


def reload_dingtalk_config():
    """从 DB 重新加载钉钉配置（DB 优先，.env 兜底）。
    供 system_settings 变更后运行时热刷新调用。
    """
    global DINGTALK_ENABLED, DINGTALK_APP_KEY, DINGTALK_APP_SECRET
    global DINGTALK_AGENT_ID, PUBLIC_BASE_URL, DINGTALK_DRY_RUN

    _ensure_env_loaded()

    # .env 兜底值
    env_defaults = {
        "dingtalk_enabled": os.environ.get("DINGTALK_ENABLED", ""),
        "dingtalk_app_key": os.environ.get("DINGTALK_APP_KEY", ""),
        "dingtalk_app_secret": os.environ.get("DINGTALK_APP_SECRET", ""),
        "dingtalk_agent_id": os.environ.get("DINGTALK_AGENT_ID", ""),
        "public_base_url": os.environ.get("PUBLIC_BASE_URL", ""),
        "dingtalk_dry_run": os.environ.get("DINGTALK_DRY_RUN", ""),
    }

    # 尝试从 DB 读取（DB 优先）
    try:
        from data.database import get_settings
        db_settings = get_settings(
            "dingtalk_enabled", "dingtalk_app_key", "dingtalk_app_secret",
            "dingtalk_agent_id", "public_base_url", "dingtalk_dry_run",
        )
    except Exception:
        db_settings = {}

    def _val(key: str) -> str:
        return (db_settings.get(key, "") or "").strip() or env_defaults.get(key, "")

    DINGTALK_ENABLED = _val("dingtalk_enabled") == "1"
    DINGTALK_APP_KEY = _val("dingtalk_app_key")
    DINGTALK_APP_SECRET = _val("dingtalk_app_secret")
    DINGTALK_AGENT_ID = _val("dingtalk_agent_id")
    # 系统访问地址统一去掉末尾斜杠（卡片 URL 拼接用）
    PUBLIC_BASE_URL = _val("public_base_url").rstrip("/")
    DINGTALK_DRY_RUN = _val("dingtalk_dry_run") == "1"


def is_dingtalk_configured() -> bool:
    """钉钉通知是否已配置且启用（发送四要素齐备：开关+AppKey+AppSecret+AgentId+访问地址）。"""
    return all([
        DINGTALK_ENABLED,
        DINGTALK_APP_KEY,
        DINGTALK_APP_SECRET,
        DINGTALK_AGENT_ID,
        PUBLIC_BASE_URL,
    ])


# 模块首次加载时自动初始化
reload_dingtalk_config()
