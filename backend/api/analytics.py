# 0727 Phase 3 分析看板 API — KPI + 趋势 + 分布 + 导出
"""分析看板 REST API 端点。
来源：pages/5_客诉分析.py（v2.1 Streamlit）
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional

from data.database import (
    get_analytics_kpi_overview,
    get_analytics_monthly_trend,
    get_analytics_daily_trend,
    get_analytics_category_distribution,
    get_analytics_priority_distribution,
    get_analytics_status_distribution,
    get_analytics_customer_top,
    get_analytics_equipment_top,
    get_kb_quality_stats,
    get_kb_top_valuable,
    get_kb_needs_review,
    get_kb_stale,
)
from middleware.auth import get_current_user
from schemas.auth import UserInfo
from schemas.common import ApiResponse

router = APIRouter()

VALID_DATE_RANGES = {"本月", "上月", "近3个月", "近6个月", "全部"}


def _validate_date_range(date_range: str) -> str:
    if date_range not in VALID_DATE_RANGES:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"无效日期范围：{date_range}，有效值：{', '.join(sorted(VALID_DATE_RANGES))}")
    return date_range


# ── GET /api/analytics/kpi — KPI 总览 ─────────────────
@router.get("/kpi")
async def kpi_overview(
    date_range: str = Query(default="近3个月", description="日期范围：本月/上月/近3个月/近6个月/全部"),
    current_user: UserInfo = Depends(get_current_user),
):
    """KPI 总览（12 项指标）。"""
    _validate_date_range(date_range)
    data = get_analytics_kpi_overview(date_range)
    return ApiResponse(success=True, data=data, message="获取 KPI 完成")


# ── GET /api/analytics/trend — 趋势数据 ───────────────
@router.get("/trend")
async def trend(
    date_range: str = Query(default="近3个月", description="日期范围"),
    granularity: str = Query(default="monthly", description="粒度：monthly/daily"),
    current_user: UserInfo = Depends(get_current_user),
):
    """工单趋势（月度/日度）。"""
    _validate_date_range(date_range)
    if granularity == "daily":
        data = get_analytics_daily_trend(date_range)
    else:
        data = get_analytics_monthly_trend(date_range)
    return ApiResponse(success=True, data=data, message="获取趋势完成")


# ── GET /api/analytics/distribution — 分布数据 ────────
@router.get("/distribution")
async def distribution(
    date_range: str = Query(default="近3个月", description="日期范围"),
    dimension: str = Query(default="category", description="维度：category/priority/status/customer/equipment"),
    current_user: UserInfo = Depends(get_current_user),
):
    """分布分析（故障类别/优先级/状态/TOP客户/TOP设备）。"""
    _validate_date_range(date_range)
    dim_map = {
        "category": get_analytics_category_distribution,
        "priority": get_analytics_priority_distribution,
        "status": get_analytics_status_distribution,
        "customer": get_analytics_customer_top,
        "equipment": get_analytics_equipment_top,
    }
    if dimension not in dim_map:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"无效维度：{dimension}，有效值：{', '.join(dim_map.keys())}")
    data = dim_map[dimension](date_range)
    return ApiResponse(success=True, data=data, message="获取分布数据完成")


# ── GET /api/analytics/kb-quality — KB 质量仪表盘 ─────
@router.get("/kb-quality")
async def kb_quality_dashboard(current_user: UserInfo = Depends(get_current_user)):
    """知识库质量仪表盘数据。"""
    stats = get_kb_quality_stats()
    top = get_kb_top_valuable(10)
    needs_review = get_kb_needs_review()
    stale = get_kb_stale(3)
    return ApiResponse(
        success=True,
        data={"stats": stats, "top_valuable": top, "needs_review": needs_review, "stale": stale},
        message="获取 KB 质量数据完成",
    )
