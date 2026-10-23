"""0729 用户使用评价 API"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from middleware.auth import get_current_user
from schemas.auth import UserInfo
from schemas.feedback import FeedbackCreate
from schemas.common import ApiResponse
from data.database import (
    create_user_feedback,
    check_feedback_exists,
    get_pending_feedback_types,
    get_feedback_summary,
)

router = APIRouter()


@router.post("")
async def submit_feedback(
    body: FeedbackCreate,
    current_user: UserInfo = Depends(get_current_user),
):
    """提交用户使用评价。"""
    result = create_user_feedback(
        username=current_user.username,
        role=current_user.role,
        complaint_no=body.complaint_no,
        feedback_type=body.feedback_type,
        ai_accuracy=body.ai_accuracy,
        ai_time_saved=body.ai_time_saved,
        ai_adopted=body.ai_adopted,
        ai_comment=body.ai_comment,
        # 0730 工单上下文 + AI 建议内容
        fault_category=body.fault_category,
        equipment_model=body.equipment_model,
        complaint_status=body.complaint_status,
        responsible_dept=body.responsible_dept,
        ai_suggestion=body.ai_suggestion,
    )
    if not result["success"]:
        raise HTTPException(status_code=409 if "已" in result["message"] else 400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.get("/pending")
async def pending_feedback(
    complaint_no: str = Query(..., description="工单编号"),
    current_user: UserInfo = Depends(get_current_user),
):
    """查询用户在某个工单上是否还有待评价的操作。"""
    types = get_pending_feedback_types(current_user.username, complaint_no, current_user.role)
    return ApiResponse(success=True, data={"pending": types, "count": len(types)}, message="查询完成")


@router.get("/check")
async def check_feedback(
    complaint_no: str = Query(..., description="工单编号"),
    feedback_type: str = Query(..., description="操作类型"),
    current_user: UserInfo = Depends(get_current_user),
):
    """检查用户是否已评价某工单的某操作类型。"""
    exists = check_feedback_exists(current_user.username, complaint_no, feedback_type)
    return ApiResponse(success=True, data={"exists": exists}, message="查询完成")


@router.get("/summary")
async def summary(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """管理员查看评价统计。"""
    if current_user.role != "管理员":
        raise HTTPException(status_code=403, detail="仅管理员可查看评价统计")
    data = get_feedback_summary(date_range)
    return ApiResponse(success=True, data=data, message="获取评价统计完成")
