# 0727 Phase 4 通知中心 API — 未读列表/未读数/标记已读
# 0819 v3.0：按角色+精准用户（user_id）过滤，删除部门通知端点
"""系统通知 REST API 端点。"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from data.database import (
    get_unread_notifications, get_unread_count,
    mark_notification_read, mark_all_notifications_read,
    mark_notifications_read_by_complaint,
)
from middleware.auth import get_current_user
from schemas.auth import UserInfo
from schemas.notification import NotificationOut, MarkByComplaintRequest
from schemas.common import ApiResponse

router = APIRouter()


# ── GET /api/notifications — 未读通知列表 ──────────
@router.get("", response_model=ApiResponse[list[NotificationOut]])
async def list_unread(current_user: UserInfo = Depends(get_current_user)):
    """获取当前角色可见的未读通知（最多 50 条）。"""
    notifs = get_unread_notifications(current_user.role, current_user.id)
    data = [{**n, "is_read": bool(n.get("is_read", 0))} for n in notifs]
    return ApiResponse(success=True, data=data, message="获取完成")


# ── GET /api/notifications/unread-count — 未读数 ───
@router.get("/unread-count")
async def unread_count(current_user: UserInfo = Depends(get_current_user)):
    """获取当前角色可见的未读通知数量（铃铛徽章用）。"""
    count = get_unread_count(current_user.role, current_user.id)
    return ApiResponse(success=True, data={"count": count}, message="获取完成")


# ── POST /api/notifications/read-all — 全部已读 ────
@router.post("/read-all")
async def read_all(current_user: UserInfo = Depends(get_current_user)):
    """将当前角色可见的通知全部标为已读。"""
    mark_all_notifications_read(current_user.role, current_user.id)
    return ApiResponse(success=True, message="已全部标为已读")


# ── POST /api/notifications/read-by-complaint — 按工单已读 ─
@router.post("/read-by-complaint")
async def read_by_complaint(
    req: MarkByComplaintRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """点击工单跳转时，将该工单相关通知标记为已读。"""
    mark_notifications_read_by_complaint(req.complaint_no, current_user.role, current_user.id)
    return ApiResponse(success=True, message="已标记为已读")


# ── POST /api/notifications/{id}/read — 单条已读 ───
@router.post("/{notification_id}/read")
async def read_one(
    notification_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """将单条通知标为已读（0820 带可见范围校验，不可见则 0 行更新）。"""
    if notification_id <= 0:
        raise HTTPException(status_code=400, detail="无效的通知 ID")
    mark_notification_read(notification_id, current_user.role, current_user.id)
    return ApiResponse(success=True, message="已标记为已读")


# 0729 通知分类计数
@router.get("/category-counts")
async def category_counts(
    current_user: UserInfo = Depends(get_current_user),
):
    """返回当前角色按分类统计的未读通知数。"""
    from data.database import get_notification_category_counts
    counts = get_notification_category_counts(current_user.role, current_user.id)
    return ApiResponse(success=True, data=counts, message="获取分类计数完成")


# 0729 通知中心分页查询（含已读+未读）
@router.get("/all")
async def list_all(
    page: int = Query(default=1, ge=1, description="页码"),
    limit: int = Query(default=20, ge=1, le=100, description="每页条数"),
    is_read: Optional[str] = Query(default=None, description="过滤已读/未读: 0=未读 1=已读 不传=全部"),
    current_user: UserInfo = Depends(get_current_user),
):
    """通知中心分页查询（全部通知，含已读+未读）。"""
    from data.database import get_all_notifications
    data = get_all_notifications(current_user.role, current_user.id, page, limit, is_read)
    return ApiResponse(success=True, data=data, message="获取通知完成")
