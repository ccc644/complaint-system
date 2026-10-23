&lt;!-- 0728 客户确认 + 邮件发送 — 邮件区在上 + 确认关闭在下
     来源：v2.1 3_工单处理.py 589-669 行 + 新增邮件功能
     0804 重构：邮件表单始终可见，双路径 — 直接发送 / 转主管审核 -->
<template>
  <div class="space-y-6">
    <!-- ====== 邮件区 ====== -->
    <details :open="true" class="group">
      <summary class="cursor-pointer text-base font-semibold text-gray-700 select-none hover:text-gray-900 py-1">
        📧 发送客户邮件 {{ emailSent ? '（已有发送记录）' : '' }}
      </summary>
      <div class="space-y-4 mt-3 pt-3 border-t border-gray-100">

        <!-- 客户邮箱 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">收件人邮箱</label>
          <input v-model="emailRecipient" type="email" placeholder="如：customer@example.com"
            class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"
            :class="{ 'border-red-300 bg-red-50': !emailRecipient.trim() && emailTouched }" />
          <p v-if="!props.customerEmail && emailTouched" class="text-xs text-red-500 mt-1">
            ⚠️ 该工单未添加客户邮箱，请在录入页补充或在此手动输入
          </p>
        </div>

        <!-- AI 生成草稿 -->
        <div class="flex items-center gap-3 flex-wrap">
          <button @click="doGenerateDraft" :disabled="generating"
            class="px-4 py-1.5 bg-primary text-white rounded text-sm hover:bg-primary/90 disabled:opacity-50 transition font-medium">
            🤖 {{ generating ? '生成中...' : 'AI 生成邮件草稿' }}
          </button>
          <span class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-2 py-0.5">
            ⚠️ <strong>AI 建议仅供参考</strong> — 发送前请核实邮件内容
          </span>
        </div>
        <div v-if="draftError" class="text-xs text-red-500">{{ draftError }}</div>

        <!-- 邮件主题 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">邮件主题</label>
          <input v-model="draftSubject" type="text" placeholder="如：关于XX设备XX问题的处理进展"
            class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm" />
        </div>

        <!-- 邮件正文 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">邮件正文</label>
          <textarea v-model="draftBody" rows="8" placeholder="邮件正文..."
            class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
        </div>

        <!-- 附件选择 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">📎 附件（可选）</label>
          <div v-if="existingAtts.length" class="mb-2">
            <p class="text-xs text-gray-500 mb-1">工单附件：</p>
            <div class="space-y-1 max-h-32 overflow-y-auto">
              <label v-for="att in existingAtts" :key="att.id"
                class="flex items-center gap-2 text-xs cursor-pointer hover:bg-gray-50 px-1 py-0.5 rounded">
                <input type="checkbox" :value="att.id" v-model="selectedAttIds" class="rounded w-3 h-3" />
                <span>{{ att.filename }}</span>
                <span class="text-gray-400">({{ (att.file_size / 1024).toFixed(1) }}KB)</span>
              </label>
            </div>
          </div>
          <p v-else class="text-xs text-gray-400">暂无工单附件</p>
        </div>

        <!-- ====== 审核状态 Banner ====== -->
        <!-- 状态1: 已通过 -->
        <div v-if="emailReviewStatus === 'approved'"
          class="text-sm text-emerald-700 bg-emerald-50 border border-emerald-300 rounded-lg px-3 py-2 flex items-center gap-2">
          <span>✅</span>
          <span>邮件已通过主管审核，可以发送</span>
        </div>

        <!-- 状态2: 等待审核 -->
        <div v-else-if="emailReviewStatus === 'pending'"
          class="text-sm text-blue-700 bg-blue-50 border border-blue-300 rounded-lg px-3 py-2 flex items-start gap-2">
          <span class="shrink-0">⏳</span>
          <div>
            <div class="font-medium">邮件审核中，请等待客服主管审核</div>
            <div class="text-xs text-blue-500 mt-0.5">审核通过后方可发送邮件，或等待审核结束后使用「直接发送」</div>
          </div>
        </div>

        <!-- 状态3: 已拒绝 -->
        <div v-else-if="emailReviewStatus === 'rejected'"
          class="text-sm text-red-700 bg-red-50 border border-red-300 rounded-lg px-3 py-2 space-y-2">
          <div class="flex items-start gap-2">
            <span class="shrink-0">❌</span>
            <div>
              <div class="font-medium">邮件审核被拒绝</div>
              <div v-if="emailReviewNote" class="text-xs text-red-600 mt-0.5">拒绝原因：{{ emailReviewNote }}</div>
            </div>
          </div>
          <div class="text-xs text-red-500">可修改邮件内容后重新提交审核，或使用「直接发送」跳过审核</div>
        </div>

        <!-- ====== 操作按钮区 ====== -->
        <div v-if="emailError" class="text-red-600 text-sm bg-red-50 p-2 rounded">{{ emailError }}</div>
        <div v-if="emailSuccess" class="text-green-600 text-sm bg-green-50 p-2 rounded">{{ emailSuccess }}</div>

        <div class="flex gap-2">
          <!-- 直接发送 -->
          <button @click="doSendEmail"
            :disabled="sending || !emailRecipient.trim() || emailReviewStatus === 'pending'"
            class="flex-1 px-4 py-2 bg-primary text-white rounded-base hover:bg-primary/90 disabled:opacity-50 transition font-medium text-sm"
            :title="emailReviewStatus === 'pending' ? '审核期间不能发送' : '直接发送邮件，无需主管审核'">
            {{ sending ? '发送中...' : '📤 直接发送' }}
          </button>

          <!-- 转主管审核 -->
          <button @click="doSubmitForReview"
            :disabled="reviewSubmitting || emailReviewStatus === 'pending' || !draftSubject.trim() || !draftBody.trim()"
            class="flex-1 px-4 py-2 bg-amber-600 text-white rounded-base hover:bg-amber-700 disabled:opacity-50 transition font-medium text-sm"
            :title="emailReviewStatus === 'pending' ? '已提交审核，请等待' : !draftSubject.trim() || !draftBody.trim() ? '请先填写邮件主题和正文' : '将邮件草稿提交给主管审核'">
            {{ reviewSubmitting ? '提交中...' : emailReviewStatus === 'rejected' ? '🔄 重新提交审核' : '📋 转主管审核' }}
          </button>
        </div>

        <div v-if="reviewMsg" :class="['text-xs', reviewOk ? 'text-green-600' : 'text-red-500']">
          {{ reviewMsg }}
        </div>
      </div>
    </details>

    <hr class="border-gray-200" />

    <!-- ====== 客户确认关闭（客服主管不可见） ====== -->
    <div v-if="canConfirm !== false" class="space-y-4">
      <h3 class="text-lg font-semibold">📋 客户确认</h3>

      <label class="flex items-center gap-2 cursor-pointer">
        <input v-model="confirmed" type="checkbox" class="w-4 h-4 rounded" />
        <span class="text-sm">客户是否确认问题已解决？</span>
      </label>

      <div>
        <label class="block text-sm font-medium text-gray-700 mb-1">客户满意度</label>
        <select v-model="satisfaction" class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm">
          <option :value="0">请选择</option>
          <option :value="1">⭐</option>
          <option :value="2">⭐⭐</option>
          <option :value="3">⭐⭐⭐</option>
          <option :value="4">⭐⭐⭐⭐</option>
          <option :value="5">⭐⭐⭐⭐⭐</option>
        </select>
      </div>

      <div v-if="errorMsg" class="text-red-600 text-sm bg-red-50 p-2 rounded">{{ errorMsg }}</div>
      <div v-if="successMsg" class="text-green-600 text-sm bg-green-50 p-2 rounded">{{ successMsg }}</div>

      <button @click="handleConfirm" :disabled="confirming"
        class="w-full px-4 py-2 bg-green-600 text-white rounded-base hover:bg-green-700 disabled:opacity-50 transition font-medium">
        ✅ 确认关闭工单
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import apiClient from '@/api/client'
import { generateEmail, sendEmail, requestEmailReview } from '@/api/complaints'
import type { Attachment } from '@/types/api'
import { aiSuggestion } from '@/composables/aiTracker'
import { bigramDice, AI_ADOPTION_MATCH_THRESHOLD } from '@/utils/textSimilarity'

const props = defineProps<{
  complaintId: number
  customerEmail?: string
  complaintNo?: string
  remarks?: string
  emailReviewStatus?: string | null
  emailReviewNote?: string | null
  emailDraftContent?: string | null   // 0804 邮件草稿 JSON
  canConfirm?: boolean               // 0806 客服主管可见但不可确认
}>()

const emit = defineEmits<{ done: []; refresh: [] }>()

// ── 确认关闭 ─────────────────────────────
const confirmed = ref(false)
const satisfaction = ref(0)
const confirming = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

async function handleConfirm() {
  errorMsg.value = ''; successMsg.value = ''
  if (!confirmed.value) { errorMsg.value = '请先确认客户已确认问题解决'; return }
  confirming.value = true
  try {
    const r = await apiClient.post(`/api/complaints/${props.complaintId}/confirm`, {
      satisfaction: satisfaction.value,
      confirm_note: '',
    })
    if (r.data?.success) { successMsg.value = r.data.message; emit('done') }
    else { errorMsg.value = r.data?.message || '确认失败' }
  } catch (e: any) { errorMsg.value = e?.response?.data?.detail || '确认失败' }
  finally { confirming.value = false }
}

// ── 邮件 ─────────────────────────────────
const emailRecipient = ref(props.customerEmail || '')
const emailTouched = ref(false)
const draftSubject = ref('')
const draftBody = ref('')
const draftError = ref('')
const generating = ref(false)
const sending = ref(false)
const emailError = ref('')
const emailSuccess = ref('')
const existingAtts = ref<Attachment[]>([])
const selectedAttIds = ref<number[]>([])
const emailSent = computed(() => (props.remarks || '').includes('[邮件记录]'))

// 0804 邮件草稿提交审核
const reviewSubmitting = ref(false)
const reviewMsg = ref('')
const reviewOk = ref(false)

async function doSubmitForReview() {
  if (!draftSubject.value.trim() || !draftBody.value.trim()) {
    reviewMsg.value = '请先填写邮件主题和正文'
    reviewOk.value = false
    return
  }
  reviewSubmitting.value = true; reviewMsg.value = ''
  try {
    const r = await requestEmailReview(props.complaintId, {
      subject: draftSubject.value,
      body: draftBody.value,
    })
    if (r.data?.success) {
      reviewOk.value = true
      reviewMsg.value = '✅ 已提交主管审核，请等待审核结果'
      emit('refresh')
    } else {
      reviewOk.value = false
      reviewMsg.value = r.data?.message || '提交失败'
    }
  } catch (e: any) {
    reviewOk.value = false
    reviewMsg.value = e?.response?.data?.detail || '提交失败'
  } finally {
    reviewSubmitting.value = false
  }
}

onMounted(async () => {
  await loadAttachments()
  restoreDraft()
})

// 0804 切换工单时重置表单并恢复该工单的草稿
watch(() => props.complaintId, () => {
  // 重置表单
  emailRecipient.value = props.customerEmail || ''
  draftSubject.value = ''
  draftBody.value = ''
  draftError.value = ''
  emailError.value = ''
  emailSuccess.value = ''
  selectedAttIds.value = []
  reviewMsg.value = ''
  aiDraft.value = null  // 0902 切单清空 AI 草稿快照，防止串单比对
  // 重新加载附件和草稿
  loadAttachments()
  restoreDraft()
})

async function loadAttachments() {
  try {
    const r = await apiClient.get(`/api/complaints/${props.complaintId}/attachments`)
    if (r.data?.success) existingAtts.value = r.data.data || []
  } catch { /* ignore */ }
}

function restoreDraft() {
  if (props.emailDraftContent) {
    try {
      const draft = JSON.parse(props.emailDraftContent)
      if (draft.subject) draftSubject.value = draft.subject
      if (draft.body) draftBody.value = draft.body
    } catch { /* ignore */ }
  }
}

// 0902 AI 采纳埋点快照：仅本次会话 AI 生成的草稿（restoreDraft 恢复的历史草稿不比对）
const aiDraft = ref<{ subject: string; body: string } | null>(null)

async function doGenerateDraft() {
  draftError.value = ''
  generating.value = true
  try {
    const r = await generateEmail(props.complaintId)
    if (r.data?.success && r.data.data) {
      const d = r.data.data
      if (d.source === 'deepseek') {
        draftSubject.value = d.subject
        draftBody.value = d.body
        aiSuggestion.current = `主题：${d.subject || ''}\n正文：${d.body || ''}`
        aiDraft.value = { subject: d.subject || '', body: d.body || '' }
      } else {
        draftError.value = d.error || 'AI 生成失败，请手动填写'
      }
    } else {
      draftError.value = r.data?.message || '生成失败'
    }
  } catch (e: any) {
    draftError.value = e?.response?.data?.detail || '生成草稿失败'
  } finally { generating.value = false }
}

async function doSendEmail() {
  emailTouched.value = true
  if (!emailRecipient.value.trim()) { emailError.value = '请输入收件人邮箱'; return }
  emailError.value = ''; emailSuccess.value = ''
  sending.value = true
  try {
    const r = await sendEmail(props.complaintId, {
      to_email: emailRecipient.value.trim(),
      subject: draftSubject.value,
      body: draftBody.value,
      attachment_ids: selectedAttIds.value,
    })
    if (r.data?.success) {
      emailSuccess.value = r.data.message
      // 0902 AI 采纳埋点：发送内容 vs 本次会话 AI 草稿的匹配度（须在清空表单前比对）
      if (aiDraft.value && props.complaintNo) {
        const sim = bigramDice(`${aiDraft.value.subject}\n${aiDraft.value.body}`, `${draftSubject.value}\n${draftBody.value}`)
        const snapshot = aiDraft.value
        import('@/api/eval').then(m => {
          m.recordAiAdoption(props.complaintNo!, 'email_draft', snapshot.subject.slice(0, 500), sim >= AI_ADOPTION_MATCH_THRESHOLD, sim)
        }).catch(() => {})
        aiDraft.value = null
      }
      emailRecipient.value = ''
      draftSubject.value = ''
      draftBody.value = ''
      selectedAttIds.value = []
      emit('refresh')
    } else {
      emailError.value = r.data?.message || '发送失败'
    }
  } catch (e: any) {
    emailError.value = e?.response?.data?.detail || '发送失败'
  } finally { sending.value = false }
}
</script>
