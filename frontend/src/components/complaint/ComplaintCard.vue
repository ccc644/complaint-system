<!-- 0724 投诉卡片 — 看板工单卡片，左侧优先级色条 + 清晰按钮层级
     0819 v3.0：新七状态按钮矩阵 + 子类型徽章 -->
<template>
  <div class="bg-white rounded-lg shadow-sm hover:shadow ring-1 ring-gray-200 hover:ring-gray-300 transition overflow-hidden">
    <!-- 顶部优先级色条 -->
    <div class="h-1" :style="{ backgroundColor: priorityColor }"></div>
    <div class="p-3 space-y-2.5">
      <!-- 头部 -->
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0 flex-1">
          <div class="font-mono text-sm font-semibold text-gray-900 truncate tracking-tight">
            {{ complaint.complaint_no }}
          </div>
          <div class="text-xs text-gray-500 mt-0.5 truncate">{{ complaint.customer_name }}</div>
          <div class="text-xs text-gray-400 truncate">{{ complaint.equipment_model }}</div>
        </div>
        <PriorityBadge :priority="complaint.priority" />
      </div>

      <!-- 进度条 -->
      <div v-if="progressPct > 0 && progressPct < 100">
        <div class="flex justify-between text-[10px] text-gray-400 mb-1">
          <span>工单跟进进度</span><span>{{ progressPct }}%</span>
        </div>
        <div class="w-full bg-gray-100 rounded-full h-1">
          <div class="h-1 rounded-full transition-all duration-500" :style="{ width: progressPct + '%', backgroundColor: priorityColor }"></div>
        </div>
      </div>

      <!-- 元数据 -->
      <div class="text-xs text-gray-500 space-y-0.5">
        <div class="flex items-center justify-between">
          <span class="text-gray-400 truncate">
            {{ complaint.fault_category || '不分类' }}<span v-if="complaint.scene_category" class="ml-2">{{ complaint.scene_category }}</span>
          </span>
          <StatusBadge :status="complaint.status" :sub-type="complaint.sub_type" />
        </div>
        <div class="text-gray-400">📅 {{ complaint.created_at?.slice(0, 10) }}</div>
        <!-- 0819 指派快照 -->
        <div v-if="assigneeNames" class="text-gray-500 truncate">👥 {{ assigneeNames }}</div>
      </div>

      <!-- 0819 退回修改提示（待客服处理 rework）；0901 区分主管退回/办理人退回 -->
      <div v-if="complaint.status === '待客服处理' && complaint.sub_type === 'rework' && complaint.supervisor_rejection_note"
        class="rounded border border-red-200 bg-red-50 px-2 py-1.5 text-xs text-red-700">
        <div class="font-medium">❌ {{ returnNote?.sourceLabel }}</div>
        <div class="mt-0.5 line-clamp-2" :title="complaint.supervisor_rejection_note || ''">
          原因：{{ returnNote?.reason }}
        </div>
      </div>
      <div v-if="complaint.status === '待客服处理' && complaint.sub_type === 'rework' && complaint.email_review_status === 'rejected'"
        class="rounded border border-red-200 bg-red-50 px-2 py-1.5 text-xs text-red-700">
        <div class="font-medium">📧 邮件审核退回</div>
        <div class="mt-0.5 line-clamp-2">{{ complaint.email_review_note || '请修改邮件内容后重新提交' }}</div>
      </div>

      <!-- 1020 退回审批中角标（申请期间状态不变，靠角标识别） -->
      <div v-if="complaint.return_request_status === 'pending'"
        class="rounded border border-indigo-200 bg-indigo-50 px-2 py-1.5 text-xs text-indigo-700">
        <div class="font-medium">🔁 退回审批中</div>
        <div class="mt-0.5 line-clamp-2">
          {{ complaint.return_request_by }} 申请：
          {{ complaint.return_request_type === 'cannot_handle' ? '承接人处理不了' : '审批人不可承接' }}
        </div>
      </div>

      <!-- 0820 指派审批人退回重派角标（hover title 显示退回人与原因） -->
      <div v-if="complaint.status === '指派审批人' && complaint.rejected_info"
        class="rounded border border-red-200 bg-red-50 px-2 py-1.5 text-xs text-red-700"
        :title="`${complaint.rejected_info.operator_name}${complaint.rejected_info.operator_position ? '（' + complaint.rejected_info.operator_position + '）' : ''}：${complaint.rejected_info.detail}`">
        <div class="font-medium">↩️ 退回重派</div>
        <div class="mt-0.5 line-clamp-2">{{ complaint.rejected_info.operator_name }}：{{ complaint.rejected_info.detail }}</div>
      </div>

      <!-- 0819 操作按钮组（状态 × 角色矩阵） -->
      <div class="space-y-1.5 pt-2 border-t border-gray-100">
        <!-- 客服主管审核（客诉）→ 客服主管/管理员 -->
        <button v-if="complaint.status === '客服主管审核' && complaint.sub_type === 'intake' && (role === '客服主管' || role === '管理员')"
          @click="$emit('viewDetail', complaint.id)"
          class="w-full text-xs py-1.5 rounded font-medium bg-sky-600 text-white hover:bg-sky-700 transition">
          🧾 客诉审核
        </button>
        <!-- 客服主管审核（邮件）→ 客服主管/管理员 -->
        <button v-if="complaint.status === '客服主管审核' && complaint.sub_type === 'email' && (role === '客服主管' || role === '管理员')"
          @click="$emit('viewDetail', complaint.id)"
          class="w-full text-xs py-1.5 rounded font-medium bg-violet-600 text-white hover:bg-violet-700 transition">
          📧 邮件审核
        </button>
        <!-- 待客服处理（修改重提）→ 录入客服/管理员 -->
        <button v-if="complaint.status === '待客服处理' && complaint.sub_type === 'rework' && ((role === '客服' && isCreator) || role === '管理员')"
          @click="$emit('viewDetail', complaint.id)"
          class="w-full text-xs py-1.5 rounded font-medium bg-amber-600 text-white hover:bg-amber-700 transition">
          ✏️ 修改重提
        </button>
        <!-- 待客服处理（待客户确认）→ 录入客服/管理员 -->
        <button v-if="complaint.status === '待客服处理' && complaint.sub_type === 'customer_confirm' && ((role === '客服' && isCreator) || role === '管理员')"
          @click="$emit('viewDetail', complaint.id)"
          class="w-full text-xs py-1.5 rounded font-medium bg-teal-600 text-white hover:bg-teal-700 transition">
          🤝 处理确认
        </button>
        <!-- 待客户排查 → 录入客服/管理员 -->
        <button v-if="complaint.status === '待客户排查' && ((role === '客服' && isCreator) || role === '管理员')"
          @click="$emit('viewDetail', complaint.id)"
          class="w-full text-xs py-1.5 rounded font-medium bg-purple-600 text-white hover:bg-purple-700 transition">
          🔍 提交排查结果
        </button>
        <!-- 指派审批人 → 办理人/管理员 -->
        <button v-if="complaint.status === '指派审批人' && (role === '办理人' || role === '管理员')"
          @click="$emit('assignApprover', complaint.id)"
          class="w-full text-xs py-1.5 rounded font-medium bg-amber-600 text-white hover:bg-amber-700 transition">
          👤 指派审批人
        </button>
        <!-- 指派承接人 → 当前审批人/管理员（0821 操作隔离；0825 办理人可为当前审批人） -->
        <button v-if="complaint.status === '指派承接人' && (isActingApprover || role === '管理员')"
          @click="$emit('viewDetail', complaint.id)"
          class="w-full text-xs py-1.5 rounded font-medium bg-orange-600 text-white hover:bg-orange-700 transition">
          👥 指派承接人
        </button>
        <!-- 处理中（追加参与人）→ 当前审批人/管理员（0821 操作隔离；0825 办理人可为当前审批人） -->
        <button v-if="complaint.status === '处理中' && (isActingApprover || role === '管理员')"
          @click="$emit('viewDetail', complaint.id)"
          class="w-full text-xs py-1.5 rounded font-medium bg-cyan-600 text-white hover:bg-cyan-700 transition">
          🤝 追加参与人
        </button>

        <!-- 0826 撤回工单 → 录入客服（全流程除已关闭/已撤回，弹窗确认） -->
        <button v-if="canWithdraw"
          @click="$emit('withdraw', complaint.id)"
          class="w-full text-xs py-1.5 rounded font-medium border-2 border-stone-400 text-stone-600 hover:bg-stone-50 transition">
          ↩️ 撤回工单
        </button>

        <!-- 编辑（管理员/客服可编辑状态） -->
        <div v-if="canEditDelete" class="grid grid-cols-2 gap-1.5">
          <button @click="$emit('edit', complaint.id)"
            class="text-xs py-1.5 rounded font-medium border border-gray-300 text-gray-600 hover:bg-gray-50 transition">
            ✏️ 编辑
          </button>
          <button v-if="role === '管理员'"
            @click="$emit('delete', complaint.id)"
            class="text-xs py-1.5 rounded font-medium border-2 border-red-300 text-red-600 hover:bg-red-50 transition">
            🗑️ 删除
          </button>
        </div>

        <!-- 查看详情 -->
        <button @click="$emit('viewDetail', complaint.id)"
          class="w-full text-xs py-1.5 rounded font-medium text-primary border border-primary/30 hover:bg-primary/5 transition">
          🔍 查看详情
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Complaint } from '@/types/api'
import PriorityBadge from '@/components/common/PriorityBadge.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { parseReturnNote } from '@/utils/complaintReturn'

const props = defineProps<{ complaint: Complaint; role: string; currentUserId?: number }>()

// 0901 退回来源（主管/办理人姓名）解析
const returnNote = computed(() => parseReturnNote(props.complaint.supervisor_rejection_note))

defineEmits<{
  edit: [id: number]; delete: [id: number]; viewDetail: [id: number]
  assignApprover: [id: number]; withdraw: [id: number]
}>()

// 0821 操作隔离：当前用户是否为该工单的当前审批人 / 录入客服
const isCurrentApprover = computed(() =>
  (props.complaint.assignees || []).some(a => a.assignee_type === 'approver' && a.user_id === props.currentUserId)
)
// 0825 办理人可被指派为审批人：绑定当前审批人且角色为审批人/办理人时，可执行审批人操作
const isActingApprover = computed(() =>
  isCurrentApprover.value && (props.role === '审批人' || props.role === '办理人')
)
const isCreator = computed(() => {
  const uid = props.complaint.created_by_user_id
  return !!uid && uid === props.currentUserId
})

// 0807 P0 深红(紧急) · P1 琥珀(高) · P2 绿色(中) · P3 蓝色(低) · 待确认 灰色
const PRIORITY_COLORS: Record<string, string> = {
  P0: '#dc2626', P1: '#f59e0b', P2: '#22c55e', P3: '#3b82f6', '待确认': '#9ca3af',
}
const priorityColor = computed(() => PRIORITY_COLORS[props.complaint.priority] || '#9ca3af')

const progressPct = computed(() => (props.complaint as any)._progress_pct ?? 0)

// 0819 指派快照展示（审批人 + 承接人）
const assigneeNames = computed(() => {
  const list = props.complaint.assignees || []
  if (!list.length) return ''
  const approver = list.filter(a => a.assignee_type === 'approver').map(a => `${a.display_name}(${a.role})`)
  const workers = list.filter(a => a.assignee_type === 'assignee').map(a => `${a.display_name}${a.is_primary === 1 ? '👑' : ''}`)
  const parts: string[] = []
  if (approver.length) parts.push(`审批:${approver.join('、')}`)
  if (workers.length) parts.push(`处理:${workers.join('、')}`)
  return parts.join(' ')
})

const canEditDelete = computed(() => {
  if (props.role === '管理员') return true
  if (props.role === '客服' && isCreator.value && (
    (props.complaint.status === '客服主管审核' && props.complaint.sub_type === 'intake')
    || props.complaint.status === '待客户排查'
    || (props.complaint.status === '待客服处理' && props.complaint.sub_type === 'rework')
  )) return true
  return false
})

// 0826 撤回：录入客服本人，全流程除终态（已关闭/已撤回）
const canWithdraw = computed(() =>
  props.role === '客服' && isCreator.value
  && props.complaint.status !== '已关闭' && props.complaint.status !== '已撤回'
)
</script>
