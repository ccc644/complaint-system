# 0824 钉钉工作通知服务 — 发送 action_card 到个人；失败绝不影响业务主流程
"""钉钉通知渠道服务。仅做「渠道」工作：解析收件人、构建卡片、调用钉钉 API、记录日志。
权限判断由系统自身负责（钉钉只负责把人带到系统，dingding.md 原则）。

API 采用旧版工作通知对（官方文档仍受支持；发送逻辑隔离在 _send_action_card 单函数，
未来可整体切换新版 v1.0/robot/oToMessages/batchSend）：
- GET  https://oapi.dingtalk.com/gettoken（appkey/appsecret → access_token，7200s）
- POST https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2
- POST https://oapi.dingtalk.com/topapi/v2/user/getbymobile（0825 管理端绑定辅助：手机号→userid）
"""

import threading
import time
from urllib.parse import quote

import httpx

from data import database as db
from core import dingtalk_config as cfg

_TOKEN_LOCK = threading.Lock()
_token_cache: dict = {"token": None, "expires_at": 0.0}
_REQUEST_TIMEOUT = 10.0           # 秒
_USERID_BATCH = 100               # asyncsend_v2 单次 userid_list 上限
_TOKEN_TTL = 7000                 # 钉钉 expires_in=7200，留 200s 余量
_DINGTALK_HOST = "https://oapi.dingtalk.com"


# ── 访问令牌 ──────────────────────────────────────
def fetch_access_token(app_key: str, app_secret: str) -> tuple[str, str]:
    """获取企业内部应用 access_token。返回 (token, err)；失败返回 ("", 错误信息)。"""
    try:
        r = httpx.get(
            f"{_DINGTALK_HOST}/gettoken",
            params={"appkey": app_key, "appsecret": app_secret},
            timeout=_REQUEST_TIMEOUT,
        )
        data = r.json()
        if data.get("errcode") == 0 and data.get("access_token"):
            return data["access_token"], ""
        return "", f"errcode={data.get('errcode')}, errmsg={data.get('errmsg')}"
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


def _get_cached_token() -> str | None:
    with _TOKEN_LOCK:
        if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
            return _token_cache["token"]
    token, _err = fetch_access_token(cfg.DINGTALK_APP_KEY, cfg.DINGTALK_APP_SECRET)
    if token:
        with _TOKEN_LOCK:
            _token_cache["token"] = token
            _token_cache["expires_at"] = time.time() + _TOKEN_TTL
    return token


def invalidate_token() -> None:
    """清空缓存令牌（40014 失效时重取用）。"""
    with _TOKEN_LOCK:
        _token_cache["token"] = None
        _token_cache["expires_at"] = 0.0


# ── UserID 查询：手机号 → 企业成员 userid（0825 管理端绑定辅助） ──
def query_userid_by_mobile(app_key: str, app_secret: str, mobile: str) -> tuple[dict | None, str]:
    """根据手机号查询企业成员 userid（topapi/v2/user/getbymobile）。
    应用需开通「通讯录-个人信息」读权限。返回 (成员dict, "") 或 (None, 错误信息)。"""
    token, err = fetch_access_token(app_key, app_secret)
    if not token:
        return None, f"获取 access_token 失败：{err}"
    try:
        r = httpx.post(
            f"{_DINGTALK_HOST}/topapi/v2/user/getbymobile",
            params={"access_token": token}, json={"mobile": mobile},
            timeout=_REQUEST_TIMEOUT,
        )
        data = r.json()
        if data.get("errcode") == 0 and data.get("result"):
            return data["result"], ""
        return None, f"errcode={data.get('errcode')}, errmsg={data.get('errmsg')}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


# ── 收件人解析：精准到人优先，否则角色→所有已绑定启用用户 ──
def resolve_recipients(target_user_id: int, target_role: str) -> list[dict]:
    """target_user_id>0 → 该用户；否则按角色展开（全员→全部角色）。
    返回已绑定钉钉的启用用户（按 dingtalk_userid 去重）。"""
    if target_user_id and target_user_id > 0:
        users = db.get_users_dingtalk_bindings(user_ids=[target_user_id])
    else:
        roles = [target_role] if target_role and target_role != "全员" else []
        users = db.get_users_dingtalk_bindings(roles=roles or None)
    seen: set[str] = set()
    out: list[dict] = []
    for u in users:
        if u["dingtalk_userid"] not in seen:
            seen.add(u["dingtalk_userid"])
            out.append(u)
    return out


# ── 卡片构建 ──────────────────────────────────────
def build_card_url(complaint_id: int, username: str = "") -> str:
    """按钮 URL：系统域名 + 工单详情路由（Vue history 模式 → /work-order/{id}）。
    0901 单收件人时带 ?u=账号：前端路由守卫从「凭证保险箱」自动恢复登录态，免输密码。
    无凭证时前端守卫带 ?redirect= 回跳该页（登录后再回到工单）。"""
    url = f"{cfg.PUBLIC_BASE_URL}/work-order/{complaint_id}"
    if username:
        url += f"?u={quote(username)}"
    return url


def _send_action_card(userids: list[str], title: str, markdown: str,
                      single_url: str) -> tuple[bool, str]:
    """同步调用 asyncsend_v2 发送 action_card。返回 (ok, err)；dry_run 时跳过 HTTP。
    内部处理 40014（token 失效重取一次）。"""
    if cfg.DINGTALK_DRY_RUN:
        return True, "dry_run"
    token = _get_cached_token()
    if not token:
        return False, "获取 access_token 失败"
    payload = {
        "agent_id": int(cfg.DINGTALK_AGENT_ID),
        "userid_list": ",".join(userids),
        "msg": {
            "msgtype": "action_card",
            "action_card": {
                "title": title[:128],
                "markdown": markdown[:2000],
                "single_title": "立即处理",
                "single_url": single_url,
            },
        },
    }
    for attempt in (1, 2):   # 第二次仅用于 40014 重取令牌后的重试
        try:
            r = httpx.post(
                f"{_DINGTALK_HOST}/topapi/message/corpconversation/asyncsend_v2",
                params={"access_token": token}, json=payload,
                timeout=_REQUEST_TIMEOUT,
            )
            data = r.json()
            errcode = data.get("errcode")
            if errcode == 0:
                return True, ""
            err = f"errcode={errcode}, errmsg={data.get('errmsg')}"
            if errcode == 40014 and attempt == 1:
                invalidate_token()
                token = _get_cached_token()
                if token:
                    continue
            return False, err
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
    return False, "unknown"


# ── 总入口：由 notification_service 包装层调用 ────
def dispatch_work_notification(complaint_no: str, title: str, message: str,
                               target_role: str, target_user_id: int) -> None:
    """派发钉钉工作通知。本地判断同步完成；HTTP 发送放守护线程，
    每次尝试记一行 dingtalk_send_log，任何异常绝不外抛。"""
    if not cfg.is_dingtalk_configured():
        return
    complaint_id = db.get_complaint_id_by_no(complaint_no) if complaint_no else None
    if not complaint_id:
        # 工单已删/不存在：记录后跳过（不发起 HTTP）
        db.record_dingtalk_send(complaint_no, target_role, "", "",
                                "no_complaint", "工单不存在或已删除")
        return
    recipients = resolve_recipients(target_user_id, target_role)
    if not recipients:
        db.record_dingtalk_send(complaint_no, target_role, "", "",
                                "no_recipient", "无已绑定钉钉的收件人")
        return
    # 0901 单收件人卡片带账号参数，配合前端保险箱自动恢复登录；群发卡片走本机上次账号兜底
    single_user = recipients[0]["username"] if len(recipients) == 1 else ""
    url = build_card_url(complaint_id, single_user)
    userids = [u["dingtalk_userid"] for u in recipients]
    ids = ",".join(str(u["id"]) for u in recipients)
    markdown = f"**工单号**：{complaint_no}\n\n{message}"

    def _run():
        for i in range(0, len(userids), _USERID_BATCH):
            batch_ids = userids[i:i + _USERID_BATCH]
            ok, err = _send_action_card(batch_ids, title, markdown, url)
            db.record_dingtalk_send(
                complaint_no, target_role, ids, ",".join(batch_ids),
                "dry_run" if err == "dry_run" else ("success" if ok else "failed"),
                "" if ok else err,
            )

    threading.Thread(target=_run, daemon=True).start()
