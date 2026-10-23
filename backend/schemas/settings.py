# 0811 SMTP 邮箱设置 — Pydantic 模型
"""系统设置相关的请求/响应模型。"""

from pydantic import BaseModel, Field


class SmtpConfigOut(BaseModel):
    """SMTP 配置响应（密码脱敏）。"""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""      # GET 时脱敏：仅返回末4位提示
    smtp_from: str = ""
    is_configured: bool = False


class SmtpConfigUpdate(BaseModel):
    """SMTP 配置更新请求。"""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""      # 空字符串表示不修改密码
    smtp_from: str = ""


class SmtpTestResult(BaseModel):
    """SMTP 连接测试结果。"""
    success: bool
    message: str


class DingtalkConfigOut(BaseModel):
    """0824 钉钉通知配置响应（密钥脱敏）。"""
    enabled: bool = False
    app_key: str = ""
    app_secret: str = ""      # GET 时脱敏：仅返回末4位提示
    agent_id: str = ""
    public_base_url: str = ""
    dry_run: bool = False
    is_configured: bool = False


class DingtalkConfigUpdate(BaseModel):
    """0824 钉钉通知配置更新请求。"""
    enabled: bool = False
    app_key: str = ""
    app_secret: str = ""      # 空字符串表示不修改密钥
    agent_id: str = ""
    public_base_url: str = ""
    dry_run: bool = False


class DingtalkTestResult(BaseModel):
    """0824 钉钉凭证测试结果（获取 access_token）。"""
    success: bool
    message: str


class DingtalkUseridQuery(BaseModel):
    """0825 手机号查钉钉 UserID 请求（凭证留空则回退已保存配置）。"""
    mobile: str = Field(max_length=20)
    app_key: str = ""
    app_secret: str = ""      # 空则回退已保存密钥


class DingtalkUseridResult(BaseModel):
    """0825 手机号查钉钉 UserID 结果。"""
    success: bool
    message: str
    userid: str = ""
    name: str = ""
