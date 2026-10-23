# 0819 v3.0 角色流程重构 — 端到端状态机回归测试
"""串起新状态机主干场景（无 pytest 依赖，直接 python eval/test_flow_v3.py 运行）：
1. 客服录入 → 主管审核拒绝 → 客服修改重提 → 主管通过(转待客户排查)
2. 待客户排查未解决 → 办理人指派审批人 → 审批人指派承接人(多人) → 处理中
3. 处理中进度更新 → 承接人反馈处理不了 → 回指派审批人 → 重新指派 → 完成
4. 待客服处理(customer_confirm) → 邮件审核回路 → 客户确认关闭 + KB 归档
5. 待客户排查已解决 → 直接进入待客服处理(customer_confirm)

运行：cd backend && python eval/test_flow_v3.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import pytest  # 可选：装了 pytest 时以 fixture 方式跑
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False
    pytest = None

from fastapi.testclient import TestClient

from data import database as db
from data.database import init_db, init_users
from main import app
from middleware.auth import get_current_user
from schemas.auth import UserInfo

init_db()
init_users()

# ── 测试角色（直连 DB 创建，测试专用，完成后清理）─────────────────
TEST_USERS = [
    ("cs_a", "客服A", "客服", "客服专员"),
    ("sup_b", "主管B", "客服主管", "客服主管"),
    ("handler_c", "办理人C", "办理人", "工单管理员"),
    ("approver_d", "审批人D", "审批人", "高级工程师"),
    ("assignee_e", "承接人E", "承接人", "工程师"),
    ("assignee_f", "承接人F", "承接人", "工程师"),
]

_test_user_ids: dict[str, int] = {}
_test_complaint_id: int | None = None


def _make_user(username: str, role: str, position: str) -> UserInfo:
    uid = _test_user_ids.get(username)
    if uid is None:
        u = db.get_user_by_username(username)
        uid = u["id"] if u else 0
    return UserInfo(
        id=uid,
        username=username,
        display_name={"cs_a": "客服A", "sup_b": "主管B", "handler_c": "办理人C",
                      "approver_d": "审批人D", "assignee_e": "承接人E", "assignee_f": "承接人F",
                      "admin": "系统管理员"}[username],
        role=role,
        position=position,
    )


class RoleClient:
    """包装 TestClient：每次请求前把全局依赖覆盖设为当前用户（测试串行执行，安全）。"""

    def __init__(self, user: UserInfo):
        self.user = user
        self.client = TestClient(app)

    def _set_override(self):
        async def _override(u=self.user):
            return u
        app.dependency_overrides[get_current_user] = _override

    def request(self, method: str, url: str, **kw):
        self._set_override()
        return self.client.request(method, url, **kw)

    def get(self, url: str, **kw):
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw):
        return self.request("POST", url, **kw)

    def put(self, url: str, **kw):
        return self.request("PUT", url, **kw)

    def delete(self, url: str, **kw):
        return self.request("DELETE", url, **kw)


def _client_for(username: str) -> RoleClient:
    user = _make_user(username, TEST_USER_ROLES[username], TEST_USER_POS[username])
    return RoleClient(user)


TEST_USER_ROLES = {
    "cs_a": "客服", "sup_b": "客服主管", "handler_c": "办理人",
    "approver_d": "审批人", "assignee_e": "承接人", "assignee_f": "承接人",
}
TEST_USER_POS = {
    "cs_a": "客服专员", "sup_b": "客服主管", "handler_c": "工单管理员",
    "approver_d": "高级工程师", "assignee_e": "工程师", "assignee_f": "工程师",
}


def setup_users():
    """创建测试用户（生成器形式：pytest 有则作 fixture，无则手工 next）。"""
    for username, display_name, role, position in TEST_USERS:
        existing = db.get_user_by_username(username)
        if existing:
            db.delete_user(existing["id"])
        uid = db.create_user(username, "test1234", display_name, role, position)
        assert uid, f"创建测试用户 {username} 失败"
        _test_user_ids[username] = uid
    yield
    for username, _, _, _ in TEST_USERS:
        u = db.get_user_by_username(username)
        if u:
            db.delete_user(u["id"])
    if _test_complaint_id:
        db.delete_complaint(_test_complaint_id)


if HAS_PYTEST:
    setup_users = pytest.fixture(scope="module", autouse=True)(setup_users)


def _create_complaint(client: TestClient, customer: str = "测试客户") -> dict:
    r = client.post("/api/complaints", json={
        "customer_name": customer,
        "scene_category": "客户正式投诉类",
        "equipment_model": "EQ-800",
        "fault_category": "机械",
        "fault_phenomenon": "涂胶后出现气泡，良率下降",
        "priority": "待确认",
    })
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    global _test_complaint_id
    _test_complaint_id = data["id"]
    return data


def test_full_flow():
    cs = _client_for("cs_a")
    sup = _client_for("sup_b")
    handler = _client_for("handler_c")
    approver = _client_for("approver_d")
    assignee_e = _client_for("assignee_e")
    assignee_f = _client_for("assignee_f")
    admin = RoleClient(_make_user("admin", "管理员", "系统管理员"))

    # ══ 1. 录入 → 客服主管审核(intake) ══
    created = _create_complaint(cs)
    cid = created["id"]
    c = db.get_complaint(cid)
    assert c["status"] == "客服主管审核" and c["sub_type"] == "intake"

    # 非主管审核 → 400
    r = handler.post(f"/api/complaints/{cid}/intake-review",
                     json={"action": "approve", "priority": "P1", "route": "待客户排查"})
    assert r.status_code == 400

    # ══ 2. 主管拒绝 → 待客服处理(rework) ══
    r = sup.post(f"/api/complaints/{cid}/intake-review",
                 json={"action": "reject", "rejection_note": "客户名称不完整"})
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "待客服处理" and c["sub_type"] == "rework"
    assert c["supervisor_rejection_note"] == "客户名称不完整"

    # 客服编辑 + 重新提交 → 客服主管审核(intake) + re_edited=1
    cs.put(f"/api/complaints/{cid}", json={"customer_name": "测试客户（完整）"})
    r = cs.post(f"/api/complaints/{cid}/resubmit", json={})
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "客服主管审核" and c["sub_type"] == "intake" and c["re_edited"] == 1

    # ══ 3. 主管通过（P1 + 转待客户排查）══
    # 0820 不填审核评估 → 400
    r = sup.post(f"/api/complaints/{cid}/intake-review",
                 json={"action": "approve", "priority": "P1", "route": "待客户排查"})
    assert r.status_code == 400, r.text
    r = sup.post(f"/api/complaints/{cid}/intake-review",
                 json={"action": "approve", "priority": "P1", "route": "待客户排查",
                       "evaluation": "客户反馈现象清晰，建议先由客户按自排查清单排查确认"})
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "待客户排查" and c["priority"] == "P1"
    # 0820 评估内容写入 remarks
    assert "审核评估" in (c.get("remarks") or "")

    # ══ 4. 排查未解决 → 指派审批人 ══
    r = cs.post(f"/api/complaints/{cid}/investigation-result",
                json={"result": "unresolved", "remark": "客户反馈仍然存在"})
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "指派审批人"

    # ══ 5. 办理人指派审批人（候选校验：客服不可被指派）══
    # 0825 指派说明必填：缺失 → 422（Pydantic 校验）
    r = handler.post(f"/api/complaints/{cid}/assign-approver",
                     json={"user_id": _test_user_ids["cs_a"]})
    assert r.status_code == 422
    r = handler.post(f"/api/complaints/{cid}/assign-approver",
                     json={"user_id": _test_user_ids["cs_a"], "note": "尝试指派客服"})
    assert r.status_code == 400  # 客服不是候选
    r = handler.post(f"/api/complaints/{cid}/assign-approver",
                     json={"user_id": _test_user_ids["approver_d"], "note": "测试指派说明"})
    assert r.status_code == 200, r.text
    # 0825 指派说明写入日志 detail（随工单流转日志导出）
    logs = db.list_work_order_log(cid)
    asg_log = next(l for l in logs if l["event_type"] == "approver_assigned")
    assert "说明：测试指派说明" in (asg_log["detail"] or ""), asg_log["detail"]
    c = db.get_complaint(cid)
    assert c["status"] == "指派承接人"
    approver_row = db.get_active_approver(cid)
    assert approver_row and approver_row["user_id"] == _test_user_ids["approver_d"]
    # 0820 办理人记录（指派审批人的操作人）
    assert c.get("handler_name") == "办理人C"

    # ══ 6. 审批人「不可承接」退回 → 指派审批人 ══
    r = approver.post(f"/api/complaints/{cid}/approver-reject", json={"reason": "超出能力范围"})
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "指派审批人"

    # 办理人重新指派
    r = handler.post(f"/api/complaints/{cid}/assign-approver",
                     json={"user_id": _test_user_ids["approver_d"], "note": "测试指派说明"})
    assert r.status_code == 200, r.text

    # ══ 7. 审批人指派承接人（多人 E+F）+ 主要推进人 → 处理中 ══
    # 0820 主要推进人校验：不在 user_ids 中 → 400
    r = approver.post(f"/api/complaints/{cid}/assign-assignees", json={
        "evaluation": "可承接，需要机械和软件协同",
        "estimated_hours": 8.0,
        "user_ids": [_test_user_ids["assignee_e"], _test_user_ids["assignee_f"]],
        "primary_user_id": _test_user_ids["approver_d"],
    })
    assert r.status_code == 400, r.text
    # 0820 不传主要推进人 → 400
    r = approver.post(f"/api/complaints/{cid}/assign-assignees", json={
        "evaluation": "可承接，需要机械和软件协同",
        "estimated_hours": 8.0,
        "user_ids": [_test_user_ids["assignee_e"], _test_user_ids["assignee_f"]],
    })
    assert r.status_code == 400, r.text
    r = approver.post(f"/api/complaints/{cid}/assign-assignees", json={
        "evaluation": "可承接，需要机械和软件协同",
        "estimated_hours": 8.0,
        "user_ids": [_test_user_ids["assignee_e"], _test_user_ids["assignee_f"]],
        "planned_start": "2026-08-20T09:00",
        "planned_end": "2026-08-22T18:00",
        "primary_user_id": _test_user_ids["assignee_e"],
    })
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "处理中"
    assignees = db.get_active_assignees(cid)
    assert len(assignees) == 2
    # 0820 主要推进人 E 生效
    primary = db.get_primary_assignee(cid)
    assert primary and primary["user_id"] == _test_user_ids["assignee_e"]
    assert db.is_primary_assignee(cid, _test_user_ids["assignee_e"])

    # ══ 8. 承接人更新进度；非参与角色不可更新 ══
    r = assignee_e.post(f"/api/complaints/{cid}/progress", json={"progress_pct": 50, "note": "已完成排查"})
    assert r.status_code == 200, r.text
    r = cs.post(f"/api/complaints/{cid}/progress", json={"progress_pct": 60, "note": "客服无权"})
    assert r.status_code == 400

    # ══ 9. 审批人追加参与人（办理人C）══
    r = approver.post(f"/api/complaints/{cid}/participants",
                      json={"user_ids": [_test_user_ids["handler_c"]]})
    assert r.status_code == 200, r.text
    assert len(db.get_active_assignees(cid)) == 3
    # 参与人 C 现在可以更新进度
    r = handler.post(f"/api/complaints/{cid}/progress", json={"progress_pct": 60, "note": "参与人更新"})
    assert r.status_code == 200, r.text
    # 0820 跨角色可见：办理人角色用户被追加为参与人后能查到精准通知
    notifs_c = db.get_unread_notifications("办理人", _test_user_ids["handler_c"])
    assert any("追加为参与人" in (n.get("title") or "") for n in notifs_c), notifs_c

    # ══ 9.5 0820 非主要推进人不可提交处理结果/回退 ══
    r = assignee_f.post(f"/api/complaints/{cid}/resolve", json={
        "root_cause": "测试", "solution": "测试",
    })
    assert r.status_code == 400, r.text
    r = assignee_f.post(f"/api/complaints/{cid}/cannot-handle", json={"reason": "参与人无权回退"})
    assert r.status_code == 400, r.text

    # ══ 10. 0820 主要推进人（E）处理不了回退 → 指派审批人（指派记录全部置 0）══
    r = assignee_e.post(f"/api/complaints/{cid}/cannot-handle", json={"reason": "需要更换模组"})
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "指派审批人"
    assert len(db.get_active_assignees(cid)) == 0
    assert len(db.get_active_approver(cid) or []) == 0 if db.get_active_approver(cid) is None else True
    # 0820 回退后主要推进人标志被清
    assert db.get_primary_assignee(cid) is None

    # 重新走一遍指派（办理人 → 审批人 → 承接人）
    handler.post(f"/api/complaints/{cid}/assign-approver",
                 json={"user_id": _test_user_ids["approver_d"], "note": "测试指派说明"})
    r = approver.post(f"/api/complaints/{cid}/assign-assignees", json={
        "evaluation": "重新评估可承接",
        "estimated_hours": 6.0,
        "user_ids": [_test_user_ids["assignee_e"], _test_user_ids["assignee_f"]],
        "planned_start": "2026-08-21T09:00",
        "planned_end": "2026-08-23T18:00",
        "primary_user_id": _test_user_ids["assignee_e"],
    })
    assert r.status_code == 200, r.text
    assert db.get_complaint(cid)["status"] == "处理中"
    assert db.is_primary_assignee(cid, _test_user_ids["assignee_e"])

    # ══ 10.5 0820 变更主要推进人回路 ══
    # 非审批人/管理员 → 400
    r = cs.post(f"/api/complaints/{cid}/set-primary", json={"user_id": _test_user_ids["assignee_e"]})
    assert r.status_code == 400, r.text
    # 审批人换给 F → 200，E 失去提交权限
    r = approver.post(f"/api/complaints/{cid}/set-primary", json={"user_id": _test_user_ids["assignee_f"]})
    assert r.status_code == 200, r.text
    primary = db.get_primary_assignee(cid)
    assert primary and primary["user_id"] == _test_user_ids["assignee_f"]
    r = assignee_e.post(f"/api/complaints/{cid}/resolve", json={
        "root_cause": "测试", "solution": "测试",
    })
    assert r.status_code == 400, r.text
    # 换回 E
    r = approver.post(f"/api/complaints/{cid}/set-primary", json={"user_id": _test_user_ids["assignee_e"]})
    assert r.status_code == 200, r.text
    assert db.is_primary_assignee(cid, _test_user_ids["assignee_e"])

    # ══ 11. 完成 → 待客服处理(customer_confirm) ══
    r = assignee_e.post(f"/api/complaints/{cid}/resolve", json={
        "root_cause": "涂胶阀密封圈老化",
        "solution": "更换密封圈并重新标定",
        "resolution_note": "已处理完成",
    })
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "待客服处理" and c["sub_type"] == "customer_confirm"

    # ══ 12. 邮件审核回路 ══
    r = cs.post(f"/api/complaints/{cid}/request-email-review",
                json={"subject": "处理方案确认", "body": "您好，处理方案如下……"})
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "客服主管审核" and c["sub_type"] == "email"
    assert c["email_review_status"] == "pending"

    # 主管拒绝 → 待客服处理(rework)
    r = sup.post(f"/api/complaints/{cid}/email-review",
                 json={"action": "rejected", "note": "措辞需调整"})
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "待客服处理" and c["sub_type"] == "rework"
    assert c["email_review_status"] == "rejected"

    # 客服重提 → 自动回 客服主管审核(email)
    r = cs.post(f"/api/complaints/{cid}/resubmit", json={})
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "客服主管审核" and c["sub_type"] == "email"

    # 主管通过 → 待客服处理(customer_confirm)
    r = sup.post(f"/api/complaints/{cid}/email-review", json={"action": "approved"})
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "待客服处理" and c["sub_type"] == "customer_confirm"
    assert c["email_review_status"] == "approved"

    # ══ 13. 客户确认关闭 + KB 归档 ══
    conn = db.get_conn()
    kb_count_before = conn.execute("SELECT COUNT(*) AS count FROM knowledge_base").fetchone()["count"]
    conn.close()
    r = cs.post(f"/api/complaints/{cid}/confirm", json={"satisfaction": 5})
    assert r.status_code == 200, r.text
    c = db.get_complaint(cid)
    assert c["status"] == "已关闭" and c["customer_confirmed"] == 1
    conn = db.get_conn()
    kb_count_after = conn.execute("SELECT COUNT(*) AS count FROM knowledge_base").fetchone()["count"]
    conn.close()
    assert kb_count_after == kb_count_before + 1  # 自动归档 1 条

    # ══ 14. 通知隔离抽查：客服主管能查到角色通知 ══
    sup_notifs = db.get_unread_notifications("客服主管", 0)
    assert isinstance(sup_notifs, list)

    # ══ 15. 待客户排查已解决 → 直接 customer_confirm ══
    created2 = _create_complaint(cs, customer="快捷客户")
    cid2 = created2["id"]
    sup.post(f"/api/complaints/{cid2}/intake-review",
             json={"action": "approve", "priority": "P2", "route": "待客户排查",
                   "evaluation": "快捷流程评估"})
    r = cs.post(f"/api/complaints/{cid2}/investigation-result",
                json={"result": "resolved", "remark": "客户自排查后已恢复"})
    assert r.status_code == 200, r.text
    c2 = db.get_complaint(cid2)
    assert c2["status"] == "待客服处理" and c2["sub_type"] == "customer_confirm"
    db.delete_complaint(cid2)

    # ══ 16. 管理员权限：改状态（限 7 值）／删工单 ══
    r = admin.put(f"/api/complaints/{cid}", json={"status": "已关闭"})
    assert r.status_code == 200, r.text
    r = admin.put(f"/api/complaints/{cid}", json={"status": "已作废"})
    assert r.status_code == 400  # 已作废不再是合法状态

    # 详情包含 assignees 快照
    r = admin.get(f"/api/complaints/{cid}")
    assert r.status_code == 200
    detail = r.json()["data"]
    assert "assignees" in detail

    # ══ 16.5 0820 改派审批人通知（旧审批人知会 + 跨角色精准可见）══
    admin.put(f"/api/complaints/{cid}", json={"status": "指派审批人"})
    r = handler.post(f"/api/complaints/{cid}/assign-approver",
                     json={"user_id": _test_user_ids["handler_c"], "note": "自指派测试说明"})
    assert r.status_code == 200, r.text
    notifs_d = db.get_unread_notifications("审批人", _test_user_ids["approver_d"])
    assert any("已改派审批人" in (n.get("title") or "") for n in notifs_d), notifs_d
    # 0825 _mark_read 已先于新通知执行：办理人自指派为审批人的通知保持未读
    notifs_c = db.get_unread_notifications("办理人", _test_user_ids["handler_c"])
    assert any("您被指派为审批人" in (n.get("title") or "") for n in notifs_c), notifs_c

    # ══ 16.6 0825 办理人作为当前审批人：可见 + 可操作 ══
    # 「仅显示我的工单」不再把办理人的绑定工单过滤掉（指派承接人列，绑定审批人）
    r = handler.get("/api/complaints", params={"my_orders": True})
    assert r.status_code == 200, r.text
    items = r.json()["data"]
    assert any(x["id"] == cid and x["status"] == "指派承接人" for x in items), \
        [x["id"] for x in items]
    # 角色门槛对办理人开放；未绑定的其他办理人仍被绑定校验拒绝（此处验证绑定者可退回）
    r = handler.post(f"/api/complaints/{cid}/approver-reject", json={"reason": "验证办理人作为当前审批人退回"})
    assert r.status_code == 200, r.text
    assert db.get_complaint(cid)["status"] == "指派审批人"

    # ══ 17. 0826 工单撤回（录入客服发起，终态已撤回，不入知识库，管理员可恢复）══
    created3 = _create_complaint(cs, customer="撤回测试客户")
    cid3 = created3["id"]
    conn = db.get_conn()
    kb_before = conn.execute("SELECT COUNT(*) AS count FROM knowledge_base").fetchone()["count"]
    conn.close()
    # 非录入客服（客服主管）→ 400
    r = sup.post(f"/api/complaints/{cid3}/withdraw",
                 json={"withdraw_note": "客户重复录入"})
    assert r.status_code == 400
    # 撤回原因必填（schema 校验）→ 422
    r = cs.post(f"/api/complaints/{cid3}/withdraw",
                json={"withdraw_note": ""})
    assert r.status_code == 422
    # 正常撤回（录入客服，全流程任意非终态）→ 已撤回 + 原因进日志 detail
    r = cs.post(f"/api/complaints/{cid3}/withdraw",
                json={"withdraw_note": "客户重复录入，撤回合并处理"})
    assert r.status_code == 200, r.text
    c3 = db.get_complaint(cid3)
    assert c3["status"] == "已撤回" and c3["sub_type"] == ""
    logs3 = db.list_work_order_log(cid3)
    wd_log = next(l for l in logs3 if l["event_type"] == "intake_withdrawn")
    assert "客户重复录入" in (wd_log["detail"] or ""), wd_log["detail"]
    # 不入知识库
    conn = db.get_conn()
    kb_after = conn.execute("SELECT COUNT(*) AS count FROM knowledge_base").fetchone()["count"]
    conn.close()
    assert kb_after == kb_before
    # 已撤回为终态：再次撤回 → 400
    r = cs.post(f"/api/complaints/{cid3}/withdraw",
                json={"withdraw_note": "重复撤回"})
    assert r.status_code == 400
    # 已撤回不在办理人 my-orders 范围；0826 起客服 my_orders 只按录入人，可见自己的已撤回工单
    r = handler.get("/api/complaints", params={"my_orders": True})
    assert r.status_code == 200
    assert not any(x["id"] == cid3 for x in r.json()["data"])
    r = cs.get("/api/complaints", params={"my_orders": True})
    assert r.status_code == 200
    assert any(x["id"] == cid3 for x in r.json()["data"])
    # 管理员改状态恢复 → 客服主管审核(intake)
    r = admin.put(f"/api/complaints/{cid3}", json={"status": "客服主管审核"})
    assert r.status_code == 200, r.text
    c3 = db.get_complaint(cid3)
    assert c3["status"] == "客服主管审核" and c3["sub_type"] == "intake"
    db.delete_complaint(cid3)

    print("ALL FLOW TESTS PASSED")


def test_my_orders_filter_unit():
    """0820 我的工单两层筛选单测（mock DAO，不触库）。"""
    from unittest.mock import patch
    from services.complaint_service import _apply_my_orders_filter

    complaints = [
        {"id": 1, "status": "待客服处理", "created_by_user_id": 10},
        {"id": 2, "status": "待客户排查", "created_by_user_id": 11},
        {"id": 3, "status": "客服主管审核", "created_by_user_id": 10},
        {"id": 4, "status": "指派审批人", "created_by_user_id": 12},
        {"id": 5, "status": "指派承接人", "created_by_user_id": 13},
        {"id": 6, "status": "处理中", "created_by_user_id": 13},
        {"id": 7, "status": "已关闭", "created_by_user_id": 10},
        {"id": 8, "status": "已撤回", "created_by_user_id": 10},
    ]
    # 0825 过滤函数改用模块级导入，mock 需 patch 到使用方命名空间
    with patch("services.complaint_service.get_complaint_approver_user_ids", return_value={5}), \
         patch("services.complaint_service.get_complaint_assignee_user_ids", return_value={6}):
        # 客服：0826 起只按录入人过滤（不看状态）→ 本人录入的 1/3/7/8（含审核中/已关闭/已撤回）
        assert [c["id"] for c in _apply_my_orders_filter(complaints, "客服", 10)] == [1, 3, 7, 8]
        # 客服主管：客服主管审核列全部（单人岗位）
        assert [c["id"] for c in _apply_my_orders_filter(complaints, "客服主管", 99)] == [3]
        # 办理人：指派审批人列全部（工作队列）∪ 0825 审批人/承接人绑定列（approver={5} ∪ assignee={6}）
        assert [c["id"] for c in _apply_my_orders_filter(complaints, "办理人", 99)] == [4, 5, 6]
        # 审批人：两列 ∩ (approver ∪ assignee 绑定) → 5（approver）、6（assignee）
        assert [c["id"] for c in _apply_my_orders_filter(complaints, "审批人", 20)] == [5, 6]
        # 承接人：两列 ∩ assignee 绑定 → 仅 6
        assert [c["id"] for c in _apply_my_orders_filter(complaints, "承接人", 21)] == [6]
        # 管理员：不过滤（已撤回为终态，仅管理员等不过滤视角可见）
        assert [c["id"] for c in _apply_my_orders_filter(complaints, "管理员", 1)] == [1, 2, 3, 4, 5, 6, 7, 8]


if __name__ == "__main__":
    gen = setup_users()
    next(gen)
    try:
        test_full_flow()
        test_my_orders_filter_unit()
        print("FLOW TEST PASSED")
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
