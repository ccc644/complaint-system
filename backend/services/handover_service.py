# 1009 离职交接 — 管理员把离职人员名下工单移交给接收人，历史过程记录完整保留
"""离职交接业务逻辑（三层分离：本模块不触碰 FastAPI，校验失败抛 HandoverError）。

设计要点：
- 人员归属核心在 complaint_assignees（换人 = 旧行 is_active=0 + 新行，指派历史天然保留）
  与 complaints.created_by_user_id（客服「我的工单」归属 + 通知目标键）；
- created_by/handler_name 等显示名字段为留痕，交接时不改写历史；
- work_order_log 只追加 handover 事件、不动旧日志 → 过程记录完整可见；
- 幂等：重复交接只处理仍 active 的指派与仍未换绑的录入归属，已完成部分自动跳过；
- 绝不走 delete_user 硬删除（会连带删光指派历史），停用一律用 deactivate。
"""

from data import database as db


class HandoverError(Exception):
    """离职交接业务校验失败。status_code 供 API 层映射为 HTTP 状态码。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _validate(from_user_id: int, to_user_id: int) -> tuple[dict, dict]:
    """双方校验：非同人、都存在、接收人在启用状态、系统管理员账号不可交接。"""
    if from_user_id == to_user_id:
        raise HandoverError("交接双方不能是同一人")
    from_user = db.get_user_by_id(from_user_id)
    if not from_user:
        raise HandoverError("离职人员不存在", status_code=404)
    to_user = db.get_user_by_id(to_user_id)
    if not to_user:
        raise HandoverError("接收人不存在", status_code=404)
    if not to_user.get("is_active", 1):
        raise HandoverError(f"接收人「{to_user['display_name']}」已停用，请先启用或另选接收人")
    if from_user.get("username") == "admin":
        raise HandoverError("系统管理员账号不可交接", status_code=409)
    return from_user, to_user


def preview_handover(from_user_id: int, to_user_id: int) -> dict:
    """预览交接范围：active 指派（审批人/承接人）+ 录入客服工单数，按工单去重合计。"""
    from_user, to_user = _validate(from_user_id, to_user_id)
    assignments = db.get_active_assignments_for_user(from_user_id)
    as_approver = sum(1 for a in assignments if a["assignee_type"] == "approver")
    as_assignee = sum(1 for a in assignments if a["assignee_type"] == "assignee")
    created = db.get_complaints_created_by_user(from_user_id)
    total = len({a["complaint_id"] for a in assignments} | {c["id"] for c in created})
    return {
        "from_user": {"id": from_user_id, "display_name": from_user["display_name"]},
        "to_user": {"id": to_user_id, "display_name": to_user["display_name"]},
        "as_approver": as_approver,
        "as_assignee": as_assignee,
        "as_creator": len(created),
        "total_complaints": total,
    }


def execute_handover(from_user_id: int, to_user_id: int,
                     operator: dict, deactivate: bool = False) -> dict:
    """执行交接：换绑指派 + 录入归属，逐单留痕 handover 日志，汇总通知接收人。

    operator: {display_name, role, position}（管理员操作人）。
    deactivate=True 时在移交完成后停用离职账号（软删除，数据保留）。
    """
    from_user, to_user = _validate(from_user_id, to_user_id)

    # 1) 指派换绑：按工单聚合该用户身上的身份（approver / assignee / is_primary）
    assignments = db.get_active_assignments_for_user(from_user_id)
    by_complaint: dict[int, dict] = {}
    for a in assignments:
        roles = by_complaint.setdefault(
            a["complaint_id"], {"approver": False, "assignee": False, "primary": False})
        if a["assignee_type"] == "approver":
            roles["approver"] = True
        else:
            roles["assignee"] = True
            if a.get("is_primary"):
                roles["primary"] = True

    moved_approver = moved_assignee = 0
    touched: set[int] = set()

    def _log_handover(complaint_id: int, roles_desc: str) -> None:
        db.create_work_order_log(
            complaint_id=complaint_id,
            event_type="handover",
            operator_name=operator["display_name"],
            operator_role=operator["role"],
            detail=f"离职交接：{from_user['display_name']} → {to_user['display_name']}"
                   f"（身份：{roles_desc}；操作人：{operator['display_name']}）",
            operator_position=operator.get("position", ""),
        )

    for cid, roles in by_complaint.items():
        if roles["approver"]:
            # set_assignee：同类型旧行自动置 is_active=0 + 插新行（审批人单值换人）
            db.set_assignee(cid, to_user_id, "approver", operator["display_name"])
            moved_approver += 1
        if roles["assignee"]:
            # 接收人已是该单有效承接人 → 仅停用离职者行；否则先补新行再停旧行
            if not db.is_active_assignee(cid, to_user_id):
                db.add_assignees(cid, [to_user_id], operator["display_name"])
            if roles["primary"]:
                db.set_primary_assignee(cid, to_user_id)
            db.deactivate_user_assignments(cid, from_user_id)
            moved_assignee += 1
        desc = "、".join(n for n, hit in (("审批人", roles["approver"]),
                                          ("承接人", roles["assignee"])) if hit)
        _log_handover(cid, desc)
        touched.add(cid)

    # 2) 录入客服归属换绑（显示名 created_by 不动，留痕）
    moved_created = 0
    created = db.get_complaints_created_by_user(from_user_id)
    if created:
        moved_created = db.transfer_complaints_creator(from_user_id, to_user_id)
        for c in created:
            if c["id"] not in touched:
                _log_handover(c["id"], "录入客服")
                touched.add(c["id"])

    # 3) 汇总通知接收人（一条，不逐单轰炸）
    if touched:
        db.create_notification(
            complaint_no="",
            title=f"🔄 离职交接：{from_user['display_name']} → {to_user['display_name']}",
            message=f"管理员 {operator['display_name']} 已完成离职交接，{len(touched)} 客户工程师单由"
                    f"{from_user['display_name']} 移交给您（审批人 {moved_approver} 张、承接人 "
                    f"{moved_assignee} 张、录入客服 {moved_created} 张）。各工单的历史过程记录"
                    f"可在时间线完整查看。",
            target_role="全员",
            category="awareness",
            target_user_id=to_user_id,
        )

    # 4) 交接成功后再停用（admin 账号已在 _validate 拦截；软删除保留全部数据）
    deactivated = False
    if deactivate:
        db.deactivate_user(from_user_id)
        deactivated = True

    return {
        "from_user": {"id": from_user_id, "display_name": from_user["display_name"]},
        "to_user": {"id": to_user_id, "display_name": to_user["display_name"]},
        "moved_approver": moved_approver,
        "moved_assignee": moved_assignee,
        "moved_created": moved_created,
        "total_complaints": len(touched),
        "deactivated": deactivated,
    }
