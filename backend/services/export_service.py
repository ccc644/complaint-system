# 0819 系统管理导出中心服务 — CSV 序列化 + 附件 ZIP 打包
"""管理员数据导出业务逻辑：导出类型映射、CSV 构建、附件 ZIP 打包。
ZIP 内保留 工单号/文件名 目录结构，避免多工单附件混杂。
"""

import csv
import io
import os
import tempfile
import uuid
import zipfile
from datetime import datetime

from data.database import (
    get_complaints_for_admin_export,
    get_work_order_log_for_export,
    get_kb_for_export,
    get_user_feedback_for_export,
    get_case_feedback_for_export,
    get_ai_adoption_for_export,
    get_sus_survey_for_export,
    get_user_activity_for_export,
    get_llm_call_log_for_export,
    get_attachments_for_zip,
    get_work_order_log_archive_for_export,
    get_progress_updates_for_export,
    get_notifications_for_export,
    get_users_for_export,
    get_kb_feedback_for_export,
    get_dingtalk_log_for_export,
    _build_abs_date_filter,
)
from eval.eval_service import build_stage_dwell_rows, STAGE_DWELL_COLUMNS
from core.config import STAGE_BLOCKAGE_THRESHOLD_HOURS
from services.file_service import UPLOAD_DIR

# 导出类型 → 数据 DAO（可精确到天的起止日期过滤）
_EXPORT_DAO_MAP = {
    "complaints": get_complaints_for_admin_export,
    "work_log": get_work_order_log_for_export,
    "kb": get_kb_for_export,
    "user_feedback": get_user_feedback_for_export,
    "case_feedback": get_case_feedback_for_export,
    "ai_adoption": get_ai_adoption_for_export,
    "sus_survey": get_sus_survey_for_export,
    "activity_log": get_user_activity_for_export,
    "llm_log": get_llm_call_log_for_export,
}

EXPORT_TYPE_KEYS = tuple(_EXPORT_DAO_MAP.keys())

# 导出类型 → 中文名（用于「一键导出全部」ZIP 内文件名）
EXPORT_TYPE_LABELS = {
    "complaints": "客诉工单",
    "work_log": "工单流转日志",
    "kb": "知识库",
    "user_feedback": "用户评价",
    "case_feedback": "案例检索评价",
    "ai_adoption": "AI采纳日志",
    "sus_survey": "系统评价(SUS问卷)",
    "activity_log": "用户活跃明细",
    "llm_log": "AI调用日志",
    "stage_dwell": "阶段停留时长明细",
    # 0824 导出补漏
    "archive_log": "归档流转日志",
    "progress_log": "工单进度记录",
    "notifications": "站内通知记录",
    "users": "用户清单(脱敏)",
    "kb_feedback": "知识库反馈记录",
    "dingtalk_log": "钉钉发送日志",
}

# 0821 阶段停留时长明细 CSV 列头（阶段名 + 卡顿阈值）
_STAGE_DWELL_EXPORT_HEADERS = {
    stage: f"{stage}（{STAGE_BLOCKAGE_THRESHOLD_HOURS.get(stage, 72)}h）"
    for stage in STAGE_DWELL_COLUMNS
}


def get_stage_dwell_for_export(start_date: str | None, end_date: str | None) -> list[dict]:
    """管理员导出：工单状态停留时长明细（各阶段分段时长，超阈值段加 ⚠️ 标记）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date, "wol.created_at")
    rows = build_stage_dwell_rows(where_clause, params)
    out = []
    for r in rows:
        item = {"工单号": r["complaint_no"], "客户": r["customer_name"]}
        for stage in STAGE_DWELL_COLUMNS:
            st = r["stages"].get(stage)
            if st and st["segments"]:
                # 0902 单元格附带推进人（进行中段无推进人标注「进行中」）
                item[_STAGE_DWELL_EXPORT_HEADERS[stage]] = " | ".join(
                    f"{s['hours']}h{'⚠️' if s['blocked'] else ''}"
                    f"（{s['advance']['name'] if s['advance'] else '进行中'}）"
                    for s in st["segments"]
                )
            else:
                item[_STAGE_DWELL_EXPORT_HEADERS[stage]] = ""
        out.append(item)
    return out


# 0821 注册到导出类型映射（函数定义后注册，避免 NameError）
_EXPORT_DAO_MAP["stage_dwell"] = get_stage_dwell_for_export
# 0824 导出补漏：归档日志/进度记录/通知/用户清单(脱敏)/KB反馈/钉钉日志
_EXPORT_DAO_MAP.update({
    "archive_log": get_work_order_log_archive_for_export,
    "progress_log": get_progress_updates_for_export,
    "notifications": get_notifications_for_export,
    "users": get_users_for_export,
    "kb_feedback": get_kb_feedback_for_export,
    "dingtalk_log": get_dingtalk_log_for_export,
})
EXPORT_TYPE_KEYS = tuple(_EXPORT_DAO_MAP.keys())


def build_export_csv(export_type: str, start_date: str | None, end_date: str | None) -> tuple[bytes, str]:
    """构建导出 CSV 字节流（UTF-8 BOM），返回 (csv_bytes, 建议文件名)。"""
    dao = _EXPORT_DAO_MAP.get(export_type)
    if dao is None:
        raise ValueError(f"未知导出类型：{export_type}，有效值：{', '.join(EXPORT_TYPE_KEYS)}")

    rows = dao(start_date, end_date)
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    else:
        output.write("暂无数据\n")

    csv_bytes = output.getvalue().encode("utf-8-sig")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{export_type}_{ts}.csv"
    return csv_bytes, filename


def build_all_csv_zip(start_date: str | None, end_date: str | None) -> tuple[str, int]:
    """一键导出全部：把全部类型 CSV 打包为单个 ZIP（内部文件名按序号+中文名），
    返回 (临时 zip 路径, 包含的 CSV 文件数)。调用方负责用完删除临时文件。
    """
    tmp_path = os.path.join(tempfile.gettempdir(), f"export_all_{uuid.uuid4().hex}.zip")
    count = 0
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, export_type in enumerate(EXPORT_TYPE_KEYS):
            csv_bytes, _ = build_export_csv(export_type, start_date, end_date)
            label = EXPORT_TYPE_LABELS.get(export_type, export_type)
            zf.writestr(f"{i + 1:02d}_{label}.csv", csv_bytes)
            count += 1
    return tmp_path, count


def build_attachments_zip(start_date: str | None, end_date: str | None) -> tuple[str, int]:
    """按日期范围打包工单附件为 ZIP（内部按 工单号/文件名 组织），
    返回 (临时 zip 路径, 实际打包附件数)。调用方负责用完删除临时文件。
    """
    attachments = get_attachments_for_zip(start_date, end_date)

    tmp_path = os.path.join(tempfile.gettempdir(), f"attachments_export_{uuid.uuid4().hex}.zip")
    added = 0
    used_names: dict[str, set[str]] = {}
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for att in attachments:
            # 防路径穿越：工单号/存储名/原文件名均只取 basename
            folder = os.path.basename(att["complaint_no"] or "")
            stored_name = os.path.basename(att["stored_name"] or "")
            if not folder:
                continue
            filepath = os.path.join(UPLOAD_DIR, folder, stored_name)
            if not os.path.exists(filepath):
                continue

            name = os.path.basename(att["filename"] or "") or stored_name
            # 同工单内重名文件追加存储名前缀，避免 ZIP 内互相覆盖
            used = used_names.setdefault(folder, set())
            if name in used:
                stem, ext = os.path.splitext(name)
                name = f"{stem}_{stored_name[:8]}{ext}"
            used.add(name)

            zf.write(filepath, os.path.join(folder, name))
            added += 1

    return tmp_path, added
