// 0724 投诉 Pinia Store — 替代 session_state 中的投诉数据缓存
// 0819 v3.0：移除旧状态机动作，保留基础 CRUD 与弹窗状态
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Complaint } from '@/types/api'
import {
  listComplaints, getComplaintById, createComplaint, updateComplaint,
  deleteComplaint,
} from '@/api/complaints'

export const useComplaintsStore = defineStore('complaints', () => {
  // ── 状态 ───────────────────────────────────────
  const list = ref<Complaint[]>([])
  const activeComplaint = ref<Complaint | null>(null)
  const loading = ref(false)
  const total = ref(0)
  const page = ref(1)
  const limit = ref(100)

  // 筛选条件
  const filters = ref({
    status: '',
    category: '',
    priority: '',
    keyword: '',
    myOrdersOnly: false,
  })

  // 看板定位 Tab（role default 后清除）
  const kanbanFocusTab = ref<string | null>(null)

  // 编辑/删除弹窗目标 ID
  const editTargetId = ref<number | null>(null)
  const deleteTargetId = ref<number | null>(null)

  // 看板 Tab（当前激活的 Tab）
  const activeTab = ref<string>('')

  // ── 计算属性 ───────────────────────────────────
  const groupedByStatus = computed(() => {
    const groups: Record<string, Complaint[]> = {}
    for (const c of list.value) {
      const status = c.status
      if (!groups[status]) groups[status] = []
      groups[status].push(c)
    }
    return groups
  })

  // ── 操作 ───────────────────────────────────────
  async function fetchList() {
    loading.value = true
    try {
      const res = await listComplaints({
        status: filters.value.status || undefined,
        category: filters.value.category || undefined,
        priority: filters.value.priority || undefined,
        keyword: filters.value.keyword || undefined,
        my_orders: filters.value.myOrdersOnly,
        page: page.value,
        limit: limit.value,
      })
      if (res.data?.success) {
        list.value = res.data.data || []
        total.value = res.data.pagination?.total || 0
      }
    } finally {
      loading.value = false
    }
  }

  async function fetchById(id: number) {
    const res = await getComplaintById(id)
    if (res.data?.success) {
      activeComplaint.value = res.data.data
    }
    return res.data
  }

  async function create(data: Record<string, any>) {
    const res = await createComplaint(data)
    if (res.data?.success) {
      await fetchList()
    }
    return res.data
  }

  async function update(id: number, data: Record<string, any>) {
    const res = await updateComplaint(id, data)
    if (res.data?.success) {
      activeComplaint.value = res.data.data
      await fetchList()
    }
    return res.data
  }

  async function remove(id: number) {
    const res = await deleteComplaint(id)
    if (res.data?.success) {
      await fetchList()
    }
    return res.data
  }

  function openEdit(id: number) {
    editTargetId.value = id
    deleteTargetId.value = null
  }

  function openDelete(id: number) {
    deleteTargetId.value = id
    editTargetId.value = null
  }

  function closeModals() {
    editTargetId.value = null
    deleteTargetId.value = null
  }

  return {
    list, activeComplaint, loading, total, page, limit,
    filters, kanbanFocusTab, editTargetId, deleteTargetId, activeTab,
    groupedByStatus,
    fetchList, fetchById, create, update, remove,
    openEdit, openDelete, closeModals,
  }
})
