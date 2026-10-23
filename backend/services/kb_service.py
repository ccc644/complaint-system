# 0727 Phase 3 知识库服务 — 质量过滤/排序/评分
"""知识库业务逻辑层。
来源：pages/4_知识库.py（v2.1 Streamlit）
"""

from datetime import datetime, timedelta
from core.config import KB_ENGINEER_SCORE_THRESHOLD, KB_PRESALES_SCORE_THRESHOLD


# ── 评分函数（对应 v2.1 pages/4_知识库.py 内的 _engineer_score / _presales_score / _composite_score）──

def calc_engineer_score(entry: dict) -> int:
    """工程师视角评分 = accuracy*3 + effectiveness*3 + clarity*2"""
    return (entry.get("accuracy_votes", 0) or 0) * 3 + \
           (entry.get("effectiveness_votes", 0) or 0) * 3 + \
           (entry.get("clarity_votes", 0) or 0) * 2


def calc_presales_score(entry: dict) -> int:
    """售前视角评分 = customer_impact*2 + presales_value*3"""
    return (entry.get("customer_impact_votes", 0) or 0) * 2 + \
           (entry.get("presales_value_votes", 0) or 0) * 3


def calc_composite_score(entry: dict) -> int:
    """综合评分 = 工程师评分 + 售前评分 + 有用数"""
    return calc_engineer_score(entry) + calc_presales_score(entry) + \
           (entry.get("useful_count", 0) or 0)


def calc_positive_pct(entry: dict) -> float:
    """好评率 = useful / (useful + unhelpful) * 100，无反馈返回 0"""
    u = entry.get("useful_count", 0) or 0
    d = entry.get("unhelpful_count", 0) or 0
    total = u + d
    return round(u / total * 100, 1) if total > 0 else 0.0


def _has_any_dimension_votes(entry: dict) -> bool:
    dims = ["accuracy_votes", "effectiveness_votes", "clarity_votes",
            "customer_impact_votes", "presales_value_votes"]
    return sum(entry.get(d, 0) or 0 for d in dims) > 0


def _is_stale(entry: dict, months: int = 3) -> bool:
    """零反馈且创建时间超过 N 个月。"""
    u = entry.get("useful_count", 0) or 0
    d = entry.get("unhelpful_count", 0) or 0
    if u + d > 0:
        return False
    created = entry.get("created_at", "")
    if not created:
        return False
    try:
        dt = datetime.strptime(created[:10], "%Y-%m-%d")
        return dt < datetime.now() - timedelta(days=months * 30)
    except (ValueError, TypeError):
        return False


# ── 质量过滤（对应 v2.1 pages/4_知识库.py 的 7 种质量筛选）──

def apply_quality_filter(entries: list[dict], quality_filter: str) -> list[dict]:
    """对 KB 条目列表应用质量筛选。

    quality_filter 可选值：
    - "" / "全部"        不筛选
    - "high_value"       高价值：useful >= unhelpful 且有维度投票
    - "top_tier"         顶级案例：工程师评分>=5 且 售前评分>=3 且 useful>=unhelpful
    - "engineer_rec"     工程师推荐：工程师评分>=阈值 且 useful>=unhelpful
    - "presales_rec"     售前推荐：售前评分>=阈值 且 useful>=unhelpful
    - "needs_review"     待修订：unhelpful > useful
    - "stale"            陈旧条目：零反馈 且 创建>3个月
    """
    if not quality_filter or quality_filter == "全部":
        return entries

    filtered = []
    for e in entries:
        useful = e.get("useful_count", 0) or 0
        unhelpful = e.get("unhelpful_count", 0) or 0
        eng_score = calc_engineer_score(e)
        pre_score = calc_presales_score(e)

        if quality_filter == "high_value":
            if useful >= unhelpful and _has_any_dimension_votes(e):
                filtered.append(e)
        elif quality_filter == "top_tier":
            if eng_score >= 5 and pre_score >= 3 and useful >= unhelpful:
                filtered.append(e)
        elif quality_filter == "engineer_rec":
            if eng_score >= KB_ENGINEER_SCORE_THRESHOLD and useful >= unhelpful:
                filtered.append(e)
        elif quality_filter == "presales_rec":
            if pre_score >= KB_PRESALES_SCORE_THRESHOLD and useful >= unhelpful:
                filtered.append(e)
        elif quality_filter == "needs_review":
            if unhelpful > useful:
                filtered.append(e)
        elif quality_filter == "stale":
            if _is_stale(e):
                filtered.append(e)
        else:
            filtered.append(e)  # 未知过滤选项，不筛选

    return filtered


# ── 排序（对应 v2.1 pages/4_知识库.py 的 6 种排序）──

def sort_kb_entries(entries: list[dict], sort_by: str) -> list[dict]:
    """对 KB 条目列表应用排序。

    sort_by 可选值：
    - "" / "default"      默认排序（FTS5 bm25 已排好，保持不变）
    - "newest"            最新优先（created_at DESC）
    - "most_useful"       最有帮助（useful_count DESC）
    - "composite"         综合评分最高
    - "engineer"          工程师优先
    - "presales"          售前优先
    """
    if not sort_by or sort_by == "default":
        return entries

    if sort_by == "newest":
        return sorted(entries, key=lambda e: e.get("created_at", ""), reverse=True)
    elif sort_by == "most_useful":
        return sorted(entries, key=lambda e: e.get("useful_count", 0) or 0, reverse=True)
    elif sort_by == "composite":
        return sorted(entries, key=calc_composite_score, reverse=True)
    elif sort_by == "engineer":
        return sorted(entries, key=calc_engineer_score, reverse=True)
    elif sort_by == "presales":
        return sorted(entries, key=calc_presales_score, reverse=True)
    else:
        return entries


# ── 搜索+过滤+排序+分页 主流程 ──

def search_and_filter(
    entries: list[dict],
    quality_filter: str = "",
    sort_by: str = "",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """对条目列表依次应用 质量过滤 → 排序 → 分页。
    返回 (当前页条目, 总条目数)。
    """
    # 1. 质量过滤
    filtered = apply_quality_filter(entries, quality_filter)

    # 2. 排序
    sorted_entries = sort_kb_entries(filtered, sort_by)

    # 3. 附加评分字段
    for e in sorted_entries:
        e["_engineer_score"] = calc_engineer_score(e)
        e["_presales_score"] = calc_presales_score(e)
        e["_composite_score"] = calc_composite_score(e)
        e["_positive_pct"] = calc_positive_pct(e)

    # 4. 分页
    total = len(sorted_entries)
    start = (page - 1) * page_size
    end = start + page_size
    return sorted_entries[start:end], total
