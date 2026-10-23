# 0724 文件上传 API — 附件上传/下载/删除/列表
"""附件管理 REST 端点。"""

import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from services.file_service import (
    validate_files, save_upload_files, get_complaint_files,
    get_file_path, remove_file, user_can_manage_files,
)
from data.database import get_complaint
from middleware.auth import get_current_user, decode_access_token
from schemas.auth import UserInfo
from schemas.common import ApiResponse

router = APIRouter()
_optional_security = HTTPBearer(auto_error=False)


async def _auth_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_security),
    token: str = Query(default=""),
) -> UserInfo | None:
    """尝试从 Bearer 或 ?token= 认证，任一通过即可。都不通过返回 None。"""
    if credentials:
        return await get_current_user(credentials)
    if token:
        payload = decode_access_token(token)
        if payload:
            return UserInfo(
                id=payload.get("user_id", 0),
                username=payload.get("sub", ""),
                display_name=payload.get("display_name", ""),
                role=payload.get("role", ""),
                position=payload.get("position", ""),
            )
    return None


@router.post("/upload", response_model=ApiResponse)
async def upload_files(
    complaint_id: int = Form(...),
    files: list[UploadFile] = File(...),
    current_user: UserInfo = Depends(get_current_user),
):
    """上传附件到指定工单。"""
    complaint = get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="工单不存在")

    # 0821 附件操作隔离：仅管理员/录入客服/当前审批人/有效承接人可上传
    if not user_can_manage_files(complaint_id, current_user):
        raise HTTPException(status_code=403, detail="仅管理员、录入客服、当前审批人或有效承接人可管理该工单附件")

    result = validate_files(files, complaint_id)
    if not result["valid"]:
        raise HTTPException(status_code=400, detail="; ".join(result["errors"]))

    saved = save_upload_files(
        result["valid_files"],
        complaint["complaint_no"],
        complaint_id,
        current_user.display_name,
    )

    return ApiResponse(success=True, data=saved, message=f"已上传 {len(saved)} 个附件")


@router.get("/{attachment_id}/download")
async def download_file(
    attachment_id: int,
    current_user: UserInfo | None = Depends(_auth_optional),
):
    """下载/预览附件。支持 Bearer token 或 ?token= query param（供 <img src> 预览用）。"""
    if not current_user:
        raise HTTPException(status_code=401, detail="请先登录")

    from data.database import get_conn
    conn = get_conn()
    row = conn.execute("SELECT * FROM attachments WHERE id = %s", (attachment_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="附件不存在")

    complaint = get_complaint(row["complaint_id"])
    if not complaint:
        raise HTTPException(status_code=404, detail="关联工单不存在")

    # 0824 安全加固：下载与上传/删除同权（0821 附件操作隔离），阻止遍历下载他人工单附件
    if not user_can_manage_files(complaint["id"], current_user):
        raise HTTPException(status_code=403, detail="仅管理员、录入客服、当前审批人或有效承接人可下载该工单附件")

    filepath = get_file_path(complaint["complaint_no"], row["stored_name"])
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="文件已缺失")

    return FileResponse(
        filepath,
        filename=row["filename"],
        media_type=row["mime_type"] or "application/octet-stream",
    )


@router.delete("/{attachment_id}", response_model=ApiResponse)
async def delete_file(
    attachment_id: int,
    current_user: UserInfo = Depends(get_current_user),
):
    """删除附件。"""
    from data.database import get_conn
    conn = get_conn()
    row = conn.execute("SELECT * FROM attachments WHERE id = %s", (attachment_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="附件不存在")

    complaint = get_complaint(row["complaint_id"])
    if not complaint:
        raise HTTPException(status_code=404, detail="关联工单不存在")

    # 0821 附件操作隔离：仅管理员/录入客服/当前审批人/有效承接人可删除
    if not user_can_manage_files(complaint["id"], current_user):
        raise HTTPException(status_code=403, detail="仅管理员、录入客服、当前审批人或有效承接人可管理该工单附件")

    success = remove_file(attachment_id, complaint["complaint_no"], row["stored_name"])
    if success:
        return ApiResponse(success=True, message="附件已删除")
    else:
        raise HTTPException(status_code=500, detail="删除失败")
