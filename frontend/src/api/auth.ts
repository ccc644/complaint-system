// 0724 认证 API — login(), getMe()
import apiClient from './client'
import type { ApiResponse, LoginRequest, LoginOut, User } from '@/types/api'

export async function login(data: LoginRequest): Promise<ApiResponse<LoginOut>> {
  const res = await apiClient.post('/api/auth/login', data)
  return res.data
}

export async function getMe(): Promise<ApiResponse<User>> {
  const res = await apiClient.get('/api/auth/me')
  return res.data
}
