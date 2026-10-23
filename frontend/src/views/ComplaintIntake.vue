<!-- 0724 客诉录入 — AI 辅助录入新客诉
     对应原 pages/1_客诉录入.py，功能 100% 保留 -->
<template>
  <AppLayout>
    <!-- 0910 批量导入 Tab 表格列多，容器放宽一档（单条录入保持原宽） -->
    <div :class="['p-4 sm:p-6 mx-auto space-y-6', activeTab === 'batch' ? 'max-w-7xl' : 'max-w-5xl']">
      <p class="text-sm text-gray-500">💡 您当前以 <strong>{{ auth.role }}</strong> 身份登录，系统默认显示客诉录入页面。</p>

      <!-- 0910 录入方式 Tab：单条录入 / 批量表单导入 -->
      <div class="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit">
        <button :class="['px-4 py-1.5 rounded-base text-sm font-medium transition',
                         activeTab === 'single' ? 'bg-white text-primary shadow-sm' : 'text-gray-500 hover:text-gray-700']"
          @click="activeTab = 'single'">📝 单条录入</button>
        <button :class="['px-4 py-1.5 rounded-base text-sm font-medium transition',
                         activeTab === 'batch' ? 'bg-white text-primary shadow-sm' : 'text-gray-500 hover:text-gray-700']"
          @click="activeTab = 'batch'">📥 批量表单导入</button>
      </div>

      <div v-if="activeTab === 'single'" class="space-y-6">
      <!-- AI 智能粘贴区 -->
      <div class="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
        <h3 class="font-semibold text-sm">📋 粘贴文本 → AI 智能填表</h3>
        <!-- 0729 AI 免责提示 -->
        <p class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-1.5">
          <span class="shrink-0">⚠️</span>
          <span><strong>AI 建议仅供参考</strong> — AI 自动填充的分类和优先级为初步判定，请人工核实确认后再提交。</span>
        </p>
        <textarea v-model="pasteText" rows="6"
          placeholder="粘贴工程师笔记、邮件、聊天记录等任意格式文本&#10;示例：&#10;客户：示例客户B&#10;设备：EQ-800&#10;现象：涂胶后出现气泡，良率下降5%"
          class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
        <div class="flex gap-3">
          <button @click="aiParse" :disabled="aiParsing"
            class="px-4 py-2 bg-primary text-white rounded-base hover:bg-primary/90 disabled:opacity-50 text-sm font-medium">
            {{ aiParsing ? '解析中...' : '🤖 AI 智能填表' }}
          </button>
          <button v-if="prefillData" @click="clearPrefill"
            class="px-4 py-2 bg-gray-100 text-gray-700 rounded-base hover:bg-gray-200 text-sm">
            🗑️ 清除预填
          </button>
        </div>
        <div v-if="aiMsg" :class="['text-sm p-2 rounded', aiOk ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600']">{{ aiMsg }}</div>
      </div>

      <!-- 录入表单 -->
      <form @submit.prevent="handleSubmit" class="bg-white rounded-lg border border-gray-200 p-4 sm:p-6 space-y-4">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">🏢 客户名称</label>
            <input v-model="form.customer_name" type="text" placeholder="请输入客户名称（选填）"
              class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">📟 设备型号</label>
            <input v-model="form.equipment_model" type="text" placeholder="如：EQ-800、H3600"
              class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm" />
          </div>
          <div>
            <!-- 1015 设备编号口径按客诉场景：工艺调试类→厂内编号，其余→出厂编号 -->
            <label class="block text-sm font-medium text-gray-700 mb-1">🔢 {{ equipmentSnLabel(form.scene_category) }}</label>
            <input v-model="form.equipment_sn" type="text"
              :placeholder="form.scene_category === '工艺调试类' ? '厂内编号（出厂前机台编号）' : '出厂编号，如：SN-20240801-001'"
              class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">🔧 设备部位</label>
            <input v-model="form.device_part" type="text" placeholder="如：涂胶阀、伺服驱动器、视觉模块"
              class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">💿 软件版本</label>
            <input v-model="form.software_version" type="text" placeholder="如：V2.3.1"
              class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">🏷️ 初步判定分类</label>
            <select v-model="form.preliminary_category"
              class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm bg-white">
              <option value="">不分类</option>
              <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">📅 客诉发生时间</label>
            <input v-model="form.occurred_at" type="date"
              class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm" />
            <div class="text-xs text-gray-400 mt-1">仅记录客诉实际发生日期；工单编号与创建时间按录入系统的时间生成</div>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">📅 客户期望完成日期</label>
            <input v-model="form.expected_complete_date" type="date"
              class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">📌 客诉场景分类 <span class="text-red-500">*</span></label>
            <select v-model="form.scene_category" required
              class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm bg-white">
              <option value="">-- 请选择客诉场景分类 --</option>
              <option v-for="s in SCENE_CATEGORY_OPTIONS" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">👤 录入人</label>
            <input v-model="form.created_by" type="text" readonly
              class="w-full px-3 py-2 border border-gray-200 rounded-base text-sm bg-gray-50 text-gray-500" />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">📧 客户联系方式</label>
            <input v-model="form.customer_email" type="text" placeholder="如：customer@example.com 或 13800138000"
              class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm" />
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">📝 客户备注</label>
          <textarea id="customer-note-field" v-model="form.customer_note" rows="4" placeholder="客户特殊要求或补充信息"
            class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">🔍 推荐客户自排查</label>
          <textarea v-model="form.customer_self_check" rows="4"
            placeholder="点击下方「AI 自排查推荐」按钮自动生成…"
            class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">🔴 故障现象 <span class="text-red-500">*</span></label>
          <textarea v-model="form.fault_phenomenon" rows="6" required placeholder="请详细描述故障现象，AI 将自动分析分类和优先级…"
            class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">⚠️ 影响程度</label>
          <select v-model="impactDropdown" @change="onImpactSelect"
            class="w-full px-3 py-2 border border-gray-300 rounded-base text-sm bg-white">
            <option value="">-- 请选择影响程度（可选）--</option>
            <option v-for="o in IMPACT_LEVEL_OPTIONS" :key="o" :value="o">{{ o }}</option>
            <option value="__custom__">✏️ 其他（手动输入）</option>
          </select>
          <textarea v-if="impactDropdown === '__custom__'" v-model="form.impact_level" rows="2"
            placeholder="请输入其他影响程度…"
            class="w-full mt-2 px-3 py-2 border border-gray-300 rounded-base text-sm"></textarea>
        </div>

        <!-- 0807 返修 + 关联工单（并排布局） -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">🔄 是否属于返修？</label>
            <div class="flex gap-4 mt-1.5">
              <label class="flex items-center gap-1 cursor-pointer text-sm">
                <input v-model="form.is_rework" type="radio" :value="true" name="is_rework" class="w-4 h-4 accent-primary" /> 是
              </label>
              <label class="flex items-center gap-1 cursor-pointer text-sm">
                <input v-model="form.is_rework" type="radio" :value="false" name="is_rework" class="w-4 h-4 accent-primary" /> 否
              </label>
            </div>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">🔗 关联工单</label>
            <LinkedComplaintPicker v-model="form.linked_complaint_ids" />
            <p class="text-[11px] text-gray-400 mt-1">如：该工单是某历史工单的返修，或由某工单引起。可通过工单号/客户名搜索关联。</p>
          </div>
        </div>

        <!-- 附件上传 -->
        <FileUploader ref="uploaderRef" :existingCount="0" />

        <div v-if="submitError" class="text-red-600 text-sm bg-red-50 p-3 rounded">{{ submitError }}</div>
        <!-- 0729 附件上传错误提示 -->
        <div v-if="uploadError" class="text-amber-600 text-sm bg-amber-50 p-2 rounded mt-2">{{ uploadError }}</div>

        <!-- 0728 AI 自排查推荐 -->
        <div class="space-y-2">
          <button type="button" @click="doSelfCheck" :disabled="selfCheckLoading || !form.fault_phenomenon.trim()"
            class="w-full py-2.5 bg-amber-500 text-white rounded-base hover:bg-amber-600
                   disabled:opacity-50 transition font-semibold">
            {{ selfCheckLoading ? '⏳ AI 分析中...' : '🔍 AI 自排查推荐（生成客户可自行排查的建议）' }}
          </button>
          <!-- 0729 AI 免责提示 -->
          <p class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-1.5">
            <span class="shrink-0">⚠️</span>
            <span><strong>AI 建议仅供参考</strong> — 排查建议面向产线操作工，为通用性安全排查步骤，具体故障排查请以工程师诊断为准。</span>
          </p>
          <!-- 0729 自排查成功提示 -->
          <div v-if="selfCheckSuccess" class="flex items-center gap-2 text-green-600 text-sm bg-green-50 border border-green-200 rounded px-3 py-2">
            <span>✅</span>
            <span>AI 建议已填入上方「推荐客户自排查」栏</span>
          </div>
        </div>

        <button type="submit" :disabled="submitting"
          class="w-full py-2.5 bg-primary text-white rounded-base hover:bg-primary/90 disabled:opacity-50 transition font-semibold">
          💾 提交客诉
        </button>
      </form>

      <!-- 重复检测弹窗 -->
      <Teleport to="body">
        <div v-if="showDuplicate" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/40" @click="showDuplicate = false"></div>
          <div class="relative bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[80vh] overflow-y-auto p-6 space-y-4">
            <h3 class="text-lg font-semibold text-red-600">
              ⚠️ 检测到近30天内已有 {{ duplicateList.length }} 个相似工单
            </h3>
            <p class="text-sm text-gray-500">
              同客户「{{ pendingData?.customer_name }}」+ 同设备型号「{{ pendingData?.equipment_model || '未填' }}」，请确认是否仍要提交：
            </p>
            <div v-for="(s, i) in duplicateList" :key="i" class="border border-gray-200 rounded p-3 text-sm space-y-1">
              <div class="font-medium">{{ i + 1 }}. {{ s.complaint_no }} {{ s.status }} {{ s.fault_category }} {{ s.created_at }}</div>
              <div class="text-gray-500">故障描述相似度：<strong>{{ Math.round(s.similarity * 100) }}%</strong>（重叠 {{ s.overlap_grams }}/{{ s.total_grams }}）</div>
              <div class="text-gray-600">{{ s.fault_phenomenon?.slice(0, 120) }}{{ (s.fault_phenomenon?.length || 0) > 120 ? '...' : '' }}</div>
            </div>
            <div class="flex gap-3">
              <button @click="forceSubmit" class="flex-1 px-4 py-2 bg-red-600 text-white rounded-base hover:bg-red-700 font-medium">✅ 仍要提交</button>
              <button @click="showDuplicate = false" class="flex-1 px-4 py-2 bg-gray-100 text-gray-700 rounded-base hover:bg-gray-200">❌ 取消</button>
            </div>
          </div>
        </div>
      </Teleport>

      <!-- 提交成功 -->
      <div v-if="submitResult" class="bg-green-50 border border-green-200 rounded-lg p-4 space-y-3">
        <p class="font-semibold text-green-800">✅ 客诉提交成功！编号：<strong>{{ submitResult.complaint_no }}</strong></p>
        <router-link to="/kanban" class="inline-block px-4 py-2 bg-primary text-white rounded-base text-sm">📊 前往客诉看板</router-link>
      </div>

      <!-- 0730 AI 辅助效果评价 — 提交成功后滚动至此 -->
      <div id="ai-feedback-card">
        <FeedbackCard
          v-if="submitResult"
          :complaintNo="submitResult.complaint_no"
          feedbackType="intake"
          :complaintContext="intakeComplaint"
          :aiSuggestion="aiSuggestion.current"
          @submitted="onFeedbackDone"
          @dismissed="onFeedbackDone"
        />
      </div>

      <div class="text-xs text-gray-400 text-center">
        💡 录入后工单进入「客服主管审核」，由客服主管确认优先级与去向；客服不可修改优先级。
      </div>
      </div>

      <!-- 0910 批量表单导入 Tab -->
      <BatchImportPanel v-if="activeTab === 'batch'" />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { useAuthStore } from '@/stores/auth'
import AppLayout from '@/components/layout/AppLayout.vue'
import FileUploader from '@/components/common/FileUploader.vue'
import LinkedComplaintPicker from '@/components/complaint/LinkedComplaintPicker.vue'
import BatchImportPanel from '@/components/complaint/BatchImportPanel.vue'
import apiClient from '@/api/client'
import { extractComplaint, classifyComplaint, getSelfCheckSuggestions } from '@/api/ai'
import FeedbackCard from '@/components/common/FeedbackCard.vue'
import { aiSuggestion } from '@/composables/aiTracker'
import { bigramDice, AI_ADOPTION_MATCH_THRESHOLD } from '@/utils/textSimilarity'
import { SCENE_CATEGORY_OPTIONS, equipmentSnLabel } from '@/types/api'

const auth = useAuthStore()
// 0910 录入方式 Tab：single=单条录入 / batch=批量表单导入
const activeTab = ref<'single' | 'batch'>('single')
const CATEGORIES = ['机械', '电气', '工艺', '光学', '软件', '其他']
const IMPACT_LEVEL_OPTIONS = ['停机', '降产', '质量影响', '轻微影响', '无影响']

// AI 智能粘贴
const pasteText = ref('')
const aiParsing = ref(false)
const aiMsg = ref('')
const aiOk = ref(false)
const prefillData = ref<any>(null)

// 表单
const form = reactive({
  customer_name: '', equipment_model: '', equipment_sn: '', device_part: '',
  software_version: '',
  customer_email: '',
  preliminary_category: '', expected_complete_date: '',
  occurred_at: new Date().toISOString().slice(0, 10),  // 1019 客诉发生时间（默认今天）
  scene_category: '',
  created_by: auth.displayName || '',
  customer_note: '', customer_self_check: '', fault_phenomenon: '', impact_level: '',
  is_rework: false,
  linked_complaint_ids: [] as Array<{id: number, no: string}>,
})

// 影响程度下拉状态
const impactDropdown = ref('')

function onImpactSelect() {
  if (impactDropdown.value && impactDropdown.value !== '__custom__') {
    form.impact_level = impactDropdown.value
  } else if (impactDropdown.value === '') {
    form.impact_level = ''
  }
}

// 预填
function applyPrefill(d: any) {
  if (!d) return
  if (d.customer_name) form.customer_name = d.customer_name
  if (d.equipment_model) form.equipment_model = d.equipment_model
  if (d.equipment_sn) form.equipment_sn = d.equipment_sn
  if (d.device_part) form.device_part = d.device_part
  if (d.software_version) form.software_version = d.software_version
  if (d.fault_phenomenon) form.fault_phenomenon = d.fault_phenomenon
  if (d.impact_level) {
    form.impact_level = d.impact_level
    // 如果 AI 解析出的影响程度匹配预设选项，同步下拉状态
    if (IMPACT_LEVEL_OPTIONS.includes(d.impact_level)) {
      impactDropdown.value = d.impact_level
    } else {
      impactDropdown.value = '__custom__'
    }
  }
  if (d.customer_note) form.customer_note = d.customer_note
  if (d.customer_self_check) form.customer_self_check = d.customer_self_check
  if (d.preliminary_category && CATEGORIES.includes(d.preliminary_category)) {
    form.preliminary_category = d.preliminary_category
  }
  if (d.expected_complete_date) form.expected_complete_date = d.expected_complete_date
  if (d.customer_email) form.customer_email = d.customer_email
}

async function aiParse() {
  if (!pasteText.value.trim()) { aiMsg.value = '请先粘贴文本再解析'; aiOk.value = false; return }
  aiParsing.value = true; aiMsg.value = ''
  try {
    // 阶段 1：从非结构化文本提取通用字段（客户/设备/现象等）
    const r = await extractComplaint(pasteText.value.trim())
    if (r.data?.success && r.data.data) {
      const d = r.data.data
      prefillData.value = d
      applyPrefill(d)
      // 阶段 2：用专用分类器重新判定故障分类（比 extract 内部的分类准确得多）
      // 来源：v2.1 1_客诉录入.py 102-108 行
      if (d.fault_phenomenon) {
        try {
          const cls = await classifyComplaint(d.fault_phenomenon)
          if (cls.data?.success && cls.data.data?.source === 'deepseek') {
            prefillData.value.preliminary_category = cls.data.data.category
            if (CATEGORIES.includes(cls.data.data.category)) {
              form.preliminary_category = cls.data.data.category
            }
          }
        } catch { /* 分类阶段失败不影响表单预填 */ }
      }
      const count = Object.entries(d).filter(([, v]) => v && typeof v === 'string' && v.trim()).length
      aiMsg.value = `✅ 已解析出 ${count} 个字段，已预填到下方表单，请核对后提交`
      aiOk.value = true
      // 0820 写入 AI 建议文本（intake 评价卡的 ai_suggestion 不再恒空）
      aiSuggestion.current = `AI 智能填表解析：\n${JSON.stringify(d, null, 2).slice(0, 800)}`
    } else {
      aiMsg.value = r.data?.message || '解析失败'; aiOk.value = false
    }
  } catch (e: any) {
    aiMsg.value = e?.response?.data?.detail || 'AI 解析失败，请手动填写'; aiOk.value = false
  } finally { aiParsing.value = false }
}

function clearPrefill() {
  prefillData.value = null; aiMsg.value = ''
  aiSuggestion.current = ''  // 0820 清空 AI 建议文本，防止串到后续评价卡
  aiSelfCheckSuggest.value = ''  // 0902 清空采纳比对快照
  pasteText.value = ''
  form.customer_name = ''
  form.equipment_model = ''
  form.equipment_sn = ''
  form.device_part = ''
  form.software_version = ''
  form.fault_phenomenon = ''
  form.impact_level = ''
  form.customer_note = ''
  form.customer_self_check = ''
  form.expected_complete_date = ''
  form.occurred_at = new Date().toISOString().slice(0, 10)  // 1019 重置回今天
  form.customer_email = ''
  form.is_rework = false
  form.linked_complaint_ids = []
  impactDropdown.value = ''
  form.preliminary_category = ''
  form.scene_category = ''
}

// 0902 AI 采纳埋点（字段级匹配度）：智能填表逐字段比对 + 自排查整文本比对。
// 匹配度 = bigram Dice 相似度(0-100)，≥阈值记采纳；匹配度存 ai_suggested_value。
// preliminary_category 不在此记——已有独立的 classify 精确比对埋点，避免重复计数。
const PREFILL_FIELDS: Array<[keyof typeof form, string]> = [
  ['customer_name', '客户名称'],
  ['equipment_model', '设备型号'],
  ['equipment_sn', '设备序列号'],
  ['device_part', '故障部位'],
  ['software_version', '软件版本'],
  ['fault_phenomenon', '故障现象'],
  ['impact_level', '影响程度'],
  ['customer_note', '客户备注'],
  ['customer_self_check', '客户自排查'],
  ['expected_complete_date', '期望完成日期'],
  ['customer_email', '客户邮箱'],
]

function recordAdoptions(complaintNo: string) {
  if (prefillData.value) {
    for (const [field, label] of PREFILL_FIELDS) {
      const aiVal = String(prefillData.value[field] ?? '').trim()
      if (!aiVal) continue
      const sim = bigramDice(aiVal, String(form[field] ?? '').trim())
      import('@/api/eval').then(m => {
        m.recordAiAdoption(complaintNo, 'prefill', `${label}:${aiVal}`.slice(0, 500), sim >= AI_ADOPTION_MATCH_THRESHOLD, sim)
      }).catch(() => {})
    }
  }
  if (aiSelfCheckSuggest.value) {
    const sim = bigramDice(aiSelfCheckSuggest.value, form.customer_self_check.trim())
    import('@/api/eval').then(m => {
      m.recordAiAdoption(complaintNo, 'self_check', aiSelfCheckSuggest.value.slice(0, 500), sim >= AI_ADOPTION_MATCH_THRESHOLD, sim)
    }).catch(() => {})
  }
}

// 提交
const uploaderRef = ref<InstanceType<typeof FileUploader>>()
const submitting = ref(false)
const uploadError = ref('')
const submitError = ref('')
const submitResult = ref<any>(null)
// 构造一个最小 Complaint 对象传给 FeedbackCard
const intakeComplaint = computed(() => {
  if (!submitResult.value) return null
  return {
    fault_category: form.preliminary_category || '',
    equipment_model: form.equipment_model || '',
    status: '待客户排查',
    responsible_dept: '',
  }
})
const showDuplicate = ref(false)
const duplicateList = ref<any[]>([])
const pendingData = ref<any>(null)

// 0728 AI 自排查推荐
const selfCheckLoading = ref(false)
const selfCheckSuccess = ref(false)
// 0902 AI 采纳埋点快照：本次会话 AI 生成的自排查文本（提交时与最终提交值比对匹配度）
const aiSelfCheckSuggest = ref('')

async function doSelfCheck() {
  if (!form.fault_phenomenon.trim()) return
  selfCheckLoading.value = true
  try {
    const r = await getSelfCheckSuggestions(form.fault_phenomenon.trim(), form.equipment_model.trim())
    if (r.data?.success && r.data.data) {
      const d = r.data.data
      const lines: string[] = []
      if (d.summary) lines.push(`📌 ${d.summary}`)
      if (d.suggestions?.length) {
        lines.push('')
        d.suggestions.forEach((s: string) => {
          lines.push(s)
        })
      }
      form.customer_self_check = lines.join('\n')
      selfCheckSuccess.value = true
      // 0820 写入 AI 建议文本（intake 评价卡携带自排查建议）
      aiSuggestion.current = lines.join('\n')
      aiSelfCheckSuggest.value = lines.join('\n')
    }
  } catch (e: any) {
    // silent fail — 自排查不是必须的
    console.error('self-check error:', e)
  } finally {
    selfCheckLoading.value = false
  }
}

async function doSubmit(data: any, force: boolean) {
  const r = await apiClient.post('/api/complaints', { ...data, force })
  return r.data
}

// 0730 提取附件上传为独立函数，供 handleSubmit 和 forceSubmit 共用
async function uploadAttachments(complaintId: number) {
  const files = uploaderRef.value?.selectedFiles || []
  if (!files.length) return
  const fd = new FormData()
  fd.append('complaint_id', String(complaintId))
  for (const f of files) fd.append('files', f)
  await apiClient.post('/api/files/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  uploaderRef.value?.clearFiles()
}

async function handleSubmit() {
  submitError.value = ''
  // 0914 客户名称改选填，不再强制校验
  if (!form.fault_phenomenon.trim()) { submitError.value = '故障现象不能为空'; return }
  if (!form.scene_category) { submitError.value = '请选择客诉场景分类'; return }

  const data: any = {
    customer_name: form.customer_name.trim(),
    scene_category: form.scene_category,
    equipment_model: form.equipment_model.trim(),
    equipment_sn: form.equipment_sn.trim(),
    device_part: form.device_part.trim(),
    software_version: form.software_version.trim(),
    fault_category: form.preliminary_category,
    preliminary_category: form.preliminary_category,
    fault_phenomenon: form.fault_phenomenon.trim(),
    impact_level: form.impact_level.trim(),
    occurred_at: form.occurred_at,  // 1019 客诉发生时间（工单号日期段）
    expected_complete_date: form.expected_complete_date,
    customer_email: form.customer_email.trim(),
    customer_note: form.customer_note.trim(),  // 0728 修复 bug：客户备注未提交
    customer_self_check: form.customer_self_check.trim(),
    is_rework: form.is_rework ? 1 : 0,
    linked_complaint_ids: JSON.stringify(form.linked_complaint_ids),
    created_by: form.created_by || auth.displayName,
  }

  submitting.value = true
  try {
    const result = await doSubmit(data, false)
    if (result?.success) {
      submitResult.value = result.data
      // 0730 滚动到 AI 评价卡片
      await nextTick()
      const el = document.getElementById('ai-feedback-card')
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      // 0730 上传附件 — 使用提取的共享函数
      if (result.data?.id) {
        try {
          await uploadAttachments(result.data.id)
        } catch (e: any) {
          uploadError.value = '⚠️ 工单已创建成功，但附件上传失败。请在工单详情页重新上传附件。'
          console.error('File upload failed:', e)
        }
      }
      // 0804 AI 采纳追踪：对比 AI 建议分类与实际提交
      if (prefillData.value?.preliminary_category && result.data?.complaint_no) {
        const adopted = prefillData.value.preliminary_category === form.preliminary_category
        import('@/api/eval').then(m => {
          m.recordAiAdoption(
            result.data.complaint_no,
            'classify',
            prefillData.value!.preliminary_category,
            adopted
          ).catch(() => {})
        })
      }
      // 0902 AI 采纳追踪：智能填表逐字段 + 自排查（字段级匹配度）
      if (result.data?.complaint_no) recordAdoptions(result.data.complaint_no)
      // 0805 操作计时：录入表单耗时
      const intakeStart = (window as any).__intakeStart
      if (intakeStart) {
        const duration = Date.now() - intakeStart
        import('@/api/eval').then(m => {
          m.recordActivity('/intake', 'timing', { action_name: 'complaint_intake', duration_ms: duration, complaint_no: result.data?.complaint_no || '' })
        }).catch(() => {})
        delete (window as any).__intakeStart
      }
    } else if (result?.data?.duplicates?.length) {
      // 检测到相似工单 → 弹窗确认
      pendingData.value = data
      duplicateList.value = result.data.duplicates
      showDuplicate.value = true
    } else {
      submitError.value = result?.message || '提交失败'
    }
  } catch (e: any) {
    submitError.value = e?.response?.data?.detail || '提交失败'
  } finally { submitting.value = false }
}

async function forceSubmit() {
  if (!pendingData.value) return
  submitting.value = true
  try {
    const result = await doSubmit(pendingData.value, true)
    if (result?.success) {
      submitResult.value = result.data; showDuplicate.value = false
      // 0820 强制提交路径补 classify 采纳记录（与 handleSubmit 对称）
      if (prefillData.value?.preliminary_category && result.data?.complaint_no) {
        const adopted = prefillData.value.preliminary_category === form.preliminary_category
        import('@/api/eval').then(m => {
          m.recordAiAdoption(result.data.complaint_no, 'classify', prefillData.value!.preliminary_category, adopted).catch(() => {})
        })
      }
      // 0902 强制提交路径补 prefill/self_check 采纳记录（与 handleSubmit 对称）
      if (result.data?.complaint_no) recordAdoptions(result.data.complaint_no)
      // 0730 强制提交后也上传附件，修复附件丢失 bug
      if (result.data?.id) {
        try {
          await uploadAttachments(result.data.id)
        } catch (e: any) {
          uploadError.value = '⚠️ 工单已创建成功，但附件上传失败。请在工单详情页重新上传附件。'
          console.error('File upload failed:', e)
        }
      }
      // 0730 滚动到评价卡片
      await nextTick()
      const el = document.getElementById('ai-feedback-card')
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  } catch (e: any) { submitError.value = e?.response?.data?.detail || '提交失败' }
  finally { submitting.value = false }
}

// 0731 评价卡片提交/关闭后自动重置表单，延迟2秒让用户看到感谢消息
function onFeedbackDone() {
  setTimeout(() => {
    submitResult.value = null
    selfCheckSuccess.value = false
    submitError.value = ''
    uploadError.value = ''
    clearPrefill()  // 清空所有表单字段
  }, 2000)
}

// Init
onMounted(() => { form.created_by = auth.displayName || ''; (window as any).__intakeStart = Date.now() })
</script>
