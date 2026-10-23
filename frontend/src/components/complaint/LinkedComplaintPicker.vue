<!-- 0807 关联工单搜索选择器 — 搜索型多选下拉 -->
<template>
  <div ref="rootRef" class="relative">
    <!-- 已选标签（chip）展示 -->
    <div v-if="modelValue.length" class="flex flex-wrap gap-1.5 mb-2">
      <span v-for="item in modelValue" :key="item.id"
        class="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 border border-blue-200 rounded text-xs text-blue-700">
        <span class="font-medium">{{ item.no }}</span>
        <button @click="remove(item.id)" class="text-blue-400 hover:text-red-500 transition text-sm leading-none">&times;</button>
      </span>
    </div>

    <!-- 搜索输入框 -->
    <input
      v-model="query"
      @input="onInput"
      @focus="showDropdown = true"
      type="text"
      placeholder="搜索工单编号 / 客户名称 / 设备编号…"
      class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30"
    />

    <!-- 加载指示器 -->
    <span v-if="searching" class="absolute right-3 top-2 text-gray-400 text-sm">⏳</span>

    <!-- 下拉列表 -->
    <div v-if="showDropdown && (suggestions.length > 0 || query)"
      class="absolute z-20 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
      <div v-if="suggestions.length">
        <div v-for="s in filteredSuggestions" :key="s.id"
          @mousedown.prevent="select(s)"
          :class="[
            'flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-blue-50 transition',
            isSelected(s.id) ? 'opacity-40 bg-gray-50 pointer-events-none' : ''
          ]">
          <span class="font-medium text-gray-800 shrink-0">{{ s.complaint_no }}</span>
          <span class="text-gray-400 text-xs">|</span>
          <span class="text-gray-600 truncate">{{ s.customer_name }}</span>
          <span v-if="s.equipment_sn" class="text-[10px] text-gray-500 mono shrink-0">{{ s.equipment_sn }}</span>
          <span class="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500 shrink-0">{{ s.fault_category }}</span>
          <span v-if="isSelected(s.id)" class="text-green-500 text-xs ml-auto">✓</span>
        </div>
      </div>
      <div v-else class="px-3 py-4 text-center text-xs text-gray-400">
        {{ query ? '未找到匹配工单' : '输入关键词搜索' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { searchComplaints } from '@/api/complaints'
import type { ComplaintSuggestion } from '@/types/api'

const props = defineProps<{
  modelValue: Array<{id: number, no: string}>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Array<{id: number, no: string}>]
}>()

const query = ref('')
const suggestions = ref<ComplaintSuggestion[]>([])
const showDropdown = ref(false)
const searching = ref(false)
const rootRef = ref<HTMLElement | null>(null)

let timer: ReturnType<typeof setTimeout> | null = null

const filteredSuggestions = computed(() => suggestions.value)

function isSelected(id: number) {
  return props.modelValue.some(item => item.id === id)
}

function onInput() {
  if (timer) clearTimeout(timer)
  showDropdown.value = true
  const q = query.value.trim()
  if (!q) {
    suggestions.value = []
    return
  }
  searching.value = true
  timer = setTimeout(async () => {
    try {
      const r = await searchComplaints(q)
      if (r.data?.success) {
        suggestions.value = r.data.data || []
      }
    } catch {
      suggestions.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

function select(item: ComplaintSuggestion) {
  if (isSelected(item.id)) return
  const next = [...props.modelValue, { id: item.id, no: item.complaint_no }]
  emit('update:modelValue', next)
  query.value = ''
  suggestions.value = []
  showDropdown.value = false
}

function remove(id: number) {
  emit('update:modelValue', props.modelValue.filter(item => item.id !== id))
}

// 点击外部关闭下拉
function onClickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    showDropdown.value = false
  }
}

if (typeof document !== 'undefined') {
  document.addEventListener('click', onClickOutside)
}

onUnmounted(() => {
  if (timer) clearTimeout(timer)
  if (typeof document !== 'undefined') {
    document.removeEventListener('click', onClickOutside)
  }
})
</script>
