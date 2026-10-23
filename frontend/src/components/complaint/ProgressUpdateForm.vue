<!-- 0724 进度更新表单 — 工程师周更进度 -->
<template>
  <div class="space-y-4">
    <h3 class="text-lg font-semibold">📈 每周进度更新（D9）</h3>
    <p class="text-xs text-gray-500">承接人需定期更新任务进度百分比</p>

    <div v-if="plannedInfo" class="text-sm bg-blue-50 text-blue-700 p-2 rounded">{{ plannedInfo }}</div>
    <div v-if="latestUpdate" class="text-sm bg-gray-50 p-2 rounded">
      📅 最近一次更新：<strong>{{ latestUpdate.progress_pct }}%</strong> — {{ latestUpdate.updated_by }} @ {{ latestUpdate.created_at }}
      <span v-if="latestUpdate.note"> — {{ latestUpdate.note }}</span>
    </div>

    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">本次处理进度百分比</label>
      <div class="flex items-center gap-3">
        <input v-model.number="progressPct" type="range" :min="0" max="100" step="5"
          class="flex-1 accent-primary" />
        <span class="text-sm font-bold w-10 text-right">{{ progressPct }}%</span>
      </div>
    </div>

    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">本周进展说明 <span class="text-red-500">*</span></label>
      <textarea v-model="note" rows="4" placeholder="如：已完成胶阀温度传感器更换与初步校准…"
        class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
    </div>

    <!-- 0826 附件上传：可多次选择累积追加，选后展示清单可单个移除 -->
    <div class="space-y-2">
      <div class="flex items-center gap-2 flex-wrap">
        <span class="text-xs text-gray-500">📎 追加附件（选填，可多选）：</span>
        <label
          class="px-3 py-1.5 bg-white border border-gray-300 rounded text-xs text-gray-700 hover:bg-gray-50 hover:border-gray-400 cursor-pointer transition">
          ＋ 选择文件
          <input type="file" multiple @change="onFilesChange" class="hidden" />
        </label>
        <span v-if="selectedFiles.length" class="text-xs text-gray-500">共 {{ selectedFiles.length }} 个文件</span>
      </div>
      <div v-if="selectedFiles.length" class="space-y-1">
        <div v-for="(f, i) in selectedFiles" :key="f.name + f.size"
          class="flex items-center gap-2 text-xs bg-gray-50 border border-gray-200 rounded px-2 py-1.5">
          <span class="flex-1 truncate text-gray-700">{{ f.name }}</span>
          <span class="text-gray-400 shrink-0">({{ (f.size / 1024).toFixed(1) }}KB)</span>
          <button type="button" @click="removeFile(i)" title="移除"
            class="shrink-0 w-5 h-5 flex items-center justify-center rounded text-gray-400 hover:text-red-600 hover:bg-red-50 transition">✕</button>
        </div>
      </div>
      <p v-if="fileHint" class="text-xs text-amber-600">{{ fileHint }}</p>
    </div>

    <div v-if="errorMsg" class="text-red-600 text-sm bg-red-50 p-2 rounded">{{ errorMsg }}</div>
    <div v-if="successMsg" class="text-green-600 text-sm bg-green-50 p-2 rounded">{{ successMsg }}</div>

    <button @click="handleSubmit" :disabled="loading"
      class="w-full px-4 py-2 bg-primary text-white rounded-base hover:bg-primary/90 disabled:opacity-50 transition font-medium">
      💾 提交进度更新
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import apiClient from '@/api/client'
import { formatDateTime } from '@/utils/datetime'

const props = defineProps<{
  complaintId: number
  plannedStart?: string
  plannedEnd?: string
  latestProgress?: { progress_pct: number; note: string; updated_by: string; created_at: string } | null
}>()
const emit = defineEmits<{ done: [] }>()

const progressPct = ref(props.latestProgress?.progress_pct || 0)
// 0806 禁止反向拉动：如果值被拉到低于上次进度，自动弹回
watch(progressPct, (val) => {
  const minVal = props.latestProgress?.progress_pct || 0
  if (val < minVal) progressPct.value = minVal
})
const note = ref('')
const selectedFiles = ref<File[]>([])
const fileHint = ref('')
const loading = ref(false)

// 0826 累积式文件选择：多次选择追加而非覆盖，可单个移除，同名去重
function onFilesChange(e: Event) {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (!files?.length) return
  const existing = new Set(selectedFiles.value.map(f => f.name))
  const dup: string[] = []
  for (const f of Array.from(files)) {
    if (existing.has(f.name)) { dup.push(f.name); continue }
    selectedFiles.value.push(f)
    existing.add(f.name)
  }
  fileHint.value = dup.length ? `已跳过重复文件：${dup.join('、')}` : ''
  input.value = ''  // 重置以允许再次选择同名/任意文件继续追加
}

function removeFile(idx: number) {
  selectedFiles.value.splice(idx, 1)
}
const errorMsg = ref('')
const successMsg = ref('')

const plannedInfo = computed(() => {
  // 0914 排期时间去 T 展示（datetime-local 原值形如 2026-09-14T10:30）
  if (props.plannedStart || props.plannedEnd) return `📅 计划排期：${formatDateTime(props.plannedStart) || '—'} → ${formatDateTime(props.plannedEnd) || '—'}`
  return ''
})
const latestUpdate = computed(() => props.latestProgress)

async function handleSubmit() {
  errorMsg.value = ''; successMsg.value = ''
  if (!note.value.trim()) { errorMsg.value = '请填写本周进展说明'; return }
  loading.value = true
  try {
    const r = await apiClient.post(`/api/complaints/${props.complaintId}/progress`, {
      progress_pct: progressPct.value, note: note.value.trim(),
    })
    if (r.data?.success) {
      // 上传附件（如有选中的文件）
      if (selectedFiles.value.length) {
        const fd = new FormData()
        fd.append('complaint_id', String(props.complaintId))
        for (const f of selectedFiles.value) fd.append('files', f)
        await apiClient.post('/api/files/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      }
      successMsg.value = r.data.message; note.value = ''; selectedFiles.value = []; emit('done')
    } else { errorMsg.value = r.data?.message || '更新失败' }
  } catch (e: any) { errorMsg.value = e?.response?.data?.detail || '更新失败' }
  finally { loading.value = false }
}
</script>
