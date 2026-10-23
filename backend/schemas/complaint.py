# 0724 投诉相关 Pydantic 模型
# 0819 v3.0 角色流程重构：状态常量单一来源，新增指派/审核请求模型
"""投诉请求/响应模型。"""

from pydantic import BaseModel, Field
from typing import Optional, Literal

from data.database import CANONICAL_STATUSES  # 0819 单一来源，消除双份漂移

CATEGORIES = ["机械", "电气", "工艺", "光学", "软件", "其他"]
PRIORITIES = ["P0", "P1", "P2", "P3"]
# 0910 客诉场景分类（录入必填）：工艺调试类/现场交付类/客户正式投诉类；0914 新增 客诉诉求
SCENE_CATEGORIES = ["工艺调试类", "现场交付类", "客户正式投诉类", "客诉诉求"]
SceneCategory = Literal["工艺调试类", "现场交付类", "客户正式投诉类", "客诉诉求"]

# 1016 工单预警关键词（两档）：低风险只知会 客服主管全员 + 承接人；
# 高风险在此外加发 HIGH_RISK_WATCHERS（按姓名精确匹配系统用户，匹配不到则跳过并提示）
WARNING_KEYWORDS_LOW = ["临期", "客户催办", "进度滞后"]
WARNING_KEYWORDS_HIGH = ["退机风险", "批量质量风险", "客诉升级"]
WARNING_KEYWORDS_ALL = WARNING_KEYWORDS_LOW + WARNING_KEYWORDS_HIGH
HIGH_RISK_WATCHERS = ["员工25", "员工26", "杜海", "张伟"]

# 1020 退回审批：审批人申请退回须由王总/关总或签（任一通过即可）
RETURN_APPROVERS = ["员工25", "员工26"]


# ── 创建请求 ───────────────────────────────────────
class ComplaintCreate(BaseModel):
    """创建投诉 — 对应原 pages/1_客诉录入.py 表单提交。"""
    customer_name: str = Field(default="", description="客户名称（0914 起选填）")
    scene_category: SceneCategory = Field(..., description="客诉场景分类（必填：工艺调试类/现场交付类/客户正式投诉类/客诉诉求）")
    equipment_model: str = Field(default="", description="设备型号")
    equipment_sn: str = Field(default="", description="设备序列号")
    device_part: str = Field(default="", description="设备部位")
    software_version: str = Field(default="", description="软件版本")
    fault_category: str = Field(default="", description="故障类别")
    fault_phenomenon: str = Field(..., description="故障现象（必填）")
    reproduction_steps: str = Field(default="", description="复现步骤")
    priority: str = Field(default="待确认", description="优先级 P0/P1/P2/P3/待确认")
    impact_level: str = Field(default="", description="影响程度")
    occurred_at: str = Field(default="", description="客诉发生时间 YYYY-MM-DD（1019；工单号日期段取此值，缺省今天）")
    expected_complete_date: str = Field(default="", description="客户期望完成日期")
    preliminary_category: str = Field(default="", description="初步分类（AI 建议）")
    created_by: str = Field(default="", description="创建人")
    customer_email: str = Field(default="", description="客户联系方式（邮箱/电话等，用于待客户确认时联系客户）")
    customer_note: str = Field(default="", description="客户备注（客户特殊要求或补充信息）")
    customer_self_check: str = Field(default="", description="AI 推荐客户自排查建议")
    is_rework: bool = Field(default=False, description="是否属于返修（录入时标记）")
    linked_complaint_ids: str = Field(default="[]", description="关联工单列表（JSON 数组 [{'id':1,'no':'CP-xxx'}]）")
    force: bool = Field(default=False, description="是否强制提交（跳过重复检测警告）")


# ── 更新请求 ───────────────────────────────────────
class ComplaintUpdate(BaseModel):
    """更新投诉 — 对应原编辑弹窗表单。"""
    customer_name: Optional[str] = None
    scene_category: Optional[SceneCategory] = None
    equipment_model: Optional[str] = None
    occurred_at: Optional[str] = None  # 1019 客诉发生时间（改它不重排工单号）
    equipment_sn: Optional[str] = None
    device_part: Optional[str] = None
    software_version: Optional[str] = None
    fault_category: Optional[str] = None
    fault_phenomenon: Optional[str] = None
    priority: Optional[str] = None
    impact_level: Optional[str] = None
    resolution_note: Optional[str] = None
    status: Optional[str] = None
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    planned_start_time: Optional[str] = None
    planned_end_time: Optional[str] = None
    estimated_hours: Optional[float] = None
    expected_complete_date: Optional[str] = None
    remarks: Optional[str] = None
    customer_note: Optional[str] = None
    customer_email: Optional[str] = None
    customer_self_check: Optional[str] = None
    linked_complaint_ids: Optional[str] = None
    # 0914 管理员改状态必填原因（仅状态变化时校验；不落库，进工单日志与通知文案）
    status_change_reason: Optional[str] = None


# ── 0819 v3.0 状态转换请求 ─────────────────────────
class IntakeReviewRequest(BaseModel):
    """客服主管客诉审核请求。
    approve: priority(P0-P3 必填) + route('待客户排查'/'指派审批人') + evaluation(审核评估，0820 必填)
    reject: rejection_note 必填
    0826 撤回动作移出审核：改由录入客服在看板发起（WithdrawRequest）
    """
    action: Literal["approve", "reject"] = Field(..., description="审核结果")
    priority: Optional[str] = Field(default=None, description="优先级 P0-P3（通过时必填）")
    route: Optional[Literal["待客户排查", "指派审批人"]] = Field(default=None, description="通过后去向")
    rejection_note: Optional[str] = Field(default=None, description="拒绝原因（拒绝时必填）")
    evaluation: Optional[str] = Field(default=None, description="客服主管审核评估（通过时必填，0820）")


class WithdrawRequest(BaseModel):
    """0826 工单撤回请求（客服录入人，全流程除已关闭/已撤回）。"""
    withdraw_note: str = Field(..., min_length=1, description="撤回原因（必填，写入工单日志，可导出）")


class InvestigationResultRequest(BaseModel):
    """待客户排查结果提交。"""
    result: Literal["resolved", "unresolved"] = Field(..., description="已解决/未解决")
    remark: Optional[str] = Field(default="", description="排查备注")


class AssignApproverRequest(BaseModel):
    """指派审批人（办理人）。0825 起指派说明必填（写入工单日志，可导出）。"""
    user_id: int = Field(..., description="审批人用户 ID（候选：办理人/审批人）")
    note: str = Field(..., min_length=1, description="指派说明（必填，进工单日志）")


class ApproverRejectRequest(BaseModel):
    """审批人「不可承接」退回。"""
    reason: str = Field(..., min_length=1, description="不可承接原因（必填）")


class HandlerRejectRequest(BaseModel):
    """0901 办理人「不可承接」退回（退回录入客服，待客服处理 rework）。"""
    reason: str = Field(..., min_length=1, description="不可承接原因（必填）")


class AssignAssigneesRequest(BaseModel):
    """审批人指派承接人（多人）+ 排期。"""
    evaluation: str = Field(..., min_length=1, description="承接可行性评估（必填）")
    estimated_hours: float = Field(..., gt=0, description="预估工时（必填，>0）")
    user_ids: list[int] = Field(..., min_length=1, description="承接人用户 ID 列表（候选：办理人/审批人/承接人）")
    planned_start: Optional[str] = Field(default="", description="计划开始时间")
    planned_end: Optional[str] = Field(default="", description="计划结束时间")
    force: bool = Field(default=False, description="是否强制指派（忽略冲突检测）")
    # 0820 主要推进人（必选，须在 user_ids 中；service 层校验）
    primary_user_id: Optional[int] = Field(default=None, description="主要推进人用户 ID（必填，须在 user_ids 中）")


class SetPrimaryRequest(BaseModel):
    """0820 变更主要推进人（审批人/管理员，处理中）。"""
    user_id: int = Field(..., description="新的主要推进人用户 ID")


class AddParticipantsRequest(BaseModel):
    """审批人追加参与人（处理中）。"""
    user_ids: list[int] = Field(..., min_length=1, description="参与人用户 ID 列表")


class CannotHandleRequest(BaseModel):
    """承接人/参与人「处理不了」回退。"""
    reason: str = Field(..., min_length=1, description="处理不了原因（必填）")


class ProgressRequest(BaseModel):
    """进度更新。"""
    progress_pct: int = Field(..., ge=0, le=100, description="进度百分比 0-100")
    note: str = Field(default="", description="进度备注")


class ResolveRequest(BaseModel):
    """解决提交。"""
    root_cause: str = Field(..., description="根本原因")
    solution: str = Field(..., description="解决方案")
    resolution_note: Optional[str] = Field(default="", description="解决备注")
    checklist: Optional[str] = Field(default="", description="检查清单")


class ConfirmRequest(BaseModel):
    """客户确认。"""
    satisfaction: int = Field(..., ge=0, le=5, description="满意度 0-5")
    is_rework: Optional[bool] = Field(default=None, description="是否返工（可选，不传则沿用录入值）")
    confirm_note: Optional[str] = Field(default="", description="确认备注")


# 0728 客户邮件
class EmailSendRequest(BaseModel):
    """发送客户邮件请求。"""
    to_email: str = Field(..., description="收件人邮箱")
    subject: str = Field(..., description="邮件主题")
    body: str = Field(..., description="邮件正文")
    attachment_ids: list[int] = Field(default=[], description="工单已有附件ID列表")


class EmailReviewRequest(BaseModel):
    """客服主管邮件审核请求。"""
    action: Literal["approved", "rejected"] = Field(..., description="审核结果")
    note: str | None = Field(default=None, description="备注（拒绝时建议填写原因）")


# 0804 邮件草稿提交审核
class EmailDraftSubmitRequest(BaseModel):
    """客服提交邮件草稿给主管审核。"""
    subject: str = Field(..., description="邮件主题")
    body: str = Field(..., description="邮件正文")


# 0806 客服排查备注
class RemarkRequest(BaseModel):
    """客服保存排查备注（仅保存，不改变状态）。"""
    remark: str = Field(..., min_length=1, description="排查备注内容")


# 1016 工单预警：客服/客服主管按关键词发起，按风险档通知到人并写工单日志
class WarningRequest(BaseModel):
    """发起工单预警。"""
    keywords: list[str] = Field(..., min_length=1, description="预警关键词（多选，取值限 WARNING_KEYWORDS_ALL）")
    note: str = Field(default="", description="补充说明（选填，随通知与日志一起展示）")


# 1020 退回审批：审批人对退回申请做通过/驳回
class ReturnReviewRequest(BaseModel):
    """审批退回申请。"""
    action: Literal["approved", "rejected"] = Field(..., description="approved=同意退回；rejected=驳回")
    note: str = Field(default="", description="审批意见（选填）")


# ── 响应模型 ───────────────────────────────────────
class AssigneeOut(BaseModel):
    """指派快照（列表响应中挂载）。"""
    user_id: int
    display_name: str = ""
    role: str = ""
    position: str = ""
    assignee_type: str = "assignee"  # approver / assignee
    is_primary: int = 0  # 0820 1=主要推进人


class ComplaintOut(BaseModel):
    """投诉完整响应 — 从 DB Row 映射。"""
    id: int
    complaint_no: str
    customer_name: str = ""
    equipment_model: str = ""
    equipment_sn: str = ""
    device_part: str = ""
    software_version: str = ""
    fault_category: str = ""
    scene_category: str = ""  # 0910 客诉场景分类（存量工单为空）
    fault_phenomenon: str = ""
    reproduction_steps: str = ""
    priority: str = "待确认"
    priority_confirmed_by: str = ""
    status: str = "待客服处理"
    sub_type: str = ""
    assigned_to: str = ""
    root_cause: str = ""
    solution: str = ""
    resolution_note: str = ""
    customer_confirmed: int = 0
    satisfaction: int = 0
    is_rework: int = 0
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""
    closed_at: Optional[str] = None
    estimated_hours: float = 0
    planned_start_time: str = ""
    planned_end_time: str = ""
    evaluated_by: str = ""
    handler_name: str = ""  # 0820 办理人（指派审批人的操作人）
    preliminary_category: str = ""
    expected_complete_date: str = ""
    impact_level: str = ""
    customer_note: str = ""
    remarks: str = ""
    customer_email: str = ""
    customer_self_check: str = ""
    linked_complaint_ids: str = "[]"
    supervisor_rejection_note: Optional[str] = None
    re_edited: int = 0  # 客服在主管退回后重新编辑过
    email_review_status: Optional[str] = None
    email_review_note: Optional[str] = None
    email_draft_content: Optional[str] = None
    # 联表数据（可选）
    assignees: Optional[list[AssigneeOut]] = None
    progress_updates: Optional[list] = None
    attachments: Optional[list] = None

    class Config:
        from_attributes = True


class ComplaintListOut(BaseModel):
    """投诉列表响应 — 精简字段，用于看板卡片。"""
    id: int
    complaint_no: str
    customer_name: str = ""
    equipment_model: str = ""
    fault_category: str = ""
    scene_category: str = ""  # 0910 客诉场景分类（看板卡片展示；存量工单为空）
    fault_phenomenon: str = ""
    priority: str = "待确认"
    status: str = "待客服处理"
    sub_type: str = ""
    assigned_to: str = ""
    estimated_hours: float = 0
    planned_start_time: str = ""
    planned_end_time: str = ""
    customer_note: str = ""
    remarks: str = ""
    customer_email: str = ""
    linked_complaint_ids: str = "[]"
    customer_self_check: str = ""
    supervisor_rejection_note: Optional[str] = None
    re_edited: int = 0  # 客服在主管退回后重新编辑过
    email_review_status: Optional[str] = None
    email_review_note: Optional[str] = None
    email_draft_content: Optional[str] = None
    assignees: Optional[list[AssigneeOut]] = None
    created_at: str = ""
    updated_at: str = ""

    class Config:
        from_attributes = True
