# 0824 通知服务包装层 — 站内通知原样保留，新增钉钉渠道（仅 action_required）
"""create_notification 包装：签名与 data.database.create_notification 完全一致，
调用方零改动。先写站内通知（行为与原来完全一致），再派发钉钉工作通知；
钉钉派发的任何异常都不影响站内通知与业务主流程。
"""

from data import database as db


def create_notification(complaint_no, title, message, target_role,
                        category: str = "awareness", target_user_id: int = 0) -> None:
    """站内通知 + 钉钉渠道分发（仅待处理类 action_required 推钉钉）。"""
    db.create_notification(complaint_no, title, message, target_role,
                           category, target_user_id)
    if category != "action_required":
        return
    try:
        from services.dingtalk_service import dispatch_work_notification
        dispatch_work_notification(complaint_no, title, message,
                                   target_role, target_user_id)
    except Exception:
        pass  # 钉钉渠道任何异常都不影响业务主流程
