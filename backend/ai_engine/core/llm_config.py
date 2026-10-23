# -*- coding: utf-8 -*-
"""
LLM 配置 — DeepSeek（OpenAI 兼容接口）
==========================================
API Key 从项目根目录 .env 文件加载，不再硬编码。
如需覆盖：设置系统环境变量 DEEPSEEK_API_KEY（优先级高于 .env）。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 0710 从 .env 文件加载配置，不再硬编码 API Key
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def is_configured() -> bool:
    """是否已配置可用 key（非空且非占位符）。"""
    return bool(DEEPSEEK_API_KEY) and DEEPSEEK_API_KEY.startswith("sk-")
