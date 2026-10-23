# 0727 Phase 3 AI 接口 Pydantic 模型
"""AI 功能请求模型。"""

from typing import Optional
from pydantic import BaseModel, Field


class ClassifyRequest(BaseModel):
    """LLM 分类请求。"""
    fault_phenomenon: str = Field(..., description="故障现象描述")


class PriorityRequest(BaseModel):
    """LLM 优先级建议请求。"""
    fault_phenomenon: str = Field(..., description="故障现象描述")
    customer_note: str = Field(default="", description="客户备注")


class DiagnoseRequest(BaseModel):
    """AI 诊断请求。"""
    fault_phenomenon: str = Field(..., description="故障现象描述")
    equipment_model: str = Field(default="", description="设备型号")
    customer_name: str = Field(default="", description="客户名称")


class ExtractTextRequest(BaseModel):
    """从文本提取请求。"""
    raw_text: str = Field(..., description="原始文本")
    allow_rule_fallback: bool = Field(default=False, description="LLM 失败时是否降级到规则引擎")


class SemanticSearchRequest(BaseModel):
    """AI 语义搜索请求。"""
    query: str = Field(..., description="搜索查询")
    top_k: int = Field(default=10, description="返回结果数")


class SimilarCasesRequest(BaseModel):
    """相似案例查找请求。"""
    fault_phenomenon: str = Field(..., description="故障现象描述")
    equipment_model: str = Field(default="", description="设备型号")
    fault_category: str = Field(default="", description="故障类别")


# 0728 AI 自排查推荐 — 面向客户的简单排查建议
class SelfCheckRequest(BaseModel):
    """AI 客户自排查请求。"""
    fault_phenomenon: str = Field(..., description="故障现象描述")
    equipment_model: str = Field(default="", description="设备型号")


# 0728 AI 排期建议 — 基于工程师历史+类别统计+负载
class ScheduleSuggestionRequest(BaseModel):
    """AI 排期建议请求。"""
    engineer_name: str = Field(..., description="目标工程师姓名（主要推进人或唯一已选承接人）")
    fault_category: str = Field(default="", description="故障类别")
    estimated_hours: float = Field(default=0, description="主管预估工时")
    assignee_count: int = Field(default=0, description="0820 协同处理人数（≥2 时按团队总工时建议）")
