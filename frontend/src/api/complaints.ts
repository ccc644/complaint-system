// 0724 投诉 API — Axios 端点封装
// 0819 v3.0：新状态机端点（指派审批人/承接人/排查结果/处理不了/邮件审核回路）
import apiClient from './client'
import type { ApiResponse, PaginatedResponse, Complaint } from '@/types/api'

export interface ComplaintFilters {
  status?: string
  category?: string
  priority?: string
  keyword?: string
  my_orders?: boolean
  page?: number
  limit?: number
}

export function listComplaints(filters: ComplaintFilters = {}) {
  return apiClient.get<PaginatedResponse<Complaint>>('/api/complaints', { params: filters })
}

/** 1014 首页四卡统计（服务端精确聚合）：总=处理中+待处理+已关闭+已撤回，待处理不含处理中 */
export function getComplaintStats() {
  return apiClient.get<ApiResponse<{
    total: number; in_progress: number; closed: number; pending: number; withdrawn: number
  }>>('/api/complaints/stats')
}

export function getComplaintById(id: number) {
  return apiClient.get<ApiResponse<Complaint>>(`/api/complaints/${id}`)
}

/** 0727 按工单号查询工单 ID（通知中心点击跳转用） */
export function getComplaintIdByNo(complaintNo: string) {
  return apiClient.get<ApiResponse<{ id: number }>>(`/api/complaints/by-no/${encodeURIComponent(complaintNo)}`)
}

export function createComplaint(data: Record<string, any>) {
  return apiClient.post<ApiResponse<{ id: number; complaint_no: string }>>('/api/complaints', data)
}

/** 0807 轻量工单搜索 — 用于关联工单选择器 */
export function searchComplaints(q: string, limit: number = 10) {
  return apiClient.get<ApiResponse<import('@/types/api').ComplaintSuggestion[]>>(
    '/api/complaints/search', { params: { q, limit } }
  )
}

/** 0915 按 ID 批量获取工单概要 — 详情页关联工单弹窗表格用 */
export function getComplaintBriefsByIds(ids: number[]) {
  return apiClient.get<ApiResponse<import('@/types/api').ComplaintBrief[]>>(
    '/api/complaints/by-ids', { params: { ids: ids.join(',') } }
  )
}

export function updateComplaint(id: number, data: Record<string, any>) {
  return apiClient.put<ApiResponse<Complaint>>(`/api/complaints/${id}`, data)
}

export function deleteComplaint(id: number) {
  return apiClient.delete<ApiResponse<null>>(`/api/complaints/${id}`)
}

// ═══════════ 0819 v3.0 新状态机端点 ═══════════

/** 客服主管客诉审核：通过（优先级+去向+审核评估）/ 拒绝（原因）。撤回已移至 withdrawComplaint（0826） */
export function intakeReview(id: number, data: {
  action: 'approve' | 'reject'
  priority?: string
  route?: string
  rejection_note?: string
  evaluation?: string       // 0820 审核评估（通过时必填）
}) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/intake-review`, data)
}

/** 0826 客服录入人撤回工单（全流程除已关闭/已撤回，原因必填写日志） */
export function withdrawComplaint(id: number, withdrawNote: string) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/withdraw`, { withdraw_note: withdrawNote })
}

/** 客服重新提交审核（待客服处理 rework → 客服主管审核） */
export function resubmitComplaint(id: number) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/resubmit`, {})
}

/** 客服提交待客户排查结果（已解决/未解决） */
export function submitInvestigationResult(id: number, result: 'resolved' | 'unresolved', remark?: string) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/investigation-result`, { result, remark: remark || '' })
}

/** 办理人指派审批人（0825 指派说明必填，写工单日志） */
export function assignApprover(id: number, userId: number, note: string) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/assign-approver`, { user_id: userId, note })
}

/** 审批人「不可承接」退回 */
export function approverReject(id: number, reason: string) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/approver-reject`, { reason })
}

/** 0901 办理人「不可承接」退回录入客服（待客服处理 rework） */
export function handlerReject(id: number, reason: string) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/handler-reject`, { reason })
}

/** 审批人指派承接人（多人）+ 排期 */
export function assignAssignees(id: number, data: {
  evaluation: string
  estimated_hours: number
  user_ids: number[]
  planned_start?: string
  planned_end?: string
  force?: boolean
  primary_user_id: number  // 0820 主要推进人（必选，须在 user_ids 中）
}) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/assign-assignees`, data)
}

/** 审批人追加参与人（处理中） */
export function addParticipants(id: number, userIds: number[]) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/participants`, { user_ids: userIds })
}

/** 0820 变更主要推进人（审批人/管理员，处理中） */
export function setPrimaryAssignee(id: number, userId: number) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/set-primary`, { user_id: userId })
}

/** 承接人/参与人「处理不了」回退 */
export function cannotHandle(id: number, reason: string) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/cannot-handle`, { reason })
}

/** 更新工单处理进度 */
export function updateProgress(id: number, progressPct: number, note: string) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/progress`, {
    progress_pct: progressPct, note,
  })
}

/** 提交解决方案 */
export function resolveComplaint(id: number, data: {
  root_cause: string
  solution: string
  resolution_note?: string
  checklist?: string
}) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/resolve`, data)
}

/** 客户确认关闭 */
export function confirmComplaint(id: number, satisfaction: number, isRework?: boolean) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/confirm`, {
    satisfaction,
    is_rework: isRework,
  })
}

// 0728 客户邮件
export function generateEmail(id: number) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/generate-email`)
}

export function sendEmail(id: number, data: { to_email: string; subject: string; body: string; attachment_ids: number[] }) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/send-email`, data)
}

// 0803 客服主管审核（0819 邮件审核回路）
export function requestEmailReview(id: number, draft: { subject: string; body: string }) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/request-email-review`, draft)
}

export function reviewEmail(id: number, action: 'approved' | 'rejected', note?: string) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/email-review`, {
    action,
    note: note || null,
  })
}

// 0803 统一工单时间线
export function getComplaintTimeline(id: number) {
  return apiClient.get<ApiResponse<import('@/types/api').WorkOrderTimeline>>(`/api/complaints/${id}/timeline`)
}

// 0806 客服排查备注（仅保存）
export function saveRemark(id: number, remark: string) {
  return apiClient.post<ApiResponse<any>>(`/api/complaints/${id}/remark`, { remark })
}

/** 侧边栏任务列表 */
export function getSidebarTasks(myOrdersOnly: boolean) {
  return apiClient.get<ApiResponse<{ pending_eval: Complaint[]; in_progress: Complaint[]; options: Complaint[] }>>(
    '/api/complaints/sidebar/tasks', { params: { my_orders_only: myOrdersOnly } }
  )
}

// ═══════════ 0910 批量表单导入（一次一个文件：解析预览 → 确认导入）═══════════

/** 上传单个表单（.xlsx/.xls）→ 识别统一表头 + 列映射 + 预览行 */
export function parseBatchImport(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return apiClient.post<ApiResponse<import('@/types/api').BatchParseResponse>>(
    '/api/batch-import/parse', fd, { headers: { 'Content-Type': 'multipart/form-data' } }
  )
}

/** 确认导入：预览行（含编辑结果）逐条创建工单，失败按表内序号回报 */
export function commitBatchImport(payload: { context: { filename: string }; rows: import('@/types/api').BatchPreviewRow[] }) {
  return apiClient.post<ApiResponse<import('@/types/api').BatchCommitResponse>>('/api/batch-import/commit', payload)
}

/** 0914 下载批量导入标准模板（.xlsx，blob 流，文件名取 Content-Disposition） */
export function downloadBatchImportTemplate() {
  return apiClient.get<Blob>('/api/batch-import/template', { responseType: 'blob' })
}

// ═══════════ 1016 工单预警 ═══════════

/** 1020 审批退回申请：approved=同意并执行原退回流转；rejected=驳回（状态不变） */
export function reviewReturn(complaintId: number, payload: { action: 'approved' | 'rejected'; note?: string }) {
  return apiClient.post<ApiResponse<{ success: boolean; message: string; action: string }>>(
    `/api/complaints/${complaintId}/return-review`, payload
  )
}

/** 发起工单预警：客服/客服主管按关键词分档通知（低风险→主管+承接人；高风险→加发指定知会人） */
export function raiseWarning(complaintId: number, payload: { keywords: string[]; note?: string }) {
  return apiClient.post<ApiResponse<import('@/types/api').WarningResult>>(
    `/api/complaints/${complaintId}/warning`, payload
  )
}
