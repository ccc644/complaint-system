// 0804 系统评估 API
import apiClient from './client'

export function getStageDuration(dateRange = '近3个月') {
  return apiClient.get('/api/eval/stage-duration', { params: { date_range: dateRange } })
}

export function getStageBlockage(dateRange = '近3个月') {
  return apiClient.get('/api/eval/stage-blockage', { params: { date_range: dateRange } })
}

// 0902: 按人卡顿统计（推进人口径）
export function getOperatorBlockage(dateRange = '近3个月', stage = '') {
  return apiClient.get('/api/eval/operator-blockage', { params: { date_range: dateRange, stage } })
}

export function getLLMHealth(dateRange = '近3个月') {
  return apiClient.get('/api/eval/llm-health', { params: { date_range: dateRange } })
}

export function getEfficiencyCompare(dateRange = '近3个月', dimension = 'priority') {
  return apiClient.get('/api/eval/efficiency-compare', { params: { date_range: dateRange, dimension } })
}

export function getBusinessQuality(dateRange = '近3个月') {
  return apiClient.get('/api/eval/business-quality', { params: { date_range: dateRange } })
}

export function submitSusSurvey(answers: number[], useModules: string[] = [], improvement = '') {
  const body: Record<string, unknown> = {}
  answers.forEach((v, i) => { body[`q${i + 1}`] = v })
  // 0923 补充题（可选，不计入 SUS 分）
  body.use_modules = useModules
  body.improvement = improvement
  return apiClient.post('/api/eval/sus-survey', body)
}

export function getSusStats() {
  return apiClient.get('/api/eval/sus-survey/stats')
}

export function checkSusCooldown() {
  return apiClient.get('/api/eval/sus-survey/check')
}

export function dismissSusSurvey() {
  return apiClient.post('/api/eval/sus-survey/dismiss')
}

// 0804 Phase 2: AI 采纳率追踪
export function recordAiAdoption(complaintNo: string, aiFunction: string, aiSuggestion: string, adopted: boolean, aiSuggestedValue?: number) {
  return apiClient.post('/api/eval/ai-adoption', { complaint_no: complaintNo, ai_function: aiFunction, ai_suggestion: aiSuggestion, adopted, ai_suggested_value: aiSuggestedValue })
}

export function getAiAdoptionStats(dateRange = '近3个月') {
  return apiClient.get('/api/eval/ai-adoption', { params: { date_range: dateRange } })
}

// 0804 Phase 2: 用户活跃度追踪
export function recordActivity(pagePath: string, action = 'page_view', metadata?: Record<string, any>) {
  return apiClient.post('/api/eval/activity', { page_path: pagePath, action, metadata })
}

export function getActivityStats(limit = 10) {
  return apiClient.get('/api/eval/activity-stats', { params: { limit } })
}

// 0804: AI 邮件草稿使用率
export function getEmailDraftUsage(dateRange = '近3个月') {
  return apiClient.get('/api/eval/email-draft-usage', { params: { date_range: dateRange } })
}

// 0805 Phase 3: 操作计时、阶段评价、排期准确度
export function getTimingStats(dateRange = '近3个月') {
  return apiClient.get('/api/eval/timing-stats', { params: { date_range: dateRange } })
}

export function getFeedbackByStage(dateRange = '近3个月') {
  return apiClient.get('/api/eval/feedback-by-stage', { params: { date_range: dateRange } })
}

export function getScheduleAccuracy(dateRange = '近3个月') {
  return apiClient.get('/api/eval/schedule-accuracy', { params: { date_range: dateRange } })
}

// 0805 Phase 4: 案例检索评价全局统计
export function getCaseFeedbackStats(dateRange = '近3个月') {
  return apiClient.get('/api/eval/case-feedback-stats', { params: { date_range: dateRange } })
}

// 0821: 工单状态停留时长明细（分页 + 排序 + 搜索；0902 加推进人筛选）
export function getStageDwellDetails(params: {
  date_range: string
  page: number
  limit?: number
  keyword?: string
  sort?: string
  operator?: string
}) {
  return apiClient.get('/api/eval/stage-dwell-details', { params })
}

// 0824 评估体系补强：通知触达 / AI采纳效果 / KB检索漏斗
export function getNotificationReach(dateRange = '近3个月') {
  return apiClient.get('/api/eval/notification-reach', { params: { date_range: dateRange } })
}

export function getAdoptionImpact(dateRange = '近3个月') {
  return apiClient.get('/api/eval/adoption-impact', { params: { date_range: dateRange } })
}

export function getKbFunnel(dateRange = '近3个月') {
  return apiClient.get('/api/eval/kb-funnel', { params: { date_range: dateRange } })
}
