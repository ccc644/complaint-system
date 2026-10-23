# 0910 批量表单导入（问题跟踪表 → 工单）：请求/响应模型
"""批量导入的解析预览与提交确认模型。

0910 用户定向：不做多模板全适配——统一定义一种标准表头（14 列，问题描述/状态必需），
表单侧改表头来适配系统；表头对不上报错并提示标准表头清单。
流程：上传单个 Excel（.xlsx/.xls）→ parse 预览 → 前端可编辑（客户名/故障分类/目标状态/勾选）
→ commit 逐行导入。失败行一律以表内「序号」列原值回报。
"""

from pydantic import BaseModel, Field
from typing import Optional

# 导入行允许落库的目标状态（受控：历史归档/承接中/走正常审核）
BATCH_TARGET_STATUSES = ["已关闭", "处理中", "客服主管审核"]


class BatchPreviewRow(BaseModel):
    """预览行（commit 时前端原样回传 + 用户编辑结果）。"""
    src_seq: str = Field(default="", description="表内「序号」列原值（失败回报的定位键）")
    src_row: int = Field(default=0, description="Excel 实际行号（诊断用）")
    include: bool = Field(default=True, description="是否导入（疑似重复行默认 False）")
    src_status: str = Field(default="", description="表内状态原值")
    target_status: str = Field(default="客服主管审核", description="目标状态（可编辑）")
    fault_phenomenon: str = Field(default="", description="问题描述")
    fault_category: str = Field(default="", description="故障分类（已映射，可编辑；空=不分类）")
    scene_category: str = Field(default="", description="客诉场景分类（0914 可选导入；空=留待编辑弹窗补填）")
    solution: str = Field(default="", description="解决方案")
    responsible: str = Field(default="", description="责任人原文")
    responsible_matched: list[str] = Field(default=[], description="匹配到系统用户的承接人姓名")
    proposer: str = Field(default="", description="提出人原文（→ 工单录入人；必填系统用户，为空/未匹配该行无法导入）")
    proposer_matched: bool = Field(default=False, description="提出人是否匹配到系统用户")
    risk: str = Field(default="", description="风险等级原文（无系统对应，并入备注）")
    priority_orig: str = Field(default="", description="优先等级原文（高/中/低 → 驱动优先级）")
    progress: str = Field(default="", description="进度原文（百分比 → 处理中行的进度提交）")
    priority: str = Field(default="待确认", description="优先级（优先等级 高/中/低 → P0/P1/P2）")
    impact_level: str = Field(default="", description="影响程度")
    created_date: str = Field(default="", description="提出日期 YYYY-MM-DD")
    expected_complete_date: str = Field(default="", description="计划完成日期（落库→排期结束时间 planned_end_time）")
    actual_date: str = Field(default="", description="实际完成时间 YYYY-MM-DD（1014；已关闭行优先落 closed_at）")
    machine_pre: str = Field(default="", description="厂内编号（原机台编号(出厂前)）——机台身份键，同机关联依据（0915/1014）")
    machine_post: str = Field(default="", description="出厂编号（原机台编号(出厂后)）——非工艺调试类场景落库设备编号取此值（1016）")
    machine_legacy: str = Field(default="", description="老表「设备序列号/机台编号」单列原值（同机关联依据，0915）")
    machine_from_filename: str = Field(default="", description="文件名机台段（严格口径，无机台列时的同机关联依据，0915）")
    equipment_sn: str = Field(default="", description="机台编号（1016 按场景取号：工艺调试类=厂内||出厂，其余=出厂||厂内；再兜底老表单列）")
    equipment_model: str = Field(default="", description="设备型号（1016：厂内编号第一个「-」前内容；厂内空取出厂编号第一段；两编号全空回退历史带出）")
    customer_name: str = Field(default="", description="客户名称（可编辑；表内列或自动匹配）")
    customer_matched: bool = Field(default=False, description="客户名是否来自历史工单自动匹配")
    remarks: str = Field(default="", description="表内备注原文（不拼接责任人/风险等级等前缀）")
    duplicate_of: Optional[str] = Field(default=None, description="疑似重复的既有工单号")
    duplicate_id: Optional[int] = Field(default=None, description="1016 疑似重复既有工单的 id（前端「去修改」跳转 /work-order/{id} 用）")
    duplicate_in_file: bool = Field(default=False, description="1016 文件内重复（与先前行同机台+同现象；提交端覆盖放行依据之一）")
    warnings: list[str] = Field(default=[], description="行级警告（不阻断导入）")


class BatchInvalidRow(BaseModel):
    """无法导入的行：表内序号 + 原因。"""
    src_seq: str = ""
    src_row: int = 0
    reason: str = ""


class BatchParseResponse(BaseModel):
    filename: str = ""
    machine: str = Field(default="", description="文件名推断的机台编号（表内机台列优先）")
    sheets_matched: int = Field(default=0, description="识别出统一表头的 sheet 数")
    sheets_ignored: list[str] = Field(default=[], description="未识别而被忽略的 sheet 名")
    warnings: list[str] = Field(default=[], description="文件级警告（如缺序号列）")
    unified_headers: str = Field(default="", description="统一表头清单（提示用）")
    rows: list[BatchPreviewRow] = Field(default=[], description="可导入的预览行")
    invalid_rows: list[BatchInvalidRow] = Field(default=[], description="无法导入的行（序号+原因）")
    summary: dict = Field(default={}, description="total/closed/processing/review/duplicates/invalid")


class BatchCommitContext(BaseModel):
    filename: str = ""


class BatchCommitRequest(BaseModel):
    context: BatchCommitContext
    rows: list[BatchPreviewRow]


class BatchCommitResultItem(BaseModel):
    src_seq: str = ""
    complaint_no: str = ""
    status: str = ""
    kb_id: Optional[int] = None
    updated: bool = Field(default=False, description="1016 该行为覆盖既有工单（False=新建）")


class BatchCommitResponse(BaseModel):
    success_count: int = 0
    skipped: int = Field(default=0, description="未勾选跳过的行数")
    by_status: dict = Field(default={}, description="各目标状态创建数")
    kb_created: int = 0
    created: list[BatchCommitResultItem] = Field(default=[], description="成功行（序号→工单号）")
    failed: list[BatchInvalidRow] = Field(default=[], description="失败行（序号+原因）")
