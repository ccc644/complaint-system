// 0727 Phase 3 分析看板 API
import apiClient from './client'

export function getKpiOverview(dateRange = '近3个月') {
  return apiClient.get('/api/analytics/kpi', { params: { date_range: dateRange } })
}

export function getTrend(dateRange = '近3个月', granularity = 'monthly') {
  return apiClient.get('/api/analytics/trend', { params: { date_range: dateRange, granularity } })
}

export function getDistribution(dateRange = '近3个月', dimension = 'category') {
  return apiClient.get('/api/analytics/distribution', { params: { date_range: dateRange, dimension } })
}

export function getKbQualityDashboard() {
  return apiClient.get('/api/analytics/kb-quality')
}
