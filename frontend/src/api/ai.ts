// 0727 Phase 3 AI 接口 API
import apiClient from './client'

export function classifyComplaint(fault_phenomenon: string) {
  return apiClient.post('/api/ai/classify', { fault_phenomenon })
}

export function suggestPriority(fault_phenomenon: string, customer_note = '') {
  return apiClient.post('/api/ai/priority', { fault_phenomenon, customer_note })
}

export function diagnoseComplaint(
  fault_phenomenon: string,
  equipment_model = '',
  customer_name = '',
) {
  return apiClient.post('/api/ai/diagnose', { fault_phenomenon, equipment_model, customer_name })
}

export function extractComplaint(raw_text: string, allow_rule_fallback = false) {
  return apiClient.post('/api/ai/extract-complaint', { raw_text, allow_rule_fallback })
}

export function extractKnowledge(raw_text: string, allow_rule_fallback = false) {
  return apiClient.post('/api/ai/extract-knowledge', { raw_text, allow_rule_fallback })
}

export function semanticSearch(query: string, top_k = 10) {
  return apiClient.post('/api/ai/semantic-search', { query, top_k })
}

export function searchSimilarCases(
  fault_phenomenon: string,
  equipment_model = '',
  fault_category = '',
) {
  return apiClient.post('/api/ai/similar-cases', {
    fault_phenomenon, equipment_model, fault_category,
  })
}

export function checkDeepSeekStatus() {
  return apiClient.get('/api/ai/deepseek-status')
}

// 0728 FTS5 秒出相似案例（无需 LLM，来源 v2.1 3_工单处理.py 334-342 行）
export function findSimilarCasesQuick(fault_phenomenon: string, fault_category = '') {
  return apiClient.post('/api/ai/similar-cases-quick', { fault_phenomenon, fault_category })
}

// 0728 推荐排查清单（来源 v2.1 3_工单处理.py 345-348 行）
export function getChecklist(fault_category: string) {
  return apiClient.post('/api/ai/checklist', { fault_phenomenon: fault_category })
}

// 0728 AI 自排查推荐 — 面向客户的简单安全排查建议
export function getSelfCheckSuggestions(fault_phenomenon: string, equipment_model = '') {
  return apiClient.post('/api/ai/self-check', { fault_phenomenon, equipment_model })
}

// 0728 AI 排期建议 — 基于承接人历史+类别统计+负载（0820 支持多人协同 assignee_count）
export function getScheduleSuggestion(engineer_name: string, fault_category = '', estimated_hours = 0, assignee_count = 0) {
  return apiClient.post('/api/ai/schedule-suggestion', { engineer_name, fault_category, estimated_hours, assignee_count })
}

// 0805 Phase 4: 案例检索评价
export function submitCaseFeedback(data: {
  complaint_no: string
  kb_id: number
  kb_title: string
  source_type: string
  referenced: boolean
  match_accuracy: number
}) {
  return apiClient.post('/api/ai/case-feedback', data)
}

export function getCaseFeedback(complaintNo: string) {
  return apiClient.get('/api/ai/case-feedback', { params: { complaint_no: complaintNo } })
}
