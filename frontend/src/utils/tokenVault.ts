// 0901 登录凭证保险箱 — 按账号分钥匙存 localStorage，供钉钉卡片/新标签页自动恢复登录态
// 活动会话仍走 sessionStorage（保留 0727 多角色多标签互不干扰的设计），本模块只负责「保管」与「取回」
const VAULT_PREFIX = 'tkv:'       // tkv:{username} → { token, userRole, userInfo }
const LAST_USER_KEY = 'tkv:last'  // 本机最近一次登录的账号（无 ?u= 时的兜底）

export interface VaultEntry {
  token: string
  userRole: string
  userInfo: string
}

export function saveToVault(username: string, entry: VaultEntry) {
  try {
    localStorage.setItem(VAULT_PREFIX + username, JSON.stringify(entry))
    localStorage.setItem(LAST_USER_KEY, username)
  } catch {
    // 存储不可用（隐私模式等）时静默降级：仍按老行为每次登录
  }
}

export function readFromVault(username: string): VaultEntry | null {
  try {
    const raw = localStorage.getItem(VAULT_PREFIX + username)
    if (!raw) return null
    const v = JSON.parse(raw) as VaultEntry
    return v.token ? v : null
  } catch {
    return null
  }
}

export function setLastUser(username: string) {
  try {
    localStorage.setItem(LAST_USER_KEY, username)
  } catch {
    // ignore
  }
}

export function clearVault(username: string) {
  try {
    localStorage.removeItem(VAULT_PREFIX + username)
  } catch {
    // ignore
  }
}
