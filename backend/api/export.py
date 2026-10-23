# 0819 系统管理导出中心 API — 数据导出（CSV + 附件 ZIP）
"""数据导出 REST API 端点。
数据范围支持精确到天的可选起止日期（start_date / end_date，YYYY-MM-DD 闭区间）。
0824 权限调整：仅管理员可导出（曾于 0824 短暂开放客服主管，同日收回）。
"""

import os
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from middleware.auth import get_current_user
from schemas.auth import UserInfo
from services.export_service import (
    EXPORT_TYPE_KEYS,
    build_export_csv,
    build_all_csv_zip,
    build_attachments_zip,
)

router = APIRouter()


def _require_export_role(user: UserInfo):
    """仅管理员可访问数据导出。"""
    if user.role != "管理员":
        raise HTTPException(status_code=403, detail="仅管理员可访问数据导出")


def _validate_dates(start_date: str | None, end_date: str | None):
    """校验可选日期参数：格式 YYYY-MM-DD，且开始不晚于结束。"""
    for label, val in (("start_date", start_date), ("end_date", end_date)):
        if val is not None:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"日期格式无效：{label}={val}，应为 YYYY-MM-DD"
                )
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")


# ── GET /api/export/data — 各类数据 CSV 导出 ─────────────

@router.get("/data")
async def export_data(
    type: str = Query(..., description=f"导出类型：{' / '.join(EXPORT_TYPE_KEYS)}"),
    start_date: str | None = Query(default=None, description="开始日期 YYYY-MM-DD（含）"),
    end_date: str | None = Query(default=None, description="结束日期 YYYY-MM-DD（含）"),
    current_user: UserInfo = Depends(get_current_user),
):
    """导出指定类型的数据为 CSV（仅管理员）。留空日期 = 不限范围。"""
    _require_export_role(current_user)
    _validate_dates(start_date, end_date)

    try:
        csv_bytes, filename = build_export_csv(type, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    safe_name = quote(filename)
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )


# ── GET /api/export/attachments — 附件 ZIP 批量打包 ──────

@router.get("/attachments")
async def export_attachments(
    background_tasks: BackgroundTasks,
    start_date: str | None = Query(default=None, description="开始日期 YYYY-MM-DD（含）"),
    end_date: str | None = Query(default=None, description="结束日期 YYYY-MM-DD（含）"),
    current_user: UserInfo = Depends(get_current_user),
):
    """按日期范围打包工单附件为 ZIP（管理员/客服主管）。ZIP 内按 工单号/文件名 组织。"""
    _require_export_role(current_user)
    _validate_dates(start_date, end_date)

    zip_path, added = build_attachments_zip(start_date, end_date)
    if added == 0:
        try:
            os.remove(zip_path)
        except OSError:
            pass
        raise HTTPException(status_code=404, detail="所选日期范围内没有附件可导出")

    background_tasks.add_task(_remove_temp_file, zip_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"attachments_{ts}.zip"
    safe_name = quote(filename)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )


# ── GET /api/export/all — 一键导出全部 CSV（ZIP 打包） ────

@router.get("/all")
async def export_all(
    background_tasks: BackgroundTasks,
    start_date: str | None = Query(default=None, description="开始日期 YYYY-MM-DD（含）"),
    end_date: str | None = Query(default=None, description="结束日期 YYYY-MM-DD（含）"),
    current_user: UserInfo = Depends(get_current_user),
):
    """一键导出全部类型数据：所有 CSV 打包为单个 ZIP（管理员/客服主管）。"""
    _require_export_role(current_user)
    _validate_dates(start_date, end_date)

    zip_path, count = build_all_csv_zip(start_date, end_date)
    background_tasks.add_task(_remove_temp_file, zip_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"export_all_{ts}.zip"
    safe_name = quote(filename)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_name}"},
    )


def _remove_temp_file(path: str):
    """清理临时 ZIP 文件（响应完成后由 BackgroundTasks 调用）。"""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
