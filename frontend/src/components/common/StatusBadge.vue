<!-- 0724 状态徽章 — 语义色药丸，带前置色点
     0819 v3.0 新七状态 + subType 子类型标签 -->
<template>
  <span class="inline-flex items-center gap-1 flex-wrap">
    <span :class="['inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium', colorClass]">
      <span class="w-1.5 h-1.5 rounded-full bg-current"></span>
      {{ status }}
    </span>
    <span v-if="subTypeLabel"
      :class="['inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium', subTypeClass]">
      {{ subTypeLabel }}
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ComplaintStatus, ComplaintSubType } from '@/types/api'

const props = defineProps<{ status: string; subType?: string }>()

const STATUS_COLORS: Record<string, string> = {
  '待客服处理': 'bg-teal-50 text-teal-700 ring-1 ring-teal-200',
  '待客户排查': 'bg-purple-50 text-purple-700 ring-1 ring-purple-200',
  '客服主管审核': 'bg-sky-50 text-sky-700 ring-1 ring-sky-200',
  '指派审批人': 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  '指派承接人': 'bg-orange-50 text-orange-700 ring-1 ring-orange-200',
  '处理中':     'bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200',
  '已关闭':     'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  '已撤回':     'bg-stone-50 text-stone-600 ring-1 ring-stone-200',
}

// 0819 子类型标签
const SUB_TYPE_MAP: Record<string, { label: string; cls: string }> = {
  rework:          { label: '待修改',     cls: 'bg-amber-100 text-amber-700' },
  customer_confirm:{ label: '待客户确认', cls: 'bg-teal-100 text-teal-700' },
  intake:          { label: '客诉审核',   cls: 'bg-sky-100 text-sky-700' },
  email:           { label: '邮件审核',   cls: 'bg-violet-100 text-violet-700' },
}

const colorClass = computed(() => STATUS_COLORS[props.status] || 'bg-gray-50 text-gray-600 ring-1 ring-gray-200')
const subTypeLabel = computed(() => SUB_TYPE_MAP[props.subType || '']?.label || '')
const subTypeClass = computed(() => SUB_TYPE_MAP[props.subType || '']?.cls || '')
</script>
