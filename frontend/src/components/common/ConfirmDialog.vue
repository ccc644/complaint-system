<!-- 0724 通用确认弹窗 — 用于删除/作废等危险操作确认 -->
<template>
  <Teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="onCancel"></div>
      <div class="relative bg-white rounded-lg shadow-xl p-6 w-full max-w-md mx-4">
        <div class="flex items-start gap-3">
          <div :class="['w-10 h-10 rounded-full flex items-center justify-center shrink-0', iconBg]">
            <AlertTriangle :size="20" :class="iconColor" />
          </div>
          <div class="flex-1">
            <h3 class="text-lg font-semibold text-gray-900">{{ title }}</h3>
            <p class="mt-1 text-sm text-gray-500">{{ message }}</p>
          </div>
        </div>
        <!-- 0914 可选内容插槽：状态变更弹窗等需要在确认前填写内容的场景；不传则外观与原来一致 -->
        <slot></slot>
        <div class="mt-6 flex justify-end gap-3">
          <button @click="onCancel"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-base hover:bg-gray-200 transition">
            取消
          </button>
          <button @click="onConfirm"
            :class="['px-4 py-2 text-sm font-medium text-white rounded-base transition', confirmClass]"
            :disabled="loading">
            {{ loading ? '处理中...' : confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { AlertTriangle } from 'lucide-vue-next'

withDefaults(defineProps<{
  visible: boolean
  title?: string
  message?: string
  confirmText?: string
  confirmClass?: string
  loading?: boolean
  iconBg?: string
  iconColor?: string
}>(), {
  title: '确认操作',
  message: '此操作不可恢复，确定要继续吗？',
  confirmText: '确认',
  confirmClass: 'bg-red-600 hover:bg-red-700',
  loading: false,
  iconBg: 'bg-red-100',
  iconColor: 'text-red-600',
})

const emit = defineEmits<{ confirm: []; cancel: [] }>()

function onConfirm() { emit('confirm') }
function onCancel() { emit('cancel') }
</script>
