<!-- 0803 统一工单日志时间线
     取代旧的三个互不关联的区块（备注记录、客户备注、进度历史）
     0804 优化：固定高度滚动、最新日志在顶部、sticky 头部、完整事件标签 -->
<template>
  <div class="bg-white rounded-lg border border-gray-200 p-4">
    <!-- 0820 修复：去掉 sticky top-0 z-10——h4 是内部滚动容器的兄弟节点，sticky 会绑定到页面级滚动容器，
         导致页面滚动时该标题行粘在详情区顶部悬浮（视觉 bug）。h4 本就在滚动区之外始终可见。 -->
    <h4 class="text-sm font-semibold text-gray-700 mb-3 pb-2 border-b border-gray-100">
      工单日志
      <span v-if="logs.length" class="text-xs font-normal text-gray-400 ml-1">（共 {{ logs.length }} 条）</span>
    </h4>

    <!-- 日志为空时显示旧备注 -->
    <div v-if="!logs.length && !hasLegacy" class="text-xs text-gray-400 text-center py-4">
      暂无操作记录
    </div>

    <!-- 时间线容器：固定最大高度，内部滚动 -->
    <div v-if="logs.length" class="max-h-[420px] overflow-y-auto -mx-1 px-1">
      <div class="space-y-0">
        <div v-for="(entry, i) in sortedLogs" :key="entry.id"
          :class="['relative pl-6 pb-4',
            i !== sortedLogs.length - 1 ? 'border-l-2 border-gray-200' : '']">
          <!-- 圆点 -->
          <span :class="['absolute left-0 top-1 w-2.5 h-2.5 rounded-full -translate-x-1/2 border-2 border-white',
            dotColor(entry.event_type)]"></span>

          <!-- 0820 排版重构：事件标签放第一行（先看"发生了什么"）；0821 状态变化箭头紧跟操作人括号后、以 | 分隔 -->
          <div class="text-xs space-y-0.5">
            <div class="flex items-center gap-2">
              <span class="font-medium text-gray-800">{{ eventLabel(entry.event_type) }}</span>
              <StatusBadge v-if="entry.new_status && entry.new_status !== entry.old_status" :status="entry.new_status" />
            </div>
            <div class="text-gray-400">
              <span class="font-mono">{{ entry.created_at }}</span>
              <span> · </span>
              <!-- 0819 留痕展示 姓名（角色 · 职位） -->
              <span class="font-medium text-gray-600">{{ entry.operator_name }}</span>
              <span>（{{ entry.operator_role }}{{ entry.operator_position ? ' · ' + entry.operator_position : '' }}）</span>
              <!-- 0821 状态变化箭头：紧接操作人括号后，以 | 分隔（不右对齐） -->
              <span v-if="entry.old_status && entry.new_status && entry.old_status !== entry.new_status"
                class="text-gray-500"> | {{ entry.old_status }} → {{ entry.new_status }}</span>
            </div>
            <div v-if="entry.detail" class="text-gray-600">{{ entry.detail }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 旧备注（fallback，仅在没有新日志时显示） -->
    <div v-if="!logs.length && legacyRemarks" class="mt-4 pt-4 border-t border-gray-100">
      <h4 class="text-xs font-medium text-gray-500 mb-2">历史备注（旧格式）</h4>
      <pre class="text-xs whitespace-pre-wrap font-sans text-gray-500">{{ legacyRemarks }}</pre>
    </div>
    <div v-if="!logs.length && legacyCustomerNote" class="mt-2">
      <h4 class="text-xs font-medium text-gray-500 mb-1">客户备注</h4>
      <pre class="text-xs whitespace-pre-wrap font-sans text-gray-500">{{ legacyCustomerNote }}</pre>
    </div>
    <div v-if="!logs.length && legacyCustomerSelfCheck" class="mt-2">
      <h4 class="text-xs font-medium text-gray-500 mb-1">推荐客户自排查</h4>
      <pre class="text-xs whitespace-pre-wrap font-sans text-gray-500">{{ legacyCustomerSelfCheck }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WorkOrderLogEntry } from '@/types/api'
import StatusBadge from '@/components/common/StatusBadge.vue'

const props = defineProps<{
  logs: WorkOrderLogEntry[]
  legacyRemarks?: string
  legacyCustomerNote?: string
  legacyCustomerSelfCheck?: string
}>()

const hasLegacy = computed(() => props.legacyRemarks || props.legacyCustomerNote || props.legacyCustomerSelfCheck)

// 0804 倒序排列：最新日志在顶部
const sortedLogs = computed(() => {
  return [...props.logs].reverse()
})

// 0819 事件类型中文标签映射（新状态机事件集）
const EVENT_LABELS: Record<string, string> = {
  'created': '创建工单',
  'intake_approved': '客诉审核通过',
  'intake_rejected': '客诉审核拒绝',
  'intake_withdrawn': '工单撤回',
  'resubmitted': '客服重新提交',
  'investigation_resolved': '排查已解决',
  'investigation_unresolved': '排查未解决',
  'approver_assigned': '指派审批人',
  'approver_rejected': '不可承接退回',
  'assignees_assigned': '指派承接人',
  'primary_changed': '变更主要推进人',
  'participant_added': '追加参与人',
  'cannot_handle': '处理不了回退',
  'progress': '进度更新',
  'resolved': '提交方案',
  'closed': '客户确认关闭',
  'email_sent': '发送邮件',
  'email_review_requested': '申请邮件审核',
  'email_review_approved': '邮件审核通过',
  'email_review_rejected': '邮件审核拒绝',
  'edited': '编辑工单',
  'deleted': '删除工单',
  'remark': '备注',
  'import_remarks': '表单导入内容', // 0911 批量导入：待审核行的表单备注+解决方案合并日志
  'import_overwrite': '批量导入覆盖', // 1016 疑似重复行勾选覆盖旧工单
  'warning': '工单预警', // 1016 客服/客服主管发起预警（低/高风险分档通知）
  'return_requested': '退回申请',      // 1020 承接人/审批人发起退回申请，待对应审批人审批
  'return_approved': '退回审批通过',   // 1020 审批通过并执行原退回流转
  'return_rejected': '退回审批驳回',   // 1020 审批驳回，工单保持原状态
}

// 0819 事件类型圆点颜色映射
const DOT_COLORS: Record<string, string> = {
  'created': 'bg-green-500',
  'intake_approved': 'bg-emerald-500',
  'intake_rejected': 'bg-red-500',
  'intake_withdrawn': 'bg-stone-500',
  'resubmitted': 'bg-blue-500',
  'investigation_resolved': 'bg-emerald-500',
  'investigation_unresolved': 'bg-purple-500',
  'approver_assigned': 'bg-amber-500',
  'approver_rejected': 'bg-orange-500',
  'assignees_assigned': 'bg-indigo-500',
  'primary_changed': 'bg-fuchsia-500',
  'participant_added': 'bg-cyan-500',
  'cannot_handle': 'bg-orange-500',
  'progress': 'bg-sky-500',
  'resolved': 'bg-teal-500',
  'closed': 'bg-green-600',
  'email_sent': 'bg-violet-500',
  'email_review_requested': 'bg-yellow-500',
  'email_review_approved': 'bg-emerald-500',
  'email_review_rejected': 'bg-red-500',
  'edited': 'bg-gray-500',
  'deleted': 'bg-red-600',
  'remark': 'bg-blue-500',
  'import_remarks': 'bg-amber-500',
  'import_overwrite': 'bg-amber-600',
  'warning': 'bg-orange-600',
  'return_requested': 'bg-indigo-500',
  'return_approved': 'bg-emerald-500',
  'return_rejected': 'bg-red-500',
}

function eventLabel(type: string): string {
  return EVENT_LABELS[type] || type
}

function dotColor(type: string): string {
  return DOT_COLORS[type] || 'bg-gray-400'
}
</script>
