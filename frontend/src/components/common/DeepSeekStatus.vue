<!-- 0727 DeepSeek 连接状态指示器 -->
<template>
  <div class="flex items-center gap-2 text-xs" :class="statusClass">
    <span v-if="loading">⚪ 检测中...</span>
    <span v-else-if="connected">🟢 已连接（{{ latency }}ms）</span>
    <span v-else>🔴 {{ error || '未连接' }}</span>
    <button
      v-if="!loading"
      @click="check"
      class="text-primary hover:underline ml-1"
      title="重新检测"
    >🔄</button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { checkDeepSeekStatus } from '@/api/ai'

const connected = ref(false)
const latency = ref(0)
const error = ref('')
const loading = ref(false)

const statusClass = ref('text-gray-400')

async function check() {
  loading.value = true
  try {
    const r = await checkDeepSeekStatus()
    if (r.data?.success) {
      const d = r.data.data
      connected.value = d.connected
      latency.value = d.latency_ms ?? 0
      error.value = d.error || ''
      statusClass.value = d.connected ? 'text-green-600' : 'text-red-500'
    }
  } catch {
    connected.value = false
    error.value = '检测失败'
    statusClass.value = 'text-red-500'
  } finally { loading.value = false }
}

// 自动检测一次
check()
</script>
