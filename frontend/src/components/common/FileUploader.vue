<!-- 0724 文件上传组件 — 拖放/点击上传 + 文件列表 -->
<template>
  <div class="space-y-3">
    <!-- 上传区域 -->
    <div
      :class="['border-2 border-dashed rounded-lg p-3 text-center transition cursor-pointer',
        isDragOver ? 'border-primary bg-primary/5' : 'border-gray-300 hover:border-gray-400 bg-gray-50']"
      @dragover.prevent="isDragOver = true"
      @dragleave.prevent="isDragOver = false"
      @drop.prevent="onDrop"
      @click="triggerInput">
      <input ref="fileInput" type="file" :accept="acceptStr" multiple hidden @change="onFileSelect" />
      <div class="text-gray-400">
        <Upload :size="20" class="mx-auto" />
        <p class="text-sm">拖放文件到此处或 <span class="text-primary">点击选择</span></p>
        <p class="text-xs text-gray-400 mt-1">
          {{ whitelistStr }} · 单文件≤{{ maxSizeMB }}MB · 最多{{ maxPerUpload }}个/次
        </p>
      </div>
    </div>

    <!-- 校验错误 -->
    <div v-if="errors.length" class="space-y-1">
      <div v-for="(e, i) in errors" :key="i" class="text-xs text-red-600 bg-red-50 px-3 py-1 rounded">{{ e }}</div>
    </div>

    <!-- 已选文件列表 -->
    <div v-if="selectedFiles.length" class="space-y-1">
      <div v-for="(f, i) in selectedFiles" :key="i"
        class="flex items-center justify-between text-sm bg-white border border-gray-200 rounded px-3 py-2">
        <div class="flex items-center gap-2 min-w-0">
          <span class="text-base">{{ fileIcon(f.name) }}</span>
          <span class="truncate text-gray-700">{{ f.name }}</span>
          <span class="text-xs text-gray-400 shrink-0">{{ formatSize(f.size) }}</span>
        </div>
        <button @click="removeFile(i)" class="text-red-400 hover:text-red-600 ml-2 shrink-0">✕</button>
      </div>
    </div>

    <!-- 0730 附件配额：计入已选文件 + 已有文件 -->
    <div class="text-xs text-gray-400">
      当前 {{ currentTotal }}/{{ maxTotal }}，还可 {{ remaining }} 个
      <span v-if="selectedFiles.length" class="text-primary">（已选 {{ selectedFiles.length }} 个）</span>
    </div>

    <!-- 上传按钮（外部使用时通过 slot 或手动调用） -->
    <slot name="actions" :upload="doUpload" :files="selectedFiles" :clear="clearFiles" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Upload } from 'lucide-vue-next'

const WHITELIST = ['jpg','jpeg','png','gif','bmp','webp','pdf','log','txt','csv','xlsx','xls','docx','doc']
const MAX_SIZE_MB = 10
const MAX_PER_UPLOAD = 5
const MAX_TOTAL = 20

const props = defineProps<{ existingCount?: number }>()
const emit = defineEmits<{ upload: [files: File[]] }>()

const existingCount = computed(() => props.existingCount || 0)
const currentTotal = computed(() => existingCount.value + selectedFiles.value.length)
const remaining = computed(() => Math.max(0, MAX_TOTAL - currentTotal.value))

const whitelistStr = WHITELIST.map(e => '.' + e).join('/')
const acceptStr = WHITELIST.map(e => '.' + e).join(',')
const maxSizeMB = MAX_SIZE_MB
const maxPerUpload = MAX_PER_UPLOAD
const maxTotal = MAX_TOTAL

const fileInput = ref<HTMLInputElement>()
const isDragOver = ref(false)
const selectedFiles = ref<File[]>([])
const errors = ref<string[]>([])

function triggerInput() { fileInput.value?.click() }
function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}
function fileIcon(name: string) {
  const ext = name.split('.').pop()?.toLowerCase() || ''
  if (['jpg','jpeg','png','gif','bmp','webp'].includes(ext)) return '🖼️'
  if (ext === 'pdf') return '📄'
  if (['xlsx','xls','csv'].includes(ext)) return '📊'
  if (['docx','doc'].includes(ext)) return '📝'
  return '📎'
}

function validate(files: FileList | File[]): File[] {
  const valid: File[] = []
  const errs: string[] = []
  for (const f of files) {
    const ext = f.name.split('.').pop()?.toLowerCase() || ''
    if (!WHITELIST.includes(ext)) { errs.push(`「${f.name}」不支持的类型`); continue }
    if (f.size > MAX_SIZE_MB * 1024 * 1024) { errs.push(`「${f.name}」超过${MAX_SIZE_MB}MB`); continue }
    valid.push(f)
  }
  if (selectedFiles.value.length + valid.length > MAX_PER_UPLOAD) {
    errs.push(`单次最多${MAX_PER_UPLOAD}个文件`)
  }
  if (currentTotal.value + valid.length > MAX_TOTAL) {
    errs.push(`超出工单总配额（${MAX_TOTAL}个）`)
  }
  errors.value = errs
  return valid
}

function addFiles(files: FileList | File[]) {
  const valid = validate(files)
  selectedFiles.value.push(...valid)
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) addFiles(input.files)
  input.value = ''
}

function onDrop(e: DragEvent) {
  isDragOver.value = false
  if (e.dataTransfer?.files) addFiles(e.dataTransfer.files)
}

function removeFile(i: number) { selectedFiles.value.splice(i, 1); errors.value = [] }
function clearFiles() { selectedFiles.value = []; errors.value = [] }

async function doUpload() {
  if (!selectedFiles.value.length) return
  emit('upload', [...selectedFiles.value])
}

defineExpose({ doUpload, clearFiles, selectedFiles })
</script>
