# 0724 文件上传服务 — 校验 + 存储 + 清理
"""文件上传业务逻辑：从 Streamlit 页面提取的附件处理逻辑。

来源：
- pages/1_客诉录入.py 38-53 行：附件保存辅助
- pages/3_工单处理.py 444-516 行：进度更新表单附件校验
- data/database.py 1650-1719 行：附件元数据 CRUD
"""

import os
import uuid

from data.database import (
    save_attachment, get_attachments, delete_attachment, count_attachments,
    ATTACHMENT_WHITELIST, ATTACHMENT_MAX_PER_UPLOAD,
    ATTACHMENT_MAX_PER_COMPLAINT, ATTACHMENT_MAX_SIZE_MB,
    _get_mime_type,
    get_complaint, is_active_approver, is_active_assignee,
)


# 0811 数据解耦：uploads 移至项目根目录 data/uploads
UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "uploads"))


# 0821 附件操作隔离守卫
def user_can_manage_files(complaint_id: int, current_user) -> bool:
    """附件上传/删除权限：管理员 / 录入客服 / 当前审批人 / 有效承接人（参与人）。"""
    if getattr(current_user, "role", "") == "管理员":
        return True
    complaint = get_complaint(complaint_id)
    if not complaint:
        return False
    if complaint.get("created_by_user_id") == current_user.id:
        return True
    if is_active_approver(complaint_id, current_user.id):
        return True
    return is_active_assignee(complaint_id, current_user.id)


def validate_files(files: list, complaint_id: int | None = None) -> dict:
    """校验上传文件：数量、大小、扩展名白名单。
    返回 {"valid": bool, "errors": list[str], "valid_files": list}
    """
    errors = []
    valid_files = []

    existing_count = count_attachments(complaint_id) if complaint_id else 0
    remaining = ATTACHMENT_MAX_PER_COMPLAINT - existing_count

    if len(files) > ATTACHMENT_MAX_PER_UPLOAD:
        errors.append(f"单次最多上传 {ATTACHMENT_MAX_PER_UPLOAD} 个文件，当前 {len(files)} 个")
        return {"valid": False, "errors": errors, "valid_files": []}

    for f in files:
        # 获取文件名和扩展名
        if hasattr(f, 'filename'):
            filename = f.filename
        else:
            filename = getattr(f, 'name', 'unknown')

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ATTACHMENT_WHITELIST:
            errors.append(f"「{filename}」不支持的文件类型（.{ext}）")
            continue

        # 获取文件大小
        if hasattr(f, 'size'):
            size = f.size
        elif hasattr(f, 'file'):
            f.file.seek(0, os.SEEK_END)
            size = f.file.tell()
            f.file.seek(0)
        else:
            size = getattr(f, 'content_length', 0)

        if size > ATTACHMENT_MAX_SIZE_MB * 1024 * 1024:
            errors.append(f"「{filename}」大小 {size/1024/1024:.1f}MB 超过 {ATTACHMENT_MAX_SIZE_MB}MB 限制")
            continue

        valid_files.append(f)

    if complaint_id and len(valid_files) > remaining:
        errors.append(f"超出剩余配额，最多还可上传 {remaining} 个（已用 {existing_count}/{ATTACHMENT_MAX_PER_COMPLAINT}）")

    return {"valid": len(errors) == 0, "errors": errors, "valid_files": valid_files}


def save_upload_files(files: list, complaint_no: str, complaint_id: int, uploaded_by: str) -> list[dict]:
    """将上传的文件写入磁盘并记录到 DB。返回已保存文件列表。"""
    target_dir = os.path.join(UPLOAD_DIR, complaint_no)
    os.makedirs(target_dir, exist_ok=True)

    saved = []
    for f in files:
        # 获取原始文件名
        orig_name = f.filename if hasattr(f, 'filename') else getattr(f, 'name', 'unknown')
        ext = orig_name.rsplit(".", 1)[-1].lower() if "." in orig_name else "bin"
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(target_dir, stored_name)

        # 读取文件内容
        if hasattr(f, 'file'):
            content = f.file.read()
        elif hasattr(f, 'read'):
            content = f.read()
        else:
            content = b''

        with open(filepath, "wb") as dst:
            dst.write(content)

        # 获取大小
        size = os.path.getsize(filepath)
        mime_type = _get_mime_type(ext)

        aid = save_attachment(complaint_id, orig_name, stored_name, mime_type, size, uploaded_by)
        saved.append({"id": aid, "filename": orig_name, "stored_name": stored_name,
                       "mime_type": mime_type, "file_size": size})

    return saved


def get_complaint_files(complaint_id: int) -> list[dict]:
    """获取工单的所有附件。"""
    return get_attachments(complaint_id)


def get_file_path(complaint_no: str, stored_name: str) -> str:
    """获取附件在磁盘上的绝对路径。"""
    return os.path.join(UPLOAD_DIR, complaint_no, stored_name)


def remove_file(attachment_id: int, complaint_no: str, stored_name: str) -> bool:
    """删除附件（DB 记录 + 磁盘文件）。"""
    filepath = get_file_path(complaint_no, stored_name)
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except OSError:
        pass

    try:
        delete_attachment(attachment_id)
        return True
    except Exception:
        return False
