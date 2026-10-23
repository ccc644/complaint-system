// 0724 API 类型定义 — 通用响应 + 分页
export interface ApiResponse<T = any> {
  success: boolean
  data: T | null
  message: string
}

export interface PaginationOut {
  page: number
  limit: number
  total: number
}

export interface PaginatedResponse<T = any> {
  success: boolean
  data: T[]
  message: string
  pagination: PaginationOut
}

// 0724 用户类型
// 0819 v3.0 角色重构：六角色直接选择，新增职位（position）
export type Role =
  | '管理员' | '客服' | '客服主管'
  | '办理人' | '审批人' | '承接人'

export interface User {
  id: number
  username: string
  display_name: string
  role: string        // 角色：管理员/客服/客服主管/办理人/审批人/承接人
  position: string    // 0819 公司职位
  dingtalk_userid?: string  // 0824 钉钉UserID绑定（空=未绑定）
  is_active?: boolean
}

// 0724 登录相关
// 0819 简化为账号+密码
export interface LoginRequest {
  username: string
  password: string
  remember?: boolean  // 0901 勾选「7天内自动登录」→ 后端签发 7 天长票并存入凭证保险箱
}

export interface LoginOut {
  token: string
  token_type: string
  user: User
}

// 0724 投诉相关
// 0819 v3.0 新七状态 + 子类型；0825 新增终态「已撤回」（客服主管撤回，不入知识库）
export type ComplaintStatus =
  | '待客服处理'
  | '待客户排查'
  | '客服主管审核'
  | '指派审批人'
  | '指派承接人'
  | '处理中'
  | '已关闭'
  | '已撤回'

// 0819 状态常量（收敛三处副本）；0825 末尾追加已撤回（看板最右 tab）
export const CANONICAL_STATUSES: ComplaintStatus[] = [
  '待客服处理', '待客户排查', '客服主管审核', '指派审批人', '指派承接人', '处理中', '已关闭', '已撤回',
]

// 0819 子类型：待客服处理(rework/customer_confirm) / 客服主管审核(intake/email)
export type ComplaintSubType = '' | 'rework' | 'customer_confirm' | 'intake' | 'email'

export type Priority = 'P0' | 'P1' | 'P2' | 'P3'

export type FaultCategory = '机械' | '电气' | '工艺' | '光学' | '软件' | '其他'

// 0910 客诉场景分类（录入必填，编辑弹窗可补填；''=历史工单未填）；0914 新增 客诉诉求
export type SceneCategory = '工艺调试类' | '现场交付类' | '客户正式投诉类' | '客诉诉求'
export const SCENE_CATEGORY_OPTIONS: SceneCategory[] = ['工艺调试类', '现场交付类', '客户正式投诉类', '客诉诉求']
// 1015 设备编号口径按客诉场景：工艺调试类→「厂内编号」（出厂前机台编号），其余（含未填）→「出厂编号」
export const equipmentSnLabel = (scene?: string): string => (scene === '工艺调试类' ? '厂内编号' : '出厂编号')

// 1016 工单预警关键词（与后端 schemas/complaint.py 同表）：低风险→主管+承接人；高风险→加发指定知会人
export const WARNING_KEYWORDS_LOW = ['临期', '客户催办', '进度滞后']
export const WARNING_KEYWORDS_HIGH = ['退机风险', '批量质量风险', '客诉升级']
export const HIGH_RISK_WATCHERS = ['员工25', '员工26', '杜海', '张伟']

// 1020 退回审批：审批人申请退回须由王总/关总或签
export const RETURN_APPROVERS = ['员工25', '员工26']

export interface WarningResult {
  success: boolean
  message: string
  tier: 'low' | 'high'
  keywords: string[]
  notified: string[]
  missing: string[]   // 指名人中未匹配到系统用户的姓名（未通知）
}

// 0819 指派快照
export interface AssigneeInfo {
  user_id: number
  display_name: string
  role: string
  position: string
  assignee_type: 'approver' | 'assignee'
  is_primary: number  // 0820 1=主要推进人
}

export interface Complaint {
  id: number
  complaint_no: string
  customer_name: string
  equipment_model: string
  equipment_sn: string
  software_version: string
  fault_category: FaultCategory | ''  // 0910 录入可选「不分类」后可为空
  scene_category: SceneCategory | ''
  fault_phenomenon: string
  reproduction_steps: string
  priority: Priority | '待确认'
  status: ComplaintStatus
  sub_type: ComplaintSubType
  assigned_to: string | null
  root_cause: string | null
  solution: string | null
  resolution_note: string | null
  customer_confirmed: number
  satisfaction: number | null
  is_rework: number
  created_by: string
  created_by_user_id?: number  // 0821 录入客服 ID（操作隔离用）
  handler_name: string  // 0820 办理人（指派审批人的操作人）
  estimated_hours: number | null
  planned_start_time: string | null
  planned_end_time: string | null
  evaluated_by: string | null
  expected_complete_date: string | null
  impact_level: string | null
  device_part: string
  preliminary_category: string | null
  customer_note: string
  customer_email: string
  remarks: string
  customer_self_check: string
  closed_at: string | null
  occurred_at: string | null   // 1019 客诉发生时间（工单号日期段取此值）
  created_at: string           // 1019 起为真实系统录入时刻
  updated_at: string
  linked_complaint_ids: string  // 0807 JSON 数组 [{"id":1,"no":"CP-xxx"}]
  // 0803 客服主管审核字段
  supervisor_rejection_note: string | null
  re_edited: number            // 客服在主管退回后重新编辑过 (0/1)
  email_review_status: string | null
  email_review_note: string | null
  email_draft_content: string | null      // 0804 JSON {subject, body}
  // 1020 退回审批：承接人退回需审批人批、审批人退回需员工25/员工26批；审批期间状态不变
  return_request_type: 'cannot_handle' | 'approver_reject' | null
  return_request_status: 'pending' | 'approved' | 'rejected' | null
  return_request_reason: string | null
  return_request_by: string | null
  return_request_by_id: number | null
  return_request_at: string | null
  return_review_note: string | null
  return_review_by: string | null
  return_review_at: string | null
  // 0819 指派快照（审批人 + 承接人/参与人）
  assignees?: AssigneeInfo[]
  progress_updates?: ProgressUpdate[]
  attachments?: Attachment[]
  /** 0820 指派审批人状态退回重派信息（最近一次进入该状态由 approver_rejected/cannot_handle 导致时非空） */
  rejected_info?: {
    event_type: 'approver_rejected' | 'cannot_handle'
    operator_name: string
    operator_position: string
    detail: string
    created_at: string
  } | null
}

// 0807 关联工单搜索建议（用于 LinkedComplaintPicker）
export interface ComplaintSuggestion {
  id: number
  complaint_no: string
  customer_name: string
  fault_category: string
  status: string
  responsible_dept: string
  equipment_sn: string  // 0914 起可按设备编号搜索并在下拉行展示
}

// 0915 关联工单概要（详情页关联工单弹窗表格用）
export interface ComplaintBrief {
  id: number
  complaint_no: string
  equipment_sn: string
  priority: string
  status: string
  fault_phenomenon: string
  solution: string
}

export interface ProgressUpdate {
  id: number
  complaint_id: number
  progress_pct: number
  note: string
  updated_by: string
  created_at: string
}

// 0803 统一工单日志条目（0819 职位留痕）
export interface WorkOrderLogEntry {
  id: number
  complaint_id: number
  event_type: string
  operator_name: string
  operator_role: string
  operator_dept: string
  operator_position: string
  old_status: string
  new_status: string
  detail: string
  metadata: string
  created_at: string
}

export interface WorkOrderTimeline {
  logs: WorkOrderLogEntry[]
  legacy_remarks: string
  legacy_customer_note: string
  legacy_customer_self_check: string
}

export interface Attachment {
  id: number
  complaint_id: number
  filename: string
  stored_name: string
  mime_type: string
  file_size: number
  uploaded_by: string
  uploaded_at: string
}

// 0724 知识库相关
export interface KBEntry {
  id: number
  complaint_no: string | null
  title: string
  fault_category: string
  equipment_model: string
  fault_keywords: string
  fault_phenomenon: string   // 0730 故障现象
  root_cause: string
  solution: string
  checklist: string | null
  lesson_learned: string | null
  contact_author: string | null
  useful_count: number
  unhelpful_count: number
  accuracy_votes: number
  effectiveness_votes: number
  clarity_votes: number
  customer_impact_votes: number
  presales_value_votes: number
  created_at: string
}

// 0727 Phase 3 知识库请求
export interface KBCreateRequest {
  title: string
  fault_category?: string
  equipment_model?: string
  fault_keywords?: string
  root_cause?: string
  solution?: string
  checklist?: string
  lesson_learned?: string
  contact_author?: string
  complaint_no?: string
}

export interface KBDimensionVoteRequest {
  dimension: string
}

// 0727 Phase 3 分析看板（0819 新状态 KPI；0825 加 withdrawn_count）
export interface AnalyticsKpi {
  total: number
  closed_count: number
  withdrawn_count: number
  pending_cs_count: number
  pending_customer_check_count: number
  pending_review_count: number
  pending_approver_count: number
  pending_assign_count: number
  in_progress_count: number
  pending_customer_count: number
  avg_satisfaction: number | null
  avg_processing_hours: number | null
  rework_rate_pct: number
  overdue_count: number
  [key: string]: any
}

export interface TrendPoint {
  period: string
  total: number
  closed_count: number
}

export interface DistributionItem {
  name: string
  count: number
}

export interface KbQualityStats {
  total: number
  high_value_count: number
  stale_count: number
  needs_review_count: number
  avg_positive_pct: number
  accuracy_total: number
  effectiveness_total: number
  clarity_total: number
  customer_impact_total: number
  presales_value_total: number
  dimension_eval_count: number
  top_tier_count: number
  engineer_rec_count: number
  presales_rec_count: number
}

// 0727 Phase 3 AI 接口
export interface ClassifyResult {
  category: string
  reason: string
  source: string
  confidence: number
}

export interface PriorityResult {
  priority: string
  reason: string
  confidence?: number
  matched_rules?: string[]
  source: string
}

export interface DiagnoseResult {
  preliminary_diagnosis: string
  lead_engineer: string
  participating_engineers: string
  collaboration_workflow: string
  source: string
}

export interface DeepSeekStatus {
  connected: boolean
  latency_ms: number
  error: string | null
  last_check: number
}

// 0727 通知中心相关（Phase 4）
export interface Notification {
  id: number
  complaint_no: string
  title: string
  message: string
  target_role: string
  target_dept: string
  notification_category: string  // 0729: action_required/awareness/experience
  is_read: boolean
  created_at: string
}

// 0727 Phase 4 用户管理相关
// 0819 角色下拉 + 职位
/** 用户管理列表/详情（脱敏，不含密码字段） */
export interface ManagedUser {
  id: number
  username: string
  display_name: string
  role: string
  position: string
  dingtalk_userid: string  // 0824 钉钉UserID绑定（空=未绑定）
  is_active: boolean
  created_at: string
}

/** 1009 离职交接预览结果 */
export interface HandoverPreview {
  from_user: { id: number; display_name: string }
  to_user: { id: number; display_name: string }
  as_approver: number   // 作为审批人的活跃指派数
  as_assignee: number   // 作为承接人的活跃指派数
  as_creator: number    // 作为录入客服的工单数
  total_complaints: number  // 按工单去重合计
}

export interface UserCreateRequest {
  username: string
  password: string
  display_name: string
  role: string
  position: string
  dingtalk_userid?: string
}

export interface UserUpdateRequest {
  display_name?: string
  role?: string
  position?: string
  dingtalk_userid?: string
  is_active?: boolean
}

/** 用户管理下拉元数据 — 0819 仅角色列表 */
export interface UserMeta {
  roles: string[]
}

/** 0819 指派下拉用户选项（GET /api/users/options） */
export interface UserOption {
  id: number
  username: string
  display_name: string
  role: string
  position: string
}

// 0728 客户邮件
export interface EmailDraft {
  subject: string
  body: string
  source: string
  error?: string
}

// 0729 用户评价
export interface FeedbackData {
  complaint_no: string
  feedback_type: string
  ai_accuracy: number
  ai_time_saved: string
  ai_adopted: number
  ai_comment: string
  // 0730 工单上下文 + AI 建议内容
  fault_category?: string
  equipment_model?: string
  complaint_status?: string
  responsible_dept?: string
  ai_suggestion?: string
}

// 0804 系统评估 类型
export interface StageDurationItem {
  stage: string
  count: number
  avg_hours: number
  p50_hours: number
  p95_hours: number
}

export interface StageBlockageItem {
  stage: string
  total: number
  blocked: number
  blockage_rate_pct: number
  threshold_hours: number
}

// 0821 工单状态停留时长明细（0902 段增加进入/推进操作人）
export interface StageDwellOperatorMark {
  name: string
  role: string
  position: string
  at: string
}

export interface StageDwellSegment {
  hours: number
  blocked: boolean
  enter: StageDwellOperatorMark | null
  advance: StageDwellOperatorMark | null  // 推进人（结束该段的操作人）；进行中末段为 null
}

export interface StageDwellStage {
  threshold_hours: number
  segments: StageDwellSegment[]
}

export interface StageDwellItem {
  complaint_no: string
  customer_name: string
  stages: Record<string, StageDwellStage>
}

// 0902 停留时长明细响应（operators 为推进人筛选项）
export interface StageDwellDetailsResponse {
  items: StageDwellItem[]
  thresholds: Record<string, number>
  operators: string[]
  pagination: { page: number; limit: number; total: number }
}

// 0902 按人卡顿统计（推进人口径）
export interface OperatorBlockageItem {
  operator: string
  role: string
  position: string
  total_segments: number
  blocked_segments: number
  blockage_rate_pct: number
  avg_dwell_hours: number
}

export interface OperatorBlockageStats {
  items: OperatorBlockageItem[]
  thresholds: Record<string, number>
}

// 0902 AI 采纳统计（avg_match_pct 仅文本类功能有值，其余为 null）
export interface AiAdoptionStatItem {
  ai_function: string
  total: number
  adopted_count: number
  adoption_rate_pct: number
  avg_match_pct: number | null
}

// 0902 用户活跃统计
export interface ActivityUserRow {
  username: string
  display_name: string
  role: string
  total_visits: number
  active_days: number
  last_active: string
}

export interface ActivityStats {
  dau: number
  wau: number
  mau: number
  page_heat: { page_path: string; cnt: number }[]
  role_activity: { role: string; unique_users: number; total_visits: number }[]
  user_activity: ActivityUserRow[]
}

export interface LLMHealthItem {
  function_name: string
  total_calls: number
  success_count: number
  success_rate_pct: number
  avg_latency_ms: number
  p50_latency_ms: number
  p95_latency_ms: number
  p99_latency_ms: number
}

export interface EfficiencyCompareItem {
  dimension_value: string
  stages: { stage: string; avg_hours: number; count: number }[]
}

export interface BusinessQuality {
  rework_by_category: { fault_category: string; total: number; rework_rate_pct: number; rework_count: number }[]
  satisfaction_dist: { satisfaction: number; cnt: number }[]
  rejection_by_category: { fault_category: string; total: number; rejection_rate_pct: number; rejection_count: number }[]
  avg_satisfaction: number
  overall_rework_rate: number
  overall_rejection_rate: number
  first_time_fix_rate: number
}

export interface SusSurveyStats {
  total_responses: number
  avg_score: number
  score_distribution: { score_range: string; cnt: number }[]
  by_role: { role: string; avg_score: number; cnt: number }[]
  // 0824 反馈率（下限口径：仅含明确提交/关闭弹窗者）
  dismissed_count: number
  invited_count: number
  feedback_rate_pct: number | null
  // 0923 补充题：常用功能分布 + 最近改进建议
  module_usage?: { module: string; count: number }[]
  recent_improvements?: { username: string; role: string; center: string; improvement: string; created_at: string }[]
}

// 0811 SMTP 邮箱设置
export interface SmtpConfig {
  smtp_host: string
  smtp_port: number
  smtp_user: string
  smtp_password: string
  smtp_from: string
  is_configured: boolean
}

export interface SmtpTestResult {
  success: boolean
  message: string
}

// 0824 钉钉通知配置
export interface DingtalkConfig {
  enabled: boolean
  app_key: string
  app_secret: string    // GET 时脱敏（仅末4位）
  agent_id: string
  public_base_url: string
  dry_run: boolean
  is_configured: boolean
}

export interface DingtalkTestResult {
  success: boolean
  message: string
}

// 0825 手机号查钉钉 UserID（绑定用户辅助）
export interface DingtalkUseridResult {
  success: boolean
  message: string
  userid: string
  name: string
}

// 0819 系统管理导出中心
export type ExportType =
  | 'complaints'
  | 'work_log'
  | 'kb'
  | 'user_feedback'
  | 'case_feedback'
  | 'ai_adoption'
  | 'sus_survey'
  | 'activity_log'
  | 'llm_log'
  | 'stage_dwell'
  // 0824 导出补漏
  | 'archive_log'
  | 'progress_log'
  | 'notifications'
  | 'users'
  | 'kb_feedback'
  | 'dingtalk_log'

// 0824 评估体系补强：通知触达 / AI采纳效果 / KB检索漏斗
export interface StationReachStats {
  total: number
  unread: number
  unread_rate_pct: number
  long_unread: number
  long_unread_rate_pct: number
  by_role: { target_role: string; total: number; unread: number; long_unread: number }[]
}

export interface DingtalkPushStats {
  by_status: Record<string, number>
  total: number
  success: number
  failed: number
  success_rate_pct: number | null
}

export interface NotificationReachStats {
  station: StationReachStats
  dingtalk: DingtalkPushStats
}

export interface AdoptionImpactGroup {
  complaint_count: number
  avg_hours_closed: number | null
  closed_count: number
  first_time_fix_pct: number
}

export interface AdoptionImpactStats {
  adopted: AdoptionImpactGroup | null
  not_adopted: AdoptionImpactGroup | null
}

export interface KbFunnelStats {
  kb_search_count: number
  similar_view_count: number
  case_evaluated: number
  case_referenced: number
  reference_pct: number
  kb_feedback_total: number
  kb_useful_rate_pct: number | null
}

// ═══════════ 0910 批量表单导入（问题跟踪表 → 工单）═══════════

export interface BatchPreviewRow {
  src_seq: string
  src_row: number
  include: boolean
  src_status: string
  target_status: '已关闭' | '处理中' | '客服主管审核'
  fault_phenomenon: string
  fault_category: string   // ''=不分类
  scene_category: string   // 0914 客诉场景分类（可选导入；''=留待编辑补填）
  solution: string
  responsible: string
  responsible_matched: string[]
  proposer: string
  proposer_matched: boolean
  risk: string
  priority_orig: string
  progress: string
  priority: string
  impact_level: string
  created_date: string
  expected_complete_date: string
  actual_date: string    // 1014 实际完成时间——已关闭行优先落 closed_at
  machine_pre: string    // 1014 厂内编号（原机台编号(出厂前)）——机台身份键，同机关联依据
  machine_post: string   // 1016 出厂编号——非工艺调试类场景落库设备编号取此值
  machine_legacy: string // 0915 老表「设备序列号/机台编号」单列原值（同机关联依据）
  machine_from_filename: string // 0915 严格口径文件名机台段（无机台列时的同机关联依据）
  equipment_sn: string   // 1016 按场景取号：工艺调试类=厂内优先，其余=出厂优先（另一编号兜底）
  equipment_model: string  // 1016 自动提取：厂内编号第一「-」前内容（缺省出厂编号第一段）
  customer_name: string
  customer_matched: boolean
  remarks: string
  duplicate_of: string | null
  duplicate_id: number | null  // 1016 疑似重复既有工单 id（「去修改」跳转 /work-order/{id} 用）
  duplicate_in_file: boolean   // 1016 文件内重复（与先前行同机台+同现象；勾选导入=覆盖先导入那条）
  warnings: string[]
}

export interface BatchInvalidRow {
  src_seq: string
  src_row: number
  reason: string
}

export interface BatchParseResponse {
  filename: string
  machine: string
  sheets_matched: number
  sheets_ignored: string[]
  warnings: string[]
  unified_headers: string
  rows: BatchPreviewRow[]
  invalid_rows: BatchInvalidRow[]
  summary: {
    total: number
    closed: number
    processing: number
    review: number
    duplicates: number
    invalid: number
  }
}

export interface BatchCommitResultItem {
  src_seq: string
  complaint_no: string
  status: string
  kb_id: number | null
  updated?: boolean  // 1016 true=该行覆盖了既有工单（false/缺省=新建）
}

export interface BatchCommitResponse {
  success_count: number
  skipped: number
  by_status: Record<string, number>
  kb_created: number
  created: BatchCommitResultItem[]
  failed: BatchInvalidRow[]
}
