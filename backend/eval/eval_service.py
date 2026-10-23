"""0804 系统评估 — 业务逻辑层
调用 database.py 基础 SQL 函数，在 Python 层做聚合 / 百分位 / 分组计算。
"""

import statistics
from collections import defaultdict
from datetime import datetime as dt

from data.database import get_conn, _rows_to_dicts, _build_date_filter, normalize_status
from core.config import STAGE_BLOCKAGE_THRESHOLD_HOURS


# ── 辅助函数 ────────────────────────────────────────────────

def _calc_percentiles(values: list[float]) -> dict:
    """计算 P50 / P95 / P99，values 需已过滤 None 和负数。"""
    if not values:
        return {"p50": 0, "p95": 0, "p99": 0}
    sv = sorted(values)
    n = len(sv)
    p50 = sv[int(n * 0.50)] if n > 1 else sv[0]
    p95 = sv[min(int(n * 0.95), n - 1)] if n > 1 else sv[-1]
    p99 = sv[min(int(n * 0.99), n - 1)] if n > 1 else sv[-1]
    return {"p50": round(p50, 1), "p95": round(p95, 1), "p99": round(p99, 1)}


def _parse_dt(ts: str):
    """安全解析时间字符串，失败返回 None。"""
    try:
        return dt.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


# ═══════════════════════════════════════ 阶段效率 ═══════════════════════════════════════

def get_stage_duration_stats(date_range: str) -> list[dict]:
    """各阶段 avg / P50 / P95 停留时长（小时）。

    从 work_order_log 按 complaint_id 分组，对相邻状态变更做时间差，
    把前一条记录的 new_status 作为「阶段名」，差值作为该阶段的停留时长。
    """
    where_clause, _ = _build_date_filter(date_range, "wol.created_at")
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT wol.complaint_id, wol.new_status, wol.created_at
        FROM work_order_log wol
        JOIN complaints c ON c.id = wol.complaint_id
        WHERE wol.new_status != ''
          AND {where_clause}
        ORDER BY wol.complaint_id, wol.created_at ASC
    """).fetchall()
    conn.close()

    # 按 complaint_id 分组
    grouped: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r["complaint_id"]].append(r)

    stage_durations: dict[str, list[float]] = defaultdict(list)
    for cid, logs in grouped.items():
        for i in range(len(logs) - 1):
            prev_stage = normalize_status(logs[i]["new_status"])
            t1 = _parse_dt(logs[i]["created_at"])
            t2 = _parse_dt(logs[i + 1]["created_at"])
            if t1 and t2:
                hours = (t2 - t1).total_seconds() / 3600.0
                if hours >= 0:
                    stage_durations[prev_stage].append(round(hours, 2))

    result = []
    for stage, vals in sorted(stage_durations.items(), key=lambda x: -len(x[1])):
        p = _calc_percentiles(vals)
        result.append({
            "stage": stage,
            "count": len(vals),
            "avg_hours": round(statistics.mean(vals), 1) if vals else 0,
            "p50_hours": p["p50"],
            "p95_hours": p["p95"],
        })
    return result


def get_stage_blockage_stats(date_range: str) -> list[dict]:
    """各阶段卡顿率（超过阈值小时数的工单占比）。"""
    # 先获取原始阶段停留数据
    where_clause, _ = _build_date_filter(date_range, "wol.created_at")
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT wol.complaint_id, wol.new_status, wol.created_at
        FROM work_order_log wol
        JOIN complaints c ON c.id = wol.complaint_id
        WHERE wol.new_status != ''
          AND {where_clause}
        ORDER BY wol.complaint_id, wol.created_at ASC
    """).fetchall()
    conn.close()

    grouped: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r["complaint_id"]].append(r)

    stage_durations: dict[str, list[float]] = defaultdict(list)
    for cid, logs in grouped.items():
        for i in range(len(logs) - 1):
            prev_stage = normalize_status(logs[i]["new_status"])
            t1 = _parse_dt(logs[i]["created_at"])
            t2 = _parse_dt(logs[i + 1]["created_at"])
            if t1 and t2:
                hours = (t2 - t1).total_seconds() / 3600.0
                if hours >= 0:
                    stage_durations[prev_stage].append(round(hours, 2))

    result = []
    for stage, vals in sorted(stage_durations.items(), key=lambda x: -len(x[1])):
        threshold = STAGE_BLOCKAGE_THRESHOLD_HOURS.get(stage, 72)
        total = len(vals)
        blocked = sum(1 for v in vals if v > threshold)
        result.append({
            "stage": stage,
            "total": total,
            "blocked": blocked,
            "blockage_rate_pct": round(blocked * 100.0 / total, 1) if total > 0 else 0.0,
            "threshold_hours": threshold,
        })
    return result


# ═══════════════════════════════════ 0821 状态停留时长明细 ═══════════════════════════════════

# 明细表阶段列（按新流程 7 状态；已关闭为终态无停留，不设列）
STAGE_DWELL_COLUMNS = ["待客服处理", "待客户排查", "客服主管审核", "指派审批人", "指派承接人", "处理中"]


def _op_mark(lg: dict, at: dt | None) -> dict:
    """0902 从日志行提取操作人标记（operator_name 为空回退「系统」）。"""
    return {
        "name": lg["operator_name"] or "系统",
        "role": lg["operator_role"] or "",
        "position": lg["operator_position"] or "",
        "at": at.strftime("%Y-%m-%d %H:%M") if at else "",
    }


def _close_stage_dwell_segment(stages: dict, stage: str, seg_start: dt, seg_end: dt,
                               enter_op: dict | None, advance_op: dict | None) -> None:
    """关闭一个停留段：不在明细列内（未知状态/已关闭）只结束不计；负数时长丢弃。
    0902 段附带操作人：enter=进入该段的操作人；advance=推进人（结束该段的操作人，进行中末段为 None）。"""
    if stage not in STAGE_DWELL_COLUMNS:
        return
    hours = (seg_end - seg_start).total_seconds() / 3600.0
    if hours < 0:
        return
    threshold = STAGE_BLOCKAGE_THRESHOLD_HOURS.get(stage, 72)
    entry = stages.setdefault(stage, {"threshold_hours": threshold, "segments": []})
    entry["segments"].append({
        "hours": round(hours, 1),
        "blocked": hours > threshold,
        "enter": enter_op,
        "advance": advance_op,
    })


def build_stage_dwell_rows(where_clause: str, params: list | None = None) -> list[dict]:
    """按工单构建各阶段停留时长分段（核心，明细接口与导出共用）。

    连续同状态日志合并为一段；回退重进同一阶段产生多段（不删除旧段）；
    0821 进行中时长计入：最后一段计到当前时间。
    返回按 complaint_no 升序的完整列表（不做分页/搜索/排序）。
    """
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT wol.complaint_id, wol.new_status, wol.created_at,
               wol.operator_name, wol.operator_role, wol.operator_position,
               c.complaint_no, c.customer_name
        FROM work_order_log wol
        JOIN complaints c ON c.id = wol.complaint_id
        WHERE wol.new_status != ''
          AND {where_clause}
        ORDER BY wol.complaint_id, wol.created_at ASC, wol.id ASC
    """, params or []).fetchall()
    conn.close()

    grouped: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r["complaint_id"]].append(r)

    result: list[dict] = []
    for cid, logs in grouped.items():
        stages: dict[str, dict] = {}
        cur_stage: str | None = None
        seg_start: dt | None = None
        cur_enter_op: dict | None = None
        for lg in logs:
            ts = _parse_dt(lg["created_at"])
            if ts is None:
                continue
            stage = lg["new_status"]
            if stage == cur_stage:
                continue  # 连续同状态日志合并
            if cur_stage is not None and seg_start is not None:
                _close_stage_dwell_segment(stages, cur_stage, seg_start, ts, cur_enter_op, _op_mark(lg, ts))
            cur_stage, seg_start = stage, ts
            cur_enter_op = _op_mark(lg, ts)
        # 进行中时长：最后一段计到当前时间（推进人未知记 None）
        if cur_stage is not None and seg_start is not None:
            _close_stage_dwell_segment(stages, cur_stage, seg_start, dt.now(), cur_enter_op, None)

        if not stages:
            continue  # 无任何有效段（如仅终态日志）丢弃
        result.append({
            "complaint_no": logs[0]["complaint_no"],
            "customer_name": logs[0]["customer_name"] or "",
            "stages": stages,
        })

    result.sort(key=lambda r: r["complaint_no"])
    return result


def get_stage_dwell_details(date_range: str, page: int, limit: int, keyword: str, sort: str,
                            operator: str = "") -> dict:
    """0821 工单状态停留时长明细（分页 + 搜索 + 排序，内存处理）。
    0902 支持按推进人筛选、按指定阶段总时长排序；返回 operators 供前端筛选下拉。"""
    where_clause, _ = _build_date_filter(date_range, "wol.created_at")
    rows = build_stage_dwell_rows(where_clause, [])
    if keyword:
        kw = keyword.lower()
        rows = [r for r in rows if kw in r["complaint_no"].lower() or kw in r["customer_name"].lower()]
    if operator:
        rows = [r for r in rows if any(
            seg["advance"] and seg["advance"]["name"] == operator
            for st in r["stages"].values() for seg in st["segments"]
        )]
    if sort == "complaint_no_desc":
        rows.sort(key=lambda r: r["complaint_no"], reverse=True)
    elif sort == "process_duration_desc":
        # 按处理中总时长降序（未进入处理中的工单按 0 计），工单号升序决胜
        rows.sort(key=lambda r: (-sum(s["hours"] for s in r["stages"].get("处理中", {}).get("segments", [])), r["complaint_no"]))
    elif sort.startswith("stage:") and sort.endswith("_desc"):
        # 0902 按指定阶段总时长降序（如 stage:处理中_desc），工单号升序决胜
        col = sort[6:-5]
        rows.sort(key=lambda r: (-sum(s["hours"] for s in r["stages"].get(col, {}).get("segments", [])), r["complaint_no"]))
    else:  # complaint_no_asc 默认
        rows.sort(key=lambda r: r["complaint_no"])
    # 0902 推进人筛选项（全量去重排序，排除「系统」）
    operators = sorted({seg["advance"]["name"]
                        for r in rows for st in r["stages"].values()
                        for seg in st["segments"]
                        if seg["advance"] and seg["advance"]["name"] != "系统"})
    total = len(rows)
    start = (page - 1) * limit
    thresholds = {stage: STAGE_BLOCKAGE_THRESHOLD_HOURS.get(stage, 72) for stage in STAGE_DWELL_COLUMNS}
    return {
        "items": rows[start:start + limit],
        "thresholds": thresholds,
        "operators": operators,
        "pagination": {"page": page, "limit": limit, "total": total},
    }


def get_operator_blockage_stats(date_range: str, stage: str = "") -> dict:
    """0902 按人统计（推进人口径）：每人处理段总数 / 卡顿段数 / 卡顿率 / 平均阶段停留时长。

    复用 build_stage_dwell_rows 的段数据，按段的 advance（推进人）聚合；
    进行中段（advance=None）与「系统」日志不计入。stage 为空统计全部阶段。
    """
    where_clause, _ = _build_date_filter(date_range, "wol.created_at")
    rows = build_stage_dwell_rows(where_clause, [])
    agg: dict[str, dict] = {}
    for r in rows:
        for st_name, st in r["stages"].items():
            if stage and st_name != stage:
                continue
            for seg in st["segments"]:
                op = seg.get("advance")
                if not op or not op.get("name") or op["name"] == "系统":
                    continue
                e = agg.setdefault(op["name"], {"role": op["role"], "position": op["position"],
                                                "total": 0, "blocked": 0, "hours_sum": 0.0})
                e["total"] += 1
                e["blocked"] += 1 if seg["blocked"] else 0
                e["hours_sum"] += seg["hours"]
    items = [{
        "operator": k,
        "role": v["role"],
        "position": v["position"],
        "total_segments": v["total"],
        "blocked_segments": v["blocked"],
        "blockage_rate_pct": round(v["blocked"] * 100.0 / v["total"], 1) if v["total"] else 0.0,
        "avg_dwell_hours": round(v["hours_sum"] / v["total"], 1) if v["total"] else 0.0,
    } for k, v in agg.items()]
    items.sort(key=lambda x: (-x["blocked_segments"], -x["total_segments"], x["operator"]))
    thresholds = {s: STAGE_BLOCKAGE_THRESHOLD_HOURS.get(s, 72) for s in STAGE_DWELL_COLUMNS}
    return {"items": items, "thresholds": thresholds}


# ═══════════════════════════════════════ AI 效能 ═══════════════════════════════════════

def get_llm_health_stats(date_range: str) -> list[dict]:
    """各 AI 功能调用量 / 成功率 / 延迟分布（P50/P95/P99）。"""
    where_clause, _ = _build_date_filter(date_range, "created_at")

    conn = get_conn()
    # 聚合统计
    agg_rows = conn.execute(f"""
        SELECT function_name,
               COUNT(*) AS total_calls,
               SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
               ROUND(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS success_rate_pct,
               ROUND(AVG(CASE WHEN status = 'success' THEN latency_ms END), 0) AS avg_latency_ms
        FROM llm_call_log
        WHERE {where_clause}
        GROUP BY function_name
        ORDER BY total_calls DESC
    """).fetchall()

    # 每个 function 的原始 latency（用于百分位）
    latency_rows = conn.execute(f"""
        SELECT function_name, latency_ms
        FROM llm_call_log
        WHERE status = 'success' AND {where_clause}
        ORDER BY function_name, latency_ms
    """).fetchall()
    conn.close()

    latency_by_fn: dict[str, list[float]] = defaultdict(list)
    for r in latency_rows:
        latency_by_fn[r["function_name"]].append(float(r["latency_ms"]))

    result = []
    for row in agg_rows:
        fn = row["function_name"]
        latencies = latency_by_fn.get(fn, [])
        p = _calc_percentiles(latencies)
        result.append({
            "function_name": fn,
            "total_calls": row["total_calls"],
            "success_count": row["success_count"],
            "success_rate_pct": row["success_rate_pct"],
            "avg_latency_ms": row["avg_latency_ms"] or 0,
            "p50_latency_ms": p["p50"],
            "p95_latency_ms": p["p95"],
            "p99_latency_ms": p["p99"],
        })
    return result


# ═══════════════════════════════════════ 效率对比 ═══════════════════════════════════════

def get_efficiency_compare(date_range: str, dimension: str) -> list[dict]:
    """按维度（priority / fault_category / 承接人）对比各阶段耗时。

    返回：每个维度值下各阶段的 avg_hours。
    """
    where_clause, _ = _build_date_filter(date_range, "wol.created_at")

    dim_col = {
        "priority": "c.priority",
        "category": "c.fault_category",
        # 0819 按有效指派人员（承接人/审批人）聚合显示名
        "engineer": (
            "COALESCE((SELECT STRING_AGG(u.display_name, '、') "
            "FROM complaint_assignees ca JOIN users u ON u.id = ca.user_id "
            "WHERE ca.complaint_id = c.id AND ca.is_active = 1), '未指派')"
        ),
    }.get(dimension, "c.priority")

    conn = get_conn()
    rows = conn.execute(f"""
        SELECT wol.complaint_id, wol.new_status, wol.created_at,
               {dim_col} AS dim_value
        FROM work_order_log wol
        JOIN complaints c ON c.id = wol.complaint_id
        WHERE wol.new_status != ''
          AND {where_clause}
        ORDER BY wol.complaint_id, wol.created_at ASC
    """).fetchall()
    conn.close()

    # 按 complaint_id 分组
    grouped: dict[int, tuple[str, list[dict]]] = {}  # cid -> (dim_value, [logs])
    for r in rows:
        cid = r["complaint_id"]
        dv = r["dim_value"] or "未知"
        if cid not in grouped:
            grouped[cid] = (dv, [])
        grouped[cid][1].append(r)

    # 聚合: dim_value → stage → [hours]
    agg: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for cid, (dv, logs) in grouped.items():
        for i in range(len(logs) - 1):
            prev_stage = normalize_status(logs[i]["new_status"])
            t1 = _parse_dt(logs[i]["created_at"])
            t2 = _parse_dt(logs[i + 1]["created_at"])
            if t1 and t2:
                hours = (t2 - t1).total_seconds() / 3600.0
                if hours >= 0:
                    agg[dv][prev_stage].append(round(hours, 2))

    result = []
    for dv in sorted(agg.keys()):
        stages_data = []
        for stage, vals in sorted(agg[dv].items()):
            stages_data.append({
                "stage": stage,
                "avg_hours": round(statistics.mean(vals), 1) if vals else 0,
                "count": len(vals),
            })
        result.append({
            "dimension_value": dv,
            "stages": stages_data,
        })
    return result


# ═══════════════════════════════════════ 业务质量 ═══════════════════════════════════════

def get_business_quality_stats(date_range: str) -> dict:
    """返工率按分类 / 满意度分布 / 拒收率按分类 / 一次解决率。"""
    where_clause, _ = _build_date_filter(date_range)
    # 0820 JOIN work_order_log 的查询需带 c. 前缀，避免 created_at 歧义
    where_clause_c, _ = _build_date_filter(date_range, "c.created_at")

    conn = get_conn()

    # 返工率按分类
    rework_rows = conn.execute(f"""
        SELECT fault_category,
               COUNT(*) AS total,
               ROUND(SUM(is_rework) * 100.0 / NULLIF(COUNT(*), 0), 1) AS rework_rate_pct,
               SUM(is_rework) AS rework_count
        FROM complaints
        WHERE fault_category != '' AND {where_clause}
        GROUP BY fault_category
        ORDER BY rework_rate_pct DESC
    """).fetchall()

    # 满意度分布（仅已关闭工单）
    sat_rows = conn.execute(f"""
        SELECT satisfaction,
               COUNT(*) AS cnt
        FROM complaints
        WHERE status = '已关闭' AND satisfaction > 0 AND {where_clause}
        GROUP BY satisfaction
        ORDER BY satisfaction
    """).fetchall()

    # 0819 回退率按分类：基于 work_order_log 的 approver_rejected / cannot_handle 事件
    rejection_rows = conn.execute(f"""
        SELECT c.fault_category,
               COUNT(DISTINCT c.id) AS total,
               ROUND(COUNT(DISTINCT CASE WHEN wl.event_type IN ('approver_rejected', 'cannot_handle')
                    THEN c.id END) * 100.0 / NULLIF(COUNT(DISTINCT c.id), 0), 1) AS rejection_rate_pct,
               COUNT(DISTINCT CASE WHEN wl.event_type IN ('approver_rejected', 'cannot_handle')
                    THEN c.id END) AS rejection_count
        FROM complaints c
        LEFT JOIN work_order_log wl ON wl.complaint_id = c.id
             AND wl.event_type IN ('approver_rejected', 'cannot_handle')
        WHERE c.fault_category != '' AND {where_clause_c}
        GROUP BY c.fault_category
        ORDER BY rejection_rate_pct DESC
    """).fetchall()

    # 总体指标（0819 回退率按事件统计）
    overall = conn.execute(f"""
        SELECT
            ROUND(AVG(CASE WHEN satisfaction > 0 THEN satisfaction END), 2) AS avg_satisfaction,
            ROUND(SUM(is_rework) * 100.0 / NULLIF(COUNT(*), 0), 1) AS overall_rework_rate,
            ROUND(COUNT(DISTINCT CASE WHEN wl.event_type IN ('approver_rejected', 'cannot_handle')
                 THEN c.id END) * 100.0 / NULLIF(COUNT(DISTINCT c.id), 0), 1) AS overall_rejection_rate
        FROM complaints c
        LEFT JOIN work_order_log wl ON wl.complaint_id = c.id
             AND wl.event_type IN ('approver_rejected', 'cannot_handle')
        WHERE {where_clause_c}
    """).fetchone()
    conn.close()

    return {
        "rework_by_category": _rows_to_dicts(rework_rows),
        "satisfaction_dist": _rows_to_dicts(sat_rows),
        "rejection_by_category": _rows_to_dicts(rejection_rows),
        "avg_satisfaction": overall["avg_satisfaction"] or 0 if overall else 0,
        "overall_rework_rate": overall["overall_rework_rate"] or 0 if overall else 0,
        "overall_rejection_rate": overall["overall_rejection_rate"] or 0 if overall else 0,
        "first_time_fix_rate": round(100 - (overall["overall_rework_rate"] or 0), 1) if overall else 100.0,
    }


# ═══════════════════════════════════════ AI 邮件草稿使用率 ═══════════════════════════════════════

def get_email_draft_usage_stats(date_range: str) -> dict:
    """AI 邮件草稿使用率：统计有草稿的工单比例 + AI 生成草稿调用量。"""
    where_clause, _ = _build_date_filter(date_range)

    conn = get_conn()

    # 工单侧：有 email_draft_content 的工单数
    draft_row = conn.execute(f"""
        SELECT
            COUNT(*) AS total_tickets,
            COUNT(CASE WHEN email_draft_content IS NOT NULL AND email_draft_content != ''
                  AND email_draft_content != '""' THEN 1 END) AS draft_tickets
        FROM complaints
        WHERE status IN ('已关闭', '待客服处理', '处理中') AND {where_clause}
    """).fetchone()

    # LLM 侧：generate_email_draft 调用次数
    llm_row = conn.execute(f"""
        SELECT
            COUNT(*) AS total_calls,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_calls
        FROM llm_call_log
        WHERE function_name = 'generate_email_draft' AND {where_clause}
    """).fetchone()
    conn.close()

    total_tickets = draft_row["total_tickets"] if draft_row else 0
    draft_tickets = draft_row["draft_tickets"] if draft_row else 0
    total_llm = llm_row["total_calls"] if llm_row else 0
    success_llm = llm_row["success_calls"] if llm_row else 0

    return {
        "total_tickets": total_tickets,
        "draft_tickets": draft_tickets,
        "draft_usage_rate_pct": round(draft_tickets * 100.0 / total_tickets, 1) if total_tickets > 0 else 0.0,
        "llm_draft_calls": total_llm,
        "llm_draft_success": success_llm,
        "llm_draft_success_rate_pct": round(success_llm * 100.0 / total_llm, 1) if total_llm > 0 else 0.0,
    }
