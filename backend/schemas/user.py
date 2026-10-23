# 0727 Phase 4 用户管理 Pydantic 模型
# 0819 v3.0 角色直接下拉选择，新增职位（position）必填
"""用户管理请求/响应模型。"""

from typing import Optional
from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    """0819 新增用户请求：账号 + 密码 + 显示名 + 角色下拉 + 职位。0824 增钉钉UserID（选填）。"""
    username: str = Field(..., min_length=1, description="登录账号")
    password: str = Field(..., min_length=4, description="登录密码（至少 4 位）")
    display_name: str = Field(..., min_length=1, description="显示名/姓名")
    role: str = Field(..., min_length=1, description="角色（六角色之一）")
    position: str = Field(..., min_length=1, description="公司职位（必填）")
    dingtalk_userid: str = Field(default="", max_length=64, description="钉钉UserID（选填，绑定后可收钉钉通知）")


class UserUpdateRequest(BaseModel):
    """0819 更新用户请求 — 字段均可选，仅更新传入的字段。0824 增钉钉UserID。"""
    display_name: Optional[str] = Field(default=None, description="显示名/姓名")
    role: Optional[str] = Field(default=None, description="角色")
    position: Optional[str] = Field(default=None, description="公司职位")
    is_active: Optional[bool] = Field(default=None, description="是否启用")
    dingtalk_userid: Optional[str] = Field(default=None, max_length=64, description="钉钉UserID（空串=解绑）")


class PasswordResetRequest(BaseModel):
    """重置密码请求。"""
    new_password: str = Field(..., min_length=4, description="新密码（至少 4 位）")


# ── 1009 离职交接 ──────────────────────────────────

class HandoverPreviewRequest(BaseModel):
    """离职交接预览请求。"""
    from_user_id: int = Field(..., description="离职人员用户 ID")
    to_user_id: int = Field(..., description="接收人用户 ID")


class HandoverExecuteRequest(BaseModel):
    """离职交接执行请求。"""
    from_user_id: int = Field(..., description="离职人员用户 ID")
    to_user_id: int = Field(..., description="接收人用户 ID")
    deactivate: bool = Field(default=True, description="交接完成后停用离职账号（软删除）")


class UserOut(BaseModel):
    """用户响应（不含密码哈希/可逆密文）。"""
    id: int
    username: str
    display_name: str
    role: str = ""
    position: str = ""
    dingtalk_userid: str = ""
    is_active: bool = True
    created_at: str = ""

    class Config:
        from_attributes = True
