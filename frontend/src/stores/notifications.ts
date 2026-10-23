// 0727 Phase 4 通知中心 Pinia Store
// 0729 增加分类计数
import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as notifApi from '@/api/notifications'
import type { Notification } from '@/types/api'

export const useNotificationsStore = defineStore('notifications', () => {
  const unread = ref<Notification[]>([])
  const unreadCount = ref(0)
  const loading = ref(false)
  // 0729 按分类统计
  const categoryCounts = ref<Record<string, number>>({ action_required: 0, awareness: 0, experience: 0 })

  async function fetchUnread() {
    loading.value = true
    try {
      const [listRes, countRes, catRes] = await Promise.all([
        notifApi.getUnreadNotifications(),
        notifApi.getUnreadCount(),
        notifApi.getCategoryCounts().catch(() => ({ data: { data: {} } })),
      ])
      if (listRes.data?.success) unread.value = listRes.data.data || []
      if (countRes.data?.success) unreadCount.value = countRes.data.data?.count ?? 0
      if (catRes.data?.success) categoryCounts.value = catRes.data.data || {}
    } catch (e: any) {
      console.error('fetchUnread error:', e)
    } finally { loading.value = false }
  }

  async function refreshCount() {
    try {
      const [r, catRes] = await Promise.all([
        notifApi.getUnreadCount(),
        notifApi.getCategoryCounts().catch(() => ({ data: { data: {} } })),
      ])
      if (r.data?.success) unreadCount.value = r.data.data?.count ?? 0
      if (catRes.data?.success) categoryCounts.value = catRes.data.data || {}
    } catch { /* 静默失败 */ }
  }

  async function markRead(id: number) {
    const idx = unread.value.findIndex(n => n.id === id)
    if (idx !== -1) unread.value.splice(idx, 1)
    unreadCount.value = Math.max(0, unreadCount.value - 1)
    try {
      await notifApi.markNotificationRead(id)
    } catch (e: any) {
      console.error('markRead error:', e)
      await fetchUnread()
    }
  }

  async function markAllRead() {
    unread.value = []
    unreadCount.value = 0
    categoryCounts.value = { action_required: 0, awareness: 0, experience: 0 }
    try {
      await notifApi.markAllNotificationsRead()
    } catch (e: any) {
      console.error('markAllRead error:', e)
      await fetchUnread()
    }
  }

  async function markByComplaint(complaintNo: string) {
    try {
      await notifApi.markNotificationsReadByComplaint(complaintNo)
    } catch (e: any) {
      console.error('markByComplaint error:', e)
    } finally {
      await fetchUnread()
    }
  }

  return {
    unread, unreadCount, loading, categoryCounts,
    fetchUnread, refreshCount, markRead, markAllRead, markByComplaint,
  }
})
