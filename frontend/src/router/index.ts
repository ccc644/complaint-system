// 0724 Vue Router 配置 — 路由定义 + 角色守卫
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { readFromVault } from '@/utils/tokenVault'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/HomeView.vue'),
    meta: { roles: ['*'] },
  },
  {
    path: '/intake',
    name: 'ComplaintIntake',
    component: () => import('@/views/ComplaintIntake.vue'),
    meta: { roles: ['管理员', '客服'] },
  },
  {
    path: '/kanban',
    name: 'KanbanBoard',
    component: () => import('@/views/KanbanBoard.vue'),
    meta: { roles: ['*'] },
  },
  {
    path: '/work-order/:id?',
    name: 'WorkOrderDetail',
    component: () => import('@/views/WorkOrderDetail.vue'),
    meta: { roles: ['管理员', '客服', '客服主管', '办理人', '审批人', '承接人'] },
  },
  {
    path: '/knowledge',
    name: 'KnowledgeBase',
    component: () => import('@/views/KnowledgeBase.vue'),
    meta: { roles: ['管理员', '客服', '客服主管', '办理人', '审批人', '承接人'] },
  },
  {
    path: '/analytics',
    name: 'Analytics',
    component: () => import('@/views/Analytics.vue'),
    meta: { roles: ['*'] },
  },
  {
    path: '/notifications',
    name: 'notifications',
    component: () => import('@/views/NotificationCenter.vue'),
    meta: { title: '通知中心' },
  },
  {
    path: '/admin',
    name: 'UserManagement',
    component: () => import('@/views/UserManagement.vue'),
    meta: { roles: ['管理员'] },
  },
  {
    path: '/export-center',
    name: 'ExportCenter',
    component: () => import('@/views/ExportCenterView.vue'),
    meta: { roles: ['管理员'] },
  },
  {
    path: '/eval',
    name: 'SystemEval',
    component: () => import('@/views/SystemEval.vue'),
    meta: { roles: ['管理员'] },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 0727 改用 sessionStorage：每个标签页独立存储 token，多角色同时登录互不干扰
const storage = sessionStorage
router.beforeEach((to, _from, next) => {
  // 0901 钉钉卡片/新标签页自动恢复：优先用链接里的 ?u=账号，其次本机上次登录账号
  if (!storage.getItem('token')) {
    const q = to.query.u
    const u = (Array.isArray(q) ? q[0] : q) as string | undefined
    const candidate = u || localStorage.getItem('tkv:last') || ''
    const v = candidate ? readFromVault(candidate) : null
    if (v?.token) {
      storage.setItem('token', v.token)
      storage.setItem('userRole', v.userRole)
      storage.setItem('userInfo', v.userInfo)
      try {
        useAuthStore().applyRestored(v.token, JSON.parse(v.userInfo))
      } catch {
        // ignore
      }
    }
  }

  const token = storage.getItem('token')
  const userRole = storage.getItem('userRole')

  // 未登录用户只能访问 Login 页面
  if (to.meta.guest) {
    if (token) {
      return next('/') // 已登录用户重定向到首页
    }
    return next()
  }

  // 非 guest 页面需要登录
  if (!token) {
    // 0824 钉钉深链：携带原目标地址，登录后回跳（fullPath 为首页时无需带参）
    const target = to.fullPath
    if (target && target !== '/') {
      return next(`/login?redirect=${encodeURIComponent(target)}`)
    }
    return next('/login')
  }

  // 角色权限校验
  const allowedRoles = to.meta.roles as string[]
  if (allowedRoles && allowedRoles.length > 0 && allowedRoles[0] !== '*') {
    if (!userRole || !allowedRoles.includes(userRole)) {
      return next('/') // 无权限，重定向到首页
    }
  }

  next()
})

// 0804 Phase 2: 页面访问追踪（仅记录已登录用户）
router.afterEach((to) => {
  const token = storage.getItem('token')
  if (token && to.path !== '/login') {
    // 异步上报，不阻塞路由切换
    import('@/api/eval').then(m => {
      m.recordActivity(to.path, 'page_view').catch(() => {})
    })
  }
})

export default router
