# 0724 投诉 API — CRUD + 状态转换端点
# 0819 v3.0 角色流程重构：新 7 状态 + 指派审批人/承接人（多人）+ 邮件审核回路
"""投诉相关 REST API 端点。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from typing import Optional

from data.database import (
    get_all_complaints, get_complaint, create_complaint as db_create_complaint,
    update_complaint, delete_complaint,
    create_work_order_log, list_work_order_log,
    get_complaint_id_by_no, get_complaint_briefs_by_ids,
    get_complaint_status_stats,
    normalize_status, get_conn,
    get_assignees_map, get_rejected_approver_info_map,
    CANONICAL_STATUSES,
)
from services.complaint_service import (
    list_complaints_for_kanban, get_progress_pct, can_edit_delete,
    generate_draft, send_customer_email,
    save_remark,
    supervisor_intake_review, cs_resubmit, cs_investigation_result,
    withdraw_complaint,
    assign_approver, approver_reject, handler_reject, assign_assignees, add_participants,
    cannot_handle, update_progress, resolve_complaint, confirm_complaint,
    set_primary,
    get_sidebar_tasks, get_work_order_progress,
    request_email_review, approve_email_send,
    raise_warning, review_return,
    _check_cs_creator,
)
from schemas.auth import UserInfo
from schemas.complaint import (
    ComplaintCreate, ComplaintUpdate,
    IntakeReviewRequest, InvestigationResultRequest, WithdrawRequest,
    AssignApproverRequest, ApproverRejectRequest, HandlerRejectRequest, AssignAssigneesRequest,
    AddParticipantsRequest, CannotHandleRequest, SetPrimaryRequest,
    ProgressRequest, ResolveRequest, ConfirmRequest,
    EmailSendRequest, EmailReviewRequest, EmailDraftSubmitRequest,
    RemarkRequest, WarningRequest, ReturnReviewRequest,
)
from schemas.common import ApiResponse, PaginatedResponse, PaginationOut
from middleware.auth import get_current_user
from core.websocket import manager

router = APIRouter()


# 0820 edited 事件 detail 中文字段名映射（ComplaintUpdate 字段全集 + 编辑端点注入的键）
FIELD_LABELS = {
    'customer_name': '客户名称',
    'equipment_model': '设备型号',
    'equipment_sn': '设备编号',
    'device_part': '部位',
    'software_version': '软件版本',
    'fault_category': '故障分类',
    'scene_category': '客诉场景分类',
    'fault_phenomenon': '故障现象',
    'priority': '优先级',
    'impact_level': '影响程度',
    'resolution_note': '处理备注',
    'status': '状态',
    'root_cause': '根因分析',
    'solution': '解决方案',
    'planned_start_time': '排期开始',
    'planned_end_time': '排期结束',
    'estimated_hours': '预估工时',
    'expected_complete_date': '客户期望日期',
    'remarks': '备注',
    'customer_note': '客户备注',
    'customer_email': '客户邮箱',
    'customer_self_check': '推荐自排查',
    'linked_complaint_ids': '关联工单',
    'sub_type': '子类型',
    'closed_at': '关闭时间',  # 0914 管理员改状态时注入（已关闭同步关闭时间）
    're_edited': '重新编辑标记',
}


# ── 辅助：DB Row → 响应 dict ────────────────────────
def _row_to_out(row: dict, assignees: Optional[list] = None) -> dict:
    """将 DB Row dict 转为前端友好的 dict，增加进度百分比和指派快照。"""
    if not row:
        return row
    out = dict(row)
    out["status"] = normalize_status(row.get("status", ""))
    out["_progress_pct"] = get_progress_pct(out["status"])
    if assignees is not None:
        out["assignees"] = assignees
    return out


# ═══════════════════════════════════════ 列表 ═══════════════════════════════════════

@router.get("", response_model=PaginatedResponse)
async def list_complaints(
    status: Optional[str] = Query(default=None, description="状态筛选"),
    category: Optional[str] = Query(default=None, description="类别筛选"),
    priority: Optional[str] = Query(default=None, description="优先级筛选"),
    keyword: str = Query(default="", description="搜索关键词"),
    my_orders: bool = Query(default=False, description="仅显示我的工单（按角色状态范围+绑定两层筛选）"),
    page: int = Query(default=1, ge=1, description="页码"),
    limit: int = Query(default=100, ge=1, le=500, description="每页条数"),
    current_user: UserInfo = Depends(get_current_user),
):
    """0819 获取投诉列表（看板用）：全部角色可见全部工单。"""
    complaints = list_complaints_for_kanban(
        role=current_user.role,
        status_filter=status,
        category_filter=category,
        priority_filter=priority,
        keyword=keyword,
        my_orders_only=my_orders,
        current_user_id=current_user.id,
    )

    total = len(complaints)
    start = (page - 1) * limit
    end = start + limit
    paged = complaints[start:end]

    # 批量挂载指派快照（防 N+1）
    assignees_map = get_assignees_map([c["id"] for c in paged])
    # 0820 批量挂载退回重派信息（指派审批人列角标）
    rejected_map = get_rejected_approver_info_map([c["id"] for c in paged])
    data = []
    for c in paged:
        out = _row_to_out(c, assignees_map.get(c["id"], []))
        out["rejected_info"] = rejected_map.get(c["id"])
        data.append(out)
    return PaginatedResponse(
        success=True,
        data=data,
        message="操作成功",
        pagination=PaginationOut(page=page, limit=limit, total=total),
    )


# ═══════════════════════════════════════ 详情 ═══════════════════════════════════════

@router.get("/by-no/{complaint_no}", response_model=ApiResponse)
async def get_complaint_id(
    complaint_no: str,
    current_user: UserInfo = Depends(get_current_user),
):
    """按工单号查询工单 ID（通知中心点击跳转用）。"""
    cid = get_complaint_id_by_no(complaint_no)
    if not cid:
        raise HTTPException(status_code=404, detail="该工单已被删除")
    return ApiResponse(success=True, data={"id": cid}, message="操作成功")


# 0807 轻量工单搜索 — 用于关联工单选择器（必须注册在 /{complaint_id} 之前）
@router.get("/search", response_model=ApiResponse)
async def search_complaints(
    q: str = Query(default="", min_length=1, description="搜索关键词（编号/客户名称/设备编号）"),
    limit: int = Query(default=10, ge=1, le=30, description="返回条数上限"),
    current_user: UserInfo = Depends(get_current_user),
):
    """轻量工单搜索 — 供关联工单下拉选择使用。返回精简字段列表。"""
    if not q.strip():
        return ApiResponse(success=True, data=[])
    keyword = f"%{q.strip()}%"
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, complaint_no, customer_name, fault_category, status, equipment_sn
           FROM complaints
           WHERE (complaint_no LIKE %s OR customer_name LIKE %s OR equipment_sn LIKE %s)
           ORDER BY created_at DESC LIMIT %s""",
        (keyword, keyword, keyword, limit),
    ).fetchall()
    conn.close()
    return ApiResponse(success=True, data=[dict(r) for r in rows])


# 0915 批量获取工单概要 — 详情页关联工单弹窗表格用（必须注册在 /{complaint_id} 之前）
@router.get("/by-ids", response_model=ApiResponse)
async def get_complaints_by_ids(
    ids: str = Query(default="", description="逗号分隔的工单 ID 列表"),
    current_user: UserInfo = Depends(get_current_user),
):
    """按 ID 批量返回工单概要（编号/设备/优先级/状态/问题/解决方案）；已删除的 id 不在返回中。"""
    id_list = []
    for seg in ids.split(","):
        seg = seg.strip()
        if seg.isdigit():
            id_list.append(int(seg))
        elif seg:
            raise HTTPException(status_code=422, detail=f"非法工单 ID：{seg}")
    if len(id_list) > 100:
        raise HTTPException(status_code=422, detail="单次最多查询 100 个工单")
    return ApiResponse(success=True, data=get_complaint_briefs_by_ids(id_list), message="操作成功")


# ── GET /api/complaints/stats — 首页四卡统计（1014）──
# 注意：必须注册在 /{complaint_id} 之前，避免 "stats" 被路径参数吞掉
@router.get("/stats", response_model=ApiResponse)
async def get_complaint_stats(
    current_user: UserInfo = Depends(get_current_user),
):
    """首页四卡统计（服务端精确聚合）：总 = 处理中 + 待处理 + 已关闭 + 已撤回；待处理不含处理中。"""
    return ApiResponse(success=True, data=get_complaint_status_stats(), message="操作成功")


@router.get("/{complaint_id}", response_model=ApiResponse)
async def get_complaint_detail(
    complaint_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """获取单个投诉详情（0819 所有角色可见）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    from data.database import get_active_approver, get_active_assignees
    approver = get_active_approver(complaint_id)
    assignees = get_active_assignees(complaint_id)
    snapshot = []
    if approver:
        snapshot.append({
            "user_id": approver["user_id"],
            "display_name": approver["display_name"],
            "role": approver["role"],
            "position": approver["position"],
            "assignee_type": "approver",
            "is_primary": 0,
        })
    snapshot.extend({
        "user_id": a["user_id"],
        "display_name": a["display_name"],
        "role": a["role"],
        "position": a["position"],
        "assignee_type": "assignee",
        "is_primary": a.get("is_primary", 0),
    } for a in assignees)
    return ApiResponse(success=True, data=_row_to_out(complaint, snapshot), message="操作成功")


# ═══════════════════════════════════════ 创建 ═══════════════════════════════════════

@router.post("", response_model=ApiResponse)
async def create_complaint_api(
    body: ComplaintCreate,
    current_user: UserInfo = Depends(get_current_user),
):
    """创建新投诉（客诉录入）。0819 仅客服/管理员可创建，创建后进入 客服主管审核(intake)。"""
    if current_user.role not in ("客服", "管理员"):
        raise HTTPException(status_code=403, detail="仅客服/管理员可录入客诉")

    from data.database import generate_complaint_no, find_similar_complaints

    data = body.model_dump(exclude={"force"})
    data["created_by"] = data.get("created_by") or current_user.display_name
    data["created_by_user_id"] = current_user.id
    data["status"] = "客服主管审核"
    data["sub_type"] = "intake"
    # 1019 客诉发生时间：表单未填则默认今天；转成 TIMESTAMP 可接受的格式（created_at 由 DB 默认取真实录入时刻）
    occurred = (data.get("occurred_at") or "").strip()
    data["occurred_at"] = f"{occurred} 00:00:00" if occurred else datetime.now().strftime("%Y-%m-%d 00:00:00")

    # 0728 重复检测：同客户+同设备+故障描述相似（非强制提交时）
    if not body.force:
        similar = find_similar_complaints(
            data["customer_name"],
            data.get("equipment_model", ""),
            data["fault_phenomenon"],
        )
        if similar:
            return ApiResponse(
                success=False,
                data={"duplicates": similar},
                message=f"检测到近30天内已有 {len(similar)} 个相似工单，请确认是否仍要提交",
            )

    complaint_id = db_create_complaint(data)
    new_complaint = get_complaint(complaint_id)

    if new_complaint:
        from services.notification_service import create_notification
        create_notification(
            complaint_no=new_complaint["complaint_no"],
            title=f"📋 新工单待审核：{new_complaint['complaint_no']}",
            message=(
                f"客服 {current_user.display_name} 录入了新工单 {new_complaint['complaint_no']}，"
                f"客户：{new_complaint.get('customer_name') or '—'}，"
                f"故障分类：{new_complaint.get('fault_category', '') or '未分类'}。请前往客诉看板「客服主管审核」列处理。"
            ),
            target_role="客服主管",
            category="action_required",
        )

        detail_parts = [f"工单 {new_complaint['complaint_no']} 创建成功"]
        cn = new_complaint.get("customer_note", "").strip()
        if cn:
            detail_parts.append(f"客户备注：{cn}")
        sc = new_complaint.get("customer_self_check", "").strip()
        if sc:
            detail_parts.append(f"推荐客户自排查：{sc}")
        if new_complaint.get("is_rework"):
            detail_parts.append("标记为返修工单")
        linked = new_complaint.get("linked_complaint_ids", "[]")
        try:
            import json
            linked_list = json.loads(linked) if isinstance(linked, str) else linked
            if linked_list:
                linked_nos = ", ".join(item["no"] if isinstance(item, dict) else item for item in linked_list)
                detail_parts.append(f"关联工单：{linked_nos}")
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
        create_work_order_log(
            complaint_id=complaint_id,
            event_type="created",
            operator_name=current_user.display_name,
            operator_role=current_user.role,
            new_status="客服主管审核",
            detail="。".join(detail_parts),
            operator_position=current_user.position,
        )

        import asyncio
        event = {
            "type": "complaint_created",
            "complaint_id": complaint_id,
            "complaint_no": new_complaint["complaint_no"],
            "status": "客服主管审核",
            "message": f"新工单已创建：{new_complaint['complaint_no']}",
        }
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(manager.broadcast(event, target_role="全员"))
        except RuntimeError:
            pass

    return ApiResponse(
        success=True,
        data={"id": complaint_id, "complaint_no": new_complaint["complaint_no"] if new_complaint else ""},
        message="客诉创建成功",
    )


# ═══════════════════════════════════════ 更新 ═══════════════════════════════════════

@router.put("/{complaint_id}", response_model=ApiResponse)
async def update_complaint_api(
    complaint_id: int,
    body: ComplaintUpdate,
    current_user: UserInfo = Depends(get_current_user),
):
    """更新投诉信息（编辑弹窗）。0819 管理员可改状态（限新 7 值）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")

    if not can_edit_delete(current_user.role, complaint.get("status", ""), complaint.get("sub_type", "")):
        raise HTTPException(status_code=403, detail="当前角色无权编辑此状态的工单")

    # 0821 客服操作隔离：仅录入该工单的客服可编辑（管理员旁路）
    cs_err = _check_cs_creator(complaint, current_user)
    if cs_err:
        raise HTTPException(status_code=403, detail=cs_err)

    update_data = {k: v for k, v in body.model_dump(exclude_none=True).items() if v is not None}
    if current_user.role != "管理员":
        update_data.pop("priority", None)
        update_data.pop("status", None)

    # 1019 客诉发生时间：空值不覆盖；有值补成 TIMESTAMP 格式（改它不会重排工单号）
    if "occurred_at" in update_data:
        _occurred = (update_data.get("occurred_at") or "").strip()
        if _occurred:
            update_data["occurred_at"] = f"{_occurred} 00:00:00"
        else:
            update_data.pop("occurred_at", None)

    # 0914 管理员改状态必填原因：先取出（非 DB 字段，绝不进 update_complaint 的 SET 列），
    # 状态实际变化时为空即 400；原因进工单日志与状态变更通知文案
    status_change_reason = (update_data.pop("status_change_reason", "") or "").strip()

    # 0819 管理员改状态限合法值（0825 起含第 8 状态「已撤回」）
    if update_data.get("status") and update_data["status"] not in CANONICAL_STATUSES:
        raise HTTPException(status_code=400, detail="无效状态值")

    status_changed = bool(update_data.get("status") and update_data["status"] != complaint.get("status", ""))
    # 1020 管理员改状态时，未决的退回申请自动失效（仅清 pending）
    if status_changed and complaint.get("return_request_status") == "pending":
        update_data["return_request_status"] = None
        update_data["return_request_type"] = None

    # 0820 管理员改状态时同步归一化子类型，防止状态/子类型不匹配导致流程卡死
    if status_changed:
        if not status_change_reason:
            raise HTTPException(status_code=400, detail="修改状态必须填写原因")
        if update_data["status"] == "待客服处理":
            update_data["sub_type"] = "customer_confirm"
        elif update_data["status"] == "客服主管审核":
            update_data["sub_type"] = "intake"
        else:
            update_data["sub_type"] = ""
        # 0914 closed_at 同步：管理员直改「已关闭」补写关闭时间（此前仅客户确认流程写），
        # 从已关闭改出则清空，避免详情页残留旧关闭时间
        if update_data["status"] == "已关闭":
            update_data["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif complaint.get("status", "") == "已关闭":
            update_data["closed_at"] = None

    # 客服在主管退回后重新编辑 → 标记 re_edited=1，供主管区分
    if current_user.role == "客服" and complaint.get("supervisor_rejection_note") and not complaint.get("re_edited"):
        update_data["re_edited"] = 1
    update_complaint(complaint_id, update_data)
    updated = get_complaint(complaint_id)

    changed_fields = [k for k in update_data if k != 'updated_at']
    if changed_fields:
        detail_parts = []
        for k in changed_fields:
            label = FIELD_LABELS.get(k, k)
            if k in ('customer_note', 'customer_self_check', 'remarks', 'fault_phenomenon', 'root_cause', 'solution',
                     'reproduction_steps', 'resolution_note'):
                val = str(update_data.get(k, ''))
                truncated = val[:100] + ('...' if len(val) > 100 else '')
                detail_parts.append(f"{label}：{truncated}")
            else:
                detail_parts.append(label)
        detail = f"编辑工单信息，修改了：{'、'.join(detail_parts)}"
        if status_changed:
            detail += f"；管理员修改状态：{complaint.get('status', '')} → {update_data['status']}（原因：{status_change_reason}）"
        create_work_order_log(
            complaint_id=complaint_id,
            event_type="edited",
            operator_name=current_user.display_name,
            operator_role=current_user.role,
            old_status=complaint.get("status", ""),
            new_status=update_data.get("status", complaint.get("status", "")),
            detail=detail,
            operator_position=current_user.position,
        )

    old_status = complaint.get("status", "")
    if status_changed:
        from services.notification_service import create_notification
        create_notification(
            complaint_no=complaint["complaint_no"],
            title=f"📝 状态变更：{complaint['complaint_no']}",
            message=f"管理员将工单状态从「{old_status}」变更为「{update_data['status']}」（原因：{status_change_reason}）。",
            target_role="全员",
            category="awareness",
        )
    elif changed_fields and current_user.role == "管理员":
        # 0820 管理员编辑非状态字段：精准知会录入客服 + 有效审批人 + 有效承接人
        from data.database import get_active_approver, get_active_assignees
        from services.notification_service import create_notification
        recipients = set()
        creator_id = complaint.get("created_by_user_id", 0)
        if creator_id:
            recipients.add(creator_id)
        approver = get_active_approver(complaint_id)
        if approver:
            recipients.add(approver["user_id"])
        for a in get_active_assignees(complaint_id):
            recipients.add(a["user_id"])
        for uid in recipients:
            create_notification(
                complaint_no=complaint["complaint_no"],
                title=f"✏️ 工单信息更新：{complaint['complaint_no']}",
                message=f"管理员 {current_user.display_name} 更新了工单信息（修改字段：{'、'.join(changed_fields)}）。",
                target_role="全员",
                category="awareness",
                target_user_id=uid,
            )

    if updated:
        import asyncio
        event = {
            "type": "complaint_updated",
            "complaint_id": complaint_id,
            "complaint_no": updated["complaint_no"],
            "status": updated.get("status", ""),
            "message": f"工单 {updated['complaint_no']} 信息已更新",
        }
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(manager.broadcast(event, target_role="全员"))
        except RuntimeError:
            pass

    return ApiResponse(success=True, data=_row_to_out(updated), message="工单已更新")


# ═══════════════════════════════════════ 删除 ═══════════════════════════════════════

@router.delete("/{complaint_id}", response_model=ApiResponse)
async def delete_complaint_api(
    complaint_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """删除投诉（0819 仅管理员）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")

    if current_user.role != "管理员":
        raise HTTPException(status_code=403, detail="仅管理员可删除工单")

    create_work_order_log(
        complaint_id=complaint_id,
        event_type="deleted",
        operator_name=current_user.display_name,
        operator_role=current_user.role,
        old_status=complaint.get("status", ""),
        detail=f"工单 {complaint.get('complaint_no', '')} 已删除",
        operator_position=current_user.position,
    )
    success = delete_complaint(complaint_id)
    if success:
        # 0820 删除知会（complaint_no 置空避免被删除清理连带删掉）
        from services.notification_service import create_notification
        create_notification(
            complaint_no="",
            title=f"🗑️ 工单已删除：{complaint.get('complaint_no', '')}",
            message=f"管理员 {current_user.display_name} 删除了工单 {complaint.get('complaint_no', '')}。",
            target_role="全员",
            category="awareness",
        )
        import asyncio
        event = {
            "type": "complaint_deleted",
            "complaint_id": complaint_id,
            "complaint_no": complaint.get("complaint_no", ""),
            "status": complaint.get("status", ""),
            "message": f"工单 {complaint.get('complaint_no', '')} 已删除",
        }
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(manager.broadcast(event, target_role="全员"))
        except RuntimeError:
            pass
        return ApiResponse(success=True, message="工单已删除")
    else:
        raise HTTPException(status_code=500, detail="删除失败")


# ═══════════════════ 0819 v3.0 新状态机端点 ═══════════════════

@router.post("/{complaint_id}/intake-review", response_model=ApiResponse)
async def intake_review(
    complaint_id: int, body: IntakeReviewRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """客服主管客诉审核：通过（优先级+去向）/ 拒绝（原因）。撤回已移至 /withdraw（0826）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    result = supervisor_intake_review(
        complaint_id, body.action, body.priority or "", body.route or "",
        body.rejection_note or "", body.evaluation or "", current_user,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/withdraw", response_model=ApiResponse)
async def withdraw(
    complaint_id: int, body: WithdrawRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """0826 客服录入人撤回工单（全流程除已关闭/已撤回；终态不入知识库，管理员可改状态恢复）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    result = withdraw_complaint(complaint_id, body.withdraw_note, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/resubmit", response_model=ApiResponse)
async def resubmit(
    complaint_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """客服重新提交审核（待客服处理 rework → 客服主管审核）。"""
    result = cs_resubmit(complaint_id, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/investigation-result", response_model=ApiResponse)
async def investigation_result(
    complaint_id: int, body: InvestigationResultRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """客服提交待客户排查结果（已解决/未解决）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    result = cs_investigation_result(complaint_id, body.result, body.remark or "", current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/assign-approver", response_model=ApiResponse)
async def assign_approver_api(
    complaint_id: int, body: AssignApproverRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """办理人指派审批人（候选：办理人/审批人；0825 指派说明必填）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    result = assign_approver(complaint_id, body.user_id, current_user, body.note)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/approver-reject", response_model=ApiResponse)
async def approver_reject_api(
    complaint_id: int, body: ApproverRejectRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """审批人「不可承接」退回指派审批人。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    result = approver_reject(complaint_id, body.reason, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/handler-reject", response_model=ApiResponse)
async def handler_reject_api(
    complaint_id: int, body: HandlerRejectRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """0901 办理人「不可承接」退回录入客服（待客服处理 rework）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    result = handler_reject(complaint_id, body.reason, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/assign-assignees", response_model=ApiResponse)
async def assign_assignees_api(
    complaint_id: int, body: AssignAssigneesRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """审批人指派承接人（多人）+ 排期 → 处理中。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    result = assign_assignees(
        complaint_id, body.evaluation, body.estimated_hours, body.user_ids,
        body.planned_start or "", body.planned_end or "", body.force,
        body.primary_user_id or 0, current_user,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/participants", response_model=ApiResponse)
async def participants_api(
    complaint_id: int, body: AddParticipantsRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """审批人追加参与人（处理中）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    result = add_participants(complaint_id, body.user_ids, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/set-primary", response_model=ApiResponse)
async def set_primary_api(
    complaint_id: int, body: SetPrimaryRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """0820 处理中变更主要推进人（审批人/管理员）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    result = set_primary(complaint_id, body.user_id, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/cannot-handle", response_model=ApiResponse)
async def cannot_handle_api(
    complaint_id: int, body: CannotHandleRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """承接人/参与人反馈「处理不了」→ 回指派审批人。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    result = cannot_handle(complaint_id, body.reason, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/progress", response_model=ApiResponse)
async def add_progress(
    complaint_id: int, body: ProgressRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """更新工单处理进度（承接人/参与人/管理员）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    if complaint.get("status") != "处理中":
        raise HTTPException(status_code=400, detail="仅处理中状态可更新进度")

    result = update_progress(
        complaint_id, body.progress_pct, body.note, current_user.display_name, complaint,
        current_user,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/resolve", response_model=ApiResponse)
async def resolve(
    complaint_id: int, body: ResolveRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """提交解决方案 → 待客服处理(customer_confirm)。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    if complaint.get("status") != "处理中":
        raise HTTPException(status_code=400, detail="仅处理中状态可提交解决方案")

    result = resolve_complaint(
        complaint_id, body.root_cause, body.solution,
        "",
        body.resolution_note or '',
        body.checklist or '',
        current_user.display_name, complaint,
        current_user,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/confirm", response_model=ApiResponse)
async def confirm(
    complaint_id: int, body: ConfirmRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """客户确认关闭工单（客服/管理员）。"""
    if current_user.role not in ("客服", "管理员"):
        raise HTTPException(status_code=403, detail="仅客服/管理员可确认关闭")

    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    if complaint.get("status") != "待客服处理" or complaint.get("sub_type") != "customer_confirm":
        raise HTTPException(status_code=400, detail="仅待客服处理（待客户确认）状态可关闭")

    result = confirm_complaint(
        complaint_id, body.satisfaction, body.is_rework, current_user.display_name, complaint,
        current_user,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


# ═══════════════════════════════════════ 查询辅助 ═══════════════════════════════════════

@router.get("/sidebar/tasks", response_model=ApiResponse)
async def sidebar_tasks(
    my_orders_only: bool = Query(default=False),
    approver_group: str = Query(default="", description="审批人分组：todo_assignee / add_assignee（0826 起仅显式传入时过滤，默认不过滤）"),
    current_user: UserInfo = Depends(get_current_user),
):
    """获取工单处理页侧边栏任务列表（0819 全员可见）。"""
    result = get_sidebar_tasks(
        current_user.role, current_user.id,
        my_orders_only=my_orders_only, approver_group=approver_group,
    )
    return ApiResponse(success=True, data=result, message="操作成功")


@router.get("/{complaint_id}/progress-info", response_model=ApiResponse)
async def progress_info(
    complaint_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """获取工单进度详情（含 progress_updates 最新值）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    result = get_work_order_progress(complaint)
    from data.database import list_progress_updates
    result["history"] = list_progress_updates(complaint_id)
    return ApiResponse(success=True, data=result, message="操作成功")


@router.get("/{complaint_id}/timeline", response_model=ApiResponse)
async def complaint_timeline(
    complaint_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """获取工单完整操作时间线（work_order_log + legacy remarks）。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    logs = list_work_order_log(complaint_id)
    result = {
        "logs": logs,
        "legacy_remarks": complaint.get("remarks", ""),
        "legacy_customer_note": complaint.get("customer_note", ""),
        "legacy_customer_self_check": complaint.get("customer_self_check", ""),
    }
    return ApiResponse(success=True, data=result, message="操作成功")


@router.get("/{complaint_id}/attachments", response_model=ApiResponse)
async def complaint_attachments(
    complaint_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """获取工单的附件列表。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")
    from data.database import get_attachments
    atts = get_attachments(complaint_id)
    return ApiResponse(success=True, data=atts, message="操作成功")


@router.post("/{complaint_id}/remark", response_model=ApiResponse)
async def save_remark_api(
    complaint_id: int,
    body: RemarkRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """客服保存排查备注（仅保存，不改变状态）。"""
    if current_user.role not in ("客服", "管理员"):
        raise HTTPException(status_code=403, detail="仅客服/管理员可添加备注")

    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")

    if complaint.get("status") != "待客户排查":
        raise HTTPException(status_code=400, detail="仅待客户排查状态可添加备注")

    result = save_remark(complaint_id, body.remark, current_user.display_name, complaint, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/return-review", response_model=ApiResponse)
async def review_return_api(
    complaint_id: int,
    body: ReturnReviewRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """1020 退回审批：审批人（或员工25/员工26）通过/驳回收到的退回申请。"""
    result = review_return(complaint_id, body.action, body.note, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/warning", response_model=ApiResponse)
async def raise_warning_api(
    complaint_id: int,
    body: WarningRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """1016 工单预警：客服/客服主管按关键词发起，按风险档通知客服主管/承接人（高风险加发指定知会人）。"""
    result = raise_warning(complaint_id, body.keywords, body.note, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


# ═══════════════════════════════════════ 客户邮件 ═══════════════════════════════════════

@router.post("/{complaint_id}/generate-email", response_model=ApiResponse)
async def generate_email_api(
    complaint_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """AI 生成发送给客户的邮件草稿（DeepSeek）。"""
    if current_user.role not in ("客服", "管理员"):
        raise HTTPException(status_code=403, detail="仅客服/管理员可生成邮件")

    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")

    # 0821 客服操作隔离：仅录入该工单的客服可生成邮件（管理员旁路）
    cs_err = _check_cs_creator(complaint, current_user)
    if cs_err:
        raise HTTPException(status_code=403, detail=cs_err)

    if complaint.get("status") != "待客服处理" or complaint.get("sub_type") != "customer_confirm":
        raise HTTPException(status_code=400, detail="仅待客服处理（待客户确认）状态可生成客户邮件")

    result = generate_draft(complaint)
    return ApiResponse(success=True, data=result, message="邮件草稿已生成")


@router.post("/{complaint_id}/send-email", response_model=ApiResponse)
async def send_email_api(
    complaint_id: int,
    body: EmailSendRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """发送客户邮件，并将记录追加到工单 remarks。附件通过 body 中的 attachment_ids 引用已有文件。"""
    if current_user.role not in ("客服", "管理员"):
        raise HTTPException(status_code=403, detail="仅客服/管理员可发送邮件")

    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")

    # 0821 客服操作隔离：仅录入该工单的客服可发送邮件（管理员旁路）
    cs_err = _check_cs_creator(complaint, current_user)
    if cs_err:
        raise HTTPException(status_code=403, detail=cs_err)

    if complaint.get("status") != "待客服处理" or complaint.get("sub_type") != "customer_confirm":
        raise HTTPException(status_code=400, detail="仅待客服处理（待客户确认）状态可发送邮件")

    if not body.to_email or not body.to_email.strip():
        raise HTTPException(status_code=400, detail="收件人邮箱不能为空")

    try:
        result = send_customer_email(
            complaint=complaint,
            to_email=body.to_email.strip(),
            subject=body.subject,
            body=body.body,
            attachment_ids=body.attachment_ids,
            operator_name=current_user.display_name,
            operator_role=current_user.role,
            operator_position=current_user.position,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])

    return ApiResponse(success=True, data=result, message=result["message"])


# ═══════════════════════════════════════ 邮件审核 ═══════════════════════════════════════

@router.post("/{complaint_id}/request-email-review", response_model=ApiResponse)
async def request_email_review_api(
    complaint_id: int,
    body: EmailDraftSubmitRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """客服提交邮件草稿给主管审核 → 客服主管审核(email)。"""
    result = request_email_review(complaint_id, body.subject, body.body, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])


@router.post("/{complaint_id}/email-review", response_model=ApiResponse)
async def email_review_api(
    complaint_id: int,
    body: EmailReviewRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """客服主管审核邮件发送申请（approved / rejected）。"""
    result = approve_email_send(complaint_id, body.action, body.note, current_user)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return ApiResponse(success=True, data=result, message=result["message"])
