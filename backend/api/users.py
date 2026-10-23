# 0727 Phase 4 用户管理 API — CRUD + 密码重置（管理员专属）
"""用户管理 REST API 端点。

三层分离约定：本层仅做参数提取 + 权限校验（管理员）+ 调用 service + 返回响应，
业务校验逻辑全部在 services/user_service.py。
来源：pages/6_系统管理.py（v2.1 Streamlit）
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from services import user_service
from services import handover_service
from services.user_service import UserServiceError
from services.handover_service import HandoverError
from middleware.auth import get_current_user, invalidate_user_checks
from schemas.auth import UserInfo
from schemas.user import (
    UserCreateRequest, UserUpdateRequest, PasswordResetRequest, UserOut,
    HandoverPreviewRequest, HandoverExecuteRequest,
)
from schemas.common import ApiResponse

router = APIRouter()


def _require_admin(current_user: UserInfo) -> None:
    """仅管理员可访问用户管理。"""
    if current_user.role != "管理员":
        raise HTTPException(status_code=403, detail="仅管理员可访问用户管理")


# ── GET /api/users/meta — 角色下拉元数据 ──────
@router.get("/meta")
async def get_meta(current_user: UserInfo = Depends(get_current_user)):
    """返回全部角色列表（供新增/编辑表单下拉）。"""
    _require_admin(current_user)
    return ApiResponse(success=True, data=user_service.get_meta(), message="获取完成")


# ── GET /api/users/options — 指派下拉用户列表（0819，注册在 /{user_id} 之前）──
@router.get("/options")
async def user_options(
    roles: str = Query(default="", description="逗号分隔的角色列表，如 办理人,审批人"),
    current_user: UserInfo = Depends(get_current_user),
):
    """按角色查询启用用户（指派审批人/承接人下拉数据源，登录即可访问）。"""
    from data.database import get_users_by_roles
    role_list = [r.strip() for r in roles.split(",") if r.strip()]
    users = get_users_by_roles(role_list) if role_list else []
    return ApiResponse(success=True, data=users, message="获取完成")


# ── GET /api/users — 用户列表 ─────────────────────
@router.get("")
async def list_users(
    role: str = Query(default="", description="按角色筛选"),
    include_inactive: bool = Query(default=False, description="是否包含已停用账号"),
    current_user: UserInfo = Depends(get_current_user),
):
    """列出用户（脱敏），支持角色筛选。"""
    _require_admin(current_user)
    users = user_service.list_users(role, include_inactive)
    return ApiResponse(success=True, data=users, message="获取完成")


# ── POST /api/users — 新增用户 ────────────────────
@router.post("", response_model=ApiResponse[dict])
async def create_user(
    req: UserCreateRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """新增用户账号（角色下拉 + 职位必填）。"""
    _require_admin(current_user)
    try:
        uid = user_service.create_user(
            username=req.username,
            password=req.password,
            display_name=req.display_name,
            role=req.role,
            position=req.position,
            dingtalk_userid=req.dingtalk_userid,
        )
    except UserServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ApiResponse(success=True, data={"id": uid}, message="账号创建成功")


# ── PUT /api/users/{id} — 更新用户 ────────────────
@router.put("/{user_id}", response_model=ApiResponse[UserOut])
async def update_user(
    user_id: int,
    req: UserUpdateRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """更新用户属性（显示名/角色/职位/启用状态）。"""
    _require_admin(current_user)
    try:
        updated = user_service.update_user(user_id, req.model_dump())
    except UserServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    invalidate_user_checks()  # 0901 角色/启用状态变更 → 存量 Token 立即按新状态校验
    return ApiResponse(success=True, data=updated, message="已保存")


# ── POST /api/users/{id}/reset-password — 重置密码 ─
@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    req: PasswordResetRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """重置用户密码（至少 4 位）。"""
    _require_admin(current_user)
    try:
        user_service.reset_password(user_id, req.new_password)
    except UserServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ApiResponse(success=True, message="密码已重置")


# ── DELETE /api/users/{id} — 硬删除账号 ──────────
@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """删除用户账号（硬删除，不可恢复）。主管理员不可删除。"""
    _require_admin(current_user)
    try:
        user_service.delete_user(user_id)
    except UserServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    invalidate_user_checks()  # 0901 删号 → 其存量长票立即失效
    return ApiResponse(success=True, message="账号已删除")


# ── DELETE /api/users/{id}/deactivate — 停用账号（软删除）─
@router.delete("/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """停用用户账号（软删除，数据保留）。主管理员不可停用。"""
    _require_admin(current_user)
    try:
        user_service.deactivate_user(user_id)
    except UserServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    invalidate_user_checks()  # 0901 停用 → 其存量长票立即失效
    return ApiResponse(success=True, message="账号已停用")


# ── POST /api/users/handover/preview — 离职交接预览 ─
@router.post("/handover/preview", response_model=ApiResponse[dict])
async def handover_preview(
    req: HandoverPreviewRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """预览交接范围：离职人员名下 active 指派 + 录入客服工单数（管理员专属）。"""
    _require_admin(current_user)
    try:
        data = handover_service.preview_handover(req.from_user_id, req.to_user_id)
    except HandoverError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ApiResponse(success=True, data=data, message="获取完成")


# ── POST /api/users/handover — 执行离职交接 ────────
@router.post("/handover", response_model=ApiResponse[dict])
async def handover_execute(
    req: HandoverExecuteRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """执行离职交接：指派/录入归属换绑 + handover 日志留痕 + 汇总通知，可选停用离职账号。"""
    _require_admin(current_user)
    operator = {
        "display_name": current_user.display_name,
        "role": current_user.role,
        "position": current_user.position,
    }
    try:
        result = handover_service.execute_handover(
            req.from_user_id, req.to_user_id, operator, req.deactivate)
    except HandoverError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    if result.get("deactivated"):
        invalidate_user_checks()  # 停用 → 离职者存量长票立即失效
    return ApiResponse(success=True, data=result,
                       message=f"交接完成：{result['total_complaints']} 客户工程师单已移交"
                               f"给 {result['to_user']['display_name']}")
