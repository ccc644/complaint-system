<!-- 0727 侧边栏导航 — 角色菜单过滤 + 用户信息 + 返回首页
     0727 UI 打磨：更精致的品牌区、导航项活跃态、用户卡片
     0819 移动端抽屉化：md: 以下 fixed 滑入滑出，桌面 md:static 还原文档流 -->
<template>
  <!-- 移动端：fixed + -translate-x-full 隐藏，open 时滑入；桌面 md:static 常驻 -->
  <aside
    class="fixed inset-y-0 left-0 z-50 w-56 bg-slate-900 text-white flex flex-col shrink-0 select-none
           transition-transform duration-200 ease-in-out md:static md:translate-x-0 md:transition-none"
    :class="open ? 'translate-x-0 shadow-2xl' : '-translate-x-full'"
    aria-label="主导航">
    <!-- Logo -->
    <div class="px-3 py-3 border-b border-white/10">
      <h2 class="flex items-center gap-2 text-base font-bold tracking-tight">
        <span class="w-7 h-7 rounded-lg bg-primary/25 flex items-center justify-center text-base shrink-0">🔧</span>
        <span class="text-[13px] leading-tight">客诉系统 <span class="block text-[11px] text-white/40 font-normal">v3.5.0</span></span>
      </h2>
    </div>

    <!-- 导航菜单 -->
    <nav class="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
      <!-- 0824 分隔线项（divider）渲染为分区线，其余为导航链接 -->
      <template v-for="item in visibleMenu" :key="item.path">
        <div v-if="item.divider" class="my-2 mx-3 border-t border-white/10"></div>
        <router-link v-else
          :to="item.path"
          class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-white/60
                 hover:bg-white/8 hover:text-white transition"
          active-class="!bg-white/12 !text-white font-medium">
          <span class="text-base w-5 text-center shrink-0">{{ item.icon }}</span>
          <span class="truncate">{{ item.label }}</span>
        </router-link>
      </template>
    </nav>

    <!-- 用户信息 -->
    <div class="px-3 py-3 border-t border-white/10 space-y-2">
      <div class="flex items-center gap-2.5">
        <div class="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold shrink-0 ring-2 ring-white/10">
          {{ (auth.displayName || 'U')[0] }}
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-xs font-medium text-white truncate">{{ auth.displayName }}</div>
          <!-- 0819 显示 角色 · 职位 -->
          <div class="text-[10px] text-white/40 truncate">{{ auth.role }} · {{ auth.position }}</div>
        </div>
        <span class="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0 animate-pulse"></span>
      </div>
      <button @click="handleLogout"
        class="w-full py-1.5 text-xs text-white/50 hover:text-white hover:bg-white/8 rounded-lg transition text-left px-2 font-medium">
        🚪 退出登录
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// 0819 移动端抽屉开关状态由 AppLayout 控制；菜单项点击后的关闭由 AppLayout watch 路由统一处理
defineProps<{ open?: boolean }>()

const router = useRouter()
const auth = useAuthStore()

// 0724 RBAC 菜单配置 — 同 app.py ROLE_PERMISSIONS
// 0819 v3.0 新六角色菜单
const MENU_ITEMS = [
  { path: '/',         icon: '🏠', label: '首页',     roles: ['*'] },
  { path: '/intake',   icon: '📋', label: '客诉录入', roles: ['管理员', '客服'] },
  { path: '/kanban',   icon: '📊', label: '客诉看板', roles: ['*'] },
  { path: '/work-order', icon: '🔍', label: '工单处理', roles: ['管理员', '客服', '客服主管', '办理人', '审批人', '承接人'] },
  { path: '/knowledge', icon: '📚', label: '知识库',   roles: ['管理员', '客服', '客服主管', '办理人', '审批人', '承接人'] },
  { path: '/analytics', icon: '📈', label: '客诉分析', roles: ['*'] },
  // 0824 管理员专区：系统评估上方加分隔线（仅管理员可见）
  { path: '_divider_admin', icon: '', label: '', divider: true, roles: ['管理员'] },
  { path: '/eval',     icon: '📊', label: '系统评估', roles: ['管理员'] },
  { path: '/export-center', icon: '📤', label: '导出中心', roles: ['管理员'] },
  { path: '/admin',    icon: '⚙️', label: '系统管理', roles: ['管理员'] },
]

const visibleMenu = computed(() =>
  MENU_ITEMS.filter(item => {
    const roleOk = item.roles[0] === '*'
      ? true
      : auth.role ? item.roles.includes(auth.role) : false
    return roleOk
  })
)

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>
