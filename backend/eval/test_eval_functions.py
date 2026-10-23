"""0804 系统评估 — 开发者自测脚本
在 if __name__ == "__main__" 中执行，负责：
1. 初始化 DB + 插入模拟工单数据
2. 调用 eval_service.py 各函数并打印结果
3. SUS 问卷写入 → 冷却检查 → 统计
4. 默认清理模拟数据（--keep-data 保留）

运行方式：
    cd backend
    python -m eval.test_eval_functions
    python -m eval.test_eval_functions --keep-data

注意：使用 ASCII 字符避免 Windows GBK 编码问题。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Fix Windows console encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

KEEP_DATA = "--keep-data" in sys.argv


def main():
    from data.database import (
        init_db, get_conn,
        submit_sus_survey, check_sus_survey_cooldown, get_sus_survey_stats,
    )
    from eval.eval_service import (
        get_stage_duration_stats,
        get_stage_blockage_stats,
        get_llm_health_stats,
        get_efficiency_compare,
        get_business_quality_stats,
    )

    print("=" * 60)
    print(" 系统评估 — 开发者自测")
    print("=" * 60)

    # ── 1. 初始化 DB ────────────────────────────────────
    print("\n[1/6] 初始化数据库...")
    init_db()
    print("  ✓ init_db() 完成")

    # ── 2. 插入模拟工单 + 日志 ──────────────────────────
    print("\n[2/6] 插入模拟工单数据...")
    conn = get_conn()
    now_ts = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 插入测试工单
    test_cids = []
    for i in range(3):
        cid = conn.execute(
            """INSERT INTO complaints (complaint_no, customer_name, equipment_model,
               fault_category, fault_phenomenon, priority, status, created_by, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                f"TEST-EVAL-{i + 1:03d}",
                f"测试客户{i + 1}",
                f"EQ-800",
                ["机械", "电气", "软件"][i],
                f"测试故障现象{i + 1}",
                ["A", "B", "C"][i],
                "已关闭",
                "测试脚本",
                now_ts,
            ),
        ).fetchone()["id"]
        test_cids.append(cid)

    # 为每客户工程师单插入完整生命周期日志
    from datetime import datetime as dt, timedelta

    base_time = dt.now() - timedelta(days=30)

    for cid in test_cids:
        stages = [
            ("", "待客服主管审核", "created", 0),
            ("待客服主管审核", "待客户排查", "supervisor_approved", 3),
            ("待客户排查", "待工程/研发评估", "advance_to_eval", 24),
            ("待工程/研发评估", "待确认优先级", "evaluate_accept", 6),
            ("待确认优先级", "待指派工程师", "priority_confirmed", 3),
            ("待指派工程师", "处理中", "assigned", 2),
            ("处理中", "待客户确认", "resolved", 48),
            ("待客户确认", "已关闭", "closed", 8),
        ]
        for old_s, new_s, evt, offset_hours in stages:
            ts = (base_time + timedelta(hours=offset_hours)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """INSERT INTO work_order_log (complaint_id, event_type, operator_name,
                   operator_role, operator_dept, old_status, new_status, detail, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (cid, evt, "测试员", "管理员", "系统管理", old_s, new_s, f"测试日志 - {evt}", ts),
            )
        base_time = base_time + timedelta(days=2)  # 交错时间

    conn.commit()
    conn.close()
    print(f"  ✓ 插入 {len(test_cids)} 条测试工单 + 生命周期日志完成")

    # ── 3. 测试 eval_service 函数 ───────────────────────
    print("\n[3/6] 测试评估函数...")

    print("\n  --- get_stage_duration_stats('全部') ---")
    dur = get_stage_duration_stats("全部")
    for d in dur:
        print(f"    {d['stage']}: avg={d['avg_hours']}h, p50={d['p50_hours']}h, "
              f"p95={d['p95_hours']}h, n={d['count']}")
    assert dur, "FAIL: 阶段耗时应返回数据"
    print("  ✓ 阶段耗时统计 OK")

    print("\n  --- get_stage_blockage_stats('全部') ---")
    blk = get_stage_blockage_stats("全部")
    for b in blk:
        print(f"    {b['stage']}: {b['blocked']}/{b['total']} 卡顿 ({b['blockage_rate_pct']}%), "
              f"阈值={b['threshold_hours']}h")
    assert blk, "FAIL: 卡顿率应返回数据"
    for b in blk:
        assert 0 <= b["blockage_rate_pct"] <= 100, f"FAIL: 卡顿率超出范围: {b['blockage_rate_pct']}"
    print("  ✓ 阶段卡顿率 OK")

    print("\n  --- get_llm_health_stats('全部') ---")
    lh = get_llm_health_stats("全部")
    if lh:
        for item in lh:
            print(f"    {item['function_name']}: {item['total_calls']} calls, "
                  f"成功率={item['success_rate_pct']}%, p50={item['p50_latency_ms']}ms")
    else:
        print("    (无 LLM 调用日志数据)")
    print("  ✓ AI 健康统计 OK")

    print("\n  --- get_efficiency_compare('全部', 'priority') ---")
    ec = get_efficiency_compare("全部", "priority")
    for d in ec:
        stages_str = ", ".join(f"{s['stage']}={s['avg_hours']}h" for s in d["stages"])
        print(f"    {d['dimension_value']}: {stages_str}")
    assert ec, "FAIL: 效率对比应返回数据"
    print("  ✓ 效率对比 OK")

    print("\n  --- get_business_quality_stats('全部') ---")
    bq = get_business_quality_stats("全部")
    print(f"    返工率={bq.get('overall_rework_rate')}%, "
          f"平均满意度={bq.get('avg_satisfaction')}, "
          f"一次解决率={bq.get('first_time_fix_rate')}%")
    print(f"    返工按分类: {len(bq.get('rework_by_category', []))} 项")
    print(f"    满意度分布: {len(bq.get('satisfaction_dist', []))} 项")
    print(f"    拒收按分类: {len(bq.get('rejection_by_category', []))} 项")
    print("  ✓ 业务质量 OK")

    # ── 4. 测试 SUS 问卷 ────────────────────────────────
    print("\n[4/6] 测试 SUS 问卷...")

    sid = submit_sus_survey(
        username="test_eval_user",
        role="管理员",
        answers=[4, 2, 5, 1, 4, 2, 5, 1, 4, 2],
        score=72.5,
        center="管理员",
        department="系统管理",
    )
    print(f"  ✓ 提交 SUS 问卷: id={sid}")

    in_cooldown = check_sus_survey_cooldown("test_eval_user", 90)
    assert in_cooldown, "FAIL: 刚提交后应在冷却期内"
    print("  ✓ 冷却检查: 已在冷却期")

    not_in_cooldown = check_sus_survey_cooldown("nonexistent_user", 90)
    assert not not_in_cooldown, "FAIL: 不存在的用户不应在冷却期"
    print("  ✓ 冷却检查: 不存在用户不在冷却期")

    stats = get_sus_survey_stats()
    assert stats["total_responses"] >= 1, "FAIL: SUS 统计应有至少 1 条"
    print(f"  ✓ SUS 统计: total={stats['total_responses']}, avg_score={stats['avg_score']}")
    print(f"    分布: {stats['score_distribution']}")
    print(f"    按角色: {stats['by_role']}")

    # ── 5. 清理 ─────────────────────────────────────────
    if KEEP_DATA:
        print("\n[5/6] --keep-data 模式：保留模拟数据")
    else:
        print("\n[5/6] 清理模拟数据...")
        conn = get_conn()
        for cid in test_cids:
            conn.execute("DELETE FROM work_order_log WHERE complaint_id = %s", (cid,))
            conn.execute("DELETE FROM complaints WHERE id = %s", (cid,))
        conn.execute("DELETE FROM sus_survey WHERE username = 'test_eval_user'")
        conn.commit()
        conn.close()
        print("  ✓ 模拟数据已清理")

    # ── 6. 总结 ─────────────────────────────────────────
    print("\n[6/6] " + "=" * 50)
    print(" ✅ 所有测试通过！")
    print("=" * 50)


if __name__ == "__main__":
    main()
