# 0910 批量表单导入 API — 三种问题跟踪表 → 工单（解析预览 / 确认导入 / 模板下载）
"""批量导入端点。权限：客服/管理员（其他角色 403）。一次一个文件。"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse

from middleware.auth import get_current_user
from schemas.auth import UserInfo
from schemas.common import ApiResponse
from schemas.batch_import import BatchCommitRequest
from services import batch_import_service

router = APIRouter()

_ALLOWED_ROLES = ("客服", "管理员")


def _check_role(current_user: UserInfo):
    if current_user.role not in _ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="仅客服/管理员可使用批量导入")


@router.post("/parse", response_model=ApiResponse)
async def parse_batch_import(
    file: UploadFile = File(...),
    current_user: UserInfo = Depends(get_current_user),
):
    """上传单个表单（.xlsx/.xls）→ 识别模板 + 列映射 + 预览行（含去重/客户匹配/警告）。"""
    _check_role(current_user)
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 表单文件")
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件超过 20MB 上限")
    try:
        preview = batch_import_service.parse_workbook(file_bytes, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"表单解析失败：{e}")
    return ApiResponse(success=True, message="解析成功，请核对预览后确认导入", data=preview)


@router.get("/template")
async def download_batch_template(
    current_user: UserInfo = Depends(get_current_user),
):
    """下载批量导入标准模板 .xlsx（表头=系统字段名 + 示例行 + 取值下拉 + 填写说明）。0914。"""
    _check_role(current_user)
    xlsx_bytes = batch_import_service.build_template_xlsx()
    filename = quote("批量导入模板.xlsx")
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/commit", response_model=ApiResponse)
async def commit_batch_import(
    body: BatchCommitRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """确认导入：逐行创建工单（单行失败不回滚整批，失败按表内序号回报）。"""
    _check_role(current_user)
    if not body.rows:
        raise HTTPException(status_code=400, detail="没有可导入的行")
    if len(body.rows) > 1000:
        raise HTTPException(status_code=400, detail="单次导入上限 1000 行")
    operator = {
        "id": current_user.id,
        "display_name": current_user.display_name,
        "role": current_user.role,
        "position": getattr(current_user, "position", "") or "",
    }
    result = batch_import_service.commit_import(body, operator)
    return ApiResponse(success=True, message=f"导入完成：成功 {result['success_count']} 条", data=result)
