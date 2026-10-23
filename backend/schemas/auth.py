# 0724 认证相关 Pydantic 模型
# 0819 v3.0 登录简化为账号+密码；UserInfo 增加职位（position）
"""认证请求/响应模型。"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """登录请求 — 账号 + 密码；remember=勾选「7天内自动登录」时签发 7 天长票。"""
    username: str
    password: str
    remember: bool = False


class TokenResponse(BaseModel):
    """JWT Token 响应。"""
    token: str
    token_type: str = "Bearer"


class UserInfo(BaseModel):
    """当前登录用户信息（嵌入 JWT payload）。"""
    id: int
    username: str
    display_name: str
    role: str        # 角色：管理员/客服/客服主管/办理人/审批人/承接人
    position: str    # 0819 公司职位（建号时手填）


class LoginOut(BaseModel):
    """登录成功完整响应。"""
    token: str
    token_type: str = "Bearer"
    user: UserInfo
