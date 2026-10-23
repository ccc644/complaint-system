<!-- 0727 KPI 指标卡片 — 图标 + 数值 + 标签 -->
<template>
  <div :class="['rounded-lg border p-4 flex flex-col gap-1', bgClass]">
    <div class="text-2xl">{{ icon }}</div>
    <div class="text-2xl font-bold">{{ formattedValue }}</div>
    <div class="text-xs text-gray-500">{{ label }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  icon?: string
  label: string
  value: number | string | null | undefined
  color?: string
  format?: 'number' | 'percent' | 'hours' | 'star' | 'text'
}>(), {
  icon: '📊',
  color: 'blue',
  format: 'number',
})

const colorMap: Record<string, string> = {
  blue: 'bg-blue-50 border-blue-100',
  green: 'bg-green-50 border-green-100',
  yellow: 'bg-yellow-50 border-yellow-100',
  red: 'bg-red-50 border-red-100',
  purple: 'bg-purple-50 border-purple-100',
  gray: 'bg-gray-50 border-gray-200',
}

const bgClass = computed(() => colorMap[props.color] || colorMap.blue)

const formattedValue = computed(() => {
  const v = props.value
  if (v === null || v === undefined || v === '') return '-'
  if (props.format === 'percent') return `${Number(v).toFixed(1)}%`
  if (props.format === 'hours') return `${Number(v).toFixed(1)}h`
  if (props.format === 'star') return '⭐'.repeat(Math.round(Number(v))) || '-'
  if (props.format === 'text') return String(v)
  return String(v)
})
</script>
