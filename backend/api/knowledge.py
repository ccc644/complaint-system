# 0727 Phase 3 知识库 API — CRUD + 搜索 + 反馈
"""知识库 REST API 端点。
来源：pages/4_知识库.py（v2.1 Streamlit）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from data.database import (
    search_kb, get_all_kb, get_kb_entry, create_kb_entry, delete_kb_entry,
    increment_kb_useful, increment_kb_unhelpful, increment_kb_dimension,
    get_kb_quality_stats, get_kb_top_valuable, get_kb_needs_review, get_kb_stale,
)
from services.kb_service import search_and_filter
from middleware.auth import get_current_user
from schemas.auth import UserInfo
from schemas.knowledge import KBCreateRequest, KBDimensionVoteRequest
from schemas.common import ApiResponse, PaginatedResponse, PaginationOut

router = APIRouter()

# 0727 知识库访问控制 — 所有登录用户可查看（客服亦可查看知识库）
KB_ALLOWED_ROLES = {"管理员", "客服", "客服主管", "办理人", "审批人", "承接人"}


def _check_kb_access(current_user: UserInfo) -> None:
    """仅允许知识库授权角色访问（客服无权查看知识库）。"""
    if current_user.role not in KB_ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="当前角色无权访问知识库")


def _check_kb_admin(current_user: UserInfo) -> None:
    """仅管理员可执行知识库写操作（更新/删除）。"""
    if current_user.role != "管理员":
        raise HTTPException(status_code=403, detail="仅管理员可操作")


# ── GET /api/knowledge — 搜索/列表 ──────────────────
@router.get("")
async def list_knowledge(
    keyword: str = Query(default="", description="搜索关键词"),
    category: str = Query(default="", description="故障类别筛选"),
    quality_filter: str = Query(default="", description="质量筛选：high_value/top_tier/engineer_rec/presales_rec/needs_review/stale"),
    sort_by: str = Query(default="", description="排序：newest/most_useful/composite/engineer/presales"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    current_user: UserInfo = Depends(get_current_user),
):
    """搜索/列表知识库条目。"""
    _check_kb_access(current_user)
    # 类别筛选即使无关键词也需要生效 — search_kb 内部会在 keyword 为空时按类别返回全量
    raw = search_kb(keyword or "", category)

    # 应用质量过滤 + 排序 + 分页
    results, total = search_and_filter(raw, quality_filter, sort_by, page, page_size)

    return PaginatedResponse(
        success=True,
        data=results,
        message="搜索完成",
        pagination=PaginationOut(page=page, limit=page_size, total=total),
    )


# ── GET /api/knowledge/quality/stats — 质量总览 ──────
@router.get("/quality/stats")
async def quality_stats(current_user: UserInfo = Depends(get_current_user)):
    """知识库质量总览统计。"""
    _check_kb_access(current_user)
    stats = get_kb_quality_stats()
    top = get_kb_top_valuable(10)
    needs_review = get_kb_needs_review()
    stale = get_kb_stale(3)
    return ApiResponse(
        success=True,
        data={"stats": stats, "top_valuable": top, "needs_review": needs_review, "stale": stale},
        message="获取质量统计完成",
    )


# ── GET /api/knowledge/quality/top — 高价值 TOP N ────
@router.get("/quality/top")
async def quality_top(
    limit: int = Query(default=10, ge=1, le=100),
    current_user: UserInfo = Depends(get_current_user),
):
    """高价值知识条目 TOP N。"""
    _check_kb_access(current_user)
    return ApiResponse(success=True, data=get_kb_top_valuable(limit), message="获取完成")


# ── GET /api/knowledge/{id} — 单条详情 ───────────────
@router.get("/{kb_id}")
async def get_entry(kb_id: int, current_user: UserInfo = Depends(get_current_user)):
    """获取单条知识条目详情。"""
    _check_kb_access(current_user)
    entry = get_kb_entry(kb_id)
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return ApiResponse(success=True, data=entry, message="获取完成")


# ── POST /api/knowledge — 新增知识 ──────────────────
@router.post("")
async def create_entry(
    req: KBCreateRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """新增知识条目。"""
    _check_kb_access(current_user)
    data = req.model_dump()
    kb_id = create_kb_entry(data)
    # 0908 RAG 阶段 1：新建条目生成向量（失败不阻断创建，回填脚本可后补）
    try:
        from ai_engine.ai_engine import embed_kb_entry
        embed_kb_entry(kb_id, data, triggered_by="kb_manual_create")
    except Exception:
        pass
    return ApiResponse(success=True, data={"id": kb_id}, message="知识条目已创建")


# ── DELETE /api/knowledge/{id} — 删除知识（管理员）─────
@router.delete("/{kb_id}")
async def delete_entry(kb_id: int, current_user: UserInfo = Depends(get_current_user)):
    """删除知识条目（仅管理员）。"""
    _check_kb_admin(current_user)
    entry = get_kb_entry(kb_id)
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    ok = delete_kb_entry(kb_id)
    return ApiResponse(success=ok, message="知识条目已删除" if ok else "删除失败")


# ── POST /api/knowledge/{id}/useful — 点赞 ───────────
@router.post("/{kb_id}/useful")
async def vote_useful(kb_id: int, current_user: UserInfo = Depends(get_current_user)):
    """点赞知识条目。"""
    _check_kb_access(current_user)
    ok = increment_kb_useful(kb_id, current_user.username)
    if not ok:
        raise HTTPException(status_code=429, detail="操作过于频繁，请 60 秒后再试")
    return ApiResponse(success=True, message="已点赞")


# ── POST /api/knowledge/{id}/unhelpful — 踩 ──────────
@router.post("/{kb_id}/unhelpful")
async def vote_unhelpful(kb_id: int, current_user: UserInfo = Depends(get_current_user)):
    """踩知识条目。"""
    _check_kb_access(current_user)
    ok = increment_kb_unhelpful(kb_id, current_user.username)
    if not ok:
        raise HTTPException(status_code=429, detail="操作过于频繁，请 60 秒后再试")
    return ApiResponse(success=True, message="已标记为无帮助")


# ── POST /api/knowledge/{id}/dimension — 维度投票 ────
@router.post("/{kb_id}/dimension")
async def vote_dimension(
    kb_id: int,
    req: KBDimensionVoteRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """维度投票（accuracy/effectiveness/clarity/customer_impact/presales_value）。"""
    _check_kb_access(current_user)
    valid_dims = {"accuracy", "effectiveness", "clarity", "customer_impact", "presales_value"}
    if req.dimension not in valid_dims:
        raise HTTPException(status_code=400, detail=f"无效维度：{req.dimension}，有效值：{', '.join(sorted(valid_dims))}")
    ok = increment_kb_dimension(kb_id, current_user.username, req.dimension)
    if not ok:
        raise HTTPException(status_code=429, detail="操作过于频繁，请 60 秒后再试")
    return ApiResponse(success=True, message=f"已对「{req.dimension}」维度投票")


# ── GET /api/knowledge/{kb_id}/case-feedback — 单条知识库案例评价汇总 ──

@router.get("/{kb_id}/case-feedback")
async def kb_case_feedback(kb_id: int):
    """查询单条知识库被案例检索评价的统计（所有角色可访问）。"""
    from data.database import get_kb_case_feedback_stats
    data = get_kb_case_feedback_stats(kb_id)
    return ApiResponse(success=True, data=data, message="查询完成")


# ── GET /api/knowledge/case-feedback-stats — 知识库级聚合统计 ──

@router.get("/case-feedback-stats")
async def kb_case_feedback_stats(
    current_user: UserInfo = Depends(get_current_user),
):
    """知识库案例检索评价聚合统计（仅管理员）。"""
    from data.database import get_kb_case_feedback_stats
    if current_user.role != "管理员":
        raise HTTPException(status_code=403, detail="仅管理员可访问")
    # 传 None 获取全部 KB 聚合
    data = get_kb_case_feedback_stats()
    return ApiResponse(success=True, data=data, message="查询完成")
