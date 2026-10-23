<!-- 0724 编辑工单弹窗 — 对应原看板编辑弹窗 -->
<template>
  <Teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="$emit('close')"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[85vh] overflow-y-auto">
        <!-- 标题 -->
        <div class="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 class="text-lg font-semibold">✏️ 编辑工单：{{ complaint?.complaint_no }}</h3>
          <button @click="$emit('close')" class="p-1 hover:bg-gray-100 rounded text-gray-400">✕</button>
        </div>

        <!-- 表单 -->
        <form @submit.prevent="handleSave" class="p-6 space-y-4">
          <div v-if="isReturnedIntake" class="text-sm text-red-700 bg-red-50 border border-red-300 rounded-lg px-3 py-2 space-y-1">
            <div class="font-medium">❌ {{ returnNote?.sourceLabel }}</div>
            <div class="text-xs whitespace-pre-wrap">退回原因：{{ returnNote?.reason }}</div>
            <div class="text-xs text-red-500">请补充或修正录入信息；保存后工单仍等待主管重新审核。</div>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">客户名称</label>
              <input v-model="form.customer_name" type="text"
                class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">设备型号</label>
              <input v-model="form.equipment_model" type="text"
                class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary" />
            </div>
            <div>
              <!-- 1015 设备编号口径按客诉场景：工艺调试类→厂内编号，其余→出厂编号 -->
              <label class="block text-sm font-medium text-gray-700 mb-1">{{ equipmentSnLabel(form.scene_category) }}</label>
              <input v-model="form.equipment_sn" type="text"
                class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">设备部位</label>
              <input v-model="form.device_part" type="text"
                class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">软件版本</label>
              <input v-model="form.software_version" type="text"
                class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">故障类别</label>
              <select v-model="form.fault_category"
                class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary">
                <option value="">不分类</option>
                <option v-for="cat in CATEGORIES" :key="cat" :value="cat">{{ cat }}</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">客诉场景分类</label>
              <select v-model="form.scene_category"
                class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary">
                <option value="">-- 请选择客诉场景分类 --</option>
                <option v-for="s in SCENE_CATEGORY_OPTIONS" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
            <!-- 1019 客诉发生时间（与创建时间分离；修改不会改变已生成的工单号） -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">客诉发生时间</label>
              <input v-model="form.occurred_at" type="date"
                class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary" />
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">故障现象</label>
            <textarea v-model="form.fault_phenomenon" rows="4"
              class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary"></textarea>
          </div>

          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                优先级
                <span v-if="!canEditPriority" class="text-gray-400">（只读，由客服主管审核时确认）</span>
              </label>
              <select v-if="canEditPriority" v-model="form.priority"
                class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm">
                <option v-for="p in ['P0','P1','P2','P3','待确认']" :key="p" :value="p">{{ p }}</option>
              </select>
              <input v-else :value="form.priority" disabled type="text"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-base text-sm bg-gray-50 text-gray-400" />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">影响程度</label>
              <select v-model="impactDropdown" @change="onImpactSelect"
                class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary">
                <option value="">-- 请选择 --</option>
                <option v-for="o in IMPACT_LEVEL_OPTIONS" :key="o" :value="o">{{ o }}</option>
                <option value="__custom__">✏️ 其他（手动输入）</option>
              </select>
              <input v-if="impactDropdown === '__custom__'" v-model="form.impact_level" type="text"
                class="w-full mt-2 px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary"
                placeholder="请输入其他影响程度…" />
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">处理备注</label>
            <textarea v-model="form.resolution_note" rows="3"
              class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary"></textarea>
          </div>

          <!-- 0728 客户备注 -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">📝 客户备注</label>
            <textarea v-model="form.customer_note" rows="3" placeholder="客户特殊要求或补充信息"
              class="w-full px-3 py-1.5 border border-gray-300 rounded-base text-sm focus:ring-2 focus:ring-primary/30 focus:border-primary"></textarea>
          </div>

          <div v-if="errorMsg" class="text-red-600 text-sm bg-red-50 rounded-base px-3 py-2">{{ errorMsg }}</div>

          <div class="flex justify-end gap-3 pt-2">
            <button type="button" @click="$emit('close')"
              class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-base hover:bg-gray-200 transition">
              取消
            </button>
            <button type="submit" :disabled="saving"
              class="px-4 py-2 text-sm font-medium text-white bg-primary rounded-base hover:bg-primary/90 transition disabled:opacity-50">
              {{ saving ? '保存中...' : '💾 保存修改' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { Complaint } from '@/types/api'
import { SCENE_CATEGORY_OPTIONS, equipmentSnLabel } from '@/types/api'
import { parseReturnNote } from '@/utils/complaintReturn'

const CATEGORIES = ['机械', '电气', '工艺', '光学', '软件', '其他']
const IMPACT_LEVEL_OPTIONS = ['停机', '降产', '质量影响', '轻微影响', '无影响']

const props = defineProps<{
  visible: boolean
  complaint: Complaint | null
  canEditPriority: boolean
}>()

// 0819 主管退回修改提示（待客服处理 rework）
const isReturnedIntake = computed(() =>
  props.complaint?.status === '待客服处理' &&
  props.complaint.sub_type === 'rework' &&
  !!props.complaint.supervisor_rejection_note,
)

// 0901 退回来源（主管/办理人姓名）解析
const returnNote = computed(() => parseReturnNote(props.complaint?.supervisor_rejection_note))

const emit = defineEmits<{
  close: []
  save: [data: Record<string, any>]
}>()

const saving = ref(false)
const errorMsg = ref('')

const form = ref<Record<string, any>>({})
const impactDropdown = ref('')

watch(() => props.complaint, (c) => {
  if (c) {
    form.value = {
      customer_name: c.customer_name || '',
      equipment_model: c.equipment_model || '',
      equipment_sn: c.equipment_sn || '',
      device_part: c.device_part || '',
      software_version: c.software_version || '',
      fault_category: c.fault_category || '',
      scene_category: c.scene_category || '',
      occurred_at: (c.occurred_at || '').slice(0, 10),  // 1019 客诉发生时间（改它不重排工单号）
      fault_phenomenon: c.fault_phenomenon || '',
      priority: c.priority || '待确认',
      impact_level: c.impact_level || '',
      resolution_note: c.resolution_note || '',
      customer_note: c.customer_note || '',  // 0728 客户备注
    }
    // 初始化影响程度下拉状态
    if (c.impact_level && IMPACT_LEVEL_OPTIONS.includes(c.impact_level)) {
      impactDropdown.value = c.impact_level
    } else if (c.impact_level) {
      impactDropdown.value = '__custom__'
    } else {
      impactDropdown.value = ''
    }
  }
}, { immediate: true })

function onImpactSelect() {
  if (impactDropdown.value && impactDropdown.value !== '__custom__') {
    form.value.impact_level = impactDropdown.value
  } else if (impactDropdown.value === '') {
    form.value.impact_level = ''
  }
}

async function handleSave() {
  errorMsg.value = ''
  if (!form.value.scene_category) {
    errorMsg.value = '请选择客诉场景分类'
    return
  }
  saving.value = true
  try {
    emit('save', { ...form.value })
  } catch {
    errorMsg.value = '保存失败'
  } finally {
    saving.value = false
  }
}
</script>
