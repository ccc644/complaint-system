<!-- 0724 解决方案提交 — 承接人/参与人提交最终处理结果 -->
<template>
  <div class="space-y-4">
    <h3 class="text-lg font-semibold">🔧 提交最终处理结果</h3>

    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">📋 排查/复现步骤</label>
      <textarea v-model="reproductionSteps" rows="4" placeholder="记录排查过程…"
        class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
    </div>
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">🔧 根因分析 <span class="text-red-500">*</span></label>
      <textarea v-model="rootCause" rows="5" placeholder="分析根本原因…"
        class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
    </div>
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">✅ 解决方案 <span class="text-red-500">*</span></label>
      <textarea v-model="solution" rows="5" placeholder="描述处理方案…"
        class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
    </div>
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">📝 经验教训（可选）</label>
      <textarea v-model="resolutionNote" rows="3" placeholder="补充说明…"
        class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
    </div>

    <div v-if="errorMsg" class="text-red-600 text-sm bg-red-50 p-2 rounded">{{ errorMsg }}</div>
    <div v-if="successMsg" class="text-green-600 text-sm bg-green-50 p-2 rounded">{{ successMsg }}</div>

    <button @click="handleSubmit" :disabled="loading"
      class="w-full px-4 py-2 bg-green-600 text-white rounded-base hover:bg-green-700 disabled:opacity-50 transition font-medium">
      ✅ 提交处理结果，转客服联系客户确认
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import apiClient from '@/api/client'

const props = defineProps<{ complaintId: number; complaintNo?: string; initialSteps?: string }>()
const emit = defineEmits<{ done: [] }>()

const reproductionSteps = ref(props.initialSteps || '')
const rootCause = ref('')
const solution = ref('')
const resolutionNote = ref('')
const loading = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

async function handleSubmit() {
  errorMsg.value = ''; successMsg.value = ''
  if (!rootCause.value.trim() || !solution.value.trim()) {
    errorMsg.value = '根因分析和解决方案为必填项'; return
  }
  loading.value = true
  try {
    const r = await apiClient.post(`/api/complaints/${props.complaintId}/resolve`, {
      root_cause: rootCause.value.trim(),
      solution: solution.value.trim(),
      reproduction_steps: reproductionSteps.value,
      resolution_note: resolutionNote.value,
      checklist: '',
    })
    if (r.data?.success) { successMsg.value = r.data.message; emit('done') }
    else { errorMsg.value = r.data?.message || '提交失败' }
  } catch (e: any) { errorMsg.value = e?.response?.data?.detail || '提交失败' }
  finally { loading.value = false }
}
</script>
