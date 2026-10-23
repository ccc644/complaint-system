# 0811 系统设置 API — SMTP 邮箱配置（管理员专属）
"""系统设置 REST API 端点。
管理员可查看和修改 SMTP 邮件配置，修改后即时生效无需重启。
"""

from fastapi import APIRouter, Depends, HTTPException

from services import settings_service
from middleware.auth import get_current_user
from schemas.auth import UserInfo
from schemas.settings import (
    DingtalkConfigUpdate, DingtalkUseridQuery, SmtpConfigUpdate,
)
from schemas.common import ApiResponse

router = APIRouter()


def _require_admin(current_user: UserInfo) -> None:
    """仅管理员可访问系统设置。"""
    if current_user.role != "管理员":
        raise HTTPException(status_code=403, detail="仅管理员可访问系统设置")


@router.get("/smtp")
async def get_smtp_config(current_user: UserInfo = Depends(get_current_user)):
    """获取当前 SMTP 配置（密码脱敏）。"""
    _require_admin(current_user)
    config = settings_service.get_smtp_config()
    return ApiResponse(success=True, data=config, message="获取完成")


@router.put("/smtp")
async def update_smtp_config(
    req: SmtpConfigUpdate,
    current_user: UserInfo = Depends(get_current_user),
):
    """更新 SMTP 配置，即时生效。"""
    _require_admin(current_user)
    config = settings_service.update_smtp_config(req)
    return ApiResponse(success=True, data=config, message="SMTP 配置已保存并生效")


@router.post("/smtp/test")
async def test_smtp_connection(
    req: SmtpConfigUpdate,
    current_user: UserInfo = Depends(get_current_user),
):
    """测试 SMTP 连接（使用提供的参数尝试登录）。"""
    _require_admin(current_user)
    result = settings_service.test_smtp_connection(req)
    return ApiResponse(success=result.success, data=result, message=result.message)


# ── 0824 钉钉通知配置（管理员专属） ────────────────
@router.get("/dingtalk")
async def get_dingtalk_config(current_user: UserInfo = Depends(get_current_user)):
    """获取当前钉钉通知配置（密钥脱敏）。"""
    _require_admin(current_user)
    config = settings_service.get_dingtalk_config()
    return ApiResponse(success=True, data=config, message="获取完成")


@router.put("/dingtalk")
async def update_dingtalk_config(
    req: DingtalkConfigUpdate,
    current_user: UserInfo = Depends(get_current_user),
):
    """更新钉钉通知配置，即时生效。"""
    _require_admin(current_user)
    config = settings_service.update_dingtalk_config(req)
    return ApiResponse(success=True, data=config, message="钉钉配置已保存并生效")


@router.post("/dingtalk/test")
async def test_dingtalk_connection(
    req: DingtalkConfigUpdate,
    current_user: UserInfo = Depends(get_current_user),
):
    """测试钉钉凭证（使用提供的参数获取 access_token）。"""
    _require_admin(current_user)
    result = settings_service.test_dingtalk_connection(req)
    return ApiResponse(success=result.success, data=result, message=result.message)


@router.post("/dingtalk/userid")
async def lookup_dingtalk_userid(
    req: DingtalkUseridQuery,
    current_user: UserInfo = Depends(get_current_user),
):
    """0825 根据手机号查询钉钉 UserID（管理员绑定用户辅助工具）。"""
    _require_admin(current_user)
    result = settings_service.lookup_dingtalk_userid(req)
    return ApiResponse(success=result.success, data=result, message=result.message)
