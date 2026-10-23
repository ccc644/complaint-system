// 0727 Phase 4 通知中心 API
import apiClient from './client'

/** 未读通知列表 */
export function getUnreadNotifications() {
  return apiClient.get('/api/notifications')
}

/** 未读通知数量（铃铛徽章） */
export function getUnreadCount() {
  return apiClient.get('/api/notifications/unread-count')
}

/** 单条标记已读 */
export function markNotificationRead(id: number) {
  return apiClient.post(`/api/notifications/${id}/read`)
}

/** 全部标记已读 */
export function markAllNotificationsRead() {
  return apiClient.post('/api/notifications/read-all')
}

/** 按工单号标记已读（点击工单跳转时调用） */
export function markNotificationsReadByComplaint(complaint_no: string) {
  return apiClient.post('/api/notifications/read-by-complaint', { complaint_no })
}

/** 0729 通知分类计数 */
export function getCategoryCounts() {
  return apiClient.get('/api/notifications/category-counts')
}

/** 0729 通知中心分页查询 */
export function getAllNotifications(page = 1, limit = 20, isRead?: string) {
  const params: Record<string, any> = { page, limit }
  if (isRead !== undefined && isRead !== null) params.is_read = isRead
  return apiClient.get('/api/notifications/all', { params })
}
