# 0724 认证 API — 登录 + 获取当前用户
# 0819 v3.0：登录仅账号+密码（中心概念取消）
# 0824 安全加固：登录失败限流（5 次/15 分钟锁定，按 账号+IP），防暴力破解
"""认证相关 API 端点。"""

import time
from fastapi import APIRouter, HTTPException, Depends, Request
from data.database import verify_user
from middleware.auth import create_access_token, get_current_user, REMEMBER_TOKEN_HOURS
from schemas.auth import LoginRequest, LoginOut, UserInfo
from schemas.common import ApiResponse

router = APIRouter()

# ── 登录限流（内存实现，单 worker 部署有效） ─────
_LOGIN_MAX_FAILURES = 5        # 连续失败次数阈值
_LOGIN_LOCK_SECONDS = 900      # 锁定 15 分钟
_fail_times: dict[str, list[float]] = {}   # key: f"{username}|{ip}" → 失败时间戳列表
_locked_until: dict[str, float] = {}       # key: f"{username}|{ip}" → 解锁时间戳


def _login_key(username: str, request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{username}|{ip}"


def _check_locked(username: str, request: Request):
    key = _login_key(username, request)
    until = _locked_until.get(key, 0)
    if until > time.time():
        remain = int(until - time.time())
        raise HTTPException(
            status_code=429,
            detail=f"登录失败次数过多，已锁定 {remain} 秒后重试",
        )


def _record_failure(username: str, request: Request):
    key = _login_key(username, request)
    now = time.time()
    times = [t for t in _fail_times.get(key, []) if now - t < _LOGIN_LOCK_SECONDS]
    times.append(now)
    _fail_times[key] = times
    if len(times) >= _LOGIN_MAX_FAILURES:
        _locked_until[key] = now + _LOGIN_LOCK_SECONDS
        _fail_times.pop(key, None)


def _clear_failures(username: str, request: Request):
    key = _login_key(username, request)
    _fail_times.pop(key, None)
    _locked_until.pop(key, None)


@router.post("/login", response_model=ApiResponse[LoginOut])
async def login(body: LoginRequest, request: Request):
    """用户登录 — 账号 + 密码。成功返回 JWT token 和用户信息；失败返回 401。"""
    _check_locked(body.username, request)
    user = verify_user(body.username, body.password)
    if user is None:
        _record_failure(body.username, request)
        raise HTTPException(
            status_code=401,
            detail="账号或密码不正确，请检查后重试",
        )

    _clear_failures(body.username, request)
    user_info = {
        "id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name", user["username"]),
        "role": user.get("role", ""),
        "position": user.get("position", ""),
    }
    # 0901 勾选「7天内自动登录」→ 签发 7 天长票（前端会存入凭证保险箱）；否则 24h 短票
    token = create_access_token(user_info, REMEMBER_TOKEN_HOURS if body.remember else None)

    return ApiResponse(
        success=True,
        data=LoginOut(
            token=token,
            user=UserInfo(**user_info),
        ),
        message="登录成功",
    )


@router.get("/me", response_model=ApiResponse[UserInfo])
async def get_me(current_user: UserInfo = Depends(get_current_user)):
    """获取当前登录用户信息（需 Bearer Token）。"""
    return ApiResponse(success=True, data=current_user, message="操作成功")
