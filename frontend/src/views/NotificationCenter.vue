<template>
  <AppLayout>
    <div class="p-6 max-w-4xl mx-auto space-y-4">
      <div class="flex items-center justify-between">
        <h1 class="text-2xl font-bold">通知中心</h1>
        <button v-if="items.length && tab === 'unread'" @click="markAllAndRefresh"
          class="text-sm text-primary hover:underline">全部已读</button>
      </div>

      <div class="flex gap-2">
        <button v-for="t in tabs" :key="t.key"
          @click="switchTab(t.key)"
          class="px-4 py-1.5 rounded-full text-sm font-medium transition"
          :class="tab === t.key ? 'bg-primary text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'">
          {{ t.label }}
        </button>
      </div>

      <div v-if="loading" class="text-center text-gray-400 py-16">加载中...</div>
      <div v-else-if="!items.length" class="text-center text-gray-400 py-16">
        {{ tab === 'unread' ? '暂无未读通知' : '暂无通知' }}
      </div>
      <div v-else class="space-y-2">
        <div v-for="n in items" :key="n.id"
          class="bg-white rounded-lg border border-gray-200 p-4 flex items-start gap-3 transition hover:shadow-sm"
          :class="{
            'opacity-60': n.is_read,
            'border-l-[3px]': true,
            'border-l-amber-500': n.notification_category === 'action_required',
            'border-l-purple-500': n.notification_category === 'experience',
            'border-l-blue-500': n.notification_category === 'awareness'
          }">
          <component :is="getIcon(n.notification_category)" :size="18" class="mt-0.5 shrink-0"
            :class="n.notification_category === 'action_required' ? 'text-amber-500' : n.notification_category === 'experience' ? 'text-purple-500' : 'text-blue-500'" />
          <div class="flex-1 min-w-0">
            <div class="flex items-start justify-between gap-2">
              <div class="text-sm font-medium text-gray-800">{{ n.title }}</div>
              <span v-if="!n.is_read" class="shrink-0 w-2 h-2 mt-1.5 rounded-full bg-primary"></span>
            </div>
            <div class="text-xs text-gray-500 mt-0.5">{{ n.message }}</div>
            <div class="flex items-center justify-between mt-2">
              <span class="text-[11px] text-gray-400 tnum">{{ n.created_at }}</span>
              <div class="flex gap-2">
                <button v-if="n.complaint_no" @click="viewComplaint(n)"
                  class="text-xs text-primary hover:underline">查看工单</button>
                <button v-if="!n.is_read" @click="markOneRead(n)"
                  class="text-xs px-2 py-0.5 rounded border border-gray-200 bg-gray-50 text-gray-500 hover:bg-green-50 hover:text-green-600 hover:border-green-300 transition">标为已读</button>
                <span v-else class="text-xs text-gray-400">已读</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 pt-4">
        <button :disabled="page <= 1" @click="goPage(page - 1)"
          class="px-3 py-1 text-sm border rounded hover:bg-gray-50 disabled:opacity-30">上一页</button>
        <span class="text-sm text-gray-500">{{ page }} / {{ totalPages }}</span>
        <button :disabled="page >= totalPages" @click="goPage(page + 1)"
          class="px-3 py-1 text-sm border rounded hover:bg-gray-50 disabled:opacity-30">下一页</button>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '@/components/layout/AppLayout.vue'
import { useNotificationsStore } from '@/stores/notifications'
import { getAllNotifications, markNotificationsReadByComplaint } from '@/api/notifications'
import { getComplaintIdByNo } from '@/api/complaints'
import { useToast } from 'vue-toastification'
import { Bell, ClipboardList, Lightbulb } from 'lucide-vue-next'
import type { Notification } from '@/types/api'

const router = useRouter()
const toast = useToast()
const notifStore = useNotificationsStore()

const items = ref<Notification[]>([])
const loading = ref(false)
const tab = ref<string>('unread')
const tabs = [
  { key: 'unread', label: '未读' },
  { key: 'all', label: '全部' },
]
const page = ref(1)
const limit = 20
const totalPages = ref(1)

function getIcon(cat: string) {
  if (cat === 'action_required') return ClipboardList
  if (cat === 'experience') return Lightbulb
  return Bell
}

async function load() {
  loading.value = true
  try {
    const isRead = tab.value === 'unread' ? '0' : undefined
    const r = await getAllNotifications(page.value, limit, isRead)
    if (r.data?.success) {
      items.value = r.data.data.items || []
      // 0820 后端不返回 total_pages（旧读法恒为 1 导致分页永远 1/1），改为按 total/limit 计算
      totalPages.value = Math.max(1, Math.ceil((r.data.data.total || 0) / limit))
    }
  } catch (e: any) {
    console.error('NotificationCenter load error:', e)
  } finally { loading.value = false }
}

function switchTab(t: string) {
  tab.value = t
  page.value = 1
  load()
}

async function markAllAndRefresh() {
  await notifStore.markAllRead()
  // 0731 全部已读后清空本地未读列表
  if (tab.value === 'unread') {
    items.value = []
  } else {
    // 全部标签页：将所有项标记为已读
    for (const item of items.value) item.is_read = true
  }
}

async function markOneRead(n: Notification) {
  // 0731 标记已读后立即更新本地列表 + store，无需手动刷新页面
  await notifStore.markRead(n.id)
  // 如果当前是未读 tab，从列表中移除该项；否则更新 is_read 状态
  if (tab.value === 'unread') {
    items.value = items.value.filter(i => i.id !== n.id)
  } else {
    const item = items.value.find(i => i.id === n.id)
    if (item) item.is_read = true
  }
  // 同步刷新 store 未读计数
  notifStore.refreshCount()
}

async function goPage(p: number) {
  page.value = p
  load()
}

async function viewComplaint(n: Notification) {
  await markNotificationsReadByComplaint(n.complaint_no)
  try {
    const r = await getComplaintIdByNo(n.complaint_no)
    const cid = r.data?.data?.id
    if (cid) {
      router.push('/work-order/' + cid)
    } else {
      toast.error('该工单已被删除')
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || '该工单已被删除')
  } finally {
    load()
    notifStore.fetchUnread()
  }
}

onMounted(() => { load() })
</script>
