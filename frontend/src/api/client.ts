// 0727 Axios HTTP 客户端 — JWT 拦截器 + 错误处理
import axios from 'axios'
import { useToast } from 'vue-toastification'
import { clearVault } from '@/utils/tokenVault'

// 0727 生产部署：同源访问时用相对路径（后端 serve 前端静态文件），无需跨域
// Vite 开发模式下 .env 中 VITE_API_BASE_URL=http://localhost:8506
const apiClient = axios.create({
  baseURL: import.meta.env.PROD ? '' : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8506'),
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// 0727 改用 sessionStorage：每个标签页独立存储 token，多角色同时登录互不干扰
const storage = sessionStorage
// 请求拦截器 — 自动注入 JWT Token
apiClient.interceptors.request.use(
  (config) => {
    const token = storage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// 响应拦截器 — 统一错误处理（登录接口的 401 由页面自行处理）
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // 401 — 未授权，跳转登录
    if (error.response?.status === 401) {
      const isLoginRequest = error.config?.url?.includes('/api/auth/login')
      if (!isLoginRequest) {
        // 0901 同步作废保险箱中该账号的过期凭证
        let name = ''
        try {
          name = JSON.parse(storage.getItem('userInfo') || '{}').username || ''
        } catch {
          // ignore
        }
        if (name) clearVault(name)
        storage.removeItem('token')
        storage.removeItem('userRole')
        storage.removeItem('userInfo')
        window.location.href = '/login'
      }
    }

    // 0731 400 状态过期检测 — 兜底刷新提示
    if (error.response?.status === 400) {
      const detail = error.response?.data?.detail || ''
      if (detail.includes('当前状态不允许')) {
        const toast = useToast()
        toast.error(`${detail}，页面数据已过期，请刷新页面（Ctrl+R 或 F5）`, {
          timeout: 8000,
          closeButton: 'button',
          onClick: () => window.location.reload(),
        })
      }
    }

    return Promise.reject(error)
  },
)

export default apiClient
