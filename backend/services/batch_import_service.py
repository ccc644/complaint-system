# 0910 批量表单导入服务
"""现场问题表（跟踪管理表/问题清单/问题统计等）→ 工单批量导入（解析 → 预览 → 逐行导入）。

0910 用户定向（最终版）：**一套系统字段词汇表 + 兼容别名**——任何 Excel 都可上传，
表头能认出的列就抓取（按文字归一化去空白后认领，非固定位置），认不出的列忽略、缺列留空；
唯一必需列是「问题描述」（找不到报错并列出可识别表头）；「状态」缺省时全部行进客服主管审核。
词汇表（标准名←别名）：提出日期←发生时间/提出时间；所属部门←问题归属；解决方案←解决方案或改善措施；
状态←结论/处理进度/未开始；计划完成日期←客户期望完成日期/预计解决时间/预计完成时间
（0916 起落库改写排期结束时间 planned_end_time，不再写 expected_complete_date）；客户名称←客户。
值约定：状态=已完成/进行中/未开始；所属部门=机械/电气/工艺/光学/软件/其他（视觉→光学）；
  优先等级=高/中/低 → P0/P1/P2（0911 改由「优先等级」驱动优先级，风险等级无系统对应、仅原文展示）；
  进度=百分比 → 工程师处理进度（处理中行按该百分比提交进度，解析不出按 0%）；
  备注=表内备注原文（0911 起不拼接 责任人/风险等级/优先等级/进度 前缀）。

状态映射（0910 用户确认）：
  已完成 → 已关闭 + KB 归档；进行中 → 责任人匹配到系统用户 → 处理中 + 承接人快照，
  否则 → 客服主管审核；未开始/空/其他 → 客服主管审核。
人员语义：表内责任人 → 流程「承接人」；表内提出人 → 工单「录入人」created_by
（仅当提出人匹配到客服角色用户才记 created_by_user_id——该 id 是客服操作隔离键，
指向非客服用户会锁死全部客服的操作入口，故非客服一律记 0）。
0916 起录入人必填：为空或未匹配系统用户整行拦截（解析行警告 + sheet 缺列文件级警告 + 提交端硬校验）。
已关闭/处理中为历史导入的显式状态 bypass（专用路径 + 工单日志留痕），不走常规状态机。
0911 通知补齐：主管审核行汇总通知客服主管；处理中行按承接人聚合同步通知（同人多单合并 1 条，
主要推进人单独点出）——不再让承接人「被指派却无感知」。
0911 编号与去向：工单编号按表内提出日期当日序号（与 created_at 对齐，手工录入不受影响）。
1009 调整：表单解决方案改为任何目标状态都直接落工单 solution 字段（同步导入）；
表单备注仍按目标状态分流——客服主管审核 → 合并一条 import_remarks 日志；处理中 → 备注一条
进度提交（pct=进度列解析值）；已关闭 → 备注进 KB 经验教训（不含表名，溯源在工单日志）、
方案进 KB 解决方案。
0914 口径调整：客户名称改选填（缺省按机台自动匹配或留空）；新增「客诉场景分类」列可选导入
（值限 SCENE_CATEGORIES，无效/缺省留空，编辑弹窗可补填）；build_template_xlsx 提供标准模板下载。
0915 机台编号拆「出厂前/后」：落库设备编号 = 出厂后 || 出厂前 || 老表单列（兜底文件名机台段/sheet 名不变）；
同机台（编号匹配，大小写不敏感，含本批次先导入行）自动双向关联——新工单写关联列表，既有工单回写追加；
出厂后编号填写但出厂前缺 → 预览警告提示补填（不阻断）。老表「设备序列号/机台编号」单列继续兼容。
1014 列名改口径：机台编号(出厂前)→「厂内编号」、机台编号(出厂后)→「出厂编号」（旧表头别名保留兼容）；
新增「实际完成时间」列（已关闭行优先落 closed_at）；模板列序照参考表 HN-B-336 交付问题处理进度表。
1016 两条口径（用户确认）：①设备型号 = 厂内编号第一个「-」前内容（厂内空取出厂编号第一段兜底；
  两编号列全空才回退历史带出）——不再依赖同机台历史工单带型号；②落库设备编号按客诉场景取号——
  工艺调试类→厂内编号优先、其余（含未填）→出厂编号优先（另一编号兜底，老列/文件名/sheet 链不变；
  预览可改场景，提交端按最新场景重算）。
"""

import io
import json
import re
from datetime import datetime, date, timedelta

import openpyxl

try:
    import xlrd
except ImportError:  # .xls 支持缺库时按需报错，不影响 .xlsx
    xlrd = None

from data.database import (
    create_complaint, create_kb_entry, create_work_order_log, create_progress_update,
    get_users_by_roles, add_assignees, set_primary_assignee,
    get_machine_history_info, find_dup_complaint_by_sn_phenomenon,
    find_complaints_by_equipment_sns, append_linked_complaint,
    get_complaint, update_complaint, get_active_assignees,
    CATEGORIES, PRIORITIES, ALL_ROLES,
)
from ai_engine.ai_engine import extract_keywords, embed_kb_entry
from services.notification_service import create_notification
from core.websocket import manager
from schemas.batch_import import (
    BATCH_TARGET_STATUSES,
    BatchPreviewRow, BatchInvalidRow,
    BatchCommitRequest, BatchCommitResultItem,
)
from schemas.complaint import SCENE_CATEGORIES


# ── 系统字段词汇表：系统字段名 → 可识别表头（0911 系统名提为首别名，提示按系统口径且表头可同名认领）──
# 0910 用户定向：任何 Excel 都可上传——表头能认出的列就抓取，认不出的忽略、缺列留空；
# 仅「问题描述」列为必需（找不到即报错并列出可识别表头）。
_UNIFIED_HEADERS = {
    "seq": ["序号"],
    "proposed_date": ["创建时间", "提出日期", "发生时间", "提出时间"],
    # 1014 列名改口径：「厂内编号」=机台身份键（原机台编号(出厂前)），「出厂编号」=出厂后 SN（原机台编号(出厂后)）；
    # 新名提为首别名（模板表头/提示口径），旧别名全部保留——存量表照常识别；
    # 别名含全/半角括号两种写法（_norm_header 只去空白不做括号归一）
    "machine_pre": ["厂内编号", "机台编号(出厂前)", "机台编号（出厂前）", "出厂前机台编号", "出厂前编号"],
    "machine_post": ["出厂编号", "机台编号(出厂后)", "机台编号（出厂后）", "出厂后机台编号", "出厂后编号"],
    "machine": ["设备序列号", "机台编号"],  # 老表单单列兼容（不进新模板）
    "customer": ["客户名称", "客户"],
    "category": ["故障分类", "所属部门", "问题归属"],
    "scene": ["客诉场景分类", "客诉场景"],  # 0914 可选导入：值限 SCENE_CATEGORIES，无效留空
    "phenomenon": ["故障现象", "问题描述"],
    "solution": ["解决方案", "解决方案或改善措施"],
    "responsible": ["承接人", "责任人"],
    "proposer": ["录入人", "提出人"],
    "risk": ["风险等级"],  # 无系统对应字段（0911 起不再映射优先级，原文并入备注）
    "priority_orig": ["优先级", "优先等级"],
    "progress": ["工程师处理进度", "进度"],
    "impact": ["影响程度", "影响"],
    "status": ["状态", "结论", "处理进度", "未开始"],  # 「未开始」兼容 EQ-500 表头误写
    # 0916 首别名改「计划完成日期」（模板表头/提示口径），「客户期望完成日期」降为兼容别名；
    # 落库目标由 expected_complete_date 改为 planned_end_time（详情页排期时间「→」后段）
    "expected_date": ["计划完成日期", "客户期望完成日期", "预计解决时间", "预计完成时间"],
    # 1014 新增「实际完成时间」列（参考 HN-B-336 交付问题处理进度表）：已关闭行优先落 closed_at
    "actual_date": ["实际完成时间", "实际完成日期"],
    "remark": ["备注"],
}
_REQUIRED_FIELDS = ("phenomenon",)  # 唯一必需列；状态缺省 → 全部客服主管审核（文件级警告）
_HINT_HIDDEN = {"seq", "risk"}  # 非系统字段不进提示：序号仅行标识，风险等级无系统对应


def _header_hint() -> str:
    """字段词汇表的人读版（界面/报错提示用）：系统字段名（或 表内叫法）。"""
    return "；".join(
        f"{v[0]}（或 {'/'.join(v[1:])}）" if len(v) > 1 else v[0]
        for k, v in _UNIFIED_HEADERS.items() if k not in _HINT_HIDDEN
    )

# 表内分类 → 系统故障分类（复合值「机械/采购」取首段；未收录 → 其他）
_CATEGORY_MAP = {"机械": "机械", "电气": "电气", "软件": "软件", "工艺": "工艺", "光学": "光学", "视觉": "光学"}
# 高/中/低 → 优先级（0911 改由「优先等级」列驱动；「风险等级」列不再参与）
_LEVEL_PRIORITY = {"高": "P0", "中": "P1", "低": "P2"}


def _norm_header(s) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _to_text(v) -> str:
    """单元格 → 干净文本（序号 1.0 → "1"；None → ""）。"""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, int):
        return str(v)
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    return str(v).strip()


def _to_date_str(v, warnings: list, label: str) -> str:
    """单元格 → YYYY-MM-DD；兼容 datetime/date/Excel 序列号/常见文本格式。"""
    if v is None or v == "":
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (int, float)):
        if 20000 <= v <= 60000:  # Excel 1900 日期系统序列号
            return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat()
        warnings.append(f"{label}非日期数值：{v}")
        return ""
    s = str(v).strip()
    m = re.match(r"^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    if s:
        warnings.append(f"{label}无法解析：{s[:30]}")
    return ""


def _parse_progress_pct(v) -> int | None:
    """单元格 → 百分比 0-100（"50%"/"50"/50.0 → 50）；解析不出返回 None（原文仍并入备注）。"""
    s = str(v if v is not None else "").strip().rstrip("%").rstrip("％").strip()
    try:
        pct = int(float(s))
    except ValueError:
        return None
    return max(0, min(100, pct))


def _machine_from_filename(filename: str) -> str:
    """从文件名提取机台编号（机台列缺省时的兜底）：取「问题/现场/清单/统计」前的机头段。"""
    stem = re.sub(r"\.(xlsx|xls)$", "", filename or "", flags=re.I).strip()
    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9 \-+#]*?)\s*(?=问题|现场|清单|统计)", stem)
    machine = (m.group(1).strip() if m and m.group(1).strip() else
               (stem.split()[0] if stem.split() else ""))
    return re.sub(r"[-\s]+$", "", machine)  # 去尾部横杠（如「EQ-200 DAF-」→「EQ-200 DAF」)


def _machine_key_from_filename(filename: str) -> str:
    """0915 自动关联用的文件名机台段（严格口径）：仅取「问题/现场/清单/统计」关键词前的机头段；
    无关键词锚点返回空——防「批量导入模板」等普通文件名首词被误当机台键互相关联。
    （_machine_from_filename 的宽松兜底只用于设备编号显示，不参与关联。）"""
    stem = re.sub(r"\.(xlsx|xls)$", "", filename or "", flags=re.I).strip()
    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9 \-+#]*?)\s*(?=问题|现场|清单|统计)", stem)
    return m.group(1).strip() if m and m.group(1).strip() else ""


def _machine_display_value(scene: str, machine_pre: str, machine_post: str, fallback: str) -> str:
    """1016 落库设备编号按客诉场景取号：工艺调试类→厂内编号优先，其余（含未填）→出厂编号优先；
    另一编号为空时互为兜底，最终 fallback（老表单列/文件名机台段/sheet 名，由调用方传入）。"""
    if scene == "工艺调试类":
        return machine_pre or machine_post or fallback
    return machine_post or machine_pre or fallback


def _model_from_machine_no(machine_pre: str, machine_post: str) -> str:
    """1016 设备型号 = 厂内编号第一个「-」之前的内容（无「-」取整列值）；
    厂内编号为空时取出厂编号第一段兜底（出厂编号通常同为型号前缀，如 EQ-200-SZ-2738→EQ-200）。"""
    raw = (machine_pre or "").strip() or (machine_post or "").strip()
    return raw.split("-", 1)[0].strip() if raw else ""


def _date_from_filename(filename: str) -> str:
    """文件名尾部 6 位日期（250919 → 2025-09-19）；提出日期列缺省时的兜底。"""
    m = re.search(r"(\d{6})(?:[.\-—_ ]|$)", re.sub(r"\.(xlsx|xls)$", "", filename or "", flags=re.I))
    if not m:
        return ""
    s = m.group(1)
    yy, mm, dd = int(s[:2]), int(s[2:4]), int(s[4:6])
    year = 2000 + yy if yy < 70 else 1900 + yy
    try:
        return date(year, mm, dd).isoformat()
    except ValueError:
        return ""


def _read_sheets(file_bytes: bytes, filename: str) -> list:
    """读工作簿 → [(sheet名, 二维网格)]；.xls 走 xlrd（日期单元格转 datetime）。"""
    is_xls = filename.lower().endswith(".xls") or file_bytes[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    if is_xls:
        if xlrd is None:
            raise ValueError("服务器未安装 xlrd，无法读取 .xls 老格式，请用 Excel 另存为 .xlsx 后重试")
        book = xlrd.open_workbook(file_contents=file_bytes)
        out = []
        for sh in book.sheets():
            grid = []
            for r in range(sh.nrows):
                row = []
                for c in range(sh.ncols):
                    cell = sh.cell(r, c)
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        row.append(xlrd.xldate_as_datetime(cell.value, book.datemode))
                    elif cell.ctype == xlrd.XL_CELL_EMPTY:
                        row.append(None)
                    else:
                        row.append(cell.value)
                grid.append(row)
            out.append((sh.name, grid))
        return out
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        ws.reset_dimensions()  # 兼容 dimension 元数据损坏的文件（部分 WPS/三方导出只声明 1 行）
        out.append((ws.title, [list(r) for r in ws.iter_rows(values_only=True)]))
    wb.close()
    return out


def _match_sheet(grid: list):
    """在前 6 行内找表头行：按词汇表逐列认领（别名任一命中即认领，取最左），
    选命中字段数最多且含「问题描述」的行 → (列映射, 表头行号)；无则 (None, -1)。"""
    best = (None, -1, -1)  # (colmap, header_idx, hits)
    for idx, row in enumerate(grid[:6]):
        if not row:
            continue
        cells = [_norm_header(c) for c in row]
        colmap = {}
        for field, aliases in _UNIFIED_HEADERS.items():
            for a in aliases:
                na = _norm_header(a)
                if na and na in cells:
                    colmap[field] = cells.index(na)
                    break
        if "phenomenon" in colmap and len(colmap) > best[2]:
            best = (colmap, idx, len(colmap))
    if best[0] is None:
        return None, -1
    return best[0], best[1]


def _cell(grid: list, r: int, colmap: dict, field: str):
    col = colmap.get(field)
    if col is None or r >= len(grid) or col >= len(grid[r]):
        return None
    return grid[r][col]


def _map_category(raw: str) -> str:
    first = re.split(r"[/、，,]", (raw or "").strip())[0].strip()
    if not first:
        return ""
    return _CATEGORY_MAP.get(first, "其他")


def _map_target_status(src_status: str, responsible_matched: list) -> str:
    s = (src_status or "").strip()
    if s == "已完成":
        return "已关闭"
    if s == "进行中":
        return "处理中" if responsible_matched else "客服主管审核"
    return "客服主管审核"  # 未开始/空/其他


# ── 导入模板生成（0914）─────────────────────────────
def build_template_xlsx() -> bytes:
    """生成批量导入标准模板 .xlsx：表头照参考表 HN-B-336 交付问题处理进度的列序与列名
    （1014 口径：厂内编号/出厂编号/实际完成时间），含示例行、取值列下拉校验与「填写说明」sheet；
    前端「下载导入模板」按钮调用。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    # 1014 模板列序照参考表 HN-B-336（18 列）；risk 重新纳入（参考表含此列），machine 老单单列不进模板。
    # 列名均为词汇表已注册别名，模板自身可直接被解析端识别。
    cols = [
        ("seq", "序号"), ("proposed_date", "提出时间"), ("proposer", "提出人"),
        ("customer", "客户名称"), ("machine_pre", "厂内编号"), ("machine_post", "出厂编号"),
        ("category", "故障分类"), ("phenomenon", "问题描述"), ("solution", "解决方案或改善措施"),
        ("responsible", "承接人"), ("risk", "风险等级"), ("priority_orig", "优先等级"),
        ("status", "状态"), ("progress", "进度"), ("expected_date", "计划完成日期"),
        ("actual_date", "实际完成时间"), ("scene", "客诉场景分类"), ("remark", "备注"),
    ]
    today_str = date.today().isoformat()
    # 示例 2 行：行1 厂内编号机台（无出厂编号/无客户）；行2 出厂编号（厂内编号仍必填用于关联）
    example_rows = [
        {
            "seq": "1", "proposed_date": today_str, "machine_pre": "EQ-200-01", "machine_post": "",
            "customer": "", "category": "机械", "scene": "工艺调试类",
            "phenomenon": "示例：涂胶头异响，设备复位后报错（仅此列必需）",
            "solution": "示例：校准涂胶阀后复测通过", "responsible": "张三/李四", "proposer": "王五",
            "risk": "", "priority_orig": "高", "progress": "50%", "impact": "中", "status": "进行中",
            "expected_date": "", "actual_date": "", "remark": "示例备注原文",
        },
        {
            "seq": "2", "proposed_date": today_str, "machine_pre": "EQ-200-01", "machine_post": "EQ-200-SZ-2000",
            "customer": "示例客户（选填）", "status": "已完成", "actual_date": today_str,
        },
    ]
    # 取值受限列 → 下拉选项（与解析端口径一致）
    dropdowns = {
        "category": list(CATEGORIES),
        "scene": list(SCENE_CATEGORIES),
        "priority_orig": ["高", "中", "低"],
        "status": ["已完成", "进行中", "未开始"],
    }

    wb = Workbook()
    ws = wb.active
    ws.title = "问题表单"
    header_fill = PatternFill("solid", fgColor="E8EEF7")
    for idx, (field, name) in enumerate(cols, start=1):
        cell = ws.cell(row=1, column=idx, value=name)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        # 列宽：现象/方案/备注宽列，其余按表头宽度略放宽
        ws.column_dimensions[get_column_letter(idx)].width = 34 if field in ("phenomenon", "solution", "remark") else max(12, len(name) * 2 + 4)
        for row_off, example_row in enumerate(example_rows, start=2):
            if field in example_row:
                ws.cell(row=row_off, column=idx, value=example_row[field])
    for field, options in dropdowns.items():
        field_idx = next((i for i, (f, _n) in enumerate(cols, start=1) if f == field), None)
        if field_idx:
            dv = DataValidation(
                type="list", formula1='"' + ",".join(options) + '"',
                allow_blank=True, showErrorMessage=False,  # 不强制，仅辅助选择
            )
            ws.add_data_validation(dv)
            dv.add(f"{get_column_letter(field_idx)}2:{get_column_letter(field_idx)}200")

    # 填写说明 sheet（与页面提示同口径）
    notes = wb.create_sheet("填写说明")
    notes.column_dimensions["A"].width = 100
    note_lines = [
        "批量导入填写说明",
        "1. 表头请按「问题表单」sheet 的列名命名（参照 HN-B-336 交付问题处理进度表）；仅「问题描述」列必需，缺「状态」列时全部行进客服主管审核，认不出的列不进行抓取。",
        "2. 厂内编号：机台统一身份键，出货后仍必须填写——系统据此自动关联同机台的既有工单。",
        "3. 出厂编号与设备编号口径：客诉场景=工艺调试类时设备编号取厂内编号，其余场景取出厂编号（另一编号为空时互为兜底）；只填出厂编号、缺厂内编号时导入将提示补填。",
        "4. 设备型号无需填写：系统自动取厂内编号（缺省取出厂编号）第一个「-」之前的内容。",
        "5. 状态：已完成 / 进行中 / 未开始。",
        "6. 故障分类：机械 / 电气 / 工艺 / 光学 / 软件 / 其他。",
        "7. 客诉场景分类（选填）：工艺调试类 / 现场交付类 / 客户正式投诉类 / 客诉诉求；留空可在导入后编辑补填。",
        "8. 优先等级：高 / 中 / 低 → 系统优先级 P0 / P1 / P2；风险等级仅入备注。",
        "9. 承接人：多人用 / 或 、 分隔，逐一匹配系统用户；「进行中」行需至少一人匹配到系统用户。",
        "10. 提出人（录入人）：必填，须为系统用户姓名；为空或未匹配系统用户该行无法导入。",
        "11. 进度：按百分比填写（如 50%），仅「进行中」行生效。",
        "12. 客户名称为选填，缺省时按机台编号自动匹配历史工单客户。",
        "13. 提出时间 / 计划完成日期 / 实际完成时间：YYYY-MM-DD（提出时间即“客诉发生时间”，仅作业务记录，不参与工单编号；工单编号按导入时间生成。缺省时取文件名尾部日期或当天；计划完成日期落工单排期结束时间；实际完成时间在「已完成」行优先作为工单关闭时间）。",
        "14. 备注为表内备注原文直接导入（按目标状态分流：待审核进工单日志 / 处理中进进度提交 / 已关闭进知识库）。",
    ]
    for i, line in enumerate(note_lines, start=1):
        c = notes.cell(row=i, column=1, value=line)
        if i == 1:
            c.font = Font(bold=True, size=12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── 解析 → 预览 ────────────────────────────────────
def parse_workbook(file_bytes: bytes, filename: str) -> dict:
    sheets = _read_sheets(file_bytes, filename)
    if not sheets:
        raise ValueError("文件中没有工作表")

    users_by_name = {u["display_name"]: u for u in get_users_by_roles(ALL_ROLES) if u.get("display_name")}
    fn_machine = _machine_from_filename(filename)
    # 0915 严格口径文件名机台段：无机台列时作为同机关联键（宽松兜底不参与关联）
    fn_machine_key = _machine_key_from_filename(filename)
    fn_date = _date_from_filename(filename)

    rows: list[dict] = []
    invalid_rows: list[dict] = []
    ignored_sheets: list[str] = []
    machine_cache: dict = {}  # 机台 → (客户名, 型号)
    seen_in_file: set = set()
    global_warnings: list[str] = []
    matched_sheets = 0

    for sheet_name, grid in sheets:
        colmap, header_idx = _match_sheet(grid)
        if colmap is None:
            ignored_sheets.append(sheet_name)
            continue
        matched_sheets += 1
        if "seq" not in colmap:
            global_warnings.append(f"sheet「{sheet_name}」未识别「序号」列，序号将以行号代替")
        if "status" not in colmap:
            global_warnings.append(f"sheet「{sheet_name}」未识别「状态」列（状态/结论/处理进度），全部行将进入客服主管审核")
        # 0916 录入人必填：缺列时各行需在预览中补填系统用户，否则整行无法导入
        if "proposer" not in colmap:
            global_warnings.append(f"sheet「{sheet_name}」未识别「录入人」列（录入人/提出人），各行需在预览中补填系统用户，否则无法导入")

        for r in range(header_idx + 1, len(grid)):
            row = grid[r]
            if not row:
                continue
            seq = _to_text(_cell(grid, r, colmap, "seq"))
            phen = _to_text(_cell(grid, r, colmap, "phenomenon"))
            if not phen and not seq:
                continue  # 空行
            if not phen:
                invalid_rows.append(BatchInvalidRow(
                    src_seq=seq or str(r + 1), src_row=r + 1,
                    reason="问题描述为空，无法导入").model_dump())
                continue

            warnings = []
            # 0914 客诉场景分类（可选导入）：值不在 SCENE_CATEGORIES 内留空，可预览中改/编辑弹窗补填
            # 1016 上移到机台编号之前——落库设备编号的取号依赖场景
            scene_raw = _to_text(_cell(grid, r, colmap, "scene"))
            scene_category = scene_raw if scene_raw in SCENE_CATEGORIES else ""
            if scene_raw and not scene_category:
                warnings.append(f"客诉场景「{scene_raw}」非有效值（{'/'.join(SCENE_CATEGORIES)}）→ 留空")

            # 0915 机台编号拆出厂前/后两列（新表）或单列（老表）；1014 起口径名为 厂内编号/出厂编号
            # 1016 落库设备编号按客诉场景取号：工艺调试类→厂内编号优先，其余（含未填）→出厂编号优先；
            # 另一编号为空时互为兜底，再兜底 老列 || 文件名机台段 || sheet 名（链不变）
            machine_pre = _to_text(_cell(grid, r, colmap, "machine_pre")).strip()
            machine_post = _to_text(_cell(grid, r, colmap, "machine_post")).strip()
            machine_legacy = _to_text(_cell(grid, r, colmap, "machine"))
            machine = _machine_display_value(
                scene_category, machine_pre, machine_post,
                machine_legacy or fn_machine or sheet_name.strip())
            # 同机台自动关联/查重的编号键：出厂后+出厂前（+老列值；无机台列时用严格口径文件名机台段），去空去重（lower 比较）
            machine_from_file = fn_machine_key if not (machine_post or machine_pre or machine_legacy) else ""
            sn_keys: list[str] = []
            for _s in (machine_post, machine_pre, machine_legacy, machine_from_file):
                if _s and all(_s.lower() != k.lower() for k in sn_keys):
                    sn_keys.append(_s)
            # 历史客户匹配按 出厂后→出厂前 优先（出厂前工单多无客户）
            hist_customer, hist_model = "", ""
            for _sn in [machine] + [s for s in sn_keys if s.lower() != machine.lower()]:
                if _sn not in machine_cache:
                    _hist = get_machine_history_info(_sn)
                    machine_cache[_sn] = ((_hist or {}).get("customer_name", ""), (_hist or {}).get("equipment_model", ""))
                hist_customer, hist_model = machine_cache[_sn]
                if hist_customer or hist_model:
                    break
            # 1016 设备型号 = 厂内编号第一「-」前内容（空则出厂编号第一段兜底；两编号列全空才回退历史带出）
            equipment_model_val = _model_from_machine_no(machine_pre, machine_post) or hist_model

            if machine_post and not machine_pre:
                warnings.append("填写了出厂编号但缺厂内编号，无法关联同机台工单——出货后也必须填写厂内编号")
            responsible = _to_text(_cell(grid, r, colmap, "responsible"))
            matched_names = [p.strip() for p in re.split(r"[/、，,]", responsible)
                             if p.strip() and p.strip() in users_by_name]
            src_status = _to_text(_cell(grid, r, colmap, "status"))
            target_status = _map_target_status(src_status, matched_names)
            if src_status == "进行中" and not matched_names:
                warnings.append("进行中但责任人未匹配到系统用户 → 转客服主管审核")

            risk = _to_text(_cell(grid, r, colmap, "risk"))
            priority_orig = _to_text(_cell(grid, r, colmap, "priority_orig"))
            # 0911 优先级由「优先等级」驱动（高/中/低→P0/P1/P2）；「风险等级」仅入备注
            priority = _LEVEL_PRIORITY.get(priority_orig, "待确认")
            if priority_orig and priority == "待确认":
                warnings.append(f"优先等级「{priority_orig}」非 高/中/低 → 优先级待确认")

            # 0911 用户定向：备注=表内备注原文（不再拼接 责任人/风险等级/优先等级/进度 前缀）
            progress = _to_text(_cell(grid, r, colmap, "progress"))
            src_remark = _to_text(_cell(grid, r, colmap, "remark"))

            customer = _to_text(_cell(grid, r, colmap, "customer"))
            customer_matched = False
            if not customer and hist_customer:
                customer, customer_matched = hist_customer, True
            proposer = _to_text(_cell(grid, r, colmap, "proposer"))
            proposer_matched = bool(proposer and proposer in users_by_name)
            # 0916 录入人必填且须为系统用户：为空/未匹配均拦截（提交端同口径硬校验）
            if not proposer:
                warnings.append("录入人为空，无法导入（可在预览中填写系统用户）")
            elif not proposer_matched:
                warnings.append(f"录入人「{proposer}」未匹配到系统用户，无法导入（可在预览中修正）")

            # 0915 查重按同机台全部编号（出厂前/后任一表示命中既有工单；文件内跨表示同键命中）
            # 1016 命中信息升级为 {id, complaint_no}：预览行带 duplicate_id 供「去修改」跳转
            _dedup_sns = sn_keys or ([machine] if machine else [])
            dup = None
            for _sn in _dedup_sns:
                dup = find_dup_complaint_by_sn_phenomenon(_sn, phen)
                if dup:
                    break
            dup_no = dup["complaint_no"] if dup else ""
            in_file_dup = False
            for _sn in _dedup_sns:
                _key = (_sn.lower(), phen)
                if _key in seen_in_file:
                    in_file_dup = True
                    break
                seen_in_file.add(_key)

            rows.append(BatchPreviewRow(
                src_seq=seq or str(r + 1),
                src_row=r + 1,
                include=not (dup_no or in_file_dup),
                src_status=src_status,
                target_status=target_status,
                fault_phenomenon=phen,
                fault_category=_map_category(_to_text(_cell(grid, r, colmap, "category"))),
                scene_category=scene_category,
                solution=_to_text(_cell(grid, r, colmap, "solution")),
                responsible=responsible,
                responsible_matched=matched_names,
                proposer=proposer,
                proposer_matched=proposer_matched,
                risk=risk,
                priority_orig=priority_orig,
                progress=progress,
                priority=priority,
                impact_level=_to_text(_cell(grid, r, colmap, "impact")),
                created_date=(_to_date_str(_cell(grid, r, colmap, "proposed_date"), warnings, "提出日期")
                              or fn_date or date.today().isoformat()),
                expected_complete_date=_to_date_str(_cell(grid, r, colmap, "expected_date"), warnings, "计划完成日期"),
                actual_date=_to_date_str(_cell(grid, r, colmap, "actual_date"), warnings, "实际完成时间"),
                machine_pre=machine_pre,
                machine_post=machine_post,
                machine_legacy=machine_legacy,
                machine_from_filename=machine_from_file,
                equipment_sn=machine,
                equipment_model=equipment_model_val,
                customer_name=customer,
                customer_matched=customer_matched,
                remarks=src_remark,
                duplicate_of=dup_no,
                duplicate_id=dup["id"] if dup else None,
                duplicate_in_file=in_file_dup,
                warnings=warnings,
            ).model_dump())

    if matched_sheets == 0:
        raise ValueError(
            "未在任何工作表识别出「问题描述」列（其余列缺省即空、表头能认出即抓取）。"
            f"可识别表头：{_header_hint()}。请调整表头后重新上传")

    summary = {
        "total": len(rows),
        "closed": sum(1 for x in rows if x["target_status"] == "已关闭"),
        "processing": sum(1 for x in rows if x["target_status"] == "处理中"),
        "review": sum(1 for x in rows if x["target_status"] == "客服主管审核"),
        "duplicates": sum(1 for x in rows if x["duplicate_of"]),
        "invalid": len(invalid_rows),
    }
    return {
        "filename": filename,
        "machine": fn_machine,
        "sheets_matched": matched_sheets,
        "sheets_ignored": ignored_sheets,
        "warnings": global_warnings,
        "unified_headers": _header_hint(),
        "rows": rows,
        "invalid_rows": invalid_rows,
        "summary": summary,
    }


# ── 逐行导入 ────────────────────────────────────────
def _archive_kb(complaint_no: str, row: BatchPreviewRow, phen: str, category: str, model: str) -> int | None:
    """已关闭行直建 KB（1016 抽出，新建/覆盖两路共用）：不走 LLM 抛光，避免一次导入几十次
    LLM 调用；embedding 照常、失败不阻塞归档（与 complaint_service._create_kb_with_embedding 同策略）。
    0911 分流：表单解决方案 → KB 解决方案；表单备注 → KB 经验教训（任一非空即建）。"""
    solution_txt = (row.solution or "").strip()[:2000]
    remarks_txt = (row.remarks or "").strip()[:2000]
    if not (solution_txt or remarks_txt):
        return None
    lesson = f"【批量导入归档】{complaint_no}"  # 0911 经验教训不写表名（工单日志已有溯源行）
    if remarks_txt:
        lesson += f"\n表单备注：{remarks_txt}"
    kb_data = {
        "complaint_no": complaint_no,
        "title": f"{row.equipment_sn or ''} {category or '其他'}问题：{phen[:30]}".strip(),
        "fault_category": category,
        "equipment_model": model,
        "fault_keywords": ", ".join(extract_keywords(f"{phen} {solution_txt} {remarks_txt}")),
        "root_cause": "",
        "solution": solution_txt[:4000],
        "checklist": "",
        "lesson_learned": lesson,
        "fault_phenomenon": phen[:1000],
    }
    kb_id = create_kb_entry(kb_data)
    try:
        embed_kb_entry(kb_id, kb_data)
    except Exception:
        pass
    return kb_id


def _import_one(row: BatchPreviewRow, ctx, operator, users_by_name) -> tuple[BatchCommitResultItem, list[int]]:
    """单行落库；返回 (结果项, 承接人 user_id 列表——仅处理中行非空，供 commit_import 聚合通知)。"""
    phen = (row.fault_phenomenon or "").strip()
    customer = (row.customer_name or "").strip()  # 0914 客户名称改选填，空串照常入库
    if not phen:
        raise ValueError("问题描述为空")

    status = row.target_status if row.target_status in BATCH_TARGET_STATUSES else "客服主管审核"
    category = row.fault_category if row.fault_category in CATEGORIES else ("其他" if row.fault_category else "")
    scene = row.scene_category if row.scene_category in SCENE_CATEGORIES else ""  # 0914 可选导入，无效回空
    priority = row.priority if row.priority in PRIORITIES or row.priority == "待确认" else "待确认"

    # 0915 同机台编号键（与解析口径一致：出厂后+出厂前+老列值+严格口径文件名机台段；不含宽松兜底/sheet 名）
    sn_keys: list[str] = []
    for _s in (row.machine_post, row.machine_pre, row.machine_legacy, row.machine_from_filename):
        _s = (_s or "").strip()
        if _s and all(_s.lower() != k.lower() for k in sn_keys):
            sn_keys.append(_s)

    # 提交时再查一次重复（防预览后库内已有人录入同问题）——按同机台全部编号查
    # 1016 分支：预览已标记的重复行（duplicate_of / 文件内重复），导入人勾选 include = 明确
    # 选择用本行覆盖旧单（人为选择，系统不自动覆盖）；预览未标记但提交时新出现（预览后他人
    # 录入）→ 维持整行报错，防误覆盖
    dup = None
    for _sn in sn_keys:
        dup = find_dup_complaint_by_sn_phenomenon(_sn, phen)
        if dup:
            break
    if dup:
        if row.duplicate_of or row.duplicate_in_file:
            return _overwrite_one(row, dup, ctx, operator, users_by_name)
        raise ValueError(f"疑似重复，已存在工单 {dup['complaint_no']}")

    # 0915 同机台自动双向关联：既有工单（含本批次先导入的行）按编号键命中即互相关联
    links = find_complaints_by_equipment_sns(sn_keys) if sn_keys else []

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created_date = row.created_date or date.today().isoformat()
    # 1016 落库设备编号按场景取号（预览可改场景，提交端按最新场景重算）：工艺调试类→厂内优先，
    # 其余→出厂优先；两编号都空时兜底预览行的 equipment_sn（含老列/文件名/sheet 兜底链）
    equipment_sn_val = _machine_display_value(
        scene, (row.machine_pre or "").strip(), (row.machine_post or "").strip(),
        (row.equipment_sn or "").strip())[:100]
    data = {
        "customer_name": customer[:200],
        "equipment_model": (row.equipment_model or "")[:100],
        "equipment_sn": equipment_sn_val,
        "fault_category": category,
        "scene_category": scene,  # 0914 起按表内「客诉场景分类」列导入（无效/缺省为空，编辑弹窗可补填）
        "fault_phenomenon": phen[:2000],
        "priority": priority,
        "impact_level": (row.impact_level or "")[:100],
        # 0916 计划完成日期改落排期结束时间（排期开始留空，详情页显示「— → 日期」）
        "planned_end_time": (row.expected_complete_date or "")[:20],
        "preliminary_category": category,  # 与录入页「初步判定分类=故障分类」同值语义
        # 1009 表单解决方案任何状态都直接落工单字段（同步导入）；备注仍按状态分流
        "solution": (row.solution or "").strip()[:2000],
        "remarks": "",
        "created_by": (row.proposer or "").strip()[:50] or operator["display_name"],
        "created_by_user_id": 0,
        "status": status,
        "sub_type": "intake" if status == "客服主管审核" else "",
        # 1019 拆分两个时间：occurred_at=表内提出日期（工单号取它）；created_at=本次导入的真实时刻
        "occurred_at": f"{created_date} 00:00:00",
        "created_at": now_str,
        "updated_at": now_str,
        "linked_complaint_ids": json.dumps(
            [{"id": x["id"], "no": x["complaint_no"]} for x in links], ensure_ascii=False),
    }

    # 提出人 → 录入人：0916 起必填且须为系统用户（为空/未匹配整行报错跳过）——
    # 服务端按最新录入人文本重查，不信任前端回传的 proposer_matched
    proposer_name = (row.proposer or "").strip()
    if not proposer_name:
        raise ValueError("录入人为空，无法导入——请在预览中填写系统用户")
    if proposer_name not in users_by_name:
        raise ValueError(f"录入人「{proposer_name}」未匹配到系统用户，无法导入——请在预览中修正")
    # 仅匹配到「客服」角色用户才记 created_by_user_id（该 id 是客服操作隔离键，
    # 指向非客服用户会锁死所有客服的操作入口，故非客服一律记 0）
    proposer_user = users_by_name.get(proposer_name)
    if proposer_user and proposer_user.get("role") == "客服":
        data["created_by_user_id"] = proposer_user["id"]

    # 处理中：责任人 → 承接人快照（0910 支持预览中编辑责任人：按最新责任人文本服务端重查，
    # 不信任前端回传的 responsible_matched 匹配结果）
    resp_names = [p.strip() for p in re.split(r"[/、，,]", (row.responsible or "")) if p.strip()]
    valid_names = [n for n in resp_names if n in users_by_name]
    assignee_ids = [users_by_name[n]["id"] for n in valid_names]
    if status == "处理中" and not assignee_ids:
        # 0910 提交端校验：无承接人的处理中工单后续无人能推进（进度/解决均需承接人身份），整行报错跳过
        raise ValueError("目标状态为处理中，但责任人未匹配到系统用户（承接人）——请改选其他状态")
    if status == "处理中":
        data["assigned_to"] = users_by_name[valid_names[0]]["display_name"]
    elif status == "已关闭" and assignee_ids:
        # 0915 已关闭历史行也记录表单责任人（指派快照+指派字段），否则预览选的责任人丢失、详情页指派为空
        data["assigned_to"] = users_by_name[valid_names[0]]["display_name"]
    if status == "已关闭":
        # 1014 关闭时间优先取表内「实际完成时间」，缺省回退计划完成日期/提出日期
        data["closed_at"] = f"{(row.actual_date or row.expected_complete_date or created_date)} 00:00:00"

    complaint_id = create_complaint(data)

    # 0915 双向关联：命中的既有工单关联列表回写追加本工单（已含同 id 自动跳过）
    for _lk in links:
        append_linked_complaint(_lk["id"], complaint_id, data["complaint_no"])

    # 0915 处理中/已关闭行都写承接人快照（已关闭为历史归档记录；审核行留给正常流程指派）
    if status in ("处理中", "已关闭") and assignee_ids:
        add_assignees(complaint_id, assignee_ids, operator["display_name"])
        set_primary_assignee(complaint_id, assignee_ids[0])

    # 已关闭 + 有解决方案/备注 → 直建 KB（不走 LLM 抛光，避免一次导入几十次 LLM 调用；embedding 照常）
    # 0911 分流：表单解决方案 → KB 解决方案；表单备注 → KB 经验教训（任一非空即建）
    # 1016 抽公共助手 _archive_kb，新建/覆盖两路共用
    remarks_txt = (row.remarks or "").strip()[:2000]
    kb_id = _archive_kb(data["complaint_no"], row, phen, category, data["equipment_model"]) if status == "已关闭" else None

    create_work_order_log(
        complaint_id=complaint_id,
        event_type="created",
        operator_name=operator["display_name"],
        operator_role=operator["role"],
        new_status=status,
        detail=f"批量导入自 {ctx.filename} 序号{row.src_seq}（历史导入，源状态：{row.src_status or '未标注'}）"
               + (f"；自动关联同机台工单 {len(links)} 条" if links else ""),
        operator_position=operator.get("position", ""),
    )

    # 0911 表单备注/进度分流（备注不落工单字段，进对应载体；解决方案 1009 起直接落工单
    # solution 字段，不再重复生成日志/进度条目；直接调 DAO 不走 update_progress——
    # 避免逐行通知审批人/WebSocket 广播）
    if status == "客服主管审核" and remarks_txt:
        create_work_order_log(
            complaint_id=complaint_id,
            event_type="import_remarks",
            operator_name=operator["display_name"],
            operator_role=operator["role"],
            detail=f"表单备注：{remarks_txt}",
            operator_position=operator.get("position", ""),
        )
    if status == "处理中":
        pct = _parse_progress_pct(row.progress) or 0
        notes = []
        if remarks_txt:
            notes.append(f"【批量导入·表单备注】{remarks_txt}")
        if not notes and pct:
            notes.append(f"【批量导入·表单进度】{row.progress}")
        for note in notes:
            create_progress_update(complaint_id, pct, note, operator["display_name"])
            create_work_order_log(
                complaint_id=complaint_id,
                event_type="progress",
                operator_name=operator["display_name"],
                operator_role=operator["role"],
                detail=f"进度更新至 {pct}%：{note}",
                operator_position=operator.get("position", ""),
            )

    item = BatchCommitResultItem(src_seq=row.src_seq, complaint_no=data["complaint_no"], status=status, kb_id=kb_id)
    return item, (assignee_ids if status == "处理中" else [])


# ── 1016 覆盖旧单（疑似重复行被勾选导入时，人为选择的执行路径）──
def _overwrite_one(row: BatchPreviewRow, dup: dict, ctx, operator, users_by_name) -> tuple[BatchCommitResultItem, list[int]]:
    """用 Excel 行的**非空字段**更新既有工单（空单元格不清空旧值；不改工单号/录入人/创建时间）。
    状态按目标状态映射推进（已关闭→KB 归档、处理中→承接人+进度、审核→备注日志），全程工单日志留痕。
    返回 (结果项 updated=True, 承接人 user_id 列表)——与 _import_one 同形，供 commit_import 聚合。"""
    phen = (row.fault_phenomenon or "").strip()
    existing = get_complaint(dup["id"])
    if not existing:
        raise ValueError(f"覆盖目标工单 {dup['complaint_no']} 已不存在（可能刚被删除）")
    old_status = existing.get("status") or ""

    status = row.target_status if row.target_status in BATCH_TARGET_STATUSES else "客服主管审核"
    category = row.fault_category if row.fault_category in CATEGORIES else ("其他" if row.fault_category else "")
    scene = row.scene_category if row.scene_category in SCENE_CATEGORIES else ""
    priority = row.priority if row.priority in PRIORITIES or row.priority == "待确认" else "待确认"

    # 承接人匹配（服务端按最新责任人文本重查，不信任前端回传——与 _import_one 同策略）
    resp_names = [p.strip() for p in re.split(r"[/、，,]", (row.responsible or "")) if p.strip()]
    valid_names = [n for n in resp_names if n in users_by_name]
    assignee_ids = [users_by_name[n]["id"] for n in valid_names]
    if status == "处理中" and not assignee_ids:
        raise ValueError("覆盖为处理中，但责任人未匹配到系统用户（承接人）——请改选其他状态")

    # 同机台编号键（与解析/新建口径一致：出厂后+出厂前+老列值+严格口径文件名机台段）
    sn_keys: list[str] = []
    for _s in (row.machine_post, row.machine_pre, row.machine_legacy, row.machine_from_filename):
        _s = (_s or "").strip()
        if _s and all(_s.lower() != k.lower() for k in sn_keys):
            sn_keys.append(_s)

    # 1016 落库设备编号按场景取号（覆盖路径同新建：预览可改场景，提交端重算）
    equipment_sn_val = _machine_display_value(
        scene, (row.machine_pre or "").strip(), (row.machine_post or "").strip(),
        (row.equipment_sn or "").strip())[:100]

    # 非空字段才覆盖（空单元格不清空旧值）；工单号/录入人/创建时间由原单保留，不进更新集
    _cand = {
        "customer_name": (row.customer_name or "").strip()[:200],
        "equipment_model": (row.equipment_model or "").strip()[:100],
        "equipment_sn": equipment_sn_val,
        # 1019 客诉发生时间按非空覆盖；created_at（录入时刻）不更新
        "occurred_at": f"{row.created_date} 00:00:00" if (row.created_date or "").strip() else "",
        "fault_category": category,
        "scene_category": scene,
        "fault_phenomenon": phen[:2000],
        "priority": priority,
        "impact_level": (row.impact_level or "").strip()[:100],
        "planned_end_time": (row.expected_complete_date or "")[:20],
        "solution": (row.solution or "").strip()[:2000],
    }
    fields = {k: v for k, v in _cand.items() if v != ""}
    if status in ("处理中", "已关闭") and valid_names:
        fields["assigned_to"] = users_by_name[valid_names[0]]["display_name"]
    if status != old_status:
        fields["status"] = status
        fields["sub_type"] = "intake" if status == "客服主管审核" else ""
        if status == "已关闭":  # 原非已关闭 → 关闭时间优先表内「实际完成时间」（已是已关闭则保留原值）
            close_d = row.actual_date or row.expected_complete_date or row.created_date or date.today().isoformat()
            fields["closed_at"] = f"{close_d} 00:00:00"
    if fields:
        update_complaint(dup["id"], fields)

    # 承接人快照：仅追加尚不活跃的（add_assignees 裸插无去重），主要推进人按表内第一位
    if status in ("处理中", "已关闭") and assignee_ids:
        active_ids = {a["user_id"] for a in get_active_assignees(dup["id"])}
        new_ids = [uid for uid in assignee_ids if uid not in active_ids]
        if new_ids:
            add_assignees(dup["id"], new_ids, operator["display_name"])
        set_primary_assignee(dup["id"], assignee_ids[0])

    # 同机台双向关联（幂等，已含同 id 自动跳过）；覆盖自身排除
    links = [x for x in (find_complaints_by_equipment_sns(sn_keys) if sn_keys else [])
             if x["id"] != dup["id"]]
    for _lk in links:
        append_linked_complaint(dup["id"], _lk["id"], _lk["complaint_no"])
        append_linked_complaint(_lk["id"], dup["id"], dup["complaint_no"])

    # KB 归档：仅当本次由非关闭推进到已关闭（原已关闭的 KB 不重建）
    kb_id = None
    if status == "已关闭" and old_status != "已关闭":
        kb_id = _archive_kb(dup["complaint_no"], row, phen,
                            category or existing.get("fault_category") or "",
                            (row.equipment_model or "").strip() or existing.get("equipment_model") or "")

    create_work_order_log(
        complaint_id=dup["id"],
        event_type="import_overwrite",
        operator_name=operator["display_name"],
        operator_role=operator["role"],
        new_status=status,
        detail=(f"批量导入覆盖自 {ctx.filename} 序号{row.src_seq}（源状态：{row.src_status or '未标注'}；原状态：{old_status}）"
                + (f"；状态推进 {old_status} → {status}" if status != old_status else "")
                + f"；更新字段：{'、'.join(fields.keys()) or '（无）'}"
                + (f"；关联同机台工单 {len(links)} 条" if links else "")),
        operator_position=operator.get("position", ""),
    )

    # 表单备注/进度按目标状态分流（与 _import_one 同口径）
    remarks_txt = (row.remarks or "").strip()[:2000]
    if status == "客服主管审核" and remarks_txt:
        create_work_order_log(
            complaint_id=dup["id"],
            event_type="import_remarks",
            operator_name=operator["display_name"],
            operator_role=operator["role"],
            detail=f"表单备注：{remarks_txt}",
            operator_position=operator.get("position", ""),
        )
    if status == "处理中":
        pct = _parse_progress_pct(row.progress) or 0
        notes = []
        if remarks_txt:
            notes.append(f"【批量导入·表单备注】{remarks_txt}")
        if not notes and pct:
            notes.append(f"【批量导入·表单进度】{row.progress}")
        for note in notes:
            create_progress_update(dup["id"], pct, note, operator["display_name"])
            create_work_order_log(
                complaint_id=dup["id"],
                event_type="progress",
                operator_name=operator["display_name"],
                operator_role=operator["role"],
                detail=f"进度更新至 {pct}%：{note}",
                operator_position=operator.get("position", ""),
            )

    # WebSocket 通知前端刷新（与编辑接口 complaint_updated 事件同形状）
    event = {
        "type": "complaint_updated",
        "complaint_id": dup["id"],
        "complaint_no": dup["complaint_no"],
        "status": status,
        "message": f"批量导入覆盖更新：{dup['complaint_no']}（{ctx.filename or '表单'}）",
    }
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(manager.broadcast(event, target_role="全员"))
    except RuntimeError:
        pass

    item = BatchCommitResultItem(src_seq=row.src_seq, complaint_no=dup["complaint_no"],
                                 status=status, kb_id=kb_id, updated=True)
    return item, (assignee_ids if status == "处理中" else [])


def commit_import(req: BatchCommitRequest, operator: dict) -> dict:
    users_by_name = {u["display_name"]: u for u in get_users_by_roles(ALL_ROLES) if u.get("display_name")}
    users_by_id = {u["id"]: u for u in users_by_name.values()}
    created, failed = [], []
    by_status: dict = {}
    kb_created = 0
    skipped = sum(1 for r in req.rows if not r.include)
    assignee_work: dict[int, dict] = {}  # 0911 承接人 user_id → {"nos": [工单号], "primary": 主要推进人条数}

    for row in req.rows:
        if not row.include:
            continue
        try:
            item, assignee_ids = _import_one(row, req.context, operator, users_by_name)
            created.append(item.model_dump())
            by_status[item.status] = by_status.get(item.status, 0) + 1
            if item.kb_id:
                kb_created += 1
            for uid in assignee_ids:
                w = assignee_work.setdefault(uid, {"nos": [], "primary": 0})
                w["nos"].append(item.complaint_no)
                if uid == assignee_ids[0]:
                    w["primary"] += 1
        except Exception as e:  # 单行失败不回滚整批
            failed.append(BatchInvalidRow(
                src_seq=row.src_seq, src_row=row.src_row, reason=str(e)[:200]).model_dump())

    # 通知克制：不逐行发通知——主管审核行向客服主管发 1 条汇总（0911）处理中行按承接人聚合
    # 每人 1 条（同人多单合并，主要推进人单独点出），对齐常规流程「您被指派处理工单」的感知
    review_count = by_status.get("客服主管审核", 0)
    updated_count = sum(1 for x in created if x.get("updated"))  # 1016 覆盖既有工单的行
    if review_count:
        create_notification(
            complaint_no="",
            title=f"📥 批量导入：{review_count} 条新工单待审核",
            message=(f"{operator['display_name']} 批量导入 {req.context.filename or '表单'}，"
                     f"共 {len(created)} 条（含覆盖既有工单 {updated_count} 条），"
                     f"其中 {review_count} 条待您审核（客诉看板「客服主管审核」列）。"),
            target_role="客服主管",
            category="action_required",
        )
    for uid, w in assignee_work.items():
        nos_part = "、".join(w["nos"][:5]) + (f" 等 {len(w['nos'])} 条" if len(w["nos"]) > 5 else "")
        primary_part = f"，其中 {w['primary']} 条您为主要推进人" if w["primary"] else ""
        create_notification(
            complaint_no="",
            title=f"📋 批量导入：{len(w['nos'])} 条处理中工单待您处理",
            message=(f"{operator['display_name']} 批量导入 {req.context.filename or '表单'}，"
                     f"{len(w['nos'])} 条工单指派给您处理{primary_part}：{nos_part}。请前往工单处理页面。"),
            target_role=users_by_id.get(uid, {}).get("role", "全员"),
            target_user_id=uid,
            category="action_required",
        )

    if created:
        event = {
            "type": "complaint_created",
            "complaint_id": 0,
            "complaint_no": "",
            "status": "",
            "message": f"批量导入完成：新增 {len(created)} 条工单（{req.context.filename or '表单'}）",
        }
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(manager.broadcast(event, target_role="全员"))
        except RuntimeError:
            pass

    return {
        "success_count": len(created),
        "skipped": skipped,
        "by_status": by_status,
        "kb_created": kb_created,
        "created": created,
        "failed": failed,
    }
