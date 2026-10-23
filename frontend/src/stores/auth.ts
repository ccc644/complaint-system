// 0727 改用 sessionStorage：每个标签页独立存储 token，多角色同时登录互不干扰
// 0819 v3.0：角色六值，新增职位（position），登录仅账号+密码
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User } from '@/types/api'
import { login as loginApi, getMe } from '@/api/auth'
import { saveToVault, clearVault, setLastUser } from '@/utils/tokenVault'

const storage = sessionStorage  // 0727: 每个标签页独立的存储

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(storage.getItem('token'))
  const user = ref<User | null>(null)

  const isLoggedIn = computed(() => !!token.value)
  const role = computed(() => user.value?.role || null)
  const position = computed(() => user.value?.position || '')
  const displayName = computed(() => user.value?.display_name || '')

  function hasRole(roles: string[]): boolean {
    if (!role.value) return false
    if (roles.length === 0 || roles[0] === '*') return true
    return roles.includes(role.value)
  }

  async function login(username: string, password: string, remember = true) {
    const res = await loginApi({ username, password, remember })
    if (res.success && res.data) {
      token.value = res.data.token
      user.value = res.data.user
      const userInfo = JSON.stringify(res.data.user)
      storage.setItem('token', res.data.token)
      storage.setItem('userRole', res.data.user.role)
      storage.setItem('userInfo', userInfo)
      // 0901 凭证保险箱：勾选「7天内自动登录」才保管；不勾则作废该账号旧凭证（行为与勾选状态一致）
      // 兜底账号始终更新为本次登录者，避免共用电脑时新标签页恢复成别人
      setLastUser(username)
      if (remember) {
        saveToVault(username, {
          token: res.data.token,
          userRole: res.data.user.role,
          userInfo,
        })
      } else {
        clearVault(username)
      }
    }
    return res
  }

  function logout() {
    // 0901 退出时同步清除该账号的保险箱凭证，避免退出后被卡片自动登回
    let username = ''
    try {
      username = JSON.parse(storage.getItem('userInfo') || '{}').username || ''
    } catch {
      // ignore
    }
    if (username) clearVault(username)
    token.value = null
    user.value = null
    storage.removeItem('token')
    storage.removeItem('userRole')
    storage.removeItem('userInfo')
  }

  // 0901 路由守卫从保险箱恢复后，同步激活当前 store（守卫已写入 sessionStorage）
  function applyRestored(savedToken: string, savedUser: User) {
    token.value = savedToken
    user.value = savedUser
  }

  async function fetchMe() {
    if (!token.value) return
    try {
      const res = await getMe()
      if (res.success && res.data) {
        user.value = res.data
      }
    } catch {
      logout()
    }
  }

  // 0727 从 sessionStorage 恢复用户信息
  function restoreFromStorage() {
    if (token.value) {
      const stored = storage.getItem('userInfo')
      if (stored) {
        try {
          user.value = JSON.parse(stored)
        } catch {
          // ignore parse errors
        }
      }
    }
  }

  // 初始化时恢复
  restoreFromStorage()

  return { token, user, isLoggedIn, role, position, displayName, hasRole, login, logout, fetchMe, applyRestored }
})
