<!-- 0804 SUS 系统可用性问卷 — 独立弹窗组件
     可在任何页面通过 v-model / ref 控制显隐，提交后 emit success 事件 -->
<template>
  <Teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center">
      <!-- 遮罩（不响应点击，阻止与下层页面交互） -->
      <div class="absolute inset-0 bg-black/50" />
      <!-- 弹窗 -->
      <div class="relative bg-white rounded-xl shadow-2xl w-full max-w-lg mx-4 max-h-[85vh] overflow-y-auto z-10">
        <!-- 头部 -->
        <div class="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between rounded-t-xl">
          <div>
            <h2 class="text-lg font-bold">📋 系统可用性评价</h2>
            <p class="text-xs text-gray-400 mt-0.5">System Usability Scale (SUS) — 10 题标准问卷</p>
          </div>
          <button @click="close" class="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition">
            <span class="text-xl leading-none">&times;</span>
          </button>
        </div>

        <!-- 已提交结果 -->
        <div v-if="submittedScore !== null" class="px-6 py-8 text-center space-y-4">
          <div class="text-5xl">{{ submittedScore >= 80 ? '🎉' : submittedScore >= 68 ? '👍' : '📝' }}</div>
          <div class="text-2xl font-bold" :class="submittedScore >= 68 ? 'text-green-600' : 'text-yellow-600'">
            SUS {{ submittedScore }} 分
          </div>
          <div class="text-sm" :class="submittedScore >= 80.3 ? 'text-green-600' : submittedScore >= 68 ? 'text-blue-600' : 'text-yellow-600'">
            <template v-if="submittedScore >= 80.3">优秀 (A) — 用户体验非常好</template>
            <template v-else-if="submittedScore >= 68">良好 (B) — 高于及格线</template>
            <template v-else-if="submittedScore >= 51">一般 (C) — 有改进空间</template>
            <template v-else>待改进 (F) — 需要重点关注</template>
          </div>
          <button @click="close" class="px-6 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary/90 transition">
            关闭
          </button>
        </div>

        <!-- 冷却期 -->
        <div v-else-if="inCooldown" class="px-6 py-8 text-center space-y-3">
          <div class="text-4xl">🕐</div>
          <p class="text-gray-600 text-sm">您已在问卷冷却期内{{ cooldownDays != null ? `，${cooldownDays} 天后可重新提交` : '' }}</p>
          <button @click="close" class="px-6 py-2 bg-gray-100 text-gray-600 rounded-lg text-sm hover:bg-gray-200 transition">
            关闭
          </button>
        </div>

        <!-- 提交中 -->
        <div v-else-if="submitting" class="px-6 py-12 text-center">
          <div class="text-gray-400 text-sm">提交中...</div>
        </div>

        <!-- 问卷表单 -->
        <div v-else class="px-6 py-4 space-y-3">
          <p class="text-xs text-gray-500 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
            💡 请根据您使用系统的真实感受作答。1=强烈不同意，5=强烈同意。
          </p>
          <div v-for="(q, idx) in QUESTIONS" :key="idx" class="flex items-center gap-2 py-1.5 border-b border-gray-50 last:border-0">
            <span class="text-xs text-gray-400 w-6 text-right shrink-0">{{ idx + 1 }}</span>
            <span class="text-sm flex-1 leading-snug">{{ q }}</span>
            <div class="flex gap-0.5 shrink-0">
              <button v-for="v in 5" :key="v" @click="answers[idx] = v"
                :class="['w-7 h-7 rounded text-xs font-medium transition',
                  answers[idx] === v
                    ? 'bg-primary text-white shadow-sm'
                    : 'bg-gray-100 text-gray-500 hover:bg-gray-200']">
                {{ v }}
              </button>
            </div>
          </div>

          <!-- 0923 补充题（可选，不计入 SUS 分） -->
          <div class="pt-3 space-y-3 border-t border-gray-100">
            <div>
              <p class="text-xs text-gray-500 mb-1.5">您最常使用的功能（可多选，选填 — 帮助分析各模块的体验差异）</p>
              <div class="flex flex-wrap gap-1.5">
                <button v-for="m in MODULES" :key="m" type="button" @click="toggleModule(m)"
                  :class="['px-2.5 py-1 rounded-full text-xs transition',
                    selectedModules.includes(m)
                      ? 'bg-primary text-white shadow-sm'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200']">
                  {{ m }}
                </button>
              </div>
            </div>
            <div>
              <p class="text-xs text-gray-500 mb-1.5">您认为当前最需要改进的一个问题（选填）</p>
              <textarea v-model="improvement" rows="2" maxlength="500"
                class="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary resize-none"
                placeholder="例如：某功能操作步骤太多 / 某个提示不清楚…" />
            </div>
          </div>

          <!-- 错误 -->
          <div v-if="errorMsg" class="text-sm text-red-500 bg-red-50 rounded-lg px-3 py-2">
            {{ errorMsg }}
          </div>

          <!-- 底部按钮 -->
          <div class="flex gap-3 pt-3 pb-1">
            <button @click="submit" :disabled="!allAnswered"
              class="flex-1 py-2.5 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition">
              提交问卷
            </button>
            <button @click="close" class="px-4 py-2.5 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition">
              稍后再说
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import * as evalApi from '@/api/eval'

// SUS 标准 10 题
const QUESTIONS = [
  '我愿意经常使用这个系统',
  '我发现这个系统过于复杂',
  '我认为这个系统容易使用',
  '我需要技术人员的支持才能使用这个系统',
  '我发现这个系统的各项功能整合得很好',
  '我认为这个系统有太多不一致的地方',
  '我认为大多数人都能很快学会使用这个系统',
  '我发现这个系统使用起来很麻烦',
  '我对使用这个系统很有信心',
  '在开始使用这个系统之前，我需要学习很多东西',
]

// 0923 补充题：常用功能选项（与后端 api/eval.py 白名单一致）
const MODULES = ['客诉录入', '审核派单', '工单处理', '案例检索与AI方案', '知识库', '统计看板', '系统评估']

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'success', score: number): void
}>()

const answers = ref<number[]>(Array(10).fill(0))
// 0923 补充题状态（均可跳过，不计入 SUS 分）
const selectedModules = ref<string[]>([])
const improvement = ref('')
const submitting = ref(false)
const submittedScore = ref<number | null>(null)
const inCooldown = ref(false)
const errorMsg = ref('')
// 0902 冷却天数从 check 接口读取（后端 config），不再用 prop/硬编码 90
const cooldownDays = ref<number | null>(null)

const allAnswered = computed(() => answers.value.every(v => v >= 1 && v <= 5))

watch(() => props.visible, async (v) => {
  if (v) {
    // 重置状态
    answers.value = Array(10).fill(0)
    selectedModules.value = []
    improvement.value = ''
    submittedScore.value = null
    errorMsg.value = ''
    // 检查冷却
    try {
      const r = await evalApi.checkSusCooldown()
      inCooldown.value = !r.data?.data?.can_submit
      cooldownDays.value = r.data?.data?.cooldown_days ?? null
    } catch {
      inCooldown.value = false
    }
  }
})

function close() {
  // 关闭/跳过问卷时记录冷却（静默失败，不影响关闭行为）
  evalApi.dismissSusSurvey().catch(() => {})
  emit('update:visible', false)
}

function toggleModule(m: string) {
  const i = selectedModules.value.indexOf(m)
  if (i >= 0) selectedModules.value.splice(i, 1)
  else selectedModules.value.push(m)
}

async function submit() {
  errorMsg.value = ''
  submitting.value = true
  try {
    const r = await evalApi.submitSusSurvey(answers.value, selectedModules.value, improvement.value.trim())
    if (r.data?.success) {
      submittedScore.value = r.data.data.score
      emit('success', r.data.data.score)
    }
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || '提交失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>
