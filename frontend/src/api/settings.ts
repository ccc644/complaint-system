// 0811 系统设置 API — SMTP 邮箱配置
import apiClient from './client'

export function getSmtpConfig() {
  return apiClient.get('/api/settings/smtp')
}

export function updateSmtpConfig(data: {
  smtp_host: string
  smtp_port: number
  smtp_user: string
  smtp_password: string
  smtp_from: string
}) {
  return apiClient.put('/api/settings/smtp', data)
}

export function testSmtpConnection(data: {
  smtp_host: string
  smtp_port: number
  smtp_user: string
  smtp_password: string
  smtp_from: string
}) {
  return apiClient.post('/api/settings/smtp/test', data)
}

// 0824 钉钉通知配置
export function getDingtalkConfig() {
  return apiClient.get('/api/settings/dingtalk')
}

export function updateDingtalkConfig(data: {
  enabled: boolean
  app_key: string
  app_secret: string
  agent_id: string
  public_base_url: string
  dry_run: boolean
}) {
  return apiClient.put('/api/settings/dingtalk', data)
}

export function testDingtalkConnection(data: {
  enabled: boolean
  app_key: string
  app_secret: string
  agent_id: string
  public_base_url: string
  dry_run: boolean
}) {
  return apiClient.post('/api/settings/dingtalk/test', data)
}

// 0825 手机号查钉钉 UserID（绑定用户辅助）
export function lookupDingtalkUserid(data: {
  mobile: string
  app_key?: string
  app_secret?: string
}) {
  return apiClient.post('/api/settings/dingtalk/userid', data)
}
