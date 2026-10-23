<!-- 0724 顶栏 — 面包屑 + 通知铃铛 + 用户菜单
     0727 Phase 4：通知铃铛完整实现（徽章/下拉列表/30秒轮询/跳转工单）
     来源：app.py render_notifications（v2.1 Streamlit）-->
<template>
  <header class="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-4 sm:px-6 shrink-0">
    <div class="flex items-center gap-1.5 text-sm text-gray-500">
      <!-- 0819 移动端汉堡按钮（md: 以上不显示） -->
      <button class="md:hidden -ml-1.5 p-2 rounded-base text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition"
        aria-label="打开导航菜单" title="菜单" @click="emit('toggle-sidebar')">
        <Menu :size="21" />
      </button>
      <span class="text-gray-400">{{ currentPageLabel }}</span>
    </div>
    <div class="flex items-center gap-3">
      <!-- 通知铃铛（加大尺寸 + 更易读徽章） -->
      <div class="relative" ref="bellRef">
        <button @click="toggleDropdown" title="通知"
          class="relative p-2 rounded-base text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition"
          :class="{ 'bell-urgent': hasActionRequired }">
          <Bell :size="21" />
          <span v-if="notif.unreadCount > 0"
            class="absolute top-0.5 right-0.5 min-w-[18px] h-[18px] px-1 text-white text-[11px] font-semibold leading-[18px] text-center rounded-full ring-2 ring-white"
            :class="hasActionRequired ? 'bg-red-500' : (notif.categoryCounts.experience > 0 && notif.categoryCounts.action_required === 0 ? 'bg-purple-500' : 'bg-blue-500')">
            {{ notif.unreadCount > 99 ? '99+' : notif.unreadCount }}
          </span>
        </button>

        <!-- 通知下拉面板 — 0819 移动端 fixed 贴视口（面板锚点在铃铛，absolute 右对齐会溢出），sm: 起还原桌面定位 -->
        <div v-if="dropdownOpen"
          class="fixed inset-x-4 top-14 sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-96 max-h-[70vh] bg-white rounded-lg shadow-xl border border-gray-200 z-50 flex flex-col overflow-hidden">
          <!-- 面板头 -->
          <div class="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 bg-gray-50/60">
            <span class="text-sm font-semibold text-gray-800">通知 <span class="text-gray-400 font-normal tnum">({{ notif.unreadCount }})</span></span>
            <button v-if="notif.unread.length" @click="notif.markAllRead()" title="全部已读"
              class="inline-flex items-center gap-1 text-xs font-medium text-primary hover:text-primary/80 transition">
              <CheckCheck :size="14" /> 全部已读
            </button>
          </div>
          <!-- 分类标签 -->
          <div class="flex gap-1 px-3 py-2 border-b border-gray-100 bg-white">
            <button v-for="cat in [
              { key: 'all', label: '全部', count: notif.unreadCount },
              { key: 'action_required', label: '待处理', count: notif.categoryCounts.action_required || 0 },
              { key: 'awareness', label: '知会', count: notif.categoryCounts.awareness || 0 },
              { key: 'experience', label: '经验', count: notif.categoryCounts.experience || 0 },
            ]" :key="cat.key"
              @click="setCategory(cat.key)"
              class="px-2.5 py-1 rounded-full text-xs font-medium transition"
              :class="activeCategory === cat.key
                ? 'bg-primary text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'">
              {{ cat.label }}
              <span v-if="cat.count > 0" class="ml-0.5 opacity-80">({{ cat.count }})</span>
            </button>
          </div>

          <!-- 通知列表 -->
          <div class="overflow-y-auto flex-1">
            <div v-if="!filteredNotifications.length" class="flex flex-col items-center justify-center gap-2 text-gray-400 text-sm py-12">
              <BellOff :size="28" class="text-gray-300" />
              {{ activeCategory === 'all' ? '暂无未读通知' : '该分类暂无通知' }}
            </div>
            <div v-for="n in filteredNotifications" :key="n.id"
              class="px-4 py-3 border-b border-gray-50 last:border-0 hover:bg-gray-50 transition border-l-[3px]"
              :class="getCategoryClass(n.notification_category)">
              <div class="flex items-start justify-between gap-2">
                <div class="flex items-start gap-2">
                  <component :is="getCategoryIcon(n.notification_category)" :size="15"
                    class="mt-0.5 shrink-0"
                    :class="n.notification_category === 'action_required' ? 'text-amber-500' : n.notification_category === 'experience' ? 'text-purple-500' : 'text-blue-500'" />
                  <div class="text-sm font-medium text-gray-800 leading-snug">{{ n.title }}</div>
                </div>
                <button @click="notif.markRead(n.id)" title="标为已读"
                  class="shrink-0 p-1.5 rounded-full text-gray-400 hover:text-green-600 hover:bg-green-50 border border-transparent hover:border-green-200 transition"
                  @click.stop>
                  <CheckCheck :size="14" />
                </button>
              </div>
              <div class="text-xs text-gray-500 mt-0.5 line-clamp-2 ml-[23px]">{{ n.message }}</div>
              <div class="flex items-center justify-between mt-2 ml-[23px]">
                <span class="text-[11px] text-gray-400 tnum">{{ n.created_at }}</span>
                <button v-if="n.complaint_no" @click="viewComplaint(n)"
                  class="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
                  查看工单 <ArrowRight :size="13" />
                </button>
              </div>
            </div>
          </div>
          <div v-if="notif.unread.length" class="px-4 py-2 border-t border-gray-100 bg-gray-50/60 text-center">
            <router-link to="/notifications" @click="dropdownOpen = false"
              class="text-xs text-primary hover:underline font-medium">
              查看全部通知 →
            </router-link>
          </div>
        </div>
      </div>

      <!-- 用户头像 -->
      <div class="flex items-center gap-2 text-sm text-gray-600">
        <div class="w-7 h-7 rounded-full bg-primary flex items-center justify-center text-white text-xs font-medium">
          {{ (auth.displayName || 'U')[0] }}
        </div>
        <span class="hidden sm:inline">{{ auth.displayName }}</span>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import { getComplaintIdByNo } from '@/api/complaints'
import type { Notification } from '@/types/api'
import { Bell, BellOff, CheckCheck, ArrowRight, ClipboardList, Lightbulb, Menu } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'

// 0819 汉堡按钮事件：通知 AppLayout 打开移动端抽屉
const emit = defineEmits<{ (e: 'toggle-sidebar'): void }>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const notif = useNotificationsStore()
const toast = useToast()

const PAGE_LABELS: Record<string, string> = {
  '/': '🏠 首页',
  '/intake': '📋 客诉录入',
  '/kanban': '📊 客诉看板',
  '/work-order': '🔍 工单处理',
  '/knowledge': '📚 知识库',
  '/analytics': '📈 客诉分析',
  '/admin': '⚙️ 系统管理',
  '/eval': '📊 系统评估',
  '/notifications': '🔔 通知中心',
}

// 0819 /work-order/:id 等动态路径用前缀匹配，避免详情页顶栏标签为空
const currentPageLabel = computed(() =>
  PAGE_LABELS[route.path] || (route.path.startsWith('/work-order/') ? '🔍 工单处理' : '')
)

// ── 下拉面板 ────────────────────────────────
const dropdownOpen = ref(false)
const bellRef = ref<HTMLElement | null>(null)

function toggleDropdown() {
  dropdownOpen.value = !dropdownOpen.value
  if (dropdownOpen.value) notif.fetchUnread() // 打开时刷新完整列表
}

// 0729 通知分类筛选
const activeCategory = ref<string>('all')
function setCategory(cat: string) { activeCategory.value = cat }
const filteredNotifications = computed(() => {
  if (activeCategory.value === 'all') return notif.unread
  return notif.unread.filter((n: any) => n.notification_category === activeCategory.value)
})
function getCategoryIcon(cat: string) {
  if (cat === 'action_required') return ClipboardList
  if (cat === 'experience') return Lightbulb
  return Bell
}
function getCategoryClass(cat: string) {
  if (cat === 'action_required') return 'border-l-amber-500'
  if (cat === 'experience') return 'border-l-purple-500'
  return 'border-l-blue-500'
}
// 0804 改用 categoryCounts 判断（refreshCount 不更新 unread 数组，避免颜色基于过时数据）
const hasActionRequired = computed(() =>
  (notif.categoryCounts.action_required ?? 0) > 0
)

function onClickOutside(e: MouseEvent) {
  if (bellRef.value && !bellRef.value.contains(e.target as Node)) {
    dropdownOpen.value = false
  }
}

// ── 点击「查看工单」：按工单号标记已读 + 跳转 ──
// 来源：v2.1 app.py render_notifications 468-477 行
async function viewComplaint(n: Notification) {
  dropdownOpen.value = false
  await notif.markByComplaint(n.complaint_no)
  try {
    const r = await getComplaintIdByNo(n.complaint_no)
    const cid = r.data?.data?.id
    if (cid) {
      router.push(`/work-order/${cid}`)
    } else {
      toast.error('该工单已被删除')
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || '该工单已被删除')
  }
}

// ── 30 秒轮询未读数（来源：v2.1 自动刷新 30 秒开关，默认开启）──
let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  notif.fetchUnread()
  pollTimer = setInterval(() => {
    if (dropdownOpen.value) notif.fetchUnread()
    else notif.refreshCount()
  }, 30_000)
  document.addEventListener('click', onClickOutside)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  document.removeEventListener('click', onClickOutside)
})
</script>

<style scoped>
@keyframes bell-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.15); }
}
.bell-urgent { animation: bell-pulse 0.4s ease-in-out 3; }
</style>
