# 0804 系统评估 API — 阶段效率 + AI 效能 + 业务质量 + SUS 问卷
"""系统评估 REST API 端点。
提供系统管理员专用的评估数据看板，全部基于现有数据库表做 SQL 聚合。
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from eval.eval_service import (
    get_stage_duration_stats,
    get_stage_blockage_stats,
    get_stage_dwell_details,
    get_operator_blockage_stats,
    get_llm_health_stats,
    get_efficiency_compare,
    get_business_quality_stats,
    STAGE_DWELL_COLUMNS,
)
from data.database import (
    submit_sus_survey,
    check_sus_survey_cooldown,
    dismiss_sus_survey,
    get_sus_survey_stats,
    get_notification_reach_stats,
    get_dingtalk_push_stats,
    get_ai_adoption_impact_stats,
    get_kb_reach_funnel_stats,
    get_activity_stats as get_activity_stats_dao,
)
from core.config import SUS_SURVEY_COOLDOWN_DAYS
from middleware.auth import get_current_user
from schemas.auth import UserInfo
from schemas.common import ApiResponse

router = APIRouter()

VALID_DATE_RANGES = {"本月", "上月", "近3个月", "近6个月", "全部"}


def _require_admin(user: UserInfo):
    """仅管理员可访问系统评估。"""
    if user.role != "管理员":
        raise HTTPException(status_code=403, detail="仅管理员可访问系统评估")


def _validate_date_range(date_range: str) -> str:
    if date_range not in VALID_DATE_RANGES:
        raise HTTPException(
            status_code=400,
            detail=f"无效日期范围：{date_range}，有效值：{', '.join(sorted(VALID_DATE_RANGES))}",
        )
    return date_range


# ── GET /api/eval/stage-duration — 阶段耗时统计 ──────────

@router.get("/stage-duration")
async def stage_duration(
    date_range: str = Query(default="近3个月", description="日期范围：本月/上月/近3个月/近6个月/全部"),
    current_user: UserInfo = Depends(get_current_user),
):
    """各阶段 avg / P50 / P95 停留时长（小时）。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    data = get_stage_duration_stats(date_range)
    return ApiResponse(success=True, data=data, message="获取阶段耗时统计完成")


# ── GET /api/eval/stage-blockage — 阶段卡顿率 ────────────

@router.get("/stage-blockage")
async def stage_blockage(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """各阶段卡顿率（超过阈值小时数的工单占比）。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    data = get_stage_blockage_stats(date_range)
    return ApiResponse(success=True, data=data, message="获取阶段卡顿率完成")


# ── GET /api/eval/stage-dwell-details — 工单状态停留时长明细 ──

@router.get("/stage-dwell-details")
async def stage_dwell_details(
    date_range: str = Query(default="近3个月", description="日期范围"),
    page: int = Query(default=1, ge=1, description="页码"),
    limit: int = Query(default=15, ge=1, le=500, description="每页条数"),
    keyword: str = Query(default="", description="搜索工单号 / 客户名"),
    operator: str = Query(default="", description="按推进人筛选（空=全部）"),
    sort: str = Query(default="complaint_no_asc", description="排序：complaint_no_asc / complaint_no_desc / process_duration_desc / stage:<阶段>_desc"),
    current_user: UserInfo = Depends(get_current_user),
):
    """0821 工单各阶段停留时长明细（分页，仅管理员）。
    0902 每段附带进入/推进操作人，支持按推进人筛选与按指定阶段时长排序。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    sort_valid = sort in ("complaint_no_asc", "complaint_no_desc", "process_duration_desc") or (
        sort.startswith("stage:") and sort.endswith("_desc") and sort[6:-5] in STAGE_DWELL_COLUMNS
    )
    if not sort_valid:
        raise HTTPException(
            status_code=400,
            detail=f"无效排序：{sort}，有效值：complaint_no_asc, complaint_no_desc, process_duration_desc, stage:<阶段>_desc",
        )
    data = get_stage_dwell_details(date_range, page, limit, keyword.strip(), sort, operator.strip())
    return ApiResponse(success=True, data=data, message="获取停留时长明细完成")


# ── GET /api/eval/operator-blockage — 按人卡顿统计 ──────

@router.get("/operator-blockage")
async def operator_blockage(
    date_range: str = Query(default="近3个月", description="日期范围"),
    stage: str = Query(default="", description="阶段筛选：空=全部阶段"),
    current_user: UserInfo = Depends(get_current_user),
):
    """0902 按人统计：每人卡顿率 / 卡顿段数 / 平均停留 / 处理段总数（仅管理员，推进人口径）。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    if stage and stage not in STAGE_DWELL_COLUMNS:
        raise HTTPException(status_code=400, detail=f"无效阶段：{stage}，有效值：{', '.join(STAGE_DWELL_COLUMNS)}")
    data = get_operator_blockage_stats(date_range, stage)
    return ApiResponse(success=True, data=data, message="获取按人卡顿统计完成")


# ── GET /api/eval/llm-health — AI 调用健康 ───────────────

@router.get("/llm-health")
async def llm_health(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """AI 各功能调用量 / 成功率 / 延迟分布。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    data = get_llm_health_stats(date_range)
    return ApiResponse(success=True, data=data, message="获取 AI 健康统计完成")


# ── GET /api/eval/efficiency-compare — 效率对比 ──────────

@router.get("/efficiency-compare")
async def efficiency_compare(
    date_range: str = Query(default="近3个月", description="日期范围"),
    dimension: str = Query(default="priority", description="对比维度：priority/category/engineer"),
    current_user: UserInfo = Depends(get_current_user),
):
    """按维度对比各阶段耗时。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    if dimension not in ("priority", "category", "engineer"):
        raise HTTPException(
            status_code=400,
            detail=f"无效维度：{dimension}，有效值：priority, category, engineer",
        )
    data = get_efficiency_compare(date_range, dimension)
    return ApiResponse(success=True, data=data, message="获取效率对比完成")


# ── GET /api/eval/business-quality — 业务质量 ────────────

@router.get("/business-quality")
async def business_quality(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """返工率按分类 / 满意度分布 / 拒收率按分类 / 一次解决率。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    data = get_business_quality_stats(date_range)
    return ApiResponse(success=True, data=data, message="获取业务质量统计完成")


# ── POST /api/eval/sus-survey — 提交 SUS 问卷 ────────────

@router.post("/sus-survey")
async def post_sus_survey(
    body: dict,
    current_user: UserInfo = Depends(get_current_user),
):
    """提交 SUS 系统可用性问卷（10 题 1-5 分）。

    请求体：{"q1":4,"q2":2,...,"q10":2}
    SUS 计分公式：(奇数题得分-1 + (5-偶数题得分)) × 2.5
    """
    # 冷却检查
    if check_sus_survey_cooldown(current_user.username, SUS_SURVEY_COOLDOWN_DAYS):
        raise HTTPException(
            status_code=429,
            detail=f"您已在 {SUS_SURVEY_COOLDOWN_DAYS} 天冷却期内，请勿重复提交",
        )

    # 参数验证
    answers = []
    for i in range(1, 11):
        v = body.get(f"q{i}")
        if v is None or not isinstance(v, int) or v < 1 or v > 5:
            raise HTTPException(status_code=400, detail="每题需填写 1-5 分")
        answers.append(v)

    # SUS 计分：奇数题(1,3,5,7,9) 为正向 → score_i - 1；偶数题(2,4,6,8,10) 为反向 → 5 - score_i
    raw_score = 0
    for i in range(10):
        if i % 2 == 0:  # 奇数题（0-indexed → 正问题）
            raw_score += answers[i] - 1
        else:  # 偶数题（0-indexed → 反向题）
            raw_score += 5 - answers[i]
    sus_score = round(raw_score * 2.5, 1)

    # 0923 补充题（可选，不计分）：常用功能多选（白名单校验，防任意文本入库）+ 改进建议（≤500字）
    SUS_MODULE_WHITELIST = {
        "客诉录入", "审核派单", "工单处理", "案例检索与AI方案",
        "知识库", "统计看板", "系统评估",
    }
    raw_modules = body.get("use_modules") or []
    if not isinstance(raw_modules, list):
        raise HTTPException(status_code=400, detail="use_modules 需为数组")
    use_modules = ",".join(
        m for m in raw_modules if isinstance(m, str) and m in SUS_MODULE_WHITELIST
    )
    improvement = str(body.get("improvement") or "").strip()[:500]

    sid = submit_sus_survey(
        username=current_user.username,
        role=current_user.role,
        answers=answers,
        score=sus_score,
        center="",
        department="",
        use_modules=use_modules,
        improvement=improvement,
    )

    return ApiResponse(
        success=True,
        data={"id": sid, "score": sus_score},
        message=f"问卷提交成功，SUS 得分：{sus_score}",
    )


# ── GET /api/eval/sus-survey/check — 检查冷却 ────────────

@router.get("/sus-survey/check")
async def sus_check(current_user: UserInfo = Depends(get_current_user)):
    """检查当前用户是否可提交 SUS 问卷。"""
    in_cooldown = check_sus_survey_cooldown(current_user.username, SUS_SURVEY_COOLDOWN_DAYS)
    return ApiResponse(
        success=True,
        data={"can_submit": not in_cooldown, "cooldown_days": SUS_SURVEY_COOLDOWN_DAYS},
        message="检查完成",
    )


# ── POST /api/eval/sus-survey/dismiss — 关闭/跳过问卷冷却记录 ────────────

@router.post("/sus-survey/dismiss")
async def sus_dismiss(current_user: UserInfo = Depends(get_current_user)):
    """记录用户关闭/跳过问卷，触发冷却期。"""
    in_cooldown = check_sus_survey_cooldown(current_user.username, SUS_SURVEY_COOLDOWN_DAYS)
    if in_cooldown:
        return ApiResponse(success=True, data={"can_submit": False}, message="已在冷却期内")
    dismiss_sus_survey(
        current_user.username, current_user.role,
        "", "",
    )
    return ApiResponse(success=True, data={"can_submit": False}, message="已记录关闭")


# ── GET /api/eval/sus-survey/stats — SUS 统计 ────────────

@router.get("/sus-survey/stats")
async def sus_stats(current_user: UserInfo = Depends(get_current_user)):
    """查看 SUS 问卷统计（仅管理员）。"""
    _require_admin(current_user)
    data = get_sus_survey_stats()
    return ApiResponse(success=True, data=data, message="获取 SUS 统计完成")


# ═══════════════════════════════════════ 0804 Phase 2: AI 采纳率 + 活跃度 ═══════════════════════════════════════

@router.post("/ai-adoption")
async def record_ai_adoption(
    body: dict,
    current_user: UserInfo = Depends(get_current_user),
):
    """记录 AI 建议采纳结果。
    请求体：{"complaint_no": "KS-...", "ai_function": "classify", "ai_suggestion": "{...}", "adopted": true, "ai_suggested_value": 8.5}
    ai_suggested_value 可选，AI 建议的具体数值（如排期工时）。
    """
    from data.database import record_ai_adoption as _record
    complaint_no = body.get("complaint_no", "")
    ai_function = body.get("ai_function", "")
    ai_suggestion = str(body.get("ai_suggestion", ""))
    adopted = bool(body.get("adopted", False))
    ai_suggested_value = body.get("ai_suggested_value")

    if not complaint_no or not ai_function:
        raise HTTPException(status_code=400, detail="complaint_no 和 ai_function 为必填项")

    _record(complaint_no, ai_function, ai_suggestion, adopted, current_user.username, ai_suggested_value)
    return ApiResponse(success=True, data=None, message="AI 采纳记录已保存")


@router.get("/ai-adoption")
async def get_ai_adoption_stats(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """AI 各功能采纳率统计（仅管理员）。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    from data.database import get_ai_adoption_stats
    data = get_ai_adoption_stats(date_range)
    return ApiResponse(success=True, data=data, message="获取 AI 采纳率完成")


@router.post("/activity")
async def record_activity(
    body: dict,
    current_user: UserInfo = Depends(get_current_user),
):
    """记录用户活跃度。
    请求体：{"page_path": "/kanban", "action": "page_view", "metadata": {}}
    metadata 为可选 JSON 扩展数据（如操作计时 {"action_name":"...", "duration_ms":123}）。
    """
    from data.database import record_user_activity as _record
    import json
    page_path = body.get("page_path", "")
    action = body.get("action", "page_view")
    metadata = body.get("metadata", {})
    metadata_str = json.dumps(metadata, ensure_ascii=False) if metadata else "{}"
    _record(current_user.username, current_user.role, page_path, action, metadata_str)
    return ApiResponse(success=True, data=None, message="活跃度已记录")


@router.get("/activity-stats")
async def get_activity_stats(
    limit: int = Query(default=10, ge=1, le=500, description="个人活跃度返回条数（查看全部时传大值）"),
    current_user: UserInfo = Depends(get_current_user),
):
    """用户活跃度统计（仅管理员）。"""
    _require_admin(current_user)
    data = get_activity_stats_dao(limit)
    return ApiResponse(success=True, data=data, message="获取活跃度统计完成")


# ── GET /api/eval/email-draft-usage — AI 邮件草稿使用率 ──

@router.get("/email-draft-usage")
async def email_draft_usage(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """AI 邮件草稿使用率统计（仅管理员）。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    from eval.eval_service import get_email_draft_usage_stats
    data = get_email_draft_usage_stats(date_range)
    return ApiResponse(success=True, data=data, message="获取邮件草稿使用率完成")


# ═══════════════════════════════════════ 0805 Phase 3: 操作计时 + 阶段评价 + 排期准确度 ═══════════════════════════════════════

@router.get("/timing-stats")
async def timing_stats(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """关键操作耗时统计：录入表单 / 指派操作 / 工单处理的 avg/P50/P95 耗时（秒）。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    from data.database import get_timing_stats
    data = get_timing_stats(date_range)
    return ApiResponse(success=True, data=data, message="获取操作耗时统计完成")


@router.get("/feedback-by-stage")
async def feedback_by_stage(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """按 feedback_type 分组的 AI 阶段评价统计（仅管理员）。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    from data.database import get_feedback_by_stage
    data = get_feedback_by_stage(date_range)
    return ApiResponse(success=True, data=data, message="获取阶段评价统计完成")


@router.get("/schedule-accuracy")
async def schedule_accuracy(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """AI 排期建议准确度：对比建议工时 vs 实际处理工时（仅管理员）。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    from data.database import get_schedule_accuracy_stats
    data = get_schedule_accuracy_stats(date_range)
    return ApiResponse(success=True, data=data, message="获取排期准确度统计完成")


# ── GET /api/eval/case-feedback-stats — 案例检索评价全局统计 ──

@router.get("/case-feedback-stats")
async def case_feedback_stats(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """案例检索评价全局匿名聚合统计（所有已登录用户）。"""
    _validate_date_range(date_range)
    from data.database import get_case_feedback_stats
    data = get_case_feedback_stats(date_range)
    return ApiResponse(success=True, data=data, message="获取案例评价统计完成")


# ═══════════════════ 0824 评估体系补强：通知触达 / AI采纳效果 / KB检索漏斗 ═══════════════════

# ── GET /api/eval/notification-reach — 通知触达统计 ──────
@router.get("/notification-reach")
async def notification_reach(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """0824 通知触达：站内待处理通知未读率 + 长期未读 + 钉钉推送成功率。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    data = {
        "station": get_notification_reach_stats(date_range),
        "dingtalk": get_dingtalk_push_stats(date_range),
    }
    return ApiResponse(success=True, data=data, message="获取通知触达统计完成")


# ── GET /api/eval/adoption-impact — AI 采纳效果对比 ──────
@router.get("/adoption-impact")
async def adoption_impact(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """0824 AI 采纳效果闭环：采纳组 vs 未采纳组的处理时长 / 一次解决率对比。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    data = get_ai_adoption_impact_stats(date_range)
    return ApiResponse(success=True, data=data, message="获取 AI 采纳效果对比完成")


# ── GET /api/eval/kb-funnel — KB 检索漏斗 ────────────────
@router.get("/kb-funnel")
async def kb_funnel(
    date_range: str = Query(default="近3个月", description="日期范围"),
    current_user: UserInfo = Depends(get_current_user),
):
    """0824 KB 检索漏斗：检索 → 相似案例查看 → 评价 → 引用 + KB 有用率。
    检索埋点自 0824 上线起累计，此前无数据。"""
    _require_admin(current_user)
    _validate_date_range(date_range)
    data = get_kb_reach_funnel_stats(date_range)
    return ApiResponse(success=True, data=data, message="获取 KB 检索漏斗完成")
