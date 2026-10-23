<!-- 0730 AI辅助效果评价卡片
     0820 风格调整：去粉色少女风与撒娇文案，改中性简洁风格（与系统其他卡片一致） -->
<template>
  <div v-if="visible" class="overflow-hidden transition-all duration-300"
    :class="dismissed ? 'max-h-0 opacity-0' : 'max-h-[800px] opacity-100'">
    <!-- 0820 底色改浅灰；高度上限 800px 避免截断「提交评价」按钮（页面可整体滚动） -->
    <div class="mt-3 bg-gray-50 border border-gray-200 rounded-lg p-5">

      <!-- 标题栏 -->
      <div class="flex items-center justify-between mb-3">
        <span class="text-base font-bold text-gray-800">AI 辅助效果评价</span>
        <button @click="handleDismiss" class="text-gray-400 hover:text-gray-600 transition-colors" title="稍后评价">
          <X :size="14" />
        </button>
      </div>

      <!-- 说明文案 -->
      <p class="text-sm text-gray-600 mb-4 leading-relaxed">
        请评价一下这次 AI 辅助效果：
      </p>

      <!-- 提交成功 -->
      <div v-if="submitted" class="text-center py-4">
        <p class="text-green-600 text-base font-semibold">
          感谢反馈，评价已提交
        </p>
      </div>

      <div v-else class="space-y-4">

        <!-- 维度1: AI准确度 — 星星 -->
        <div>
          <div class="text-sm text-gray-700 font-medium mb-2">建议准确度</div>
          <div class="flex gap-1.5 items-center">
            <button v-for="s in 5" :key="s" @click="form.ai_accuracy = s"
              class="star-btn w-9 h-9 rounded-full text-xl transition-all duration-150 select-none"
              :class="form.ai_accuracy >= s
                ? 'text-amber-400 scale-110'
                : 'text-gray-300 hover:text-amber-300 hover:scale-105'">
              ★
            </button>
            <span v-if="form.ai_accuracy > 0" class="ml-2 text-sm text-gray-500 font-medium">
              {{ ['', '完全不靠谱', '不太行', '还可以', '挺准的', '超级准'][form.ai_accuracy] }}
            </span>
          </div>
        </div>

        <!-- 维度2: 省时间 -->
        <div>
          <div class="text-sm text-gray-700 font-medium mb-2">是否节省了时间</div>
          <div class="flex flex-wrap gap-2">
            <button v-for="opt in timeOptions" :key="opt.value"
              @click="form.ai_time_saved = opt.value"
              class="px-3 py-1.5 rounded-lg text-sm transition-all duration-150"
              :class="form.ai_time_saved === opt.value
                ? 'bg-primary text-white shadow-sm'
                : 'bg-white border border-gray-200 text-gray-600 hover:border-primary/40 hover:bg-primary/5'">
              {{ opt.label }}
            </button>
          </div>
        </div>

        <!-- 0820 维度3: 是否采纳 AI 建议（替代硬编码 0，补全采纳率统计） -->
        <div>
          <div class="text-sm text-gray-700 font-medium mb-2">是否采纳了 AI 建议</div>
          <div class="flex flex-wrap gap-2">
            <button @click="form.ai_adopted = 1"
              class="px-3 py-1.5 rounded-lg text-sm transition-all duration-150"
              :class="form.ai_adopted === 1
                ? 'bg-primary text-white shadow-sm'
                : 'bg-white border border-gray-200 text-gray-600 hover:border-primary/40 hover:bg-primary/5'">
              采纳了
            </button>
            <button @click="form.ai_adopted = -1"
              class="px-3 py-1.5 rounded-lg text-sm transition-all duration-150"
              :class="form.ai_adopted === -1
                ? 'bg-primary text-white shadow-sm'
                : 'bg-white border border-gray-200 text-gray-600 hover:border-primary/40 hover:bg-primary/5'">
              没采纳
            </button>
          </div>
        </div>

        <!-- 自由评价 -->
        <div>
          <textarea v-model="form.ai_comment" rows="3"
            placeholder="补充评价（选填）…"
            class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
              placeholder-gray-400 focus:ring-2 focus:ring-primary/30 focus:border-primary
              transition-colors"></textarea>
        </div>

        <!-- 提交 -->
        <div class="flex items-center gap-2">
          <button @click="doSubmit" :disabled="!canSubmit || loading"
            class="px-5 py-2 bg-primary text-white rounded-base text-sm font-semibold
              hover:bg-primary/90 disabled:opacity-40 transition-all duration-150
              active:scale-95">
            {{ loading ? '发送中...' : '提交评价' }}
          </button>
          <span v-if="errorMsg" class="text-xs text-red-500">{{ errorMsg }}</span>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { X } from 'lucide-vue-next'
import { submitFeedback } from '@/api/feedback'

const props = defineProps<{
  complaintNo: string
  feedbackType: string  // intake/evaluate/assign/resolve/confirm
  autoShow?: boolean
  // 0730 工单上下文 + AI 建议内容（可选，未传则为空）
  complaintContext?: {
    fault_category?: string
    equipment_model?: string
    status?: string
    responsible_dept?: string
  } | null
  aiSuggestion?: string
}>()

const emit = defineEmits<{
  submitted: []
  dismissed: []
}>()

const visible = ref(true)
const dismissed = ref(false)
const submitted = ref(false)
const loading = ref(false)
const errorMsg = ref('')

const form = ref({
  ai_accuracy: 0,
  ai_time_saved: '',
  ai_adopted: 1,  // 0820 默认采纳，用户可改为未采纳（-1）
  ai_comment: '',
})

const timeOptions = [
  { value: 'significant', label: '省了好多' },
  { value: 'moderate', label: '帮到一点点' },
  { value: 'slight', label: '没啥感觉' },
  { value: 'negative', label: '反而更慢了' },
  { value: 'none', label: '本次没用到 AI' },  // 0820 补 none 选项（后端本就允许）
]

const canSubmit = computed(() =>
  form.value.ai_accuracy > 0 && !!form.value.ai_time_saved
)

function handleDismiss() {
  dismissed.value = true
  emit('dismissed')
}

async function doSubmit() {
  if (!canSubmit.value) return
  loading.value = true
  errorMsg.value = ''
  try {
    const r = await submitFeedback({
      complaint_no: props.complaintNo,
      feedback_type: props.feedbackType,
      ai_accuracy: form.value.ai_accuracy,
      ai_time_saved: form.value.ai_time_saved,
      ai_adopted: form.value.ai_adopted,  // 0820 1=采纳 / -1=未采纳
      ai_comment: form.value.ai_comment,
      // 0730 工单上下文 + AI 建议内容
      fault_category: props.complaintContext?.fault_category || '',
      equipment_model: props.complaintContext?.equipment_model || '',
      complaint_status: props.complaintContext?.status || '',
      responsible_dept: props.complaintContext?.responsible_dept || '',
      ai_suggestion: props.aiSuggestion || '',
    })
    if (r.data?.success) {
      submitted.value = true
      emit('submitted')
      setTimeout(() => { dismissed.value = true }, 1500)
    } else {
      errorMsg.value = r.data?.message || '提交失败'
    }
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '提交失败，请稍后重试'
  } finally { loading.value = false }
}
</script>

<style scoped>
.star-btn {
  line-height: 1;
}
.star-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .star-btn {
    transition: none !important;
  }
  .transition-all,
  .transition-colors {
    transition: none !important;
  }
}
</style>
