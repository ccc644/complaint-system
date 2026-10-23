<!-- 0724 首页仪表板 — KPI 概览 + 最近工单 + 通知中心
     对应原 app.py 首页部分（312-420 行） -->
<template>
  <AppLayout>
    <div class="p-4 sm:p-6 space-y-6">
      <!-- 欢迎横幅 -->
      <div class="bg-gradient-to-r from-primary to-violet-600 rounded-xl p-6 text-white shadow-md">
        <h1 class="text-2xl font-bold">👋 欢迎回来，{{ auth.displayName }}</h1>
        <!-- 0819 显示 角色 · 职位 -->
        <p class="text-white/70 mt-1">{{ auth.role }} · {{ auth.position }}</p>
      </div>

      <!-- KPI 概览卡片（1016 增第五卡「已撤回」：五卡互斥，可直接相加得总数） -->
      <div class="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <div class="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
          <div class="text-xs text-gray-500 mb-1">📋 总工单数</div>
          <div class="text-2xl font-bold text-gray-900">{{ stats.total }}</div>
        </div>
        <div class="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
          <div class="text-xs text-gray-500 mb-1">🔄 处理中</div>
          <div class="text-2xl font-bold text-indigo-600">{{ stats.inProgress }}</div>
        </div>
        <div class="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
          <div class="text-xs text-gray-500 mb-1">✅ 已关闭</div>
          <div class="text-2xl font-bold text-green-600">{{ stats.closed }}</div>
        </div>
        <div class="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
          <div class="text-xs text-gray-500 mb-1">⚠️ 待处理</div>
          <div class="text-2xl font-bold text-orange-600">{{ stats.pending }}</div>
        </div>
        <div class="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
          <div class="text-xs text-gray-500 mb-1">↩️ 已撤回</div>
          <div class="text-2xl font-bold text-gray-500">{{ stats.withdrawn }}</div>
        </div>
      </div>
      <!-- 对齐提示：五卡口径互斥，总数 = 后四卡之和（1014 起服务端聚合，不再有「待处理」含「处理中」的重叠） -->
      <div class="text-xs text-gray-400 -mt-2">
        口径：总工单数 = 处理中 + 待处理 + 已关闭 + 已撤回（五卡互斥，可直接相加核对）
      </div>

      <!-- 最近工单 -->
      <div class="bg-white rounded-lg border border-gray-200 shadow-sm">
        <div class="px-5 py-3 border-b border-gray-200 flex items-center justify-between">
          <h3 class="font-semibold text-gray-800">📌 最近工单</h3>
          <router-link to="/kanban" class="text-sm text-primary hover:underline">查看全部 →</router-link>
        </div>
        <div v-if="loading" class="p-5 text-center text-gray-400 text-sm">加载中...</div>
        <div v-else-if="!recentList.length" class="p-5 text-center text-gray-400 text-sm">暂无工单数据</div>
        <div v-else class="divide-y divide-gray-100">
          <div v-for="c in recentList" :key="c.id"
            class="px-5 py-3 flex items-center justify-between flex-wrap gap-y-1 hover:bg-gray-50 cursor-pointer transition"
            @click="router.push(`/work-order/${c.id}`)">
            <div class="flex items-center gap-3">
              <span class="text-sm font-mono text-gray-600">{{ c.complaint_no }}</span>
              <span class="text-sm text-gray-700">{{ c.customer_name }}</span>
              <span class="text-xs text-gray-400 hidden sm:inline">{{ c.equipment_model }}</span>
            </div>
            <div class="flex items-center gap-2">
              <StatusBadge :status="c.status" />
              <PriorityBadge :priority="c.priority" />
            </div>
          </div>
        </div>
      </div>

      <!-- 看板快捷入口 -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <router-link v-for="item in quickLinks" :key="item.path" :to="item.path"
          class="flex items-center gap-3 bg-white rounded-lg border border-gray-200 p-4 shadow-sm hover:shadow-md hover:border-primary/30 transition group">
          <span class="text-2xl">{{ item.icon }}</span>
          <div>
            <div class="text-sm font-medium text-gray-800 group-hover:text-primary transition">{{ item.label }}</div>
            <div class="text-xs text-gray-400">{{ item.desc }}</div>
          </div>
        </router-link>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/components/layout/AppLayout.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import PriorityBadge from '@/components/common/PriorityBadge.vue'
import { listComplaints, getComplaintStats } from '@/api/complaints'

const router = useRouter()
const auth = useAuthStore()

const loading = ref(false)
const recentList = ref<any[]>([])

const stats = reactive({ total: 0, inProgress: 0, closed: 0, pending: 0, withdrawn: 0 })

// 快捷入口（0819 基于新六角色过滤）
const MENU_LINKS = [
  { path: '/kanban', icon: '📊', label: '客诉看板', desc: '全流程可视化', roles: ['*'] },
  { path: '/intake', icon: '📋', label: '客诉录入', desc: '新建投诉工单', roles: ['管理员','客服'] },
  { path: '/work-order', icon: '🔍', label: '工单处理', desc: '处理与跟进', roles: ['管理员','客服','客服主管','办理人','审批人','承接人'] },
  { path: '/knowledge', icon: '📚', label: '知识库', desc: '经验沉淀与搜索', roles: ['管理员','客服','客服主管','办理人','审批人','承接人'] },
  { path: '/analytics', icon: '📈', label: '客诉分析', desc: '数据洞察', roles: ['*'] },
]

const quickLinks = computed(() =>
  MENU_LINKS.filter(item => {
    if (item.roles[0] === '*') return true
    return auth.role ? item.roles.includes(auth.role) : false
  })
)

onMounted(async () => {
  loading.value = true
  try {
    // 1014 四卡统计改走服务端精确聚合端点（原前端拉 500 条过滤：超量低估 + 待处理含处理中重叠）
    const [res, statsRes] = await Promise.all([
      listComplaints({ limit: 10 }),
      getComplaintStats(),
    ])
    if (res.data?.success) {
      const all = res.data.data || []
      recentList.value = all.slice(0, 5)
    }
    if (statsRes.data?.success && statsRes.data.data) {
      const s = statsRes.data.data
      stats.total = s.total
      stats.inProgress = s.in_progress
      stats.closed = s.closed
      // 1014 待处理不含处理中：总 = 处理中 + 待处理 + 已关闭 + 已撤回（五卡互斥可加总）
      stats.pending = s.pending
      // 1016 新增已撤回卡（后端 stats 早已返回 withdrawn）
      stats.withdrawn = s.withdrawn ?? 0
    }
  } finally {
    loading.value = false
  }
})
</script>
