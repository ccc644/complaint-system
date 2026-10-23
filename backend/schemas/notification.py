# 0727 Phase 4 通知中心 Pydantic 模型
# 0819 v3.0：移除部门通知请求模型
"""系统通知请求/响应模型。
来源：app.py render_notifications（v2.1 Streamlit）
"""

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    """单条通知响应。"""
    id: int
    complaint_no: str = ""
    title: str = ""
    message: str = ""
    target_role: str = ""
    notification_category: str = "awareness"  # 0729 新增：action_required/awareness/experience
    is_read: bool = False
    created_at: str = ""

    class Config:
        from_attributes = True


class MarkByComplaintRequest(BaseModel):
    """按工单号标记已读请求（点击工单跳转时调用）。"""
    complaint_no: str = Field(..., description="工单编号")
