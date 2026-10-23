// 0729 用户使用评价 API
import apiClient from './client'

export function submitFeedback(data: {
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
}) {
  return apiClient.post('/api/feedback', data)
}

export function getPendingFeedback(complaintNo: string) {
  return apiClient.get('/api/feedback/pending', { params: { complaint_no: complaintNo } })
}

export function checkFeedbackExists(complaintNo: string, feedbackType: string) {
  return apiClient.get('/api/feedback/check', { params: { complaint_no: complaintNo, feedback_type: feedbackType } })
}
