// 0727 Phase 3 知识库 API
import apiClient from './client'
import type { KBCreateRequest, KBDimensionVoteRequest } from '@/types/api'

export function searchKb(params: {
  keyword?: string
  category?: string
  quality_filter?: string
  sort_by?: string
  page?: number
  page_size?: number
}) {
  return apiClient.get('/api/knowledge', { params })
}

export function getKbEntry(id: number) {
  return apiClient.get(`/api/knowledge/${id}`)
}

export function createKbEntry(data: KBCreateRequest) {
  return apiClient.post('/api/knowledge', data)
}

export function voteUseful(id: number) {
  return apiClient.post(`/api/knowledge/${id}/useful`)
}

export function voteUnhelpful(id: number) {
  return apiClient.post(`/api/knowledge/${id}/unhelpful`)
}

export function voteDimension(id: number, dimension: string) {
  const data: KBDimensionVoteRequest = { dimension }
  return apiClient.post(`/api/knowledge/${id}/dimension`, data)
}

export function getKbQualityStats() {
  return apiClient.get('/api/knowledge/quality/stats')
}

export function getKbTopValuable(limit = 10) {
  return apiClient.get('/api/knowledge/quality/top', { params: { limit } })
}

// 0729 管理员删除知识条目
export function deleteKbEntry(id: number) {
  return apiClient.delete(`/api/knowledge/${id}`)
}

// 0805 Phase 4: 案例检索评价
export function getKbCaseFeedback(kbId: number) {
  return apiClient.get(`/api/knowledge/${kbId}/case-feedback`)
}

export function getKbCaseFeedbackStats() {
  return apiClient.get('/api/knowledge/case-feedback-stats')
}
