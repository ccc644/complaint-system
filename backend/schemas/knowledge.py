# 0727 Phase 3 知识库 Pydantic 模型
"""知识库请求/响应模型。"""

from typing import Optional
from pydantic import BaseModel, Field


class KBCreateRequest(BaseModel):
    """新增知识条目请求。"""
    title: str = Field(..., description="标题")
    fault_category: str = Field(default="", description="故障类别")
    equipment_model: str = Field(default="", description="设备型号")
    fault_keywords: str = Field(default="", description="故障关键词（逗号分隔）")
    root_cause: str = Field(default="", description="根因分析")
    solution: str = Field(default="", description="解决方案")
    checklist: str = Field(default="", description="检查清单")
    lesson_learned: str = Field(default="", description="经验教训")
    contact_author: str = Field(default="", description="联系人/作者")
    complaint_no: str = Field(default="", description="关联工单号")
    fault_phenomenon: str = Field(default="", description="故障现象")


class KBDimensionVoteRequest(BaseModel):
    """维度投票请求。"""
    dimension: str = Field(..., description="维度名称：accuracy/effectiveness/clarity/customer_impact/presales_value")


class KBEntryOut(BaseModel):
    """知识库条目响应。"""
    id: int
    complaint_no: str = ""
    title: str
    fault_category: str = ""
    equipment_model: str = ""
    fault_keywords: str = ""
    root_cause: str = ""
    solution: str = ""
    checklist: str = ""
    lesson_learned: str = ""
    contact_author: str = ""
    created_at: str = ""
    useful_count: int = 0
    unhelpful_count: int = 0
    accuracy_votes: int = 0
    effectiveness_votes: int = 0
    clarity_votes: int = 0
    customer_impact_votes: int = 0
    presales_value_votes: int = 0
    fault_phenomenon: str = ""

    class Config:
        from_attributes = True
