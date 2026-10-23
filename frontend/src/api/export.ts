// 0819 系统管理导出中心 API — 管理员数据导出（CSV + 附件 ZIP）
import apiClient from './client'
import type { ExportType } from '@/types/api'

// 导出耗时可能较长（ZIP 打包），放宽超时到 5 分钟
const EXPORT_TIMEOUT = 300000

export function exportData(type: ExportType, startDate = '', endDate = '') {
  return apiClient.get('/api/export/data', {
    params: { type, start_date: startDate || undefined, end_date: endDate || undefined },
    responseType: 'blob',
    timeout: EXPORT_TIMEOUT,
  })
}

export function exportAttachmentsZip(startDate = '', endDate = '') {
  return apiClient.get('/api/export/attachments', {
    params: { start_date: startDate || undefined, end_date: endDate || undefined },
    responseType: 'blob',
    timeout: EXPORT_TIMEOUT,
  })
}

// 0819 一键导出全部：所有 CSV 打包为单个 ZIP
export function exportAllZip(startDate = '', endDate = '') {
  return apiClient.get('/api/export/all', {
    params: { start_date: startDate || undefined, end_date: endDate || undefined },
    responseType: 'blob',
    timeout: EXPORT_TIMEOUT,
  })
}
