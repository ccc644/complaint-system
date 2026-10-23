<!-- 0724 进度历史 — 垂直时间线展示 -->
<template>
  <div v-if="history.length" class="space-y-3">
    <h4 class="text-sm font-medium text-gray-600">📜 工程师处理进度历史（共 {{ history.length }} 条）</h4>
    <div class="relative pl-6 border-l-2 border-gray-200 space-y-4">
      <div v-for="h in history" :key="h.id" class="relative">
        <div class="absolute -left-[25px] w-3 h-3 rounded-full border-2 border-primary bg-white"></div>
        <div class="text-sm">
          <span class="font-semibold text-primary">{{ h.progress_pct }}%</span>
          <span class="text-gray-500 ml-2">{{ h.created_at }}</span>
          <span class="text-gray-400 ml-1">（{{ h.updated_by }}）</span>
        </div>
        <div class="text-sm text-gray-600 mt-0.5">{{ h.note }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ history: Array<{ id: number; progress_pct: number; note: string; updated_by: string; created_at: string }> }>()
</script>
