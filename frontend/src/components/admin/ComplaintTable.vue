<!-- 0729 管理员工单管理 — 表格列表 + 筛选搜索 + 状态变更 + 删除 + 跳转详情 -->
<template>
  <div class="space-y-4">
    <!-- 筛选栏 -->
    <div class="bg-white rounded-lg border border-gray-200 p-4 flex flex-wrap items-end gap-3">
      <div>
        <label class="text-xs text-gray-500 mb-1 block">状态筛选</label>
        <select v-model="filters.status" @change="fetchList"
          class="px-3 py-1.5 border border-gray-300 rounded-base text-sm bg-white">
          <option value="">全部状态</option>
          <option v-for="s in CANONICAL_STATUSES" :key="s" :value="s">{{ s }}</option>
        </select>
      </div>
      <div>
        <label class="text-xs text-gray-500 mb-1 block">类别筛选</label>
        <select v-model="filters.category" @change="fetchList"
          class="px-3 py-1.5 border border-gray-300 rounded-base text-sm bg-white">
          <option value="">全部类别</option>
          <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>
      <div>
        <label class="text-xs text-gray-500 mb-1 block">优先级筛选</label>
        <select v-model="filters.priority" @change="fetchList"
          class="px-3 py-1.5 border border-gray-300 rounded-base text-sm bg-white">
          <option value="">全部优先级</option>
          <option value="P0">P0</option><option value="P1">P1</option><option value="P2">P2</option><option value="P3">P3</option>
          <option value="待确认">待确认</option>
        </select>
      </div>
      <div>
        <label class="text-xs text-gray-500 mb-1 block">关键词搜索</label>
        <input v-model="filters.keyword" @input="onKeywordInput"
          placeholder="🔍 搜索编号/客户/设备/工程师"
          class="px-3 py-1.5 border border-gray-300 rounded-base text-sm w-56 focus:ring-2 focus:ring-primary/30" />
      </div>
      <span class="text-xs text-gray-400 ml-auto">{{ total }} 条工单</span>
    </div>

    <!-- 表格 -->
    <div class="bg-white rounded-lg border border-gray-200 overflow-x-auto">
      <div v-if="loading" class="p-8 text-center text-gray-400">加载中...</div>
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="bg-gray-50 border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wider">
            <th class="px-3 py-3 w-36">工单编号</th>
            <th class="px-3 py-3 w-24">客户</th>
            <th class="px-3 py-3 w-16">类别</th>
            <th class="px-3 py-3 w-14">优先级</th>
            <th class="px-3 py-3 w-20">状态</th>
            <th class="px-3 py-3 w-16">指派人</th>
            <th class="px-3 py-3 w-36">创建时间</th>
            <th class="px-3 py-3 w-48 text-center">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in complaints" :key="c.id"
            class="border-b border-gray-100 hover:bg-gray-50/50 transition">
            <!-- 工单编号 — 可点击跳转 -->
            <td class="px-3 py-2">
              <a href="#" @click.prevent="goDetail(c.id)"
                class="text-primary hover:underline font-medium mono text-xs">{{ c.complaint_no }}</a>
            </td>
            <td class="px-3 py-2 text-gray-700 text-xs truncate max-w-[6rem]" :title="c.customer_name">{{ c.customer_name }}</td>
            <td class="px-3 py-2">
              <span v-if="c.fault_category" class="text-xs bg-gray-100 text-gray-600 px-1 py-0.5 rounded">{{ c.fault_category }}</span>
            </td>
            <td class="px-3 py-2"><PriorityBadge :priority="c.priority" /></td>
            <td class="px-3 py-2"><StatusBadge :status="c.status" /></td>
            <td class="px-3 py-2 text-gray-500 text-xs">{{ c.assigned_to || '-' }}</td>
            <td class="px-3 py-2 text-gray-400 mono text-xs">{{ formatDate(c.created_at) }}</td>
            <!-- 操作列 -->
            <td class="px-3 py-2">
              <div class="flex items-center gap-1.5 justify-center flex-wrap">
                <!-- 查看详情 -->
                <button @click="goDetail(c.id)"
                  class="text-xs text-primary hover:underline">查看</button>
                <!-- 0914 状态变更：按钮 + 弹窗确认（原因必填），替代原直接生效的下拉 -->
                <button @click="openStatusChange(c)"
                  class="text-xs text-primary hover:underline">改状态</button>
                <!-- 优先级修改 -->
                <select @change="onChangePriority(c, ($event.target as HTMLSelectElement).value)"
                  class="text-xs border border-gray-300 rounded px-1 py-0.5 bg-white" :title="c.priority">
                  <option value="">改优先级</option>
                  <option v-for="p in PRIORITY_OPTIONS" :key="p" :value="p" :disabled="p === c.priority">{{ p === '待确认' ? '待确认' : p }}</option>
                </select>
                <!-- 删除 -->
                <button @click="confirmDelete(c)"
                  class="text-xs text-red-500 hover:text-red-700 hover:underline">删除</button>
              </div>
            </td>
          </tr>
          <tr v-if="complaints.length === 0">
            <td colspan="8" class="px-4 py-8 text-center text-gray-400">暂无数据</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 分页 -->
    <div v-if="total > 0" class="flex items-center justify-between text-sm text-gray-500">
      <div class="flex items-center gap-1">
        <span>每页</span>
        <select v-model="pageSize" @change="page=1; fetchList()" class="px-2 py-0.5 border border-gray-300 rounded text-xs">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
        <span>条</span>
      </div>
      <div class="flex items-center gap-2">
        <button @click="page--; fetchList()" :disabled="page <= 1"
          class="px-3 py-1 border border-gray-300 rounded text-xs disabled:opacity-40 hover:bg-gray-50 transition">上一页</button>
        <span>{{ page }} / {{ Math.ceil(total / pageSize) || 1 }}</span>
        <button @click="page++; fetchList()" :disabled="page >= Math.ceil(total / pageSize)"
          class="px-3 py-1 border border-gray-300 rounded text-xs disabled:opacity-40 hover:bg-gray-50 transition">下一页</button>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <ConfirmDialog
      :visible="!!deleteTarget"
      title="删除工单"
      :message="deleteTarget ? `确定要删除工单「${(deleteTarget as any).complaint_no}」吗？此操作不可恢复。` : ''"
      @confirm="doDelete"
      @cancel="deleteTarget = null"
    />

    <!-- 0914 状态变更弹窗：目标状态下拉 + 原因必填 -->
    <ConfirmDialog
      :visible="!!statusTarget"
      title="修改工单状态"
      :message="statusTarget ? `工单「${(statusTarget as any).complaint_no}」当前状态：${(statusTarget as any).status}。请选择目标状态并填写变更原因。` : ''"
      confirm-text="确认修改"
      confirm-class="bg-primary hover:bg-primary/90"
      icon-bg="bg-blue-100"
      icon-color="text-blue-600"
      :loading="statusChanging"
      @confirm="doChangeStatus"
      @cancel="closeStatusChange"
    >
      <div v-if="statusTarget" class="mt-4 space-y-3">
        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">目标状态 <span class="text-red-500">*</span></label>
          <select v-model="statusValue"
            class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm bg-white">
            <option v-for="s in CANONICAL_STATUSES" :key="s" :value="s" :disabled="s === (statusTarget as any).status">{{ s }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-600 mb-1">变更原因 <span class="text-red-500">*</span></label>
          <textarea v-model="statusReason" rows="3" placeholder="必填：写入工单日志并随状态变更通知展示"
            class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
        </div>
        <p class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-base px-2 py-1.5">
          ⚠️ 直接改状态会跳过常规流程校验（如承接人/审批环节），请确认原因后操作。
        </p>
        <p v-if="statusError" class="text-xs text-red-600">{{ statusError }}</p>
      </div>
    </ConfirmDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listComplaints, updateComplaint, deleteComplaint } from '@/api/complaints'
import type { Complaint } from '@/types/api'
import PriorityBadge from '@/components/common/PriorityBadge.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const router = useRouter()

// 0819 新七状态（管理员改状态下拉）；0825 加已撤回
const CANONICAL_STATUSES = [
  '待客服处理', '待客户排查', '客服主管审核', '指派审批人', '指派承接人', '处理中', '已关闭', '已撤回',
]
const PRIORITY_OPTIONS = ['P0', 'P1', 'P2', 'P3', '待确认']
const CATEGORIES = ['机械', '电气', '工艺', '光学', '软件', '其他']

const complaints = ref<Complaint[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)

const filters = reactive({ status: '', category: '', priority: '', keyword: '' })

const deleteTarget = ref<Complaint | null>(null)

let keywordTimer: ReturnType<typeof setTimeout> | null = null

function onKeywordInput() {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => { page.value = 1; fetchList() }, 300)
}

async function fetchList() {
  loading.value = true
  try {
    const r = await listComplaints({
      status: filters.status || undefined,
      category: filters.category || undefined,
      priority: filters.priority || undefined,
      keyword: filters.keyword || undefined,
      page: page.value,
      limit: pageSize.value,
    })
    if (r.data?.success) {
      complaints.value = r.data.data || []
      total.value = r.data.pagination?.total || 0
    }
  } catch (e: any) {
    console.error('ComplaintTable fetchList error:', e)
  } finally { loading.value = false }
}

// 0914 状态变更改按钮+弹窗（原因必填，后端同样强制校验）
const statusTarget = ref<Complaint | null>(null)
const statusValue = ref('')
const statusReason = ref('')
const statusError = ref('')
const statusChanging = ref(false)

function openStatusChange(c: Complaint) {
  statusTarget.value = c
  statusValue.value = ''
  statusReason.value = ''
  statusError.value = ''
}

function closeStatusChange() {
  statusTarget.value = null
  statusValue.value = ''
  statusReason.value = ''
  statusError.value = ''
}

async function doChangeStatus() {
  const c = statusTarget.value
  if (!c) return
  if (!statusValue.value) { statusError.value = '请选择目标状态'; return }
  if (statusValue.value === c.status) { statusError.value = '目标状态与当前状态相同'; return }
  if (!statusReason.value.trim()) { statusError.value = '请填写变更原因'; return }
  statusChanging.value = true
  statusError.value = ''
  try {
    await updateComplaint(c.id, { status: statusValue.value, status_change_reason: statusReason.value.trim() })
    closeStatusChange()
    fetchList()
  } catch (e: any) {
    statusError.value = e?.response?.data?.detail || '状态修改失败'
  } finally { statusChanging.value = false }
}

async function onChangePriority(c: Complaint, newPriority: string) {
  if (!newPriority || newPriority === c.priority) return
  try {
    await updateComplaint(c.id, { priority: newPriority })
    c.priority = newPriority as Complaint['priority']
    fetchList()
  } catch (e: any) {
    console.error('ComplaintTable changePriority error:', e)
  }
}

function confirmDelete(c: Complaint) {
  deleteTarget.value = c
}

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await deleteComplaint(deleteTarget.value.id)
    deleteTarget.value = null
    fetchList()
  } catch (e: any) {
    console.error('ComplaintTable delete error:', e)
  }
}

function goDetail(id: number) {
  router.push(`/work-order/${id}`)
}

function formatDate(d: string) {
  if (!d) return '-'
  return d.slice(0, 16).replace('T', ' ')
}

onMounted(() => { fetchList() })
</script>
