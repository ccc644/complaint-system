<!-- 0807 优先级徽章 — P0/P1/P2/P3 四级色标，紧凑药丸 -->
<template>
  <span
    :style="{ backgroundColor: bgColor, color: textColor }"
    class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold tracking-wide leading-tight"
  >
    {{ priority === '待确认' ? '—' : priority }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ priority: string }>()

// P0 深红(紧急) · P1 琥珀(高) · P2 绿色(中) · P3 蓝色(低) · 待确认 灰色
const PRIORITY_COLORS: Record<string, { bg: string; text: string }> = {
  P0: { bg: '#dc2626', text: '#ffffff' },
  P1: { bg: '#f59e0b', text: '#ffffff' },
  P2: { bg: '#22c55e', text: '#ffffff' },
  P3: { bg: '#3b82f6', text: '#ffffff' },
  '待确认': { bg: '#e5e7eb', text: '#6b7280' },
}

const bgColor = computed(() => PRIORITY_COLORS[props.priority]?.bg || '#e5e7eb')
const textColor = computed(() => PRIORITY_COLORS[props.priority]?.text || '#6b7280')
</script>
