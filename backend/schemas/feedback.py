"""0729 用户使用评价 Schema"""
from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    """提交评价请求。"""
    complaint_no: str = Field(..., description="工单编号")
    feedback_type: str = Field(..., description="操作类型: intake/evaluate/assign/resolve/confirm")
    ai_accuracy: int = Field(..., ge=1, le=5, description="AI建议准确度 1-5星")
    ai_time_saved: str = Field(..., description="节省时间: significant/moderate/slight/none/negative")
    ai_adopted: int = Field(..., description="是否采纳AI: 1=是 -1=否 0=未用AI")
    ai_comment: str = Field(default="", description="自由评价，选填")
    # 0730 工单上下文 + AI 建议内容
    fault_category: str = Field(default="", description="故障分类")
    equipment_model: str = Field(default="", description="设备型号")
    complaint_status: str = Field(default="", description="评价时工单状态")
    responsible_dept: str = Field(default="", description="负责部门")
    ai_suggestion: str = Field(default="", description="AI建议原文，未使用为空")
