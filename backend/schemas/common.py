# 0724 通用 Pydantic 模型 — API 响应封装
"""通用请求/响应模型。"""

from typing import Any, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一成功响应格式。"""
    success: bool = True
    data: T | None = None
    message: str = "操作成功"


class PaginationOut(BaseModel):
    """分页信息。"""
    page: int
    limit: int
    total: int


class PaginatedResponse(BaseModel, Generic[T]):
    """带分页的响应。"""
    success: bool = True
    data: list[T] = []
    message: str = "操作成功"
    pagination: PaginationOut


class ErrorDetail(BaseModel):
    """错误详情。"""
    code: str
    message: str
    details: list[Any] | None = None


class ErrorResponse(BaseModel):
    """统一错误响应格式。"""
    success: bool = False
    error: ErrorDetail
