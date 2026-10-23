<!-- 0727 知识库卡片 — 内容展示 + 多维度投票
     来源：components/kb_card.py（v2.1 Streamlit）-->
<template>
  <div class="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
    <!-- 头部 -->
    <div class="flex items-start justify-between gap-3">
      <div class="flex-1 min-w-0">
        <!-- 0901 标题行整合：客诉编号(可点跳工单详情) + 标题分段 + 型号 + 入库时间，间距拉开；原独立元信息行删除 -->
        <div class="flex items-baseline flex-wrap gap-x-3 gap-y-1">
          <button v-if="entry.complaint_no" type="button" @click="goComplaint"
            :disabled="jumpLoading || jumpDeleted"
            :title="jumpDeleted ? '该工单已被删除' : '点击查看工单详情'"
            class="font-semibold text-sm mono tnum transition"
            :class="jumpDeleted
              ? 'text-gray-400 cursor-not-allowed line-through'
              : 'text-primary hover:underline cursor-pointer'">
            {{ entry.complaint_no }}
          </button>
          <span v-if="jumpDeleted" class="text-xs text-red-400">已删除</span>
          <span v-for="(seg, i) in titleSegments" :key="i" class="font-semibold text-sm text-gray-800">{{ seg }}</span>
          <span v-if="entry.equipment_model" class="text-xs text-gray-800">型号 {{ entry.equipment_model }}</span>
          <span class="text-xs text-gray-800">入库时间 <span class="mono tnum">{{ entry.created_at?.slice(0, 10) }}</span></span>
        </div>
        <!-- 0730 故障现象 -->
        <p v-if="entry.fault_phenomenon" class="text-sm text-gray-600 mt-1.5 line-clamp-2">{{ entry.fault_phenomenon }}</p>
      </div>
      <!-- 满意度 -->
      <div v-if="satisfaction !== null" class="text-xs text-yellow-500 shrink-0">
        {{ '⭐'.repeat(satisfaction) }}
      </div>
    </div>

    <!-- 内容展开 -->
    <details class="text-sm">
      <summary class="cursor-pointer text-primary font-medium select-none">📖 查看详情</summary>
      <div class="mt-2 space-y-2 pl-1">
        <div v-if="entry.root_cause">
          <span class="font-medium text-gray-700">🔧 根因分析：</span>
          <span class="text-gray-600">{{ entry.root_cause }}</span>
        </div>
        <div v-if="entry.solution">
          <span class="font-medium text-gray-700">✅ 解决方案：</span>
          <span class="text-gray-600">{{ entry.solution }}</span>
        </div>
        <div v-if="entry.checklist">
          <span class="font-medium text-gray-700">📋 检查清单：</span>
          <pre class="text-gray-600 whitespace-pre-wrap font-sans mt-1">{{ entry.checklist }}</pre>
        </div>
        <div v-if="entry.lesson_learned">
          <span class="font-medium text-gray-700">💡 经验教训：</span>
          <pre class="text-gray-600 whitespace-pre-wrap font-sans mt-1">{{ entry.lesson_learned }}</pre>
        </div>
      </div>
    </details>

    <!-- 0727 评价一行化：👍👎 + 好评率 + 5 维评分 + 综合分 收纳进单行，减少卡片高度 -->
    <div class="flex items-center gap-1.5 flex-wrap border-t border-gray-100 pt-2 text-xs">
      <!-- 👍 / 👎 -->
      <button @click="doVote('useful')" :disabled="cooldowns['useful'] > 0" title="有用"
        class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border transition"
        :class="cooldowns['useful'] > 0 ? 'bg-gray-50 text-gray-400 cursor-not-allowed border-gray-200' : 'border-green-300 text-green-700 hover:bg-green-50'">
        👍 <span class="tnum">{{ entry.useful_count || 0 }}</span><span v-if="cooldowns['useful'] > 0" class="text-[10px]">({{ cooldowns['useful'] }}s)</span>
      </button>
      <button @click="doVote('unhelpful')" :disabled="cooldowns['unhelpful'] > 0" title="无帮助"
        class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border transition"
        :class="cooldowns['unhelpful'] > 0 ? 'bg-gray-50 text-gray-400 cursor-not-allowed border-gray-200' : 'border-red-300 text-red-700 hover:bg-red-50'">
        👎 <span class="tnum">{{ entry.unhelpful_count || 0 }}</span><span v-if="cooldowns['unhelpful'] > 0" class="text-[10px]">({{ cooldowns['unhelpful'] }}s)</span>
      </button>

      <!-- 好评率迷你条 -->
      <span class="flex items-center gap-1 text-gray-400" title="好评率">
        <span class="w-12 h-1.5 bg-gray-100 rounded-full overflow-hidden inline-block">
          <span class="block h-full bg-green-500 rounded-full transition-all" :style="{ width: positivePct + '%' }"></span>
        </span>
        <span class="tnum">{{ positivePct }}%</span>
      </span>

      <span class="h-3 w-px bg-gray-200 mx-0.5"></span>

      <!-- 5 维评分 chips（图标 + 标签 + 票数，利于快速识别评价维度） -->
      <button v-for="dim in [...techDims, ...bizDims]" :key="dim.key"
        @click="doVoteDimension(dim.key)" :disabled="cooldowns[dim.key] > 0" :title="dim.label"
        class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border transition text-[11px]"
        :class="cooldowns[dim.key] > 0 ? 'bg-gray-50 text-gray-400 cursor-not-allowed border-gray-200' : 'border-gray-300 text-gray-600 hover:bg-blue-50 hover:border-blue-300'">
        {{ dim.icon }}{{ dim.label }} <span class="tnum">{{ getDimValue(dim.key) }}</span><span v-if="cooldowns[dim.key] > 0" class="text-[10px]">({{ cooldowns[dim.key] }}s)</span>
      </button>

      <!-- 综合评分 -->
      <span class="ml-auto font-medium text-amber-600 cursor-default"
        :title="`工程师 ${engScore} + 售前 ${preScore} + 有用 ${entry.useful_count || 0}`">
        ⭐ <span class="tnum">{{ compScore }}</span>
      </span>
    </div>

    <!-- 0805 Phase 4: 案例检索评价统计 -->
    <div v-if="caseFeedbackStats && caseFeedbackStats.total_feedback > 0" class="border-t border-blue-100 pt-2 text-xs flex items-center gap-3 flex-wrap">
      <span class="text-blue-600 font-medium" title="被工单引用次数">📋 被引用 {{ caseFeedbackStats.total_feedback }} 次</span>
      <span class="text-gray-500">|</span>
      <span :class="caseFeedbackStats.reference_pct >= 60 ? 'text-green-600' : 'text-yellow-600'" title="可参考率">
        👍 可参考率 {{ caseFeedbackStats.reference_pct }}%
      </span>
      <span class="text-gray-500">|</span>
      <span class="text-yellow-600" title="检索匹配准确性">⭐ 匹配度 {{ caseFeedbackStats.avg_match_accuracy }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import type { KBEntry } from '@/types/api'
import { useKnowledgeStore } from '@/stores/knowledge'
import { getKbCaseFeedback } from '@/api/knowledge'
import { getComplaintIdByNo } from '@/api/complaints'

const props = defineProps<{
  entry: KBEntry
}>()

const store = useKnowledgeStore()
const router = useRouter()

// 0901 标题分段：标题按空白拆段拉开间距展示；客诉编号已含在标题里时由专属按钮展示、分段中不再重复
const titleSegments = computed(() => {
  const segs = (props.entry.title || '').trim().split(/\s+/).filter(Boolean)
  const no = props.entry.complaint_no
  return no ? segs.filter(s => s !== no) : segs
})

// 0901 点击客诉编号跳转工单详情（工单号→ID，复用通知中心跳转接口；404=工单已删除）
const jumpLoading = ref(false)
const jumpDeleted = ref(false)

async function goComplaint() {
  if (!props.entry.complaint_no || jumpLoading.value || jumpDeleted.value) return
  jumpLoading.value = true
  try {
    const r = await getComplaintIdByNo(props.entry.complaint_no)
    const id = r.data?.data?.id
    if (id) {
      router.push(`/work-order/${id}`)
    } else {
      jumpDeleted.value = true
    }
  } catch (e: any) {
    if (e?.response?.status === 404) jumpDeleted.value = true
    else console.error('KBCard jump error:', e)
  } finally {
    jumpLoading.value = false
  }
}

// 0805 Phase 4: 案例检索评价统计
const caseFeedbackStats = ref<any>(null)
onMounted(async () => {
  try {
    const r = await getKbCaseFeedback(props.entry.id)
    if (r.data?.success) caseFeedbackStats.value = r.data.data
  } catch (e) { /* silent */ }
})

const techDims = [
  { key: 'accuracy', label: '根因准确', icon: '🎯' },
  { key: 'effectiveness', label: '方案有效', icon: '🔧' },
  { key: 'clarity', label: '步骤清晰', icon: '📋' },
]
const bizDims = [
  { key: 'customer_impact', label: '客户影响', icon: '⚡' },
  { key: 'presales_value', label: '售前标杆', icon: '💼' },
]

// 冷却计时器（每个维度一个）
const cooldowns = ref<Record<string, number>>({})
const timers: Record<string, ReturnType<typeof setInterval>> = {}

function startCooldown(key: string) {
  cooldowns.value[key] = 60
  timers[key] = setInterval(() => {
    if (cooldowns.value[key] > 0) {
      cooldowns.value[key]--
    } else {
      clearInterval(timers[key])
      delete timers[key]
    }
  }, 1000)
}

async function doVote(type: 'useful' | 'unhelpful') {
  const ok = type === 'useful'
    ? await store.voteUseful(props.entry.id)
    : await store.voteUnhelpful(props.entry.id)
  if (ok) {
    startCooldown(type)
    if (type === 'useful') props.entry.useful_count++
    else props.entry.unhelpful_count++
  }
}

async function doVoteDimension(dim: string) {
  const ok = await store.voteDimension(props.entry.id, dim)
  if (ok) {
    startCooldown(dim)
    const key = dim + '_votes' as keyof KBEntry
    ;(props.entry as any)[key] = (props.entry as any)[key] + 1
  }
}

function getDimValue(dim: string): number {
  const key = (dim + '_votes') as keyof KBEntry
  return (props.entry as any)[key] || 0
}

// 评分计算
const engScore = computed(() => {
  return (props.entry.accuracy_votes || 0) * 3 +
    (props.entry.effectiveness_votes || 0) * 3 +
    (props.entry.clarity_votes || 0) * 2
})
const preScore = computed(() => {
  return (props.entry.customer_impact_votes || 0) * 2 +
    (props.entry.presales_value_votes || 0) * 3
})
const compScore = computed(() => engScore.value + preScore.value + (props.entry.useful_count || 0))

const positivePct = computed(() => {
  const u = props.entry.useful_count || 0
  const d = props.entry.unhelpful_count || 0
  const total = u + d
  return total > 0 ? Math.round((u / total) * 100) : 0
})

// satisfaction 是 computed 从 complaint_no lookup，此处用 0 避免每卡都调 API
const satisfaction = ref<number | null>(null)

onUnmounted(() => {
  Object.values(timers).forEach(clearInterval)
})
</script>
