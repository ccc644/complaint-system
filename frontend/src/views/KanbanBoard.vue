<!-- 0724 客诉看板 — 全流程可视化看板
     0819 v3.0：新七状态 + 子类型徽章 + 仅显示我的工单（指派承接人/处理中两列生效）-->
<template>
  <AppLayout>
    <div class="p-4 space-y-4">
      <!-- 标题 + 角色提示 -->
      <div>
        <h1 class="text-2xl font-bold">📊 客诉看板</h1>
        <p v-if="role === '客服'" class="text-sm text-gray-500 mt-1">
          💡 您当前以客服身份登录。您可录入工单、处理退回修改、提交客户排查结果，以及客户确认与邮件。
        </p>
        <p v-else-if="role === '客服主管'" class="text-sm text-gray-500 mt-1">
          💡 您当前以客服主管身份登录。您可审核新工单（确认优先级与去向）、处理邮件审核申请。
        </p>
        <p v-else-if="role === '办理人'" class="text-sm text-gray-500 mt-1">
          💡 您当前以办理人身份登录。您负责指派审批人（工单回退后重新指派）。
        </p>
        <p v-else-if="role === '审批人'" class="text-sm text-gray-500 mt-1">
          💡 您当前以审批人身份登录。您负责承接评估、指派承接人（可多人）与处理排期，处理中可追加参与人。
        </p>
        <p v-else-if="role === '承接人'" class="text-sm text-gray-500 mt-1">
          💡 您当前以承接人身份登录。您负责工单处理：进度更新、处理不了反馈、提交处理结果。
        </p>
      </div>

      <!-- 筛选栏 -->
      <div class="flex flex-wrap gap-3 items-center bg-white rounded-lg border border-gray-200 p-3">
        <select v-model="filters.status" @change="refresh" class="px-3 py-1.5 border border-gray-300 rounded-base text-sm bg-white">
          <option value="">全部状态</option>
          <option v-for="s in CANONICAL_STATUSES" :key="s" :value="s">{{ s }}</option>
        </select>
        <select v-model="filters.category" @change="refresh" class="px-3 py-1.5 border border-gray-300 rounded-base text-sm bg-white">
          <option value="">全部类别</option>
          <option value="机械">机械</option><option value="电气">电气</option><option value="工艺">工艺</option>
          <option value="光学">光学</option><option value="软件">软件</option><option value="其他">其他</option>
        </select>
        <select v-model="filters.priority" @change="refresh" class="px-3 py-1.5 border border-gray-300 rounded-base text-sm bg-white">
          <option value="">全部优先级</option>
          <option value="P0">P0</option><option value="P1">P1</option><option value="P2">P2</option><option value="P3">P3</option><option value="待确认">待确认</option>
        </select>
        <input v-model="filters.keyword" @input="onKeywordInput" placeholder="🔍 搜索编号/客户/设备"
          class="px-3 py-1.5 border border-gray-300 rounded-base text-sm w-full sm:w-56 focus:ring-2 focus:ring-primary/30" />
        <!-- 0820 仅显示我的工单：五角色可用且默认勾选（两层筛选：角色状态范围 + 按人；管理员无复选框，用户决策） -->
        <label v-if="['客服', '客服主管', '办理人', '审批人', '承接人'].includes(role)"
          class="flex items-center gap-1 text-sm text-gray-600 cursor-pointer select-none">
          <input type="checkbox" v-model="filters.myOrdersOnly" @change="refresh" class="rounded" />
          🔍 仅显示我的工单
        </label>
        <!-- 0821 审批人分组切换：处理中 tab 在「自己承接」与「需追加承接人」两档间切换（不勾选仅显示我的工单时置灰） -->
        <button v-if="role === '审批人'" type="button"
          :disabled="!filters.myOrdersOnly"
          @click="approverGroupMode = approverGroupMode === 'todo_assignee' ? 'add_assignee' : 'todo_assignee'"
          :title="!filters.myOrdersOnly ? '需勾选「仅显示我的工单」后生效' : (approverGroupMode === 'todo_assignee' ? '点击切换：处理中仅显示需追加承接人的工单（您审批的）' : '点击切换：处理中仅显示自己承接的工单（您参与的）')"
          class="px-3 py-1.5 text-sm border border-gray-300 rounded-base bg-white hover:bg-gray-50 transition disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white">
          ⇄ {{ approverGroupMode === 'todo_assignee' ? '需审批+自己承接' : '需追加承接人' }}
        </button>
        <span class="text-xs text-gray-400 ml-auto">{{ total }} 条工单</span>
      </div>

      <!-- 看板：Tab 切换 + 网格卡片 -->
      <div class="space-y-4">
        <div class="flex flex-wrap border-b border-gray-200">
          <button v-for="status in CANONICAL_STATUSES" :key="status"
            @click="activeTab = status"
            :class="['relative px-4 py-2.5 text-sm font-medium transition-colors -mb-px',
              activeTab === status
                ? 'text-primary border-b-2 border-primary'
                : 'text-gray-500 hover:text-gray-700 border-b-2 border-transparent']">
            {{ status }}
            <span :class="['ml-1.5 text-xs rounded-full px-1.5 py-0.5',
              (groupedByStatus[status]?.length || 0) === 0
                ? 'bg-gray-100 text-gray-400'
                : activeTab === status
                  ? 'bg-primary/10 text-primary'
                  : 'bg-red-300 text-black']">
              {{ groupedByStatus[status]?.length || 0 }}
            </span>
          </button>
        </div>

        <!-- 0821 审批人分组提示（处理中 tab + 仅显示我的工单时） -->
        <div v-if="role === '审批人' && activeTab === '处理中' && filters.myOrdersOnly"
          class="text-xs text-gray-500">
          📌 当前分组：{{ approverGroupMode === 'todo_assignee' ? '需审批+自己承接（显示您参与的工单）' : '需追加承接人（显示您审批的工单）' }}
        </div>

        <div v-if="groupedByStatus[activeTab]?.length" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          <ComplaintCard
            v-for="c in groupedByStatus[activeTab]" :key="c.id"
            :complaint="c" :role="role" :current-user-id="auth.user?.id"
            @edit="store.openEdit(c.id)"
            @delete="store.openDelete(c.id)"
            @viewDetail="onViewDetail"
            @assignApprover="USE_INLINE_ASSIGN_APPROVER ? openAssignApproverModal(c.id) : onViewDetail(c.id)"
            @withdraw="openWithdrawModal(c.id)" />
        </div>
        <div v-else class="text-center text-gray-400 py-16">
          {{ role === '审批人' && activeTab === '处理中' && filters.myOrdersOnly ? '该分组暂无工单（点击上方分组按钮切换查看）' : '暂无工单' }}
        </div>
      </div>

      <!-- 颜色图例 -->
      <div class="text-xs text-gray-400 bg-white rounded-lg border border-gray-200 p-2 text-center">
        🏷️ P0(紧急) · P1(高) · P2(中) · P3(低) · 待确认　|　流程：客服录入 → 客服主管审核 → 待客户排查 → 指派审批人 → 指派承接人 → 处理 → 客户确认 → 已关闭
      </div>
    </div>

    <!-- 编辑弹窗 -->
    <EditComplaintModal :visible="!!store.editTargetId"
      :complaint="editTargetComplaint"
      :canEditPriority="role === '管理员'"
      @close="store.closeModals()"
      @save="onSaveEdit" />

    <!-- 删除确认弹窗 -->
    <ConfirmDialog :visible="!!store.deleteTargetId"
      title="⚠️ 删除工单"
      :message="`确定要删除工单（ID-${store.deleteTargetId}）吗？此操作不可恢复！`"
      @confirm="onDeleteConfirm" @cancel="store.closeModals()" />

    <!-- 0819 指派审批人弹窗（办理人） -->
    <Teleport to="body">
      <div v-if="assignApproverId" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/40" @click="assignApproverId = null"></div>
        <div class="relative bg-white rounded-lg shadow-xl p-6 w-full max-w-sm mx-4">
          <h3 class="text-lg font-semibold mb-4">👤 指派审批人</h3>
          <div class="space-y-3">
            <div>
              <label class="block text-xs text-gray-500 mb-1">审批人（办理人/审批人） <span class="text-red-400">*</span></label>
              <UserSelect :roles="['办理人', '审批人']" single v-model="approverUserId" />
            </div>
            <!-- 0825 指派说明必填：写入工单日志，可导出 -->
            <div>
              <label class="block text-xs text-gray-500 mb-1">指派说明 <span class="text-red-400">*</span></label>
              <textarea v-model="approverNote" rows="3" placeholder="指派说明（必填，如客诉背景/优先处理原因/期望，将写入工单日志）..."
                class="w-full px-3 py-2 border border-gray-300 rounded text-sm"></textarea>
            </div>
            <div v-if="assignMsg" class="text-sm p-2 rounded" :class="assignOk ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'">{{ assignMsg }}</div>
          </div>
          <div class="flex justify-end gap-3 mt-4">
            <button @click="assignApproverId = null" class="px-4 py-2 text-sm text-gray-700 bg-gray-100 rounded-base hover:bg-gray-200 transition">取消</button>
            <button @click="onAssignApprover" :disabled="approverSubmitting"
              class="px-4 py-2 text-sm text-white bg-primary rounded-base hover:bg-primary/90 disabled:opacity-50 transition">确认指派</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 0826 撤回工单弹窗（录入客服，全流程除已关闭/已撤回） -->
    <Teleport to="body">
      <div v-if="withdrawTargetId" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/40" @click="withdrawTargetId = null"></div>
        <div class="relative bg-white rounded-lg shadow-xl p-6 w-full max-w-sm mx-4">
          <h3 class="text-lg font-semibold mb-2">↩️ 撤回工单</h3>
          <p class="text-xs text-stone-600 bg-stone-50 rounded p-2 mb-3">
            撤回后工单（{{ withdrawTargetNo }}）转入「已撤回」终态，不归档知识库；如需恢复请联系管理员调整状态。
          </p>
          <div class="space-y-3">
            <div>
              <label class="block text-xs text-gray-500 mb-1">撤回原因 <span class="text-red-400">*</span></label>
              <textarea v-model="withdrawNote" rows="3" placeholder="撤回原因（必填，将写入工单日志，可导出）..."
                class="w-full px-3 py-2 border border-gray-300 rounded text-sm"></textarea>
            </div>
            <div v-if="withdrawMsg" class="text-sm p-2 rounded" :class="withdrawOk ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'">{{ withdrawMsg }}</div>
          </div>
          <div class="flex justify-end gap-3 mt-4">
            <button @click="withdrawTargetId = null" class="px-4 py-2 text-sm text-gray-700 bg-gray-100 rounded-base hover:bg-gray-200 transition">取消</button>
            <button @click="onWithdraw" :disabled="!withdrawNote.trim() || withdrawSubmitting"
              class="px-4 py-2 text-sm text-white bg-stone-600 rounded-base hover:bg-stone-700 disabled:opacity-50 transition">
              {{ withdrawSubmitting ? '撤回中...' : '确认撤回' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, reactive, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useComplaintsStore } from '@/stores/complaints'
import AppLayout from '@/components/layout/AppLayout.vue'
import ComplaintCard from '@/components/complaint/ComplaintCard.vue'
import EditComplaintModal from '@/components/complaint/EditComplaintModal.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import UserSelect from '@/components/common/UserSelect.vue'
import { onWsEvent } from '@/composables/useWebSocket'
import { assignApprover as assignApproverApi, withdrawComplaint } from '@/api/complaints'
import { CANONICAL_STATUSES } from '@/types/api'

const router = useRouter()
const auth = useAuthStore()
const store = useComplaintsStore()

const role = computed(() => auth.role || '')

// 0901 优先级排序权重（指派审批人/指派承接人两列默认排序用；与 PriorityBadge/P0-P3 字面量一致）
const PRIORITY_RANK: Record<string, number> = { P0: 0, P1: 1, P2: 2, P3: 3, 待确认: 4 }

// 筛选条件
// 0820 客服/客服主管/办理人/审批人/承接人默认「仅显示我的工单」（两层筛选由后端按角色决定）
const filters = reactive({
  status: '', category: '', priority: '', keyword: '',
  myOrdersOnly: ['客服', '客服主管', '办理人', '审批人', '承接人'].includes(auth.role || ''),
})
let keywordTimer: ReturnType<typeof setTimeout> | null = null

function onKeywordInput() {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => refresh(), 300)
}

const total = ref(0)

// 按状态分组
const groupedByStatus = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const s of CANONICAL_STATUSES) groups[s] = []
  // 0821 审批人 + 仅显示我的工单时：处理中按分组档位过滤（自己承接 / 需追加承接人）
  const uid = auth.user?.id
  const approverModeFilter = role.value === '审批人' && filters.myOrdersOnly
  for (const c of store.list) {
    const s = c.status
    if (!groups[s]) continue
    if (approverModeFilter && s === '处理中') {
      const mine = (c.assignees || []).some(a =>
        approverGroupMode.value === 'todo_assignee'
          ? a.assignee_type === 'assignee' && a.user_id === uid
          : a.assignee_type === 'approver' && a.user_id === uid
      )
      if (!mine) continue
    }
    groups[s].push(c)
  }
  // 0819 排序：处理中按 planned_end_time 升序
  groups['处理中'].sort((a, b) => {
    const aT = a.planned_end_time || ''
    const bT = b.planned_end_time || ''
    if (!aT && !bT) return 0
    if (!aT) return 1
    if (!bT) return -1
    return aT.localeCompare(bT)
  })
  // 0901 指派审批人/指派承接人默认按优先级排（P0→P3→待确认），同级保持后端返回的录入时间倒序（稳定排序）
  for (const s of ['指派审批人', '指派承接人']) {
    groups[s].sort((a, b) => (PRIORITY_RANK[a.priority] ?? 5) - (PRIORITY_RANK[b.priority] ?? 5))
  }
  return groups
})

async function refresh() {
  store.filters.status = filters.status
  store.filters.category = filters.category
  store.filters.priority = filters.priority
  store.filters.keyword = filters.keyword
  store.filters.myOrdersOnly = filters.myOrdersOnly
  await store.fetchList()
  total.value = store.total
}

// 0819 角色默认定位 Tab
const ROLE_DEFAULT_TABS: Record<string, string> = {
  '客服': '待客服处理',
  '客服主管': '客服主管审核',
  '办理人': '指派审批人',
  '审批人': '指派承接人',
  '承接人': '处理中',
}
const activeTab = ref('')

// 0826 状态筛选联动状态 tab：下拉选中某状态后自动切到对应 tab；清空回落角色默认 tab
watch(() => filters.status, (s) => {
  if (s) activeTab.value = s
  else activeTab.value = ROLE_DEFAULT_TABS[role.value] || CANONICAL_STATUSES[0]
})

// 0821 审批人分组切换：todo_assignee=需审批+自己承接（处理中仅显示自己承接的）；add_assignee=需追加承接人（处理中仅显示我是当前审批人的）
const approverGroupMode = ref<'todo_assignee' | 'add_assignee'>('todo_assignee')

onMounted(async () => {
  await refresh()
  const def = ROLE_DEFAULT_TABS[role.value] || ''
  if (def && groupedByStatus.value[def]?.length > 0) {
    activeTab.value = def
  } else {
    for (const s of CANONICAL_STATUSES) {
      if (groupedByStatus.value[s]?.length > 0) { activeTab.value = s; break }
    }
  }
  if (!activeTab.value) activeTab.value = CANONICAL_STATUSES[0]
})

// 0731 WebSocket 实时刷新
const offWsKanban = onWsEvent((evt) => {
  if (evt.type === 'complaint_created' || evt.type === 'complaint_updated' || evt.type === 'complaint_deleted') {
    refresh()
  }
})
onUnmounted(() => offWsKanban())

// ── 编辑 ──
const editTargetComplaint = computed(() =>
  store.list.find(c => c.id === store.editTargetId) || null
)

async function onSaveEdit(data: Record<string, any>) {
  if (!store.editTargetId) return
  await store.update(store.editTargetId, data)
  store.closeModals()
}

// ── 删除 ──
async function onDeleteConfirm() {
  if (!store.deleteTargetId) return
  await store.remove(store.deleteTargetId)
  store.closeModals()
}

function onViewDetail(id: number) { router.push(`/work-order/${id}`) }

// ── 0819 指派审批人弹窗 ──
// 0901 看板内嵌快捷指派开关：false = 卡片「指派审批人」按钮跳工单详情（详情页含「不可承接退回客服」按钮）；
// 弹窗代码保留，改回 true 即恢复看板内快捷指派
const USE_INLINE_ASSIGN_APPROVER = false
const assignApproverId = ref<number | null>(null)
const approverUserId = ref<number>(0)
const approverNote = ref('')   // 0825 指派说明（必填，写日志）
const approverSubmitting = ref(false)
const assignMsg = ref('')
const assignOk = ref(false)

function openAssignApproverModal(id: number) {
  assignApproverId.value = id
  approverUserId.value = 0
  approverNote.value = ''
  assignMsg.value = ''
  assignOk.value = false
}

async function onAssignApprover() {
  if (!assignApproverId.value || !approverUserId.value) {
    assignMsg.value = '请选择审批人'
    assignOk.value = false
    return
  }
  // 0825 指派说明必填（写工单日志）
  if (!approverNote.value.trim()) {
    assignMsg.value = '请填写指派说明'
    assignOk.value = false
    return
  }
  approverSubmitting.value = true
  try {
    const r = await assignApproverApi(assignApproverId.value, approverUserId.value, approverNote.value.trim())
    if (r.data?.success) {
      assignOk.value = true
      assignMsg.value = r.data?.message || '已指派审批人'
      assignApproverId.value = null
      refresh()
    } else {
      assignOk.value = false
      assignMsg.value = r.data?.message || '指派失败'
    }
  } catch (e: any) {
    assignOk.value = false
    assignMsg.value = e?.response?.data?.detail || '指派失败'
  } finally {
    approverSubmitting.value = false
  }
}

// ── 0826 撤回工单弹窗（录入客服） ──
const withdrawTargetId = ref<number | null>(null)
const withdrawTargetNo = ref('')
const withdrawNote = ref('')
const withdrawSubmitting = ref(false)
const withdrawMsg = ref('')
const withdrawOk = ref(false)

function openWithdrawModal(id: number) {
  withdrawTargetId.value = id
  withdrawTargetNo.value = store.list.find(c => c.id === id)?.complaint_no || ''
  withdrawNote.value = ''
  withdrawMsg.value = ''
  withdrawOk.value = false
}

async function onWithdraw() {
  if (!withdrawTargetId.value) return
  if (!withdrawNote.value.trim()) {
    withdrawMsg.value = '请填写撤回原因'
    withdrawOk.value = false
    return
  }
  withdrawSubmitting.value = true
  try {
    const r = await withdrawComplaint(withdrawTargetId.value, withdrawNote.value.trim())
    if (r.data?.success) {
      withdrawOk.value = true
      withdrawMsg.value = r.data?.message || '工单已撤回'
      withdrawTargetId.value = null
      refresh()
    } else {
      withdrawOk.value = false
      withdrawMsg.value = r.data?.message || '撤回失败'
    }
  } catch (e: any) {
    withdrawOk.value = false
    withdrawMsg.value = e?.response?.data?.detail || '撤回失败'
  } finally {
    withdrawSubmitting.value = false
  }
}
</script>
