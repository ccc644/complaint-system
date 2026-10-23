// 0727 Phase 4 用户管理 API
// 0819 v3.0：角色下拉 + 职位；新增指派下拉用户列表
import apiClient from './client'
import type { UserCreateRequest, UserUpdateRequest, UserOption } from '@/types/api'

/** 角色下拉元数据 */
export function getUserMeta() {
  return apiClient.get('/api/users/meta')
}

/** 用户列表（角色筛选，可含已停用） */
export function listUsers(params: { role?: string; include_inactive?: boolean }) {
  return apiClient.get('/api/users', { params })
}

/** 0819 指派下拉用户列表（按角色过滤，登录即可访问） */
export function getUserOptions(roles: string[]) {
  return apiClient.get('/api/users/options', { params: { roles: roles.join(',') } })
}

/** 新增用户 */
export function createUser(data: UserCreateRequest) {
  return apiClient.post('/api/users', data)
}

/** 更新用户属性 */
export function updateUser(id: number, data: UserUpdateRequest) {
  return apiClient.put(`/api/users/${id}`, data)
}

/** 重置用户密码 */
export function resetUserPassword(id: number, new_password: string) {
  return apiClient.post(`/api/users/${id}/reset-password`, { new_password })
}

/** 停用用户账号（软删除） */
export function deactivateUser(id: number) {
  return apiClient.delete(`/api/users/${id}/deactivate`)
}

/** 删除用户账号（硬删除） */
export function deleteUser(id: number) {
  return apiClient.delete(`/api/users/${id}`)
}

/** 1009 离职交接预览：统计离职人员名下待移交工单 */
export function previewHandover(fromUserId: number, toUserId: number) {
  return apiClient.post('/api/users/handover/preview', { from_user_id: fromUserId, to_user_id: toUserId })
}

/** 1009 执行离职交接：移交工单（可选同时停用离职账号） */
export function executeHandover(fromUserId: number, toUserId: number, deactivate: boolean) {
  return apiClient.post('/api/users/handover', { from_user_id: fromUserId, to_user_id: toUserId, deactivate })
}
