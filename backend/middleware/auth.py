# 0724 JWT 认证中间件 — Token 签发 + 验证依赖
# 0819 v3.0：payload 精简为 账号/ID/角色/显示名/职位
# 0824 安全加固：密钥强制从环境变量读取（缺失即启动失败），不再有硬编码默认值
"""JWT 认证工具：签发、验证、依赖注入。"""

import os
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from jose import JWTError, jwt

from schemas.auth import UserInfo

# 0824 从 backend/.env 加载 JWT_SECRET_KEY（与 llm_config.py 的 .env 路径一致）
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# ── 配置 ──────────────────────────────────────────
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY 未配置：请在 backend/.env 中设置随机密钥（secrets.token_hex(32)），"
        "缺失时拒绝启动以防使用可预测密钥。"
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24   # 0901 默认短票 24 小时（登录页未勾选「7天内自动登录」）
REMEMBER_TOKEN_HOURS = 168       # 0901 勾选「7天内自动登录」时签发 7 天长票（配合前端凭证保险箱）

# 0901 账号有效性回查缓存：Token 7 天长效后，停用/删除账号必须能立即踢出
# （JWT 无状态，本身感知不到账号状态变化）；60s TTL 兼顾安全生效窗口与查库频率
_USER_CHECK_TTL = 60
_user_check_cache: dict[str, tuple[float, bool]] = {}


def _user_still_active(username: str) -> bool:
    now = time.time()
    hit = _user_check_cache.get(username)
    if hit and now - hit[0] < _USER_CHECK_TTL:
        return hit[1]
    from data.database import get_user_by_username  # 局部导入避免启动期循环依赖
    user = get_user_by_username(username)
    ok = bool(user) and int(user.get("is_active") or 0) == 1
    _user_check_cache[username] = (now, ok)
    return ok


def invalidate_user_checks() -> None:
    """管理员变更用户（停用/删除/改角色）后调用：整体清空校验缓存，踢出立即生效。"""
    _user_check_cache.clear()


# HTTP Bearer 认证方案
security = HTTPBearer()


def create_access_token(user: dict, hours: int | None = None) -> str:
    """根据用户信息生成 JWT Token。
    user dict 预期包含：id, username, display_name, role, position
    hours：凭证有效期（小时）；None 用默认 24h 短票（勾选记住我时由调用方传 168h 长票）。
    """
    to_encode = {
        "sub": user["username"],
        "user_id": user["id"],
        "role": user["role"],
        "display_name": user.get("display_name", ""),
        "position": user.get("position", ""),
        "exp": datetime.now(timezone.utc) + timedelta(hours=hours or ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """解析 JWT Token，返回 payload dict；无效/过期返回 None。"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> UserInfo:
    """FastAPI 依赖：从 Authorization Header 解析当前用户。
    在需要认证的路由中作为 Depends() 使用。
    """
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None or not _user_still_active(payload.get("sub", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期，请重新登录",
        )
    # 0819 旧 token 无 position 字段，用 .get 兜底避免存量会话 500
    return UserInfo(
        id=payload.get("user_id", 0),
        username=payload.get("sub", ""),
        display_name=payload.get("display_name", ""),
        role=payload.get("role", ""),
        position=payload.get("position", ""),
    )
