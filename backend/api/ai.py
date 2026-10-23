# 0727 Phase 3 AI 接口 — 分类/诊断/语义搜索/知识提取
"""AI 智能功能 REST API 端点。
来源：ai_engine/ai_engine.py（v2.1）
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from ai_engine.ai_engine import (
    classify_complaint_llm,
    suggest_priority_llm,
    diagnose_complaint,
    extract_complaint_from_text,
    extract_knowledge_from_text,
    semantic_search_kb,
    case_search_solution,
    check_deepseek_connection,
    find_similar_cases,
    suggest_checklist,
    suggest_customer_self_check,
    suggest_schedule,
)
from middleware.auth import get_current_user
from schemas.auth import UserInfo
from schemas.ai import (
    ClassifyRequest, PriorityRequest, DiagnoseRequest,
    ExtractTextRequest, SemanticSearchRequest, SimilarCasesRequest,
    SelfCheckRequest, ScheduleSuggestionRequest,
)
from schemas.common import ApiResponse

router = APIRouter()


# ── POST /api/ai/classify — LLM 故障分类 ──────────────
@router.post("/classify")
async def classify(req: ClassifyRequest, current_user: UserInfo = Depends(get_current_user)):
    """LLM 故障分类（自动化设备 领域）。"""
    result = classify_complaint_llm(req.fault_phenomenon)
    if result is None:
        raise HTTPException(status_code=503, detail="DeepSeek 服务暂不可用，请稍后重试")
    return ApiResponse(success=True, data=result, message="分类完成")


# ── POST /api/ai/priority — LLM 优先级建议 ────────────
@router.post("/priority")
async def priority(req: PriorityRequest, current_user: UserInfo = Depends(get_current_user)):
    """LLM 优先级评估（A/B/C）。LLM 失败时自动降级到规则引擎。"""
    result = suggest_priority_llm(req.fault_phenomenon, req.customer_note)
    return ApiResponse(success=True, data=result, message="优先级评估完成")


# ── POST /api/ai/diagnose — AI 诊断 ───────────────────
@router.post("/diagnose")
async def diagnose(req: DiagnoseRequest, current_user: UserInfo = Depends(get_current_user)):
    """AI 诊断：结合知识库给出诊断建议和协作方案。"""
    result = diagnose_complaint(req.fault_phenomenon, req.equipment_model, req.customer_name)
    if result is None:
        raise HTTPException(status_code=503, detail="DeepSeek 服务暂不可用，请稍后重试")
    return ApiResponse(success=True, data=result, message="诊断完成")


# ── POST /api/ai/extract-complaint — 从文本提取客诉 ───
@router.post("/extract-complaint")
async def extract_complaint(req: ExtractTextRequest, current_user: UserInfo = Depends(get_current_user)):
    """从聊天/邮件文本中提取客诉表单字段。"""
    result = extract_complaint_from_text(req.raw_text, req.allow_rule_fallback)
    if result.get("source") == "failed":
        raise HTTPException(status_code=503, detail=result.get("error", "DeepSeek 提取失败"))
    return ApiResponse(success=True, data=result, message="提取完成")


# ── POST /api/ai/extract-knowledge — 从文本提取知识 ───
@router.post("/extract-knowledge")
async def extract_knowledge(req: ExtractTextRequest, current_user: UserInfo = Depends(get_current_user)):
    """从非结构化文本中提取知识条目字段。"""
    result = extract_knowledge_from_text(req.raw_text, req.allow_rule_fallback)
    if result.get("source") == "failed":
        raise HTTPException(status_code=503, detail=result.get("error", "DeepSeek 提取失败"))
    return ApiResponse(success=True, data=result, message="提取完成")


# ── POST /api/ai/semantic-search — AI 语义搜索 ────────
@router.post("/semantic-search")
async def semantic_search(req: SemanticSearchRequest, current_user: UserInfo = Depends(get_current_user)):
    """AI 语义搜索：FTS5 粗筛 + LLM 重排序。"""
    # 0824 KB 检索漏斗埋点（不记录检索词内容，防敏感信息落日志）
    try:
        from data.database import record_user_activity
        record_user_activity(current_user.username, current_user.role,
                             "/knowledge", "kb_search", "{}")
    except Exception:
        pass
    results = semantic_search_kb(req.query, req.top_k)
    return ApiResponse(success=True, data=results, message=f"语义搜索完成，找到 {len(results)} 条")


# ── POST /api/ai/similar-cases — 查找相似案例 ─────────
@router.post("/similar-cases")
async def similar_cases(req: SimilarCasesRequest, current_user: UserInfo = Depends(get_current_user)):
    """查找相似案例并生成解决方案摘要。"""
    # 0824 KB 检索漏斗埋点
    try:
        from data.database import record_user_activity
        record_user_activity(current_user.username, current_user.role,
                             "/work-order", "similar_cases_view", "{}")
    except Exception:
        pass
    result = case_search_solution(req.fault_phenomenon, req.equipment_model, req.fault_category)
    if result is None:
        raise HTTPException(status_code=503, detail="DeepSeek 服务暂不可用或未找到相似案例")
    return ApiResponse(success=True, data=result, message="案例检索完成")


# ── GET /api/ai/deepseek-status — DeepSeek 连接状态 ────
@router.get("/deepseek-status")
async def deepseek_status(current_user: UserInfo = Depends(get_current_user)):
    """检查 DeepSeek API 连接状态。"""
    status = check_deepseek_connection()
    return ApiResponse(success=True, data=status, message="状态检测完成")


# ── POST /api/ai/similar-cases-quick — FTS5 秒出相似案例 ──
# 0728 增加 fault_category 字段用于同类优先检索
@router.post("/similar-cases-quick")
async def similar_cases_quick(req: SimilarCasesRequest, current_user: UserInfo = Depends(get_current_user)):
    """从知识库中 FTS5 全文检索相似案例（秒出，无需 LLM）。
    来源：v2.1 3_工单处理.py 334-342 行
    """
    # 0824 KB 检索漏斗埋点
    try:
        from data.database import record_user_activity
        record_user_activity(current_user.username, current_user.role,
                             "/work-order", "similar_cases_view", "{}")
    except Exception:
        pass
    results = find_similar_cases(req.fault_phenomenon, fault_category=req.fault_category)
    return ApiResponse(success=True, data=results, message=f"找到 {len(results)} 条相似案例")


# ── POST /api/ai/checklist — 推荐排查清单 ────────────
@router.post("/checklist")
async def checklist(req: ClassifyRequest, current_user: UserInfo = Depends(get_current_user)):
    """根据故障类别推荐标准排查清单。
    来源：v2.1 3_工单处理.py 345-348 行
    """
    cat = req.fault_phenomenon  # 这里传 fault_category（复用 ClassifyRequest 字段名）
    items = suggest_checklist(cat or "其他")
    return ApiResponse(success=True, data=items, message="获取排查清单完成")


# 0728 AI 自排查推荐 — 面向客户的简单安全排查建议
@router.post("/self-check")
async def self_check(req: SelfCheckRequest, current_user: UserInfo = Depends(get_current_user)):
    """AI 客户自排查建议：生成最多 5 条面向产线操作工的简单安全排查建议。"""
    result = suggest_customer_self_check(req.fault_phenomenon, req.equipment_model)
    if result is None:
        raise HTTPException(status_code=503, detail="DeepSeek 服务暂不可用，请稍后重试")
    return ApiResponse(success=True, data=result, message="生成排查建议完成")


# 0728 AI 排期建议 — 基于工程师历史+类别统计+负载
@router.post("/schedule-suggestion")
async def schedule_suggestion(req: ScheduleSuggestionRequest, current_user: UserInfo = Depends(get_current_user)):
    """AI 排期建议：综合工程师历史、故障类别统计、当前负载给出建议工时。"""
    from data.database import get_engineer_avg_stats, get_category_avg_hours, get_engineer_active_complaints

    eng = get_engineer_avg_stats(req.engineer_name)
    cat = get_category_avg_hours(req.fault_category) if req.fault_category else {"total_closed": 0, "avg_hours": 0}
    active = get_engineer_active_complaints(req.engineer_name)

    result = suggest_schedule(
        req.engineer_name, req.fault_category, req.estimated_hours,
        eng.get("avg_hours") or 0, eng.get("total_closed") or 0,
        cat.get("avg_hours") or 0, cat.get("total_closed") or 0,
        len(active), req.assignee_count,
    )
    if result is None:
        raise HTTPException(status_code=503, detail="DeepSeek 服务暂不可用，请稍后重试")
    return ApiResponse(success=True, data=result, message="排期建议生成完成")


# ═══════════════════════════════════════ 0805 Phase 4: 案例检索评价 ═══════════════════════════════════════

@router.post("/case-feedback")
async def submit_case_feedback(
    body: dict,
    current_user: UserInfo = Depends(get_current_user),
):
    """提交/修改案例检索评价。
    请求体：{"complaint_no":"KS-...", "kb_id":1, "kb_title":"...", "source_type":"fts5_auto", "referenced":true, "match_accuracy":4}
    """
    from data.database import record_case_feedback
    complaint_no = body.get("complaint_no", "")
    kb_id = body.get("kb_id", 0)
    kb_title = body.get("kb_title", "")
    source_type = body.get("source_type", "")
    referenced = bool(body.get("referenced", False))
    match_accuracy = int(body.get("match_accuracy", 0))

    if not complaint_no or not kb_id or not source_type:
        raise HTTPException(status_code=400, detail="complaint_no / kb_id / source_type 为必填项")
    if match_accuracy < 0 or match_accuracy > 5:
        raise HTTPException(status_code=400, detail="match_accuracy 需为 0-5")

    record_case_feedback(
        username=current_user.username,
        complaint_no=complaint_no,
        kb_id=kb_id,
        kb_title=kb_title,
        source_type=source_type,
        referenced=referenced,
        match_accuracy=match_accuracy,
    )
    return ApiResponse(success=True, data=None, message="案例评价已保存")


@router.get("/case-feedback")
async def get_case_feedback_list(
    complaint_no: str = Query(..., description="工单编号"),
    current_user: UserInfo = Depends(get_current_user),
):
    """查询某工单下已有案例评价（供前端回显）。"""
    from data.database import get_case_feedback
    data = get_case_feedback(complaint_no)
    return ApiResponse(success=True, data=data, message="查询完成")
