<!-- 0730 工单处理页 — 相似案例卡片（默认无评价行）+ 点击弹出浮层详情 -->
<template>
  <div class="border-2 border-gray-300 rounded-lg p-2.5 text-xs hover:border-primary/50 hover:bg-gray-50/50 cursor-pointer transition-colors"
    @click="showModal = true">
    <!-- 标题行 -->
    <div class="font-medium text-gray-800 truncate">{{ entry.title }}</div>
    <!-- 元信息 -->
    <div class="flex items-center gap-2 mt-0.5 text-gray-500 flex-wrap">
      <span v-if="entry.fault_category" class="px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 text-[10px]">{{ entry.fault_category }}</span>
      <span v-if="entry.equipment_model" class="text-[10px]">{{ entry.equipment_model }}</span>
    </div>
    <!-- 故障现象 2行 -->
    <p v-if="entry.fault_phenomenon" class="mt-1 text-gray-600 leading-relaxed line-clamp-2">{{ entry.fault_phenomenon }}</p>
  </div>

  <!-- 浮层详情（含评价行） -->
  <Teleport to="body">
    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center" @click.self="showModal = false">
      <div class="absolute inset-0 bg-black/30"></div>
      <div class="relative bg-white rounded-xl shadow-2xl max-w-lg w-full mx-4 max-h-[80vh] overflow-y-auto p-6">
        <button @click="showModal = false" class="absolute top-3 right-3 text-gray-400 hover:text-gray-600">
          <X :size="18" />
        </button>
        <h3 class="text-base font-semibold text-gray-800 pr-6">{{ entry.title }}</h3>
        <div class="flex items-center gap-2 mt-1 flex-wrap">
          <span v-if="entry.fault_category" class="text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-600">{{ entry.fault_category }}</span>
          <span v-if="entry.equipment_model" class="text-xs text-gray-400">{{ entry.equipment_model }}</span>
          <span v-if="entry.complaint_no" class="text-xs text-gray-400">📋 {{ entry.complaint_no }}</span>
        </div>

        <div class="mt-4 space-y-3 text-sm">
          <div v-if="entry.fault_phenomenon">
            <div class="font-medium text-gray-700">🔍 故障现象</div>
            <p class="text-gray-600 mt-1 whitespace-pre-wrap">{{ entry.fault_phenomenon }}</p>
          </div>
          <div v-if="entry.root_cause">
            <div class="font-medium text-gray-700">🔧 根因分析</div>
            <p class="text-gray-600 mt-1 whitespace-pre-wrap">{{ entry.root_cause }}</p>
          </div>
          <div v-if="entry.checklist">
            <div class="font-medium text-gray-700">📋 排查步骤</div>
            <pre class="text-gray-600 mt-1 whitespace-pre-wrap font-sans">{{ entry.checklist }}</pre>
          </div>
          <div v-if="entry.solution">
            <div class="font-medium text-gray-700">✅ 解决方案</div>
            <p class="text-gray-600 mt-1 whitespace-pre-wrap">{{ entry.solution }}</p>
          </div>
          <div v-if="entry.lesson_learned">
            <div class="font-medium text-gray-700">💡 经验教训</div>
            <p class="text-gray-600 mt-1 whitespace-pre-wrap">{{ entry.lesson_learned }}</p>
          </div>
        </div>

        <!-- 0805 Phase 4: 案例检索评价 -->
        <div v-if="complaintNo && sourceType" class="mt-4 pt-3 border-t border-primary/10">
          <div class="flex items-center gap-2 text-xs text-gray-500 mb-2">
            <ThumbsUp :size="12" />
            <span>此案例对本次处理：</span>
          </div>

          <!-- 已评价状态 -->
          <div v-if="feedbackSubmitted" class="text-xs space-y-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span :class="feedbackReferenced ? 'text-green-600 font-medium' : 'text-gray-400'">
                {{ feedbackReferenced ? '✅ 已标记为可参考' : 'ℹ️ 已标记为不可参考' }}
              </span>
              <span v-if="feedbackMatchAccuracy > 0" class="text-yellow-600">
                ⭐ 匹配准确性 {{ feedbackMatchAccuracy }} 星
              </span>
            </div>
            <button @click="resetFeedback" class="text-primary hover:underline text-[11px]">修改评价</button>
          </div>

          <!-- 未评价状态 -->
          <div v-else class="space-y-2">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="text-xs text-gray-500">是否可参考？</span>
              <button @click="feedbackReferenced = true"
                :class="['px-2 py-0.5 rounded text-xs transition', feedbackReferenced ? 'bg-green-500 text-white' : 'bg-gray-100 text-gray-600 hover:bg-green-100']">
                👍 可参考
              </button>
              <button @click="feedbackReferenced = false"
                :class="['px-2 py-0.5 rounded text-xs transition', !feedbackReferenced && feedbackReferenced !== null ? 'bg-red-100 text-red-600 ring-1 ring-red-300' : 'bg-gray-100 text-gray-500 hover:bg-red-50']">
                👎 不可参考
              </button>
            </div>

            <div v-if="feedbackReferenced" class="flex items-center gap-1 flex-wrap">
              <span class="text-xs text-gray-500">检索准确性：</span>
              <button v-for="i in 5" :key="i" @click="feedbackMatchAccuracy = i"
                :class="['w-6 h-6 rounded text-xs transition', i <= feedbackMatchAccuracy ? 'bg-yellow-400 text-white' : 'bg-gray-100 text-gray-400 hover:bg-yellow-100']">
                {{ i }}
              </button>
              <span class="text-xs text-gray-400">{{ feedbackMatchAccuracy > 0 ? feedbackMatchAccuracy + '星' : '' }}</span>
            </div>

            <div class="flex items-center gap-2">
              <button @click="doSubmitFeedback" :disabled="feedbackSubmitting"
                class="px-3 py-1 bg-primary text-white rounded text-xs hover:bg-primary/90 disabled:opacity-50 transition">
                {{ feedbackSubmitting ? '提交中...' : '提交评价' }}
              </button>
              <span v-if="feedbackError" class="text-xs text-red-500">{{ feedbackError }}</span>
            </div>
          </div>
        </div>

        <div class="mt-4 flex justify-end">
          <button @click="showModal = false" class="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 transition">关闭</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { X, ThumbsUp } from 'lucide-vue-next'
import type { KBEntry } from '@/types/api'
import { submitCaseFeedback } from '@/api/ai'

const props = defineProps<{
  entry: KBEntry
  complaintNo?: string
  sourceType?: string
  caseFeedbackMap?: Record<string, any>
}>()

const showModal = ref(false)

// 0805 Phase 4: 案例评价
const feedbackKey = computed(() => `${props.entry.id}_${props.sourceType || ''}`)
const existingFeedback = computed(() => props.caseFeedbackMap?.[feedbackKey.value] || null)
const hasFeedback = computed(() => !!existingFeedback.value?.referenced || existingFeedback.value?.match_accuracy > 0)

// 0820 默认「可参考」（用户反馈：不要默认落在不可参考上）
const feedbackReferenced = ref(true)
const feedbackMatchAccuracy = ref(0)
const feedbackSubmitting = ref(false)
const feedbackSubmitted = ref(false)
const feedbackError = ref('')

// 打开浮层时从已有评价初始化
watch(showModal, (v) => {
  if (v) {
    if (hasFeedback.value) {
      feedbackReferenced.value = existingFeedback.value.referenced === 1
      feedbackMatchAccuracy.value = existingFeedback.value.match_accuracy || 0
      feedbackSubmitted.value = true
    } else {
      feedbackReferenced.value = true
      feedbackMatchAccuracy.value = 0
      feedbackSubmitted.value = false
    }
    feedbackError.value = ''
  }
})

async function doSubmitFeedback() {
  if (!props.complaintNo || !props.sourceType) return
  feedbackSubmitting.value = true
  feedbackError.value = ''
  try {
    await submitCaseFeedback({
      complaint_no: props.complaintNo,
      kb_id: props.entry.id,
      kb_title: props.entry.title || '',
      source_type: props.sourceType,
      referenced: feedbackReferenced.value,
      match_accuracy: feedbackMatchAccuracy.value,
    })
    feedbackSubmitted.value = true
  } catch (e: any) {
    feedbackError.value = e?.response?.data?.detail || '提交失败'
  } finally {
    feedbackSubmitting.value = false
  }
}

function resetFeedback() {
  feedbackSubmitted.value = false
  feedbackReferenced.value = true
  feedbackMatchAccuracy.value = 0
  feedbackError.value = ''
}

const compositeScore = computed(() => {
  const e = props.entry
  const eng = (e.accuracy_votes || 0) * 3 + (e.effectiveness_votes || 0) * 3 + (e.clarity_votes || 0) * 2
  const presales = (e.customer_impact_votes || 0) * 2 + (e.presales_value_votes || 0) * 3
  return eng + presales + (e.useful_count || 0)
})
</script>
