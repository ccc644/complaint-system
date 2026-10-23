# 0811 系统设置服务 — SMTP 配置读写 + 连接测试
"""SMTP 邮箱设置业务逻辑：DB 优先、.env 兜底、运行时热刷新。
0824 增钉钉通知配置三件套（读/写热刷新/凭证测试）。
"""

import os
import smtplib
from pathlib import Path
from dotenv import load_dotenv

from data.database import get_setting, get_settings, set_settings_batch
from schemas.settings import (
    DingtalkConfigOut, DingtalkConfigUpdate, DingtalkTestResult,
    DingtalkUseridQuery, DingtalkUseridResult,
    SmtpConfigOut, SmtpConfigUpdate, SmtpTestResult,
)

# .env 兜底：读取项目根目录 .env 中的 SMTP_* 变量
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)

_SMTP_KEYS = ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from"]


def _read_from_env(key: str) -> str:
    """从 .env 读取单个 SMTP 配置项（兜底）。"""
    env_map = {
        "smtp_host": "SMTP_HOST",
        "smtp_port": "SMTP_PORT",
        "smtp_user": "SMTP_USER",
        "smtp_password": "SMTP_PASSWORD",
        "smtp_from": "SMTP_FROM",
    }
    env_key = env_map.get(key, "")
    return os.environ.get(env_key, "")


def _mask_password(pwd: str) -> str:
    """密码脱敏：仅保留末4位用于识别。"""
    if not pwd:
        return ""
    if len(pwd) <= 4:
        return "*" * len(pwd)
    return "*" * (len(pwd) - 4) + pwd[-4:]


def get_smtp_config() -> SmtpConfigOut:
    """获取当前 SMTP 配置（DB 优先，.env 兜底）。"""
    db_settings = get_settings(*_SMTP_KEYS)

    def _val(key: str) -> str:
        return db_settings.get(key, "") or _read_from_env(key)

    host = _val("smtp_host")
    port_str = _val("smtp_port")
    try:
        port = int(port_str) if port_str else 587
    except ValueError:
        port = 587
    user = _val("smtp_user")
    password = _val("smtp_password")
    sender = _val("smtp_from")

    return SmtpConfigOut(
        smtp_host=host,
        smtp_port=port,
        smtp_user=user,
        smtp_password=_mask_password(password),
        smtp_from=sender,
        is_configured=all([host, user, password, sender]),
    )


def update_smtp_config(data: SmtpConfigUpdate) -> SmtpConfigOut:
    """更新 SMTP 配置并热刷新运行时变量。"""
    batch: dict[str, str] = {}

    if data.smtp_host:
        batch["smtp_host"] = data.smtp_host
    batch["smtp_port"] = str(data.smtp_port)
    if data.smtp_user:
        batch["smtp_user"] = data.smtp_user
    # 密码：非空时更新，为空时保留原值
    if data.smtp_password:
        batch["smtp_password"] = data.smtp_password
    if data.smtp_from:
        batch["smtp_from"] = data.smtp_from

    if batch:
        set_settings_batch(batch)

    # 热刷新运行时 SMTP 模块变量
    from core.smtp_config import reload_smtp_config
    reload_smtp_config()

    return get_smtp_config()


def test_smtp_connection(config: SmtpConfigUpdate) -> SmtpTestResult:
    """测试 SMTP 连接：尝试连接 + STARTTLS + 登录。"""
    host = config.smtp_host
    port = config.smtp_port
    user = config.smtp_user
    password = config.smtp_password
    sender = config.smtp_from

    if not host:
        return SmtpTestResult(success=False, message="SMTP 服务器地址不能为空")
    if not user or not password:
        return SmtpTestResult(success=False, message="用户名和密码不能为空")

    try:
        server = smtplib.SMTP(host, port, timeout=15)
        server.ehlo()
        if server.has_extn("STARTTLS"):
            server.starttls()
            server.ehlo()
        server.login(user, password)
        server.quit()
        return SmtpTestResult(
            success=True,
            message=f"✅ 连接成功！{host}:{port}，发件人：{sender or user}",
        )
    except smtplib.SMTPAuthenticationError:
        return SmtpTestResult(success=False, message="❌ 认证失败：用户名或密码错误")
    except smtplib.SMTPConnectError:
        return SmtpTestResult(success=False, message=f"❌ 无法连接到 {host}:{port}，请检查地址和端口")
    except Exception as e:
        return SmtpTestResult(success=False, message=f"❌ 连接失败：{str(e)}")


# ═══════════════════ 0824 钉钉通知配置（DB 优先，.env 兜底，运行时热刷新） ═══════════════════

_DINGTALK_KEYS = [
    "dingtalk_enabled", "dingtalk_app_key", "dingtalk_app_secret",
    "dingtalk_agent_id", "public_base_url", "dingtalk_dry_run",
]


def get_dingtalk_config() -> DingtalkConfigOut:
    """获取当前钉钉配置（读 core 运行时变量，密钥脱敏）。"""
    from core import dingtalk_config as cfg
    return DingtalkConfigOut(
        enabled=cfg.DINGTALK_ENABLED,
        app_key=cfg.DINGTALK_APP_KEY,
        app_secret=_mask_password(cfg.DINGTALK_APP_SECRET),
        agent_id=cfg.DINGTALK_AGENT_ID,
        public_base_url=cfg.PUBLIC_BASE_URL,
        dry_run=cfg.DINGTALK_DRY_RUN,
        is_configured=cfg.is_dingtalk_configured(),
    )


def update_dingtalk_config(data: DingtalkConfigUpdate) -> DingtalkConfigOut:
    """更新钉钉配置并热刷新运行时变量。"""
    batch: dict[str, str] = {
        "dingtalk_enabled": "1" if data.enabled else "",
        "dingtalk_app_key": (data.app_key or "").strip(),
        "dingtalk_agent_id": (data.agent_id or "").strip(),
        "public_base_url": (data.public_base_url or "").strip().rstrip("/"),
        "dingtalk_dry_run": "1" if data.dry_run else "",
    }
    # 密钥：非空时更新，为空时保留原值
    if (data.app_secret or "").strip():
        batch["dingtalk_app_secret"] = data.app_secret.strip()

    set_settings_batch(batch)

    # 热刷新运行时钉钉模块变量
    from core.dingtalk_config import reload_dingtalk_config
    reload_dingtalk_config()

    return get_dingtalk_config()


def test_dingtalk_connection(config: DingtalkConfigUpdate) -> DingtalkTestResult:
    """测试钉钉凭证：用表单参数（缺项回退当前配置值）获取 access_token。"""
    from core import dingtalk_config as cfg
    from services.dingtalk_service import fetch_access_token

    key = (config.app_key or "").strip() or cfg.DINGTALK_APP_KEY
    secret = (config.app_secret or "").strip() or cfg.DINGTALK_APP_SECRET
    if not key or not secret:
        return DingtalkTestResult(success=False, message="AppKey 和 AppSecret 不能为空")

    token, err = fetch_access_token(key, secret)
    if token:
        return DingtalkTestResult(success=True, message="✅ 获取 access_token 成功，凭证有效")
    return DingtalkTestResult(success=False, message=f"❌ 获取失败：{err}")


def lookup_dingtalk_userid(req: DingtalkUseridQuery) -> DingtalkUseridResult:
    """0825 根据手机号查钉钉 UserID（绑定用户辅助）。凭证缺省回退当前配置。"""
    from core import dingtalk_config as cfg
    from services.dingtalk_service import query_userid_by_mobile

    mobile = (req.mobile or "").strip()
    if len(mobile) != 11 or not mobile.isdigit():
        return DingtalkUseridResult(success=False, message="请输入 11 位手机号")

    key = (req.app_key or "").strip() or cfg.DINGTALK_APP_KEY
    secret = (req.app_secret or "").strip() or cfg.DINGTALK_APP_SECRET
    if not key or not secret:
        return DingtalkUseridResult(success=False, message="AppKey 和 AppSecret 不能为空（请先填写或保存配置）")

    user, err = query_userid_by_mobile(key, secret, mobile)
    if user:
        return DingtalkUseridResult(
            success=True, message="✅ 查询成功",
            userid=user.get("userid") or "", name=user.get("name") or "",
        )
    # 常见错误码补人话提示，其余原样透出
    hint = ""
    if "60121" in err or "40019" in err:
        hint = "（该手机号可能不在企业通讯录中）"
    elif "errcode=88" in err or "60011" in err:
        hint = "（应用可能未开通「通讯录-个人信息」读权限，请在钉钉开放平台-权限管理中申请）"
    return DingtalkUseridResult(success=False, message=f"❌ 查询失败：{err}{hint}")
