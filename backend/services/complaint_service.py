# 0724 投诉业务逻辑层 — 状态机 / 校验 / 通知触发
# 0819 v3.0 角色流程重构：新 7 状态 + 子类型 + 多人指派（complaint_assignees）
"""投诉生命周期业务逻辑。

新状态机：
录入(客服) → 客服主管审核(intake) → 通过[待客户排查|指派审批人] / 拒绝 → 待客服处理(rework)
待客户排查 → 已解决 → 待客服处理(customer_confirm) / 未解决 → 指派审批人
指派审批人(办理人) → 指派承接人(审批人评估+多人指派+排期) → 处理中
处理中 → 完成 → 待客服处理(customer_confirm) / 处理不了 → 指派审批人
待客服处理(customer_confirm) → 邮件审核回路(客服主管审核(email)) → 客户确认 → 已关闭(+KB归档)
"""

from datetime import datetime
from types import SimpleNamespace
from typing import Optional

from data.database import (
    get_all_complaints, get_complaint, create_complaint, update_complaint,
    delete_complaint, create_kb_entry,
    create_work_order_log,
    get_engineer_processing_hours,
    normalize_status, CANONICAL_STATUSES, PRIORITIES,
    APPROVER_CANDIDATE_ROLES, ASSIGNEE_CANDIDATE_ROLES,
    create_progress_update, latest_progress,
    mark_notifications_read_by_complaint,
    set_email_review_status,
    set_assignee, add_assignees, deactivate_assignees,
    get_active_approver, get_historical_approver_user_ids, get_active_assignees, get_assignees_map,
    is_active_assignee, is_active_approver, get_assignee_active_complaints,
    get_complaint_approver_user_ids, get_complaint_assignee_user_ids,
    set_primary_assignee, get_primary_assignee, is_primary_assignee,
    get_users_by_roles, get_users_by_display_names, get_user_by_id,
)
from schemas.complaint import (
    WARNING_KEYWORDS_LOW, WARNING_KEYWORDS_HIGH, WARNING_KEYWORDS_ALL, HIGH_RISK_WATCHERS,
    RETURN_APPROVERS,
)
# 0824 钉钉通知：create_notification 改走包装层（站内通知原样 + action_required 派发钉钉）
from services.notification_service import create_notification
from ai_engine.ai_engine import (
    find_similar_cases, extract_keywords, extract_knowledge_llm, embed_kb_entry,
)
from core.websocket import manager

import os
import re

# ── WebSocket 广播辅助 ────────────────────────────────
def _broadcast(event_type: str, complaint_id: int, complaint_no: str,
               status: str, message: str, target_role: str = "全员") -> None:
    """异步安全：同步触发后台广播任务（不阻塞当前请求）。0819 仅角色过滤。"""
    import asyncio
    event = {
        "type": event_type,
        "complaint_id": complaint_id,
        "complaint_no": complaint_no,
        "status": status,
        "message": message,
    }
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(manager.broadcast(event, target_role=target_role))
    except RuntimeError:
        pass  # 无事件循环时静默跳过


# ── 看板业务逻辑：带筛选/搜索的投诉列表 ─────────────
def list_complaints_for_kanban(
    role: str,
    status_filter: str | None = None,
    category_filter: str | None = None,
    priority_filter: str | None = None,
    keyword: str = "",
    dept_filter: str = "",
    my_orders_only: bool = False,
    current_user_id: int = 0,
    current_display_name: str = "",
) -> list[dict]:
    """0819 获取看板投诉列表：所有角色可见全部工单；
    my_orders_only 按角色匹配「我的工单」（0820 见 _apply_my_orders_filter）。
    """
    complaints = get_all_complaints(
        status_filter=status_filter if status_filter and status_filter != "全部" else None,
        category_filter=category_filter if category_filter and category_filter != "全部" else None,
    )

    # 优先级筛选（内存过滤）
    if priority_filter and priority_filter != "全部":
        complaints = [c for c in complaints if c["priority"] == priority_filter]

    # 关键词搜索：编号/客户/设备
    if keyword:
        kw = keyword.lower()
        complaints = [
            c for c in complaints
            if kw in (c.get("complaint_no") or "").lower()
            or kw in (c.get("customer_name") or "").lower()
            or kw in (c.get("equipment_model") or "").lower()
        ]

    # 0820 「仅显示我的工单」按角色软过滤（不勾选时全员可见全部工单）
    if my_orders_only and current_user_id:
        complaints = _apply_my_orders_filter(complaints, role, current_user_id)

    return complaints


# ── 0820 「仅显示我的工单」两层筛选 ──────────────────
# 第一层：角色状态范围（勾选后仅显示这些列）；第二层：按人过滤
# 0825 办理人扩列：办理人可被指派为审批人（指派承接人）/追加为承接人（处理中），需按绑定可见
# 终态（已关闭/已撤回）不进任何角色范围——勾选「我的工单」时不显示，不勾选时全员可见
_STATUS_SCOPE_BY_ROLE = {
    "客服": ("待客服处理", "待客户排查"),
    "客服主管": ("客服主管审核",),
    "办理人": ("指派审批人", "指派承接人", "处理中"),
    "审批人": ("指派承接人", "处理中"),
    "承接人": ("指派承接人", "处理中"),
}


def _apply_my_orders_filter(complaints: list[dict], role: str, user_id: int) -> list[dict]:
    """0820 按角色两层软过滤「我的工单」（不勾选时全部可见）：
    第一层按 _STATUS_SCOPE_BY_ROLE 保留本角色状态列；
    第二层：客服→录入人（created_by_user_id）；审批人→审批人绑定 ∪ 承接人绑定（双权限）；
    0825 办理人→指派审批人列全员保留（单人岗位工作队列）∪（指派承接人/处理中列按审批人∪承接人绑定）；
    承接人→承接人绑定；客服主管无第二层（单人岗位）；管理员无范围→不过滤。
    0826 客服例外：只按录入人过滤、不看状态——自己录入的所有状态工单（含审核中/已撤回/已关闭）均可见。
    """
    if role == "客服":
        return [c for c in complaints if c.get("created_by_user_id") == user_id]
    scope = _STATUS_SCOPE_BY_ROLE.get(role)
    if not scope:
        return complaints
    complaints = [c for c in complaints if c["status"] in scope]
    if role == "审批人":
        my_ids = get_complaint_approver_user_ids(user_id) | get_complaint_assignee_user_ids(user_id)
        return [c for c in complaints if c["id"] in my_ids]
    if role == "办理人":
        my_ids = get_complaint_approver_user_ids(user_id) | get_complaint_assignee_user_ids(user_id)
        return [c for c in complaints if c["status"] == "指派审批人" or c["id"] in my_ids]
    if role == "承接人":
        my_ids = get_complaint_assignee_user_ids(user_id)
        return [c for c in complaints if c["id"] in my_ids]
    return complaints


# ── 进度百分比计算（看板卡片） ──────────────────────
def get_progress_pct(status: str) -> int:
    """0819 根据状态返回看板卡片进度百分比。已撤回（0825 终态）不适用进度，保持 0。"""
    if status == "已关闭":
        return 100
    if status == "已撤回":
        return 0
    if status == "待客服处理":
        return 80
    if status == "处理中":
        return 50
    if status == "指派承接人":
        return 30
    if status == "指派审批人":
        return 20
    if status == "待客户排查":
        return 10
    if status == "客服主管审核":
        return 5
    return 0


# ── 编辑/删除权限检查 ──────────────────────────────
def can_edit_delete(role: str, status: str, sub_type: str = "") -> bool:
    """0819 检查当前角色是否可以编辑/删除指定状态的工单。
    管理员始终可编辑/删除；客服仅 客服主管审核(intake)、待客户排查、待客服处理(rework)。
    """
    if role == "管理员":
        return True
    if role == "客服" and (
        (status == "客服主管审核" and sub_type == "intake")
        or status == "待客户排查"
        or (status == "待客服处理" and sub_type == "rework")
    ):
        return True
    return False


# ── 备注追加辅助 ─────────────────────────────────
def _append_remark(existing: str, operator_name: str, content: str) -> str:
    """在已有备注后追加一条新备注（操作人 + 时间 + 内容）。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"[{operator_name}] {now} | {content}"
    existing = existing or ""
    return existing + "\n---\n" + entry if existing else entry


# 0923 KB 归档知识提取：排查快捷路径关单时，从备注中提取这些标签的内容块
# （排查结果=客服提交的客户排查发现；审核评估=主管初判；主管评估=自排查审核意见，可能套 [自排查审核] 等前缀）
_KB_REMARK_BLOCK_RE = re.compile(
    r"^\[([^\]]+)\]\s+[\d\-: .]+\s*\|\s*(?:\[[^\]]+\]\s*)?(排查结果|审核评估|主管评估)\s*[:：]\s*(.+)$",
    re.DOTALL,
)


def _extract_remark_kb_blocks(remarks: str) -> list:
    """解析备注流中含排查知识的内容块，返回 [(操作人, 标签, 内容), ...]。

    备注格式（_append_remark 产物）：`[操作人] YYYY-MM-DD HH:MM | 标签：内容`，
    多条以 `\\n---\\n` 分隔；无匹配标签的块（回退/撤回/承接评估等）跳过。
    """
    if not remarks:
        return []
    blocks = []
    for chunk in remarks.split("\n---\n"):
        m = _KB_REMARK_BLOCK_RE.match(chunk.strip())
        if m:
            blocks.append((m.group(1), m.group(2), m.group(3).strip()))
    return blocks


# 0803 统一日志写入辅助（0819 职位留痕）
def _log_event(complaint_id: int, event_type: str, operator_name: str, operator_role: str,
               operator_position: str = "", old_status: str = "", new_status: str = "",
               detail: str = "", metadata: str = "{}") -> int:
    """所有状态变更和关键操作统一写入 work_order_log（含职位）。"""
    return create_work_order_log(
        complaint_id=complaint_id,
        event_type=event_type,
        operator_name=operator_name,
        operator_role=operator_role,
        old_status=old_status,
        new_status=new_status or old_status,
        detail=detail,
        metadata=metadata,
        operator_position=operator_position,
    )


# 0819 标记通知已读辅助（新签名：角色 + user_id）
def _mark_read(complaint_no: str, current_user) -> None:
    mark_notifications_read_by_complaint(complaint_no, current_user.role, current_user.id)


# ── 0821 工单操作隔离守卫 ──────────────────────────
def _check_active_approver(complaint_id: int, current_user) -> str | None:
    """审批人操作隔离：管理员旁路；仅该工单当前有效审批人可操作。
    返回错误消息（阻断）或 None（放行）。"""
    if current_user.role == "管理员":
        return None
    approver = get_active_approver(complaint_id)
    if not approver:
        return "该工单当前无有效审批人，请联系管理员重新指派"
    if approver.get("user_id") != current_user.id:
        return "仅该工单的当前审批人可执行此操作"
    return None


def _check_cs_creator(complaint: dict, current_user) -> str | None:
    """客服操作隔离：管理员旁路；客服仅能操作自己录入的工单（容忍 current_user=None）。
    返回错误消息（阻断）或 None（放行）。"""
    if not current_user or current_user.role != "客服":
        return None
    if complaint.get("created_by_user_id") != current_user.id:
        return "仅录入该工单的客服可执行此操作"
    return None


# ── 0819 客服主管客诉审核（intake）─────────────────
def supervisor_intake_review(
    complaint_id: int, action: str, priority: str, route: str,
    rejection_note: str, evaluation: str = "", current_user=None,
) -> dict:
    """客服主管审核客诉录入内容。
    approve：必须携带 P0-P3 优先级 + route（待客户排查 / 指派审批人）+ 审核评估（0820）
    reject：必须携带拒绝原因 → 待客服处理(rework)
    0826 撤回动作移出审核：改由录入客服在看板发起（withdraw_complaint）
    """
    if current_user.role not in ("客服主管", "管理员"):
        return {"success": False, "message": "仅客服主管/管理员可执行此操作"}

    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    if complaint.get("status") != "客服主管审核" or complaint.get("sub_type") != "intake":
        return {"success": False, "message": "当前状态不允许客诉审核"}

    if action == "approve":
        if priority not in PRIORITIES:
            return {"success": False, "message": "请确认优先级（P0-P3）"}
        if route not in ("待客户排查", "指派审批人"):
            return {"success": False, "message": "请选择通过后去向（转待客户排查 / 转指派审批人）"}
        # 0820 审核通过也必须填写审核评估
        if not evaluation or not evaluation.strip():
            return {"success": False, "message": "请填写客服主管审核评估（可点击上方 AI 生成）"}

        evaluation_text = evaluation.strip()
        eval_brief = evaluation_text[:100] + ("…" if len(evaluation_text) > 100 else "")
        update_complaint(complaint_id, {
            "priority": priority,
            "priority_confirmed_by": current_user.display_name,
            "status": route,
            "sub_type": "",
            "supervisor_rejection_note": None,
            "re_edited": 0,
            "remarks": _append_remark(
                complaint.get("remarks", ""), current_user.display_name,
                f"审核评估：{evaluation_text}",
            ),
        })
        _log_event(complaint_id, "intake_approved",
                   current_user.display_name, current_user.role, current_user.position,
                   old_status="客服主管审核", new_status=route,
                   detail=f"客诉审核通过，优先级 {priority}，转入{route}（评估：{eval_brief}）")
        create_notification(
            complaint_no=complaint["complaint_no"],
            title=f"✅ 审核已通过：{complaint['complaint_no']}",
            message=f"客服主管 {current_user.display_name} 已审核通过工单（优先级 {priority}），已进入「{route}」。审核评估：{eval_brief}",
            target_role="客服",
            category="action_required",
            target_user_id=complaint.get("created_by_user_id", 0),
        )
        # 0820 审核通过直接转指派时知会办理人（其余进入指派审批人的路径均已有通知）
        if route == "指派审批人":
            create_notification(
                complaint_no=complaint["complaint_no"],
                title=f"📌 待指派审批人：{complaint['complaint_no']}",
                message=f"客诉审核已通过（优先级 {priority}），请办理人为工单指派审批人。",
                target_role="办理人",
                category="action_required",
            )
        _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
                   route, f"客诉审核通过（优先级 {priority}），转入{route}", target_role="全员")
        _mark_read(complaint["complaint_no"], current_user)
        return {"success": True, "message": f"审核通过，工单进入{route}"}

    # reject
    if not rejection_note or not rejection_note.strip():
        return {"success": False, "message": "拒绝原因不得为空"}
    update_complaint(complaint_id, {
        "status": "待客服处理",
        "sub_type": "rework",
        "supervisor_rejection_note": rejection_note.strip(),
        "re_edited": 0,
    })
    _log_event(complaint_id, "intake_rejected",
               current_user.display_name, current_user.role, current_user.position,
               old_status="客服主管审核", new_status="待客服处理",
               detail=f"客诉审核拒绝：{rejection_note.strip()}")
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"❌ 审核被拒绝：{complaint['complaint_no']}",
        message=f"客服主管 {current_user.display_name} 拒绝了工单录入审核。原因：{rejection_note.strip()}。请修改后重新提交。",
        target_role="客服",
        category="action_required",
        target_user_id=complaint.get("created_by_user_id", 0),
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "待客服处理", "客诉审核被拒绝，退回客服修改", target_role="客服")
    _mark_read(complaint["complaint_no"], current_user)
    return {"success": True, "message": "已拒绝，退回客服修改"}


# ── 0826 工单撤回（客服录入人，全流程除终态）──────────
def withdraw_complaint(complaint_id: int, withdraw_note: str, current_user) -> dict:
    """录入客服撤回自己的工单 → 终态「已撤回」（不入知识库，管理员可改状态恢复）。
    0826 由客服主管审核动作移入：客服在看板对非「已关闭/已撤回」工单发起，原因必填写日志。
    """
    if current_user.role != "客服":
        return {"success": False, "message": "仅录入该工单的客服可撤回"}
    if not withdraw_note or not withdraw_note.strip():
        return {"success": False, "message": "撤回原因不得为空"}

    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    if complaint.get("created_by_user_id") != current_user.id:
        return {"success": False, "message": "仅录入该工单的客服可撤回"}
    if complaint.get("status") in ("已关闭", "已撤回"):
        return {"success": False, "message": "终态工单不可撤回"}

    old_status = complaint.get("status", "")
    note = withdraw_note.strip()
    update_complaint(complaint_id, {
        "status": "已撤回",
        "sub_type": "",
        "supervisor_rejection_note": None,
        "re_edited": 0,
        "remarks": _append_remark(
            complaint.get("remarks", ""), current_user.display_name,
            f"工单撤回：{note}",
        ),
    })
    _mark_read(complaint["complaint_no"], current_user)
    _log_event(complaint_id, "intake_withdrawn",
               current_user.display_name, current_user.role, current_user.position,
               old_status=old_status, new_status="已撤回",
               detail=f"录入客服撤回工单（原状态 {old_status}）：{note}")
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"↩️ 工单已撤回：{complaint['complaint_no']}",
        message=f"录入客服 {current_user.display_name} 撤回了工单（原状态：{old_status}）。原因：{note}。工单已转入「已撤回」。",
        target_role="全员",
        category="awareness",
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "已撤回", f"录入客服撤回工单：{note}", target_role="全员")
    return {"success": True, "message": "工单已撤回"}


# ── 0819 客服重新提交（待客服处理 rework）────────────
def cs_resubmit(complaint_id: int, current_user) -> dict:
    """客服修改完成后重新提交审核。
    邮件审核被拒的工单（email_review_status=rejected）重提后回到 客服主管审核(email)；
    客诉审核退回的重提后回到 客服主管审核(intake)。
    """
    if current_user.role not in ("客服", "管理员"):
        return {"success": False, "message": "仅客服/管理员可执行此操作"}

    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    # 0821 客服操作隔离：仅录入该工单的客服可重新提交
    cs_err = _check_cs_creator(complaint, current_user)
    if cs_err:
        return {"success": False, "message": cs_err}
    if complaint.get("status") != "待客服处理" or complaint.get("sub_type") != "rework":
        return {"success": False, "message": "当前状态不允许重新提交"}

    review_type = "email" if complaint.get("email_review_status") == "rejected" else "intake"
    # 0819 邮件重提：重置审核状态为 pending，供主管再次审核
    if review_type == "email":
        set_email_review_status(complaint_id, "pending")
    update_complaint(complaint_id, {
        "status": "客服主管审核",
        "sub_type": review_type,
        "re_edited": 1,
    })
    _log_event(complaint_id, "resubmitted",
               current_user.display_name, current_user.role, current_user.position,
               old_status="待客服处理", new_status="客服主管审核",
               detail=f"客服重新提交{'邮件' if review_type == 'email' else '客诉'}审核")
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"📋 待审核：{complaint['complaint_no']}",
        message=f"客服 {current_user.display_name} 已重新提交{'邮件' if review_type == 'email' else '客诉'}内容，请审核。",
        target_role="客服主管",
        category="action_required",
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "客服主管审核", "客服已重新提交审核", target_role="客服主管")
    _mark_read(complaint["complaint_no"], current_user)
    return {"success": True, "message": "已重新提交审核"}


# ── 0819 待客户排查结果 ────────────────────────────
def cs_investigation_result(complaint_id: int, result: str, remark: str, current_user) -> dict:
    """客服提交客户排查结果。
    resolved → 待客服处理(customer_confirm)；unresolved → 指派审批人。
    """
    if current_user.role not in ("客服", "管理员"):
        return {"success": False, "message": "仅客服/管理员可执行此操作"}

    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    # 0821 客服操作隔离：仅录入该工单的客服可提交排查结果
    cs_err = _check_cs_creator(complaint, current_user)
    if cs_err:
        return {"success": False, "message": cs_err}
    if complaint.get("status") != "待客户排查":
        return {"success": False, "message": "当前状态不允许提交排查结果"}

    if result not in ("resolved", "unresolved"):
        return {"success": False, "message": "无效的排查结果"}

    update_data = {}
    if remark and remark.strip():
        update_data["remarks"] = _append_remark(
            complaint.get("remarks", ""), current_user.display_name,
            f"排查结果：{remark.strip()}",
        )

    if result == "resolved":
        update_data.update({"status": "待客服处理", "sub_type": "customer_confirm"})
        event = "investigation_resolved"
        detail = "客户排查结果为已解决，转入待客服处理（待客户确认）"
        notif_title = f"✋ 待客户确认：{complaint['complaint_no']}"
        notif_msg = "客户排查已解决，请客服联系客户确认并关闭工单。"
        notif_role = "客服"
        notif_uid = complaint.get("created_by_user_id", 0)
        notif_cat = "action_required"
    else:
        update_data.update({"status": "指派审批人", "sub_type": ""})
        event = "investigation_unresolved"
        detail = "客户排查结果为未解决，转入指派审批人"
        notif_title = f"📌 待指派审批人：{complaint['complaint_no']}"
        notif_msg = "客户排查未解决，请办理人指派审批人。"
        notif_role = "办理人"
        notif_uid = 0
        notif_cat = "action_required"

    if remark and remark.strip():
        detail += f"（备注：{remark.strip()}）"
    update_complaint(complaint_id, update_data)

    _log_event(complaint_id, event,
               current_user.display_name, current_user.role, current_user.position,
               old_status="待客户排查", new_status=update_data.get("status", ""),
               detail=detail)
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=notif_title,
        message=notif_msg,
        target_role=notif_role,
        category=notif_cat,
        target_user_id=notif_uid,
    )
    # 0820 知会客服主管（单人岗位角色广播）
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"🔍 排查结果已提交：{complaint['complaint_no']}",
        message=(
            f"客服 {current_user.display_name} 提交了排查结果：{'已解决（转客户确认）' if result == 'resolved' else '未解决（转指派审批人）'}。"
        ),
        target_role="客服主管",
        category="awareness",
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               update_data.get("status", ""), detail, target_role="全员")
    _mark_read(complaint["complaint_no"], current_user)
    return {"success": True, "message": "排查结果已提交"}


# ── 0819 指派审批人（办理人）──────────────────────
def assign_approver(complaint_id: int, user_id: int, current_user, note: str = "") -> dict:
    """办理人指派审批人（候选角色：办理人/审批人），工单转入指派承接人。
    0825 指派说明必填：写入工单日志 detail，随工单流转日志导出。"""
    if current_user.role not in ("办理人", "管理员"):
        return {"success": False, "message": "仅办理人/管理员可指派审批人"}
    if not note or not note.strip():
        return {"success": False, "message": "请填写指派说明（必填，将写入工单日志）"}

    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    if complaint.get("status") != "指派审批人":
        return {"success": False, "message": "当前状态不允许指派审批人"}

    candidates = get_users_by_roles(APPROVER_CANDIDATE_ROLES)
    target = next((u for u in candidates if u["id"] == user_id), None)
    if not target:
        return {"success": False, "message": "只能从「办理人/审批人」中选择审批人"}

    # 0825 先清操作者本工单旧通知再生成新通知：防止自指派时刚生成的通知立即被自己置为已读
    _mark_read(complaint["complaint_no"], current_user)

    # 0820 改派时知会旧审批人
    old_approver = get_active_approver(complaint_id)
    if old_approver and old_approver["user_id"] != user_id:
        create_notification(
            complaint_no=complaint["complaint_no"],
            title=f"🔁 已改派审批人：{complaint['complaint_no']}",
            message=f"工单 {complaint['complaint_no']} 已由办理人 {current_user.display_name} 改派给其他审批人，您不再负责该工单。",
            target_role="全员",
            category="awareness",
            target_user_id=old_approver["user_id"],
        )

    set_assignee(complaint_id, user_id, "approver", current_user.display_name)
    # 0820 记录办理人（指派审批人的操作人），重派时覆盖
    update_complaint(complaint_id, {
        "status": "指派承接人",
        "sub_type": "",
        "handler_name": current_user.display_name,
    })

    _log_event(complaint_id, "approver_assigned",
               current_user.display_name, current_user.role, current_user.position,
               old_status="指派审批人", new_status="指派承接人",
               detail=f"指派审批人：{target['display_name']}（{target['position']}）。说明：{note.strip()}")
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"📌 您被指派为审批人：{complaint['complaint_no']}",
        message=f"办理人 {current_user.display_name} 指派您为工单 {complaint['complaint_no']} 的审批人，请完成承接评估与承接人指派。",
        target_role="审批人",
        category="action_required",
        target_user_id=user_id,
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "指派承接人", f"已指派审批人 {target['display_name']}", target_role="全员")
    return {"success": True, "message": f"已指派审批人 {target['display_name']}"}


# ── 0819 审批人「不可承接」退回 ────────────────────
def approver_reject(complaint_id: int, reason: str, current_user) -> dict:
    """审批人评估不可承接 → 退回指派审批人，由办理人重新指派。

    1020 退回审批：非管理员不再即时退回，改为生成退回申请，由员工25/员工26或签审批；
    管理员保留直接退回（跳过审批）。审批通过后由 _execute_approver_reject 执行原流转。"""
    if current_user.role == "管理员":
        if not reason or not reason.strip():
            return {"success": False, "message": "不可承接原因不得为空"}
        complaint = get_complaint(complaint_id)
        if not complaint:
            return {"success": False, "message": "工单不存在"}
        if complaint.get("status") != "指派承接人":
            return {"success": False, "message": "当前状态不允许退回"}
        # 1020 管理员直退：若存在待审申请则一并清掉（不保留 pending）
        if complaint.get("return_request_status") == "pending":
            update_complaint(complaint_id, {"return_request_status": None, "return_request_type": None})
        return _execute_approver_reject(complaint_id, reason.strip(), complaint, current_user)
    return request_return(complaint_id, "approver_reject", reason, current_user)


def _execute_approver_reject(complaint_id: int, reason: str, complaint: dict, actor) -> dict:
    """执行审批人退回流转（管理员直退 / 退回申请审批通过后调用）。actor 为退回动作的名义人。"""
    update_complaint(complaint_id, {
        "status": "指派审批人",
        "sub_type": "",
        "remarks": _append_remark(
            complaint.get("remarks", ""), actor.display_name,
            f"审批人不可承接退回：{reason}",
        ),
    })
    # 0820 退回即清除指派绑定（该状态尚无承接人，安全），防止被退回审批人继续收到进度/关闭通知
    deactivate_assignees(complaint_id)
    # 0825 先清操作者旧通知再生成新通知（同 assign_approver）
    _mark_read(complaint["complaint_no"], actor)
    _log_event(complaint_id, "approver_rejected",
               actor.display_name, actor.role, actor.position,
               old_status="指派承接人", new_status="指派审批人",
               detail=f"不可承接退回：{reason}")
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"🔄 审批人退回工单：{complaint['complaint_no']}",
        message=f"审批人 {actor.display_name} 评估不可承接并退回。原因：{reason}。请办理人重新指派审批人。",
        target_role="办理人",
        category="action_required",
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "指派审批人", f"审批人退回：{reason}", target_role="全员")
    return {"success": True, "message": "已退回指派审批人，等待办理人重新指派"}


# ── 0901 办理人「不可承接」退回录入客服 ────────────
def handler_reject(complaint_id: int, reason: str, current_user) -> dict:
    """办理人评估本工单不应由自己处理 → 退回录入客服（待客服处理 rework）。
    客服可修改后重新提交客服主管审核（cs_resubmit），或撤回工单——补齐指派审批人状态的退回闭环。"""
    if current_user.role not in ("办理人", "管理员"):
        return {"success": False, "message": "仅办理人/管理员可执行此操作"}
    if not reason or not reason.strip():
        return {"success": False, "message": "不可承接原因不得为空"}

    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    if complaint.get("status") != "指派审批人":
        return {"success": False, "message": "当前状态不允许退回"}

    deactivate_assignees(complaint_id)   # 保险：清可能残留的指派绑定（处理不了/审批人退回路径已清，双保险）
    update_complaint(complaint_id, {
        "status": "待客服处理",
        "sub_type": "rework",   # 复用 rework 语义：客服端「修改后重新提交」入口直接可用
        "handler_name": "",
        "supervisor_rejection_note": f"办理人 {current_user.display_name}：{reason.strip()}",   # 复用退回原因字段（前缀退回人身份），客服端醒目可见
        "remarks": _append_remark(
            complaint.get("remarks", ""), current_user.display_name,
            f"办理人不可承接退回：{reason.strip()}",
        ),
    })
    _mark_read(complaint["complaint_no"], current_user)
    _log_event(complaint_id, "handler_rejected",
               current_user.display_name, current_user.role, current_user.position,
               old_status="指派审批人", new_status="待客服处理",
               detail=f"办理人不可承接退回：{reason.strip()}")
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"↩️ 办理人退回工单：{complaint['complaint_no']}",
        message=f"办理人 {current_user.display_name} 评估不可承接并退回。原因：{reason.strip()}。请修改后重新提交审核，或撤回工单。",
        target_role="客服",
        category="action_required",
        target_user_id=complaint.get("created_by_user_id", 0),
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "待客服处理", f"办理人不可承接退回：{reason.strip()}", target_role="客服")
    return {"success": True, "message": "已退回录入客服，等待客服修改后重新提交或撤回"}


# ── 0819 审批人指派承接人（多人）+ 排期 ────────────
def assign_assignees(
    complaint_id: int, evaluation: str, estimated_hours: float,
    user_ids: list[int], planned_start: str, planned_end: str,
    force: bool, primary_user_id: int, current_user,
) -> dict:
    """审批人完成承接评估并指派多位承接人（候选：办理人/审批人/承接人），转入处理中。
    0820 必须指定一位主要推进人（primary_user_id ∈ user_ids），由其负责提交处理结果/回退。
    0825 办理人可被指派为审批人：角色门槛对办理人开放，授权仍由 _check_active_approver 绑定校验把关。
    """
    if current_user.role not in (*APPROVER_CANDIDATE_ROLES, "管理员"):
        return {"success": False, "message": "仅办理人/审批人/管理员可执行此操作（需为该工单当前审批人）"}

    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    # 0821 操作隔离：仅该工单当前有效审批人可指派承接人
    approver_err = _check_active_approver(complaint_id, current_user)
    if approver_err:
        return {"success": False, "message": approver_err}
    if complaint.get("status") != "指派承接人":
        return {"success": False, "message": "当前状态不允许指派承接人"}
    # 1020 退回审批：审批人已申请退回时，禁止同时指派承接人（避免申请与状态冲突）
    if (complaint.get("return_request_status") == "pending"
            and complaint.get("return_request_type") == "approver_reject"):
        return {"success": False, "message": "该工单已有退回申请待王总/关总审批，请等待审批结果"}
    if not evaluation or not evaluation.strip():
        return {"success": False, "message": "请填写承接可行性评估"}
    if estimated_hours is None or estimated_hours <= 0:
        return {"success": False, "message": "请填写预估工时（>0）"}
    if not user_ids:
        return {"success": False, "message": "请至少选择一位承接人"}
    # 0820 主要推进人必填且必须在已选承接人中
    if not primary_user_id:
        return {"success": False, "message": "请指定一位主要推进人"}
    if primary_user_id not in user_ids:
        return {"success": False, "message": "主要推进人必须是已选择的承接人之一"}

    candidates = get_users_by_roles(ASSIGNEE_CANDIDATE_ROLES)
    candidate_ids = {u["id"] for u in candidates}
    invalid = [uid for uid in user_ids if uid not in candidate_ids]
    if invalid:
        return {"success": False, "message": "只能从「办理人/审批人/承接人」中选择承接人"}

    # 冲突检测：任一承接人已有处理中工单
    conflict_info = {}
    for uid in user_ids:
        active = get_assignee_active_complaints(uid)
        if active:
            conflict_info[uid] = [c["complaint_no"] for c in active]
    if conflict_info and not force:
        names = "、".join(
            next((u["display_name"] for u in candidates if u["id"] == uid), str(uid))
            for uid in conflict_info
        )
        return {
            "success": True,
            "has_conflict": True,
            "conflicts": conflict_info,
            "message": f"承接人「{names}」当前已有处理中工单，确认继续指派？",
        }

    update_data = {
        "estimated_hours": estimated_hours,
        "evaluated_by": current_user.display_name,
        "planned_start_time": planned_start or "",
        "planned_end_time": planned_end or "",
        "status": "处理中",
        "sub_type": "",
        "remarks": _append_remark(
            complaint.get("remarks", ""), current_user.display_name,
            f"承接评估：{evaluation.strip()}（预计 {estimated_hours}h）",
        ),
    }
    update_complaint(complaint_id, update_data)

    for uid in user_ids:
        add_assignees(complaint_id, [uid], current_user.display_name)
    # 0820 指定主要推进人
    set_primary_assignee(complaint_id, primary_user_id)
    create_progress_update(complaint_id, 0, "已指派承接人，开始处理", current_user.display_name)

    assignee_names = "、".join(u["display_name"] for u in candidates if u["id"] in user_ids)
    primary_name = next((u["display_name"] for u in candidates if u["id"] == primary_user_id), "")
    schedule_part = f"，排期 {planned_start} ~ {planned_end}" if planned_start else ""
    _log_event(complaint_id, "assignees_assigned",
               current_user.display_name, current_user.role, current_user.position,
               old_status="指派承接人", new_status="处理中",
               detail=f"承接评估通过（预计 {estimated_hours}h），指派承接人：{assignee_names}，主要推进人：{primary_name}{schedule_part}")

    # 0825 先清操作者旧通知再生成新通知：审批人把自己指派为承接人时，通知保持未读
    _mark_read(complaint["complaint_no"], current_user)
    # 通知每位承接人（精准；主要推进人单独文案）
    for uid in user_ids:
        is_primary = uid == primary_user_id
        create_notification(
            complaint_no=complaint["complaint_no"],
            title=f"{'👑 您被设为主要推进人' if is_primary else '📋 您被指派处理工单'}：{complaint['complaint_no']}",
            message=(
                f"审批人 {current_user.display_name} 指派您为工单 {complaint['complaint_no']} 的【主要推进人】，请主导推进处理并提交结果。"
                if is_primary else
                f"审批人 {current_user.display_name} 指派您处理工单 {complaint['complaint_no']}，请前往工单处理页面。"
            ),
            target_role="承接人",
            category="action_required",
            target_user_id=uid,
        )
    # 0914 知会录入客服升级为待处理类（钉钉推送 + 待处理分桶，此前仅站内静默知会），并带上排期窗口
    schedule_note = (f"，排期 {planned_start.replace('T', ' ')} ~ {planned_end.replace('T', ' ')}"
                     if planned_start else "")
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"🔧 工单开始处理：{complaint['complaint_no']}",
        message=f"工单已指派给 {assignee_names} 处理（预计 {estimated_hours}h{schedule_note}）。",
        target_role="客服",
        category="action_required",
        target_user_id=complaint.get("created_by_user_id", 0),
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "处理中", f"已指派承接人：{assignee_names}", target_role="全员")
    return {
        "success": True,
        "message": f"已指派承接人（{assignee_names}），工单进入处理中",
        "has_conflict": bool(conflict_info),
    }


# ── 0819 审批人追加参与人（处理中）─────────────────
def add_participants(complaint_id: int, user_ids: list[int], current_user) -> dict:
    """审批人在处理中阶段追加参与人（候选：办理人/审批人/承接人）。
    0825 办理人可被指派为审批人：角色门槛对办理人开放，授权仍由 _check_active_approver 绑定校验把关。"""
    if current_user.role not in (*APPROVER_CANDIDATE_ROLES, "管理员"):
        return {"success": False, "message": "仅办理人/审批人/管理员可追加参与人（需为该工单当前审批人）"}

    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    # 0821 操作隔离：仅该工单当前有效审批人可追加参与人
    approver_err = _check_active_approver(complaint_id, current_user)
    if approver_err:
        return {"success": False, "message": approver_err}
    if complaint.get("status") != "处理中":
        return {"success": False, "message": "仅处理中工单可追加参与人"}
    if not user_ids:
        return {"success": False, "message": "请选择参与人"}

    candidates = get_users_by_roles(ASSIGNEE_CANDIDATE_ROLES)
    candidate_ids = {u["id"] for u in candidates}
    invalid = [uid for uid in user_ids if uid not in candidate_ids]
    if invalid:
        return {"success": False, "message": "只能从「办理人/审批人/承接人」中选择参与人"}

    add_assignees(complaint_id, user_ids, current_user.display_name)
    names = "、".join(u["display_name"] for u in candidates if u["id"] in user_ids)
    _log_event(complaint_id, "participant_added",
               current_user.display_name, current_user.role, current_user.position,
               old_status="处理中", new_status="处理中",
               detail=f"追加参与人：{names}")
    # 0825 先清操作者旧通知再生成新通知：追加自己为参与人时，通知保持未读
    _mark_read(complaint["complaint_no"], current_user)
    for uid in user_ids:
        create_notification(
            complaint_no=complaint["complaint_no"],
            title=f"🤝 您被追加为参与人：{complaint['complaint_no']}",
            message=f"审批人 {current_user.display_name} 将您追加为工单 {complaint['complaint_no']} 的参与人。",
            target_role="承接人",
            category="action_required",
            target_user_id=uid,
        )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "处理中", f"已追加参与人：{names}", target_role="全员")
    return {"success": True, "message": f"已追加参与人（{names}）"}


# ── 0820 变更主要推进人（审批人/管理员，处理中）────────
def set_primary(complaint_id: int, user_id: int, current_user) -> dict:
    """处理中阶段变更主要推进人。目标必须是当前有效的 assignee 类型（承接人/参与人）。
    0825 办理人可被指派为审批人：角色门槛对办理人开放，授权仍由 _check_active_approver 绑定校验把关。"""
    if current_user.role not in (*APPROVER_CANDIDATE_ROLES, "管理员"):
        return {"success": False, "message": "仅办理人/审批人/管理员可变更主要推进人（需为该工单当前审批人）"}

    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    # 0821 操作隔离：仅该工单当前有效审批人可变更主要推进人
    approver_err = _check_active_approver(complaint_id, current_user)
    if approver_err:
        return {"success": False, "message": approver_err}
    if complaint.get("status") != "处理中":
        return {"success": False, "message": "仅处理中工单可变更主要推进人"}

    active = get_active_assignees(complaint_id)
    target = next((a for a in active if a["user_id"] == user_id), None)
    if not target:
        return {"success": False, "message": "目标用户不是该工单当前有效的承接人/参与人"}

    old = get_primary_assignee(complaint_id)
    set_primary_assignee(complaint_id, user_id)
    old_name = old["display_name"] if old else "（无）"
    _log_event(complaint_id, "primary_changed",
               current_user.display_name, current_user.role, current_user.position,
               old_status="处理中", new_status="处理中",
               detail=f"主要推进人变更：{old_name} → {target['display_name']}（{target['position']}）")
    # 0825 先清操作者旧通知再生成新通知：把自己设为主要推进人时，通知保持未读
    _mark_read(complaint["complaint_no"], current_user)
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"👑 您被设为主要推进人：{complaint['complaint_no']}",
        message=f"审批人 {current_user.display_name} 将您设为工单 {complaint['complaint_no']} 的主要推进人，请主导推进处理并提交结果。",
        target_role="承接人",
        category="action_required",
        target_user_id=user_id,
    )
    # 0820 知会旧主要推进人（若存在且非同一人）
    if old and old["user_id"] != user_id:
        create_notification(
            complaint_no=complaint["complaint_no"],
            title=f"🔁 主要推进人已变更：{complaint['complaint_no']}",
            message=f"工单 {complaint['complaint_no']} 的主要推进人已变更为 {target['display_name']}，您不再担任。",
            target_role="全员",
            category="awareness",
            target_user_id=old["user_id"],
        )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "处理中", f"主要推进人已变更为 {target['display_name']}", target_role="全员")
    return {"success": True, "message": f"主要推进人已变更为 {target['display_name']}"}


# ── 0819 进度更新（承接人/参与人/管理员）────────────
def update_progress(
    complaint_id: int,
    progress_pct: int,
    note: str,
    operator_name: str,
    complaint: dict,
    current_user,
) -> dict:
    """承接人/参与人更新工单进度百分比。"""
    if not note.strip():
        return {"success": False, "message": "请填写进展说明"}

    # 0819 权限：有效承接人/参与人（user_id）或管理员
    if current_user.role != "管理员" and not is_active_assignee(complaint_id, current_user.id):
        return {"success": False, "message": "仅该工单的承接人/参与人可更新进度"}

    pct = max(0, min(100, int(progress_pct)))
    create_progress_update(complaint_id, pct, note.strip(), operator_name)

    _log_event(complaint_id, "progress",
               operator_name, current_user.role, current_user.position,
               old_status=complaint.get("status", ""), new_status=complaint.get("status", ""),
               detail=f"进度更新至 {pct}%，说明：{note.strip()}")

    approver = get_active_approver(complaint_id)
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"📈 进度更新：{complaint['complaint_no']} → {pct}%",
        message=f"{operator_name} 更新进度至 {pct}%。说明：{note.strip()}",
        target_role="审批人",
        target_user_id=approver["user_id"] if approver else 0,
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "处理中", f"进度更新至 {pct}%", target_role="全员")
    return {"success": True, "message": f"进度已更新至 {pct}%"}


# ── 0819 处理不了回退（承接人/参与人/管理员）────────
def cannot_handle(complaint_id: int, reason: str, current_user) -> dict:
    """0820 主要推进人（或管理员）反馈处理不了 → 回指派审批人；全部指派记录置 0（历史保留）。

    1020 退回审批：非管理员不再即时回退，改为生成退回申请，由该工单当前审批人审批；
    管理员保留直接回退（跳过审批）。审批通过后由 _execute_cannot_handle 执行原流转。"""
    if current_user.role == "管理员":
        if not reason or not reason.strip():
            return {"success": False, "message": "处理不了原因不得为空"}
        complaint = get_complaint(complaint_id)
        if not complaint:
            return {"success": False, "message": "工单不存在"}
        if complaint.get("status") != "处理中":
            return {"success": False, "message": "当前状态不允许回退"}
        # 1020 管理员直退：若存在待审申请则一并清掉（不保留 pending）
        if complaint.get("return_request_status") == "pending":
            update_complaint(complaint_id, {"return_request_status": None, "return_request_type": None})
        return _execute_cannot_handle(complaint_id, reason.strip(), complaint, current_user)
    return request_return(complaint_id, "cannot_handle", reason, current_user)


def _execute_cannot_handle(complaint_id: int, reason: str, complaint: dict, actor) -> dict:
    """执行承接人处理不了回退（管理员直退 / 退回申请审批通过后调用）。"""
    deactivate_assignees(complaint_id)
    update_complaint(complaint_id, {
        "status": "指派审批人",
        "sub_type": "",
        "remarks": _append_remark(
            complaint.get("remarks", ""), actor.display_name,
            f"处理不了回退：{reason}",
        ),
    })
    _log_event(complaint_id, "cannot_handle",
               actor.display_name, actor.role, actor.position,
               old_status="处理中", new_status="指派审批人",
               detail=f"处理不了回退：{reason}")
    # 0825 先清操作者旧通知再生成新通知：办理人作为承接人回退时，「请重新指派审批人」广播保持未读
    _mark_read(complaint["complaint_no"], actor)
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"🔄 工单处理回退：{complaint['complaint_no']}",
        message=f"{actor.display_name} 反馈处理不了并回退。原因：{reason}。请办理人重新指派审批人。",
        target_role="办理人",
        category="action_required",
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "指派审批人", f"处理不了回退：{reason}", target_role="全员")
    return {"success": True, "message": "已回退指派审批人，等待办理人重新指派"}


# ── 1020 退回审批：申请与审批 ────────────────────────
def request_return(complaint_id: int, request_type: str, reason: str, current_user) -> dict:
    """创建退回申请（不立即改变工单状态）。

    - cannot_handle（承接人处理不了）→ 审批人 = 该工单当前有效审批人；
    - approver_reject（审批人不可承接退回）→ 审批人 = 员工25/员工26（或签）。
    审批期间工单状态保持不变，审批通过后才执行原退回流转。
    """
    if not reason or not reason.strip():
        return {"success": False, "message": "退回原因不得为空"}
    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    if complaint.get("return_request_status") == "pending":
        return {"success": False, "message": "该工单已有退回申请待审批，请等待处理"}

    reason = reason.strip()
    reviewers: list[dict] = []
    missing: list[str] = []

    if request_type == "cannot_handle":
        if complaint.get("status") != "处理中":
            return {"success": False, "message": "当前状态不允许申请退回"}
        if not is_primary_assignee(complaint_id, current_user.id):
            return {"success": False, "message": "仅主要推进人可申请退回"}
        approver = get_active_approver(complaint_id)
        if not approver:
            return {"success": False, "message": "该工单暂无有效审批人，无法提交退回申请"}
        reviewers = [approver]
        type_label = "承接人处理不了"
    elif request_type == "approver_reject":
        if current_user.role not in (*APPROVER_CANDIDATE_ROLES, "管理员"):
            return {"success": False, "message": "仅办理人/审批人可申请退回（需为该工单当前审批人）"}
        approver_err = _check_active_approver(complaint_id, current_user)
        if approver_err:
            return {"success": False, "message": approver_err}
        if complaint.get("status") != "指派承接人":
            return {"success": False, "message": "当前状态不允许申请退回"}
        matched = get_users_by_display_names(RETURN_APPROVERS)
        for name in RETURN_APPROVERS:
            u = matched.get(name)
            if u:
                reviewers.append(u)
            else:
                missing.append(name)
        type_label = "审批人不可承接"
    else:
        return {"success": False, "message": "无效的退回类型"}

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_complaint(complaint_id, {
        "return_request_type": request_type,
        "return_request_status": "pending",
        "return_request_reason": reason,
        "return_request_by": current_user.display_name,
        "return_request_by_id": current_user.id,
        "return_request_at": now_str,
        "return_review_note": None,
        "return_review_by": None,
        "return_review_at": None,
    })

    _log_event(complaint_id, "return_requested",
               current_user.display_name, current_user.role, current_user.position,
               old_status=complaint.get("status", ""), new_status=complaint.get("status", ""),
               detail=f"发起退回申请（{type_label}）：{reason}"
                      + (f"；待审批人：{'、'.join(r['display_name'] for r in reviewers)}" if reviewers else "")
                      + (f"；未匹配用户：{'、'.join(missing)}" if missing else ""))

    # 通知审批人（精准到人；target_role 必须传本人真实角色，否则可见范围判定会漏）
    notified_ids: set[int] = set()
    for r in reviewers:
        uid = r.get("user_id") or r.get("id")
        if not uid or uid in notified_ids:
            continue
        notified_ids.add(uid)
        create_notification(
            complaint_no=complaint["complaint_no"],
            title=f"🔄 退回申请待审批：{complaint['complaint_no']}",
            message=(f"{current_user.display_name} 申请退回（{type_label}）。原因：{reason}。"
                     f"请审批是否同意退回。"),
            target_role=r.get("role") or "审批人",
            category="action_required",
            target_user_id=uid,
        )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               complaint.get("status", ""), f"退回申请待审批：{reason}", target_role="全员")
    return {
        "success": True,
        "pending": True,
        "message": "退回申请已提交，等待审批" + (f"；{'、'.join(missing)} 未找到用户，未通知" if missing else ""),
        "reviewers": [r.get("display_name", "") for r in reviewers],
        "missing": missing,
    }


def review_return(complaint_id: int, action: str, note: str, current_user) -> dict:
    """审批退回申请：approved=同意并执行原退回流转；rejected=驳回（状态不变）。"""
    if action not in ("approved", "rejected"):
        return {"success": False, "message": "无效的审批动作"}
    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    if complaint.get("return_request_status") != "pending":
        return {"success": False, "message": "该工单没有待审批的退回申请"}

    rtype = complaint.get("return_request_type")
    if current_user.role != "管理员":
        if rtype == "cannot_handle":
            if not is_active_approver(complaint_id, current_user.id):
                return {"success": False, "message": "仅该工单当前审批人可审批此退回申请"}
        elif rtype == "approver_reject":
            if current_user.display_name not in RETURN_APPROVERS:
                return {"success": False, "message": f"仅{'/'.join(RETURN_APPROVERS)}可审批审批人的退回申请"}
        else:
            return {"success": False, "message": "退回申请类型无效"}
    # 不能审批自己发起的申请（管理员除外）
    if current_user.role != "管理员" and complaint.get("return_request_by_id") == current_user.id:
        return {"success": False, "message": "不能审批自己发起的退回申请"}

    # 状态校验：申请期间工单若已流转，申请失效
    expected = "处理中" if rtype == "cannot_handle" else "指派承接人"
    if complaint.get("status") != expected:
        update_complaint(complaint_id, {
            "return_request_status": None,
            "return_request_type": None,
        })
        return {"success": False, "message": "工单状态已变化，退回申请已失效"}

    requester_id = complaint.get("return_request_by_id") or 0
    requester = get_user_by_id(requester_id) if requester_id else None
    reason = complaint.get("return_request_reason") or ""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    note = (note or "").strip()

    update_complaint(complaint_id, {
        "return_request_status": action,
        "return_review_note": note or None,
        "return_review_by": current_user.display_name,
        "return_review_at": now_str,
    })

    if action == "approved":
        # 以申请人为动作名义人执行原退回流转（通知/日志语义保持"谁申请谁退回"）
        if requester:
            actor = SimpleNamespace(
                id=requester.get("id", 0),
                display_name=requester.get("display_name", "") or complaint.get("return_request_by", ""),
                role=requester.get("role", ""),
                position=requester.get("position", ""),
            )
        else:
            actor = current_user
        if rtype == "cannot_handle":
            result = _execute_cannot_handle(complaint_id, reason, complaint, actor)
        else:
            result = _execute_approver_reject(complaint_id, reason, complaint, actor)
        review_msg = f"已同意退回；{result.get('message', '')}"
    else:
        review_msg = "已驳回退回申请，工单保持原状态"

    _log_event(complaint_id, "return_approved" if action == "approved" else "return_rejected",
               current_user.display_name, current_user.role, current_user.position,
               old_status=complaint.get("status", ""), new_status=complaint.get("status", ""),
               detail=f"退回审批{('通过' if action == 'approved' else '驳回')}（申请人："
                      f"{complaint.get('return_request_by') or '—'}）" + (f"；意见：{note}" if note else ""))

    # 通知申请人
    if requester_id:
        create_notification(
            complaint_no=complaint["complaint_no"],
            title=f"{'✅' if action == 'approved' else '❌'} 退回申请"
                  f"{'已通过' if action == 'approved' else '被驳回'}：{complaint['complaint_no']}",
            message=(f"您提交的退回申请（{reason}）"
                     f"{'已通过，工单已退回' if action == 'approved' else '被驳回，工单保持原状态'}。"
                     + (f"审批意见：{note}。" if note else "")),
            target_role=(requester or {}).get("role") or "全员",
            category="action_required",
            target_user_id=requester_id,
        )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               complaint.get("status", ""),
               f"退回申请{'已通过' if action == 'approved' else '被驳回'}",
               target_role="全员")
    return {"success": True, "message": review_msg, "action": action}


# ── 0819 提交解决方案 → 待客服处理(customer_confirm) ─
def resolve_complaint(
    complaint_id: int,
    root_cause: str,
    solution: str,
    reproduction_steps: str,
    resolution_note: str,
    checklist: str,
    operator_name: str,
    complaint: dict,
    current_user,
) -> dict:
    """0820 主要推进人（或管理员）提交最终处理结果 → 待客服处理(customer_confirm)。"""
    if not root_cause.strip() or not solution.strip():
        return {"success": False, "message": "根因分析和解决方案为必填项"}

    # 0820 仅主要推进人可提交处理结果（防多人扯皮）
    if current_user.role != "管理员" and not is_primary_assignee(complaint_id, current_user.id):
        return {"success": False, "message": "仅主要推进人或管理员可提交处理结果"}

    create_progress_update(complaint_id, 100, "已处理完成并提交结果。", operator_name)
    _resolve_fields = {
        "reproduction_steps": reproduction_steps,
        "root_cause": root_cause,
        "solution": solution,
        "resolution_note": resolution_note,
        "status": "待客服处理",
        "sub_type": "customer_confirm",
    }
    # 1020 工单已流转，未决的退回申请自动失效（仅清 pending，保留已审批记录）
    if complaint.get("return_request_status") == "pending":
        _resolve_fields["return_request_status"] = None
        _resolve_fields["return_request_type"] = None
    update_complaint(complaint_id, _resolve_fields)

    _log_event(complaint_id, "resolved",
               operator_name, current_user.role, current_user.position,
               old_status=complaint.get("status", ""), new_status="待客服处理",
               detail=f"提交解决方案，等待客户确认。方案摘要：{solution[:80]}{'...' if len(solution) > 80 else ''}")

    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"✋ 待客户确认：{complaint['complaint_no']}",
        message="承接人已提交处理方案，请客服联系客户确认问题是否解决。",
        target_role="客服",
        category="action_required",
        target_user_id=complaint.get("created_by_user_id", 0),
    )
    _mark_read(complaint["complaint_no"], current_user)
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "待客服处理", "已提交处理方案，等待客户确认", target_role="全员")
    return {"success": True, "message": "处理结果已提交，等待客户确认"}


# ── 0819 客户确认 → 已关闭 + KB 归档 ────────────────
def confirm_complaint(
    complaint_id: int,
    satisfaction: int,
    is_rework: Optional[bool] = None,
    operator_name: str = "",
    complaint: dict = None,
    current_user=None,
) -> dict:
    """客服确认客户问题已解决 → 已关闭 + 自动归档知识库。"""
    # 0821 客服操作隔离：仅录入该工单的客服可确认关闭（管理员旁路）
    cs_err = _check_cs_creator(complaint or {}, current_user)
    if cs_err:
        return {"success": False, "message": cs_err}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rework_val = 1 if is_rework else 0 if is_rework is not None else int(complaint.get("is_rework", 0))

    # 0923 空壳归档治理：根因与解决方案均为空时改走备注知识提取（LLM→原文兜底），备注也无可用内容才不归档
    will_archive = bool(
        (complaint.get("solution") or "").strip()
        or (complaint.get("root_cause") or "").strip()
        or _extract_remark_kb_blocks(complaint.get("remarks", ""))
    )
    archive_text = (
        "已关闭并自动归档知识库"
        if will_archive else
        "已关闭（根因、解决方案与排查备注均为空，暂未归档知识库）"
    )

    update_complaint(complaint_id, {
        "customer_confirmed": 1,
        "satisfaction": satisfaction,
        "is_rework": rework_val,
        "status": "已关闭",
        "sub_type": "",
        "closed_at": now,
    })

    _log_event(complaint_id, "closed",
               operator_name, current_user.role, current_user.position,
               old_status=complaint.get("status", ""), new_status="已关闭",
               detail=f"客户确认{'（返修）' if is_rework else ''}，满意度 {'⭐' * satisfaction}，工单已关闭")

    # 0819 经验学习通知：客服主管
    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"📚 经验学习：{complaint['complaint_no']} 已关闭",
        message=(
            f"工单 {complaint['complaint_no']}（{complaint['fault_category'] or '未分类'}故障）"
            f"已关闭并自动归档知识库。满意度：{'⭐' * satisfaction}。"
        ),
        target_role="客服主管",
        category="experience",
    )
    # 0820 经验学习通知：每位有效承接人（精准，跨角色可见）
    active_assignees = get_active_assignees(complaint_id)
    # 0821 经验学习通知：所有历史审批人（含中途换人失效的审批记录；跳过同时是有效承接人的用户防重复）
    assignee_ids = {a["user_id"] for a in active_assignees}
    for uid in get_historical_approver_user_ids(complaint_id):
        if uid in assignee_ids:
            continue
        create_notification(
            complaint_no=complaint["complaint_no"],
            title=f"📚 经验学习：{complaint['complaint_no']} 已关闭",
            message=(
                f"您审批过的工单 {complaint['complaint_no']}（{complaint['fault_category'] or '未分类'}故障）"
                f"{archive_text}。满意度：{'⭐' * satisfaction}。"
            ),
            target_role="审批人",
            category="experience",
            target_user_id=uid,
        )
    for a in active_assignees:
        create_notification(
            complaint_no=complaint["complaint_no"],
            title=f"📚 经验学习：{complaint['complaint_no']} 已关闭",
            message=(
                f"您参与处理的工单 {complaint['complaint_no']}（{complaint['fault_category'] or '未分类'}故障）"
                f"{archive_text}。满意度：{'⭐' * satisfaction}。"
            ),
            target_role="全员",
            category="experience",
            target_user_id=a["user_id"],
        )

    # 自动存入知识库
    _archive_closed_to_kb(complaint, resolution_note=complaint.get("resolution_note", ""))

    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "已关闭", f"工单已关闭，满意度：{'⭐' * satisfaction}", target_role="全员")
    _mark_read(complaint["complaint_no"], current_user)
    return {"success": True,
            "message": "工单已关闭，已自动归档知识库" if will_archive
            else "工单已关闭（根因、解决方案与排查备注均为空，暂未归档知识库）"}


# 0908 RAG 阶段 1：KB 写入统一挂向量生成（失败不阻断归档，回填脚本可后补）
def _create_kb_with_embedding(data: dict) -> int:
    """create_kb_entry + embedding 向量生成（0908 RAG 阶段 1）。
    向量不可用/失败时 embed_kb_entry 内部记日志返回 False，归档照常完成。"""
    kb_id = create_kb_entry(data)
    try:
        embed_kb_entry(kb_id, data)
    except Exception:
        pass  # 双保险：embed_kb_entry 已内部兜异常，此处保证归档链路绝不被向量拖挂
    return kb_id


# ── 关闭工单后自动归档知识库（0819 仅保留客户确认模式）──
def _archive_remark_knowledge(complaint: dict) -> int:
    """排查快捷路径关单的知识归档（0923）。

    排查路径（待客户排查→排查解决→关闭）的工单 solution/root_cause 结构化字段
    从未被填写，知识只存在于备注块（排查结果/审核评估/主管评估）。
    策略：LLM 结构化抽取 → 失败或空结果时排查块原文直存 solution 兜底
    → 备注无可用内容则放弃归档（返回 0，不产生空壳条目）。
    """
    blocks = _extract_remark_kb_blocks(complaint.get("remarks", ""))
    if not blocks:
        return 0
    no = complaint["complaint_no"]
    phen = complaint.get("fault_phenomenon", "") or ""
    cat = complaint.get("fault_category", "") or ""
    fallback_title = f"{no} {cat}故障"
    raw_text = "\n".join(f"{label}：{content}" for _, label, content in blocks)

    # ① LLM 结构化抽取（extract_knowledge_llm 失败返回 None，异常兜住走原文直存）
    extracted = None
    try:
        extracted = extract_knowledge_llm(raw_text)
    except Exception:
        extracted = None

    if extracted and (extracted.get("root_cause", "").strip() or extracted.get("solution", "").strip()):
        # 工单已有字段是真实来源优先采用，抽取结果补缺
        return _create_kb_with_embedding({
            "complaint_no": no,
            "title": extracted.get("title", "").strip() or fallback_title,
            "fault_category": extracted.get("fault_category", "") or cat,
            "equipment_model": complaint.get("equipment_model", "") or extracted.get("equipment_model", ""),
            "fault_keywords": extracted.get("fault_keywords", "").strip() or ", ".join(extract_keywords(raw_text)),
            "root_cause": extracted.get("root_cause", ""),
            "solution": extracted.get("solution", ""),
            "checklist": extracted.get("checklist", ""),
            "contact_author": next((op for op, lb, _ in blocks if lb == "排查结果"), ""),
            "lesson_learned": f"【自动归档·排查提取】{no} - {extracted.get('lesson_learned', '')}".strip(),
            "fault_phenomenon": phen,
        })

    # ② 兜底：排查块原文直存 solution（优先排查结果块，无则全部块），知识不丢
    # （extracted 为 None 是 LLM 不可用；非 None 但根因/方案空是内容无结论、LLM 拒绝编造。
    #   兜底时 LLM 已产出的标题/关键词仍可采用——它只是不肯编造根因/方案，不影响提炼）
    fallback_reason = "LLM 不可用" if extracted is None else "LLM 无有效结构化结果"
    sol_blocks = [c for _, lb, c in blocks if lb == "排查结果"] or [c for _, _, c in blocks]
    sol_text = "\n".join(sol_blocks)
    return _create_kb_with_embedding({
        "complaint_no": no,
        "title": ((extracted or {}).get("title", "") or "").strip() or fallback_title,
        "fault_category": cat,
        "equipment_model": complaint.get("equipment_model", ""),
        "fault_keywords": (((extracted or {}).get("fault_keywords", "") or "").strip()
                           or ", ".join(extract_keywords(f"{phen} {sol_text}"))),
        "root_cause": "",
        "solution": sol_text,
        "contact_author": next((op for op, lb, _ in blocks if lb == "排查结果"), ""),
        "lesson_learned": f"【自动归档·排查提取】{no} - {fallback_reason}，排查备注原文直存",
        "fault_phenomenon": phen,
    })


def _archive_closed_to_kb(
    complaint: dict,
    solution: str = "",
    resolution_note: str = "",
) -> int:
    """客户确认关闭后自动归档 KB 条目，返回新 KB 条目 ID。

    0923 空壳治理：root_cause 与 solution 均为空时不再直接归档空壳条目，
    改走 _archive_remark_knowledge 从备注提取知识（LLM 抽取 → 原文兜底 → 无内容放弃）。"""
    sol = (solution or complaint.get("solution", "")).strip()
    root = (complaint.get("root_cause", "") or "").strip()
    if not sol and not root:
        return _archive_remark_knowledge(complaint)
    no = complaint["complaint_no"]
    phen = complaint.get("fault_phenomenon", "") or ""
    res_note = (resolution_note or complaint.get("resolution_note", "") or "").strip()
    fallback_title = f"{no} {complaint.get('fault_category', '')}故障".strip()

    # 0923 LLM 抛光：根因/方案保持工单真实值为准，LLM 仅生成描述性标题/规范关键词/
    # 检查清单/经验教训；失败或无有效标题时回退机械格式
    raw_text = f"故障现象：{phen}\n根因：{root}\n处理方案：{sol}\n处理备注：{res_note}"
    extracted = None
    try:
        extracted = extract_knowledge_llm(raw_text)
    except Exception:
        extracted = None

    if extracted:
        title = extracted.get("title", "").strip() or fallback_title
        keywords = (extracted.get("fault_keywords", "") or "").strip() \
            or ", ".join(extract_keywords(f"{phen} {sol}"))
        checklist = extracted.get("checklist", "") or ""
        lesson_core = (extracted.get("lesson_learned", "") or "").strip() or res_note
    else:
        title = fallback_title
        keywords = ", ".join(extract_keywords(f"{phen} {sol}"))
        checklist = ""
        lesson_core = res_note
    lesson = f"【自动归档】{no} - {lesson_core}".strip()

    return _create_kb_with_embedding({
        "complaint_no": no,
        "title": title,
        "fault_category": complaint["fault_category"],
        "equipment_model": complaint.get("equipment_model", ""),
        "fault_keywords": keywords,
        "root_cause": root,
        "solution": sol,
        "checklist": checklist,
        "lesson_learned": lesson,
        "fault_phenomenon": phen,
    })


# ── 0806 客服保存排查备注 — 仅保存不改变状态 ────────
def save_remark(complaint_id: int, remark: str, operator_name: str, complaint: dict,
                current_user=None) -> dict:
    """客服在待客户排查状态保存排查备注（不改变状态）。"""
    if not remark.strip():
        return {"success": False, "message": "备注内容不能为空"}

    # 0821 客服操作隔离：仅录入该工单的客服可保存排查备注
    cs_err = _check_cs_creator(complaint, current_user)
    if cs_err:
        return {"success": False, "message": cs_err}

    updated_remarks = _append_remark(complaint.get("remarks", ""), operator_name, remark.strip())
    update_complaint(complaint_id, {"remarks": updated_remarks})

    _log_event(complaint_id, "remark",
               operator_name, current_user.role, current_user.position,
               old_status=complaint.get("status", ""),
               new_status=complaint.get("status", ""),
               detail=f"备注：{remark.strip()}")

    _broadcast("complaint_updated", complaint_id, complaint.get("complaint_no", ""),
               complaint.get("status", ""), f"客服 {operator_name} 添加了排查备注",
               target_role="全员")
    return {"success": True, "message": "备注已保存"}


# ── 1016 工单预警 ────────────────────────────────────
def raise_warning(complaint_id: int, keywords: list[str], note: str, current_user) -> dict:
    """客服/客服主管发起工单预警：按关键词档位通知到人 + 写工单日志。

    低风险档（临期/客户催办/进度滞后）→ 客服主管全员 + 该工单承接人；
    高风险档（退机风险/批量质量风险/客诉升级）→ 上述基础上加发 HIGH_RISK_WATCHERS（按姓名精确匹配，
    匹配不到的姓名收集进 missing 返回给前端提示，不阻断预警）。
    渠道：站内通知 + 钉钉（category=action_required，钉钉未配置时静默跳过）。
    已关闭/已撤回工单不可预警；同一工单可重复预警（风险会反复出现）。
    """
    if current_user.role not in ("客服", "客服主管", "管理员"):
        return {"success": False, "message": "仅客服/客服主管/管理员可发起预警"}
    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    status = complaint.get("status") or ""
    if status in ("已关闭", "已撤回"):
        return {"success": False, "message": f"工单已{status}，无需预警"}

    # 关键词白名单校验 + 去重保序
    picked: list[str] = []
    for k in (keywords or []):
        k = (k or "").strip()
        if k and k in WARNING_KEYWORDS_ALL and k not in picked:
            picked.append(k)
    if not picked:
        return {"success": False, "message": f"请至少选择一个有效预警关键词（{'/'.join(WARNING_KEYWORDS_ALL)}）"}

    # 档位：含任一高风险词即按高风险档
    is_high = any(k in WARNING_KEYWORDS_HIGH for k in picked)
    tier = "high" if is_high else "low"
    keywords_text = "、".join(picked)
    note = (note or "").strip()

    complaint_no = complaint.get("complaint_no", "")
    title = f"{'🚨 高风险预警' if is_high else '⚠️ 工单预警'}：{complaint_no}"
    body_head = (f"{current_user.display_name}（{current_user.role}）对工单 {complaint_no} 发起"
                 f"{'高风险' if is_high else '低风险'}预警：{keywords_text}。")
    message = body_head + (f"\n补充说明：{note}" if note else "")

    notified: list[str] = []
    notified_ids: set[int] = set()

    # ① 客服主管全员（角色广播一次；不用 target_user_id）
    create_notification(
        complaint_no=complaint_no,
        title=title,
        message=message,
        target_role="客服主管",
        category="action_required",
    )
    for sup in get_users_by_roles(["客服主管"]):
        if sup["id"] not in notified_ids:
            notified_ids.add(sup["id"])
            notified.append(sup["display_name"])

    # ② 承办当事人 = 本工单有效承接人（逐个精准通知，target_role 必须传本人真实角色，否则可见范围判定会漏）
    for a in get_active_assignees(complaint_id):
        uid = a.get("user_id")
        if not uid or uid in notified_ids:
            continue
        notified_ids.add(uid)
        notified.append(a.get("display_name") or "")
        create_notification(
            complaint_no=complaint_no,
            title=title,
            message=message + "\n您是该工单的承接人，请关注风险并推进处理。",
            target_role=a.get("role") or "承接人",
            category="action_required",
            target_user_id=uid,
        )

    # ③ 高风险档：加发指定知会人（按姓名匹配，匹配不到进 missing）
    missing: list[str] = []
    if is_high:
        watchers = get_users_by_display_names(HIGH_RISK_WATCHERS)
        for name in HIGH_RISK_WATCHERS:
            u = watchers.get(name)
            if not u:
                missing.append(name)
                continue
            if u["id"] in notified_ids:
                continue
            notified_ids.add(u["id"])
            notified.append(name)
            create_notification(
                complaint_no=complaint_no,
                title=title,
                message=message + "\n该工单已列为高风险，请知悉并关注。",
                target_role=u.get("role") or "全员",
                category="action_required",
                target_user_id=u["id"],
            )

    notify_detail = "、".join(notified) or "无（无匹配收件人）"
    _log_event(complaint_id, "warning",
               current_user.display_name, current_user.role, current_user.position,
               old_status=status, new_status=status,
               detail=(f"发起预警：{keywords_text}（{'高风险' if is_high else '低风险'}档）；"
                       f"通知对象：{notify_detail}"
                       + (f"；未匹配用户：{'、'.join(missing)}" if missing else "")
                       + (f"；补充说明：{note}" if note else "")))
    _broadcast("complaint_updated", complaint_id, complaint_no, status,
               f"{current_user.display_name} 发起工单预警：{keywords_text}",
               target_role="全员")

    return {
        "success": True,
        "message": f"预警已发出（{'高风险' if is_high else '低风险'}档），已通知 {len(notified)} 人"
                   + (f"；{'、'.join(missing)} 未找到用户，未通知" if missing else ""),
        "tier": tier,
        "keywords": picked,
        "notified": notified,
        "missing": missing,
    }


# ── 工单处理页：侧边栏任务列表（0819 全员可见）─────
def get_sidebar_tasks(role: str, current_user_id: int, my_orders_only: bool = False,
                      approver_group: str = "") -> dict:
    """0819 工单处理页侧边栏：全部工单可见；
    my_orders_only 按角色匹配「我的工单」（0820 与看板同一规则）；
    0821 审批人分组：todo_assignee=需审批+自己承接（处理中仅自己承接）；
    add_assignee=处理中仅需追加承接人（我是当前审批人）。
    0826 分组平铺改造：approver_group 仅显式传入时过滤（侧栏前端已改为按 _my_roles 分组，
    默认不传即不过滤，审批人/办理人任审批的"按需管理"单也能拿到）；
    每条 option 挂 _my_roles 身份标记（creator=录入 / approver=当前审批 / assignee=承接·参与 /
    primary=主要推进），供前端按「需我处理 / 按需关注」分组。"""
    all_complaints = get_all_complaints()

    options = (
        _apply_my_orders_filter(all_complaints, role, current_user_id)
        if my_orders_only and current_user_id else all_complaints
    )

    # 0821 审批人分组过滤（0826 起仅显式传入时生效，默认不过滤）
    if role == "审批人" and my_orders_only and current_user_id and approver_group \
            and approver_group in ("todo_assignee", "add_assignee"):
        if approver_group == "add_assignee":
            ids = get_complaint_approver_user_ids(current_user_id)
        else:
            ids = get_complaint_assignee_user_ids(current_user_id)
        options = [c for c in options if c.get("status") != "处理中" or c.get("id") in ids]

    # 0826 挂"我的身份"标记，供前端侧栏分组
    assignees_map = get_assignees_map([c["id"] for c in options])
    for c in options:
        roles: list[str] = []
        if c.get("created_by_user_id") == current_user_id:
            roles.append("creator")
        for a in assignees_map.get(c["id"], []):
            if a.get("user_id") != current_user_id:
                continue
            if a.get("assignee_type") == "approver":
                roles.append("approver")
            else:
                roles.append("assignee")
                if a.get("is_primary"):
                    roles.append("primary")
        c["_my_roles"] = roles

    return {"pending_eval": [], "in_progress": [], "options": options}


# ── 工单处理页：进度百分比计算（含 progress_updates 最新值） ──
def get_work_order_progress(complaint: dict) -> dict:
    """获取工单处理页的进度信息。"""
    progress_map = {
        "已关闭": 100, "待客服处理": 80, "处理中": 50,
        "指派承接人": 30, "指派审批人": 20, "待客户排查": 10,
        "客服主管审核": 5, "已撤回": 0,
    }
    latest = latest_progress(complaint["id"])

    result = {"pct": 0, "method": "", "latest": None}
    if latest:
        result["pct"] = latest["progress_pct"]
        result["method"] = "actual"
        result["latest"] = latest
    else:
        result["pct"] = progress_map.get(complaint["status"], 0)
        result["method"] = "mapped"
    return result


# ── 0728 客户邮件 ──────────────────────────────

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import re as _re

from core.smtp_config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, is_smtp_configured,
)
from ai_engine.ai_engine import generate_email_draft as _ai_generate_email_draft
from data.database import get_attachments


def generate_draft(complaint: dict) -> dict:
    """委托 AI 生成邮件草稿。
    成功返回 {subject, body, source: "deepseek"}；
    AI 失败返回 {subject, body, source: "failed", error}。
    """
    result = _ai_generate_email_draft(
        fault_phenomenon=complaint.get("fault_phenomenon", ""),
        solution=complaint.get("solution", ""),
        customer_name=complaint.get("customer_name", ""),
        equipment_model=complaint.get("equipment_model", ""),
        complaint_no=complaint.get("complaint_no", ""),
    )
    if result:
        return result
    return {
        "subject": "",
        "body": "",
        "source": "failed",
        "error": "DeepSeek 生成邮件草稿失败，请手动填写",
    }


def send_customer_email(
    complaint: dict,
    to_email: str,
    subject: str,
    body: str,
    attachment_ids: list[int],
    local_files: list | None = None,
    operator_name: str = "",
    operator_role: str = "",
    operator_position: str = "",
) -> dict:
    """连接 SMTP 服务器发送邮件，并将记录追加到工单 remarks。
    返回 {"success": bool, "message": str}。
    0819 邮件审核拦截：仅 pending/rejected 拦截，NULL/approved 放行。
    """
    review_status = complaint.get("email_review_status")
    if review_status == "pending":
        raise ValueError("邮件正在等待主管审核，审核通过后方可发送")
    if review_status == "rejected":
        note = complaint.get("email_review_note") or ""
        raise ValueError(f"邮件已被主管拒绝，无法发送。拒绝原因：{note}" if note else "邮件已被主管拒绝，无法发送。请修改邮件内容后重新提交审核")

    if not is_smtp_configured():
        return {"success": False, "message": "SMTP 未配置，无法发送邮件。请在系统管理中配置 SMTP。"}

    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body.replace("\n", "<br>"), "html", "utf-8"))

        # 工单已有附件
        if attachment_ids:
            all_atts = get_attachments(complaint["id"]) or []
            for att_id in attachment_ids:
                try:
                    att = next((a for a in all_atts if a["id"] == att_id), None)
                    if not att:
                        continue
                    fpath = os.path.join(
                        os.path.dirname(__file__), "..", "..", "data", "uploads",
                        complaint["complaint_no"], att["stored_name"],
                    )
                    if not os.path.exists(fpath):
                        continue
                    with open(fpath, "rb") as fh:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(fh.read())
                        encoders.encode_base64(part)
                        part.add_header("Content-Disposition", f'attachment; filename="{att["filename"]}"')
                        msg.attach(part)
                except Exception:
                    pass  # 单附件失败不影响整体

        # 本地上传文件
        if local_files:
            for fname, fbytes, fmime in local_files:
                part = MIMEBase(*(fmime.split("/", 1) if "/" in fmime else ("application", "octet-stream")))
                part.set_payload(fbytes)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
                msg.attach(part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())

        _log_event(complaint["id"], "email_sent",
                   operator_name, operator_role, operator_position,
                   old_status=complaint.get("status", ""), new_status=complaint.get("status", ""),
                   detail=f"已发送邮件至 {to_email}，主题：{subject}")

        # 记录到 remarks
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        body_plain = _re.sub(r"<[^>]+>", "", body)[:200]
        entry = f"[邮件记录] {now} | 收件人: {to_email} | 发送人: {operator_name} | 主题: {subject} | 内容: {body_plain}"
        existing = complaint.get("remarks") or ""
        updated_remarks = existing + "\n---\n" + entry if existing else entry
        update_complaint(complaint["id"], {"remarks": updated_remarks})

        return {"success": True, "message": f"邮件已发送至 {to_email}"}

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "SMTP 认证失败，请检查邮箱账号密码配置"}
    except smtplib.SMTPException as e:
        return {"success": False, "message": f"SMTP 发送失败: {str(e)[:100]}"}
    except Exception as e:
        return {"success": False, "message": f"邮件发送异常: {str(e)[:100]}"}


# ═══════════════════════════════════════ 0819 邮件审核 Service ═══════════════════════════════════════

def request_email_review(complaint_id: int, subject: str, body: str, current_user) -> dict:
    """客服申请邮件审核：保存草稿 → email_review_status=pending →
    工单转入 客服主管审核(email)。
    """
    if current_user.role not in ("客服", "管理员"):
        return {"success": False, "message": "仅客服/管理员可申请邮件审核"}

    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    # 0821 客服操作隔离：仅录入该工单的客服可申请邮件审核
    cs_err = _check_cs_creator(complaint, current_user)
    if cs_err:
        return {"success": False, "message": cs_err}
    if complaint.get("status") != "待客服处理" or complaint.get("sub_type") != "customer_confirm":
        return {"success": False, "message": "仅待客户确认状态的工单可申请邮件审核"}

    current_review = complaint.get("email_review_status")
    if current_review == "pending":
        return {"success": False, "message": "已提交邮件审核申请，请等待主管审核"}

    if not subject.strip() or not body.strip():
        return {"success": False, "message": "邮件主题和正文不能为空"}

    import json
    draft_content = json.dumps({"subject": subject, "body": body}, ensure_ascii=False)

    set_email_review_status(complaint_id, "pending", draft_content=draft_content)
    update_complaint(complaint_id, {"status": "客服主管审核", "sub_type": "email"})

    _log_event(complaint_id, "email_review_requested",
               current_user.display_name, current_user.role, current_user.position,
               old_status="待客服处理", new_status="客服主管审核",
               detail=f"客服提交了邮件草稿等待主管审核（主题：{subject[:50]}{'...' if len(subject) > 50 else ''}）")

    create_notification(
        complaint_no=complaint["complaint_no"],
        title=f"📧 邮件待审核：{complaint['complaint_no']}",
        message=f"客服 {current_user.display_name} 提交了客户邮件草稿，请审核邮件内容。",
        target_role="客服主管",
        category="action_required",
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               "客服主管审核", "客服已提交邮件草稿，请主管审核", target_role="客服主管")
    _mark_read(complaint["complaint_no"], current_user)
    return {"success": True, "message": "已提交邮件草稿，请等待主管审核"}


def approve_email_send(complaint_id: int, action: str, note: str | None, current_user) -> dict:
    """客服主管审核邮件发送申请（approved / rejected）。
    通过 → 回 待客服处理(customer_confirm)；拒绝 → 待客服处理(rework)（客服改邮件重提）。
    """
    if current_user.role not in ("客服主管", "管理员"):
        return {"success": False, "message": "仅客服主管/管理员可审核邮件"}

    complaint = get_complaint(complaint_id)
    if not complaint:
        return {"success": False, "message": "工单不存在"}
    if complaint.get("status") != "客服主管审核" or complaint.get("sub_type") != "email":
        return {"success": False, "message": "该工单不在邮件审核状态"}
    if complaint.get("email_review_status") != "pending":
        return {"success": False, "message": "该工单无待审核的邮件申请"}

    if action not in ("approved", "rejected"):
        return {"success": False, "message": "无效的审核动作"}

    if action == "approved":
        set_email_review_status(complaint_id, "approved", note)
        update_complaint(complaint_id, {"status": "待客服处理", "sub_type": "customer_confirm"})
        new_status, new_sub = "待客服处理", "customer_confirm"
    else:
        set_email_review_status(complaint_id, "rejected", note)
        update_complaint(complaint_id, {"status": "待客服处理", "sub_type": "rework"})
        new_status, new_sub = "待客服处理", "rework"

    _log_event(complaint_id, "email_review_" + action,
               current_user.display_name, current_user.role, current_user.position,
               old_status="客服主管审核", new_status=new_status,
               detail=f"邮件审核{'通过' if action == 'approved' else '拒绝'}" + (f"（{note}）" if note else ""))

    if action == "approved":
        msg = f"主管已批准邮件发送申请，您现在可以发送客户确认邮件。工单：{complaint['complaint_no']}。"
        title = f"✅ 邮件审核已通过：{complaint['complaint_no']}"
    else:
        reason = note or "（无）"
        msg = f"主管拒绝了邮件发送申请。拒绝原因：{reason}。请修改邮件内容后重新提交。工单：{complaint['complaint_no']}。"
        title = f"❌ 邮件审核被拒：{complaint['complaint_no']}"

    create_notification(
        complaint_no=complaint["complaint_no"],
        title=title,
        message=msg,
        target_role="客服",
        category="action_required",
        target_user_id=complaint.get("created_by_user_id", 0),
    )
    _broadcast("complaint_updated", complaint_id, complaint["complaint_no"],
               new_status, f"邮件审核结果：{'通过' if action == 'approved' else '拒绝'}",
               target_role="客服")
    _mark_read(complaint["complaint_no"], current_user)
    action_label = "已批准" if action == "approved" else "已拒绝"
    return {"success": True, "message": f"邮件审核{action_label}，客服将收到通知"}
