# -*- coding: utf-8 -*-
"""0820 一次性数据迁移脚本：旧线上库(v2.x) → 新 v3.0 六角色/七状态库

用法（后端已停止状态下，项目根目录执行）：
    python backend/scripts/migrate_old_data.py

迁移源：data/backups/old-keshu-complaints.db（桌面旧库的 checkpoint 副本，桌面原件不动）
回滚：用 data/backups/complaints.db.migration-bak-20260820 覆盖 data/complaints.db 后重启

映射规则（2026-08-20 用户确认）：
  - 角色：管理员→管理员；客服→客服（zw-support01 张伟 → 客服主管）；部门主管→审批人；
          工程师→承接人；运营部→办理人；position=旧 department 列
  - 状态：待客服主管审核→客服主管审核(sub_type=intake)；待工程/研发评估→指派审批人
  - 日志事件：supervisor_approve/selfcheck_review/supervisor_skip_to_eval→intake_approved
  - 旧通知不迁移；按最终状态生成新通知（9 待审核→客服主管，3 指派审批人→办理人）
  - 新库测试工单（KH-20260820-001 与旧单同号）及其附件/日志/通知/统计行删除
"""
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NEW_DB = os.path.join(ROOT, "data", "complaints.db")
OLD_DB = os.path.join(ROOT, "data", "backups", "old-keshu-complaints.db")

# 旧角色 → 新角色（客服主管按 is_dept_head 单独处理）
ROLE_MAP = {
    "管理员": "管理员",
    "客服": "客服",
    "部门主管": "审批人",
    "工程师": "承接人",
    "运营部": "办理人",
}
DEPT_HEAD_CS_USERNAMES = {"zw-support01"}  # 张伟：客服 + is_dept_head → 客服主管

STATUS_MAP = {
    "待客服主管审核": ("客服主管审核", "intake"),
    "待工程/研发评估": ("指派审批人", ""),
    "待客户排查": ("待客户排查", ""),
}

EVENT_MAP = {
    "created": "created",
    "remark": "remark",
    "supervisor_approve": "intake_approved",
    "selfcheck_review": "intake_approved",
    "supervisor_skip_to_eval": "intake_approved",
}


def map_role(username: str, old_role: str) -> str:
    if username in DEPT_HEAD_CS_USERNAMES:
        return "客服主管"
    return ROLE_MAP.get(old_role, old_role)


def main():
    old = sqlite3.connect("file:" + OLD_DB + "?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    old.text_factory = str
    new = sqlite3.connect(NEW_DB)
    new.row_factory = sqlite3.Row
    new.text_factory = str
    new.execute("PRAGMA foreign_keys = OFF")  # 导入期间暂关，提交后自动恢复

    # ══════════ 1. 清理新库测试数据 ══════════
    test_rows = new.execute(
        "SELECT id, complaint_no FROM complaints ORDER BY id"
    ).fetchall()
    for t in test_rows:
        tid, tno = t["id"], t["complaint_no"]
        print(f"[clean] 删除测试工单 {tno} (id={tid}) 及其关联数据")
        new.execute("DELETE FROM work_order_log WHERE complaint_id = ?", (tid,))
        atts = new.execute(
            "SELECT stored_name FROM attachments WHERE complaint_id = ?", (tid,)
        ).fetchall()
        new.execute("DELETE FROM attachments WHERE complaint_id = ?", (tid,))
        new.execute("DELETE FROM notifications WHERE complaint_no = ?", (tno,))
        new.execute("DELETE FROM complaints WHERE id = ?", (tid,))
        # 物理附件文件
        for a in atts:
            fpath = os.path.join(ROOT, "data", "uploads", tno, a["stored_name"])
            if os.path.exists(fpath):
                os.remove(fpath)
                print(f"[clean] 删除附件文件 {fpath}")
            dirp = os.path.dirname(fpath)
            if os.path.isdir(dirp) and not os.listdir(dirp):
                os.rmdir(dirp)
    # 测试期间的统计行（全部视为测试数据）
    n = new.execute("DELETE FROM user_activity_log").rowcount
    print(f"[clean] 清理测试 user_activity_log {n} 行")
    n = new.execute("DELETE FROM sus_survey").rowcount
    print(f"[clean] 清理测试 sus_survey {n} 行")
    # 保留：users(admin)、system_settings

    # ══════════ 2. 用户迁移 ══════════
    exist_usernames = {r["username"] for r in new.execute("SELECT username FROM users")}
    name_to_id = {r["display_name"]: r["id"] for r in new.execute("SELECT id, display_name FROM users")}
    inserted_users = 0
    for u in old.execute("SELECT * FROM users ORDER BY id"):
        if u["username"] in exist_usernames:
            print(f"[users] 跳过已存在 {u['username']}")
            continue
        new_role = map_role(u["username"], u["role"])
        cur = new.execute(
            """INSERT INTO users (id, username, password_hash, display_name, role, is_active,
                                  created_at, department, is_dept_head, updated_at,
                                  center, position)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                u["id"], u["username"], u["password_hash"], u["display_name"], new_role,
                u["is_active"], u["created_at"], u["department"], u["is_dept_head"],
                u["updated_at"], u["center"],
                u["department"],  # position = 旧部门名
            ),
        )
        name_to_id[u["display_name"]] = cur.lastrowid
        inserted_users += 1
    print(f"[users] 新增 {inserted_users} 个用户（共 {len(exist_usernames) + inserted_users} 个）")

    # ══════════ 3. 工单迁移（保留旧 id） ══════════
    C_COLS = [
        "id", "complaint_no", "customer_name", "equipment_model", "equipment_sn",
        "fault_category", "fault_phenomenon", "reproduction_steps", "priority",
        "priority_confirmed_by", "status", "assigned_to", "root_cause", "solution",
        "resolution_note", "customer_confirmed", "satisfaction", "is_rework",
        "created_by", "created_at", "updated_at", "closed_at", "estimated_hours",
        "planned_start_time", "planned_end_time", "evaluated_by", "handler_name",
        "supervisor_rejection_note", "email_review_status", "email_review_note",
        "email_draft_content", "software_version", "preliminary_category",
        "expected_complete_date", "impact_level", "device_part", "responsible_dept",
        "remarks", "customer_email", "re_edited", "customer_note",
        "collaborating_depts", "customer_self_check", "linked_complaint_ids",
        "review_context", "sub_type", "created_by_user_id",
    ]
    C_SQL = (
        f"INSERT INTO complaints ({', '.join(C_COLS)}) "
        f"VALUES ({', '.join(['?'] * len(C_COLS))})"
    )
    assert len(C_COLS) == 47, f"列数异常: {len(C_COLS)}"
    inserted_complaints = 0
    for c in old.execute("SELECT * FROM complaints ORDER BY id"):
        new_status, sub_type = STATUS_MAP.get(c["status"], (c["status"], ""))
        creator_uid = name_to_id.get(c["created_by"], 0)
        new.execute(
            C_SQL,
            (
                c["id"], c["complaint_no"], c["customer_name"], c["equipment_model"], c["equipment_sn"],
                c["fault_category"], c["fault_phenomenon"], c["reproduction_steps"], c["priority"],
                c["priority_confirmed_by"], new_status, c["assigned_to"], c["root_cause"], c["solution"],
                c["resolution_note"], c["customer_confirmed"], c["satisfaction"], c["is_rework"],
                c["created_by"], c["created_at"], c["updated_at"], c["closed_at"], c["estimated_hours"],
                c["planned_start_time"], c["planned_end_time"], c["evaluated_by"], "",
                c["supervisor_rejection_note"], c["email_review_status"], c["email_review_note"],
                c["email_draft_content"], c["software_version"], c["preliminary_category"],
                c["expected_complete_date"], c["impact_level"], c["device_part"], c["responsible_dept"],
                c["remarks"], c["customer_email"], c["re_edited"], c["customer_note"],
                c["collaborating_depts"], c["customer_self_check"], c["linked_complaint_ids"],
                c["review_context"], sub_type, creator_uid,
            ),
        )
        inserted_complaints += 1
        print(f"[complaints] {c['complaint_no']} : {c['status']} → {new_status} (creator_uid={creator_uid})")
    print(f"[complaints] 共迁移 {inserted_complaints} 客户工程师单")

    # ══════════ 4. 工单日志迁移（保留旧 id，映射事件/状态/角色） ══════════
    inserted_logs = 0
    for lg in old.execute("SELECT * FROM work_order_log ORDER BY id"):
        ev = EVENT_MAP.get(lg["event_type"], lg["event_type"])
        old_st = lg["old_status"] or ""
        new_st = lg["new_status"] or ""
        old_st_m = STATUS_MAP.get(old_st, (old_st, ""))[0] if old_st else ""
        new_st_m = STATUS_MAP.get(new_st, (new_st, ""))[0] if new_st else ""
        # 操作人角色：优先按姓名查迁移后的新角色（如张伟 → 客服主管），否则按旧角色映射
        op_role = ROLE_MAP.get(lg["operator_role"], lg["operator_role"])
        if lg["operator_name"]:
            row = new.execute(
                "SELECT role FROM users WHERE display_name = ?", (lg["operator_name"],)
            ).fetchone()
            if row:
                op_role = row["role"]
        new.execute(
            """INSERT INTO work_order_log (id, complaint_id, event_type, operator_name, operator_role,
                                           operator_dept, old_status, new_status, detail, metadata,
                                           created_at, operator_position)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                lg["id"], lg["complaint_id"], ev, lg["operator_name"], op_role,
                lg["operator_dept"] or "", old_st_m, new_st_m, lg["detail"], "{}",
                lg["created_at"], "",
            ),
        )
        inserted_logs += 1
    print(f"[logs] 共迁移 {inserted_logs} 条工单日志")

    # ══════════ 5. 评估/统计表迁移（结构一致，原样插入） ══════════
    def copy_table(name, cols):
        n = 0
        for r in old.execute(f"SELECT {', '.join(cols)} FROM {name}"):
            new.execute(
                f"INSERT INTO {name} ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
                tuple(r[c] for c in cols),
            )
            n += 1
        print(f"[{name}] 迁移 {n} 行")
        return n

    copy_table("user_feedback", ["id", "username", "role", "complaint_no", "feedback_type",
                                 "ai_accuracy", "ai_time_saved", "ai_adopted", "ai_comment",
                                 "created_at", "fault_category", "equipment_model",
                                 "complaint_status", "responsible_dept", "ai_suggestion"])
    copy_table("ai_adoption_log", ["id", "complaint_no", "ai_function", "ai_suggestion",
                                   "adopted", "username", "created_at", "ai_suggested_value"])
    copy_table("sus_survey", ["id", "username", "role", "center", "department",
                              "q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10",
                              "sus_score", "response_type", "created_at"])
    copy_table("llm_call_log", ["id", "function_name", "model", "latency_ms", "prompt_chars",
                                "status", "error_msg", "created_at", "triggered_by", "complaint_id"])
    # user_activity_log：role 字符串按映射改新角色名（避免评估页出现旧角色分组）
    n = 0
    for r in old.execute("SELECT * FROM user_activity_log"):
        new.execute(
            """INSERT INTO user_activity_log (id, username, role, page_path, action, created_at, metadata)
               VALUES (?,?,?,?,?,?,?)""",
            (r["id"], r["username"], ROLE_MAP.get(r["role"], r["role"]),
             r["page_path"], r["action"], r["created_at"], r["metadata"]),
        )
        n += 1
    print(f"[user_activity_log] 迁移 {n} 行（role 已映射新角色）")

    # ══════════ 6. 按最终状态生成新通知 ══════════
    n_notif = 0
    for c in new.execute(
        "SELECT id, complaint_no, status, created_by, customer_name, fault_category, priority FROM complaints ORDER BY id"
    ):
        if c["status"] == "客服主管审核":
            new.execute(
                """INSERT INTO notifications (complaint_no, title, message, target_role, is_read,
                                              created_at, target_dept, notification_category,
                                              target_user, target_is_dept_head, target_user_id)
                   VALUES (?,?,?,?,0,datetime('now','localtime'),'','action_required','',0,0)""",
                (
                    c["complaint_no"],
                    f"📋 新工单待审核：{c['complaint_no']}",
                    f"客服 {c['created_by']} 录入了新工单 {c['complaint_no']}，"
                    f"客户：{c['customer_name'] or ''}，故障分类：{c['fault_category'] or ''}。"
                    "请前往客诉看板「客服主管审核」列处理。",
                    "客服主管",
                ),
            )
        elif c["status"] == "指派审批人":
            new.execute(
                """INSERT INTO notifications (complaint_no, title, message, target_role, is_read,
                                              created_at, target_dept, notification_category,
                                              target_user, target_is_dept_head, target_user_id)
                   VALUES (?,?,?,?,0,datetime('now','localtime'),'','action_required','',0,0)""",
                (
                    c["complaint_no"],
                    f"📌 待指派审批人：{c['complaint_no']}",
                    f"客诉审核已通过（优先级 {c['priority']}），请办理人为工单指派审批人。",
                    "办理人",
                ),
            )
        else:
            continue
        n_notif += 1
    print(f"[notifications] 生成 {n_notif} 条新通知")

    new.commit()

    # ══════════ 7. 校验 ══════════
    checks = {
        "complaints": (12, new.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]),
        "users": (52, new.execute("SELECT COUNT(*) FROM users").fetchone()[0]),
        "work_order_log": (17, new.execute("SELECT COUNT(*) FROM work_order_log").fetchone()[0]),
        "notifications": (12, new.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]),
        "user_feedback": (1, new.execute("SELECT COUNT(*) FROM user_feedback").fetchone()[0]),
        "ai_adoption_log": (2, new.execute("SELECT COUNT(*) FROM ai_adoption_log").fetchone()[0]),
        "sus_survey": (17, new.execute("SELECT COUNT(*) FROM sus_survey").fetchone()[0]),
        "user_activity_log": (550, new.execute("SELECT COUNT(*) FROM user_activity_log").fetchone()[0]),
        "llm_call_log": (14, new.execute("SELECT COUNT(*) FROM llm_call_log").fetchone()[0]),
    }
    ok = True
    for k, (exp, got) in checks.items():
        status = "OK" if exp == got else "FAIL"
        if exp != got:
            ok = False
        print(f"[verify] {k}: expect {exp}, got {got} [{status}]")
    # 状态分布
    print("[verify] 状态分布:", dict(new.execute("SELECT status, COUNT(*) FROM complaints GROUP BY status").fetchall()))
    # 日志事件无旧英文名残留
    unknown = [r[0] for r in new.execute(
        "SELECT DISTINCT event_type FROM work_order_log WHERE event_type IN "
        "('supervisor_approve','selfcheck_review','supervisor_skip_to_eval')"
    ).fetchall()]
    print("[verify] 旧事件名残留:", unknown if unknown else "无")
    # 状态无旧名残留
    old_status_left = [r[0] for r in new.execute(
        "SELECT DISTINCT status FROM complaints WHERE status NOT IN "
        "('待客服处理','待客户排查','客服主管审核','指派审批人','指派承接人','处理中','已关闭')"
    ).fetchall()]
    print("[verify] 工单旧状态残留:", old_status_left if old_status_left else "无")
    # 唯一性
    dup_no = new.execute(
        "SELECT complaint_no, COUNT(*) c FROM complaints GROUP BY complaint_no HAVING c > 1").fetchall()
    print("[verify] complaint_no 重复:", dup_no if dup_no else "无")
    print("\n迁移" + ("成功 ✅" if ok else "存在问题，请检查 ❌"))

    old.close()
    new.close()


if __name__ == "__main__":
    main()
