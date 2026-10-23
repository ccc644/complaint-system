<!-- 0819 系统管理导出中心 — 管理员按日期范围导出各类数据（CSV / 附件 ZIP）
     CSV 通过 /api/export/data 导出；附件通过 /api/export/attachments 打包为 ZIP（内部按 工单号/文件名 组织）-->
<template>
  <div class="space-y-4">
    <!-- 时间范围（可选，精确到天） -->
    <div class="bg-white rounded-lg border border-gray-200 p-4">
      <h3 class="font-semibold mb-1">📅 时间范围（可选）</h3>
      <p class="text-xs text-gray-400 mb-3">
        精确到天，闭区间。留空 = 不限范围；附件按所属工单的创建时间过滤。
      </p>
      <div class="flex flex-wrap items-center gap-2">
        <input type="date" v-model="startDate"
          class="px-3 py-1.5 border border-gray-300 rounded text-sm" />
        <span class="text-gray-400 text-sm">至</span>
        <input type="date" v-model="endDate"
          class="px-3 py-1.5 border border-gray-300 rounded text-sm" />
        <button @click="clearDates"
          class="px-3 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50 transition">
          ✕ 清空
        </button>
      </div>
      <p v-if="dateError" class="text-xs text-red-500 mt-2">{{ dateError }}</p>
    </div>

    <!-- 导出列表 -->
    <div class="bg-white rounded-lg border border-gray-200 p-4">
      <div class="flex items-center justify-between flex-wrap gap-2 mb-1">
        <h3 class="font-semibold">📥 数据导出</h3>
        <button @click="doExportAll" :disabled="!!exporting"
          class="px-3 py-1.5 bg-primary text-white rounded text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition"
          :title="`将全部 ${items.length} 类数据打包为一个 ZIP 下载`">
          {{ exporting === 'all' ? '打包中...' : '📦 一键导出全部' }}
        </button>
      </div>
      <p class="text-xs text-gray-400 mb-3">
        点击「导出」下载对应数据的 CSV 文件；「一键导出全部」将所有 CSV 打包为一个 ZIP。
        <span class="text-amber-600">注：不包含附件，附件需在下方「附件批量打包」单独下载。</span>
      </p>
      <div class="space-y-2">
        <div v-for="item in items" :key="item.type"
          class="flex items-center gap-3 p-3 border border-gray-100 rounded-lg hover:bg-gray-50 transition">
          <span class="text-lg shrink-0">{{ item.icon }}</span>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium">{{ item.label }}</div>
            <div class="text-xs text-gray-400">{{ item.desc }}</div>
          </div>
          <button @click="doExport(item)" :disabled="!!exporting"
            class="px-3 py-1.5 border border-gray-300 rounded text-sm hover:bg-gray-50 disabled:opacity-50 transition shrink-0">
            {{ exporting === item.type ? '导出中...' : '📥 导出' }}
          </button>
        </div>

        <!-- 附件 ZIP 打包 -->
        <div class="flex items-center gap-3 p-3 border border-blue-100 bg-blue-50/50 rounded-lg">
          <span class="text-lg shrink-0">📦</span>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium">附件批量打包（ZIP）</div>
            <div class="text-xs text-gray-400">
              打包范围内工单的全部附件文件，ZIP 内按「工单号/文件名」分文件夹存放
            </div>
          </div>
          <button @click="doExportZip" :disabled="!!exporting"
            class="px-3 py-1.5 border border-blue-300 bg-white rounded text-sm text-blue-600 hover:bg-blue-50 disabled:opacity-50 transition shrink-0">
            {{ exporting === 'attachments' ? '打包中...' : '📦 打包下载' }}
          </button>
        </div>
      </div>

      <p v-if="errorMsg" class="text-xs text-red-500 mt-3">{{ errorMsg }}</p>
      <p class="text-xs text-gray-400 mt-3">
        ⚠️ 导出数据含客户联系方式、用户账号等信息，请妥善保管，仅限内部使用。
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useToast } from 'vue-toastification'
import * as exportApi from '@/api/export'
import type { ExportType } from '@/types/api'

const toast = useToast()

const startDate = ref('')
const endDate = ref('')
const dateError = ref('')
const exporting = ref<'' | ExportType | 'attachments' | 'all'>('')
const errorMsg = ref('')

const items: { type: ExportType; icon: string; label: string; desc: string }[] = [
  { type: 'complaints', icon: '📋', label: '客诉工单', desc: '全字段明细 + 附件文件名列，按创建时间排序' },
  { type: 'work_log', icon: '📜', label: '工单流转日志', desc: '操作时间 / 操作人 / 角色 / 部门 / 状态变更 / 详情' },
  { type: 'kb', icon: '📚', label: '知识库', desc: '标题 / 分类 / 机型 / 原因 / 解决方案 / 检查项 / 经验教训' },
  { type: 'user_feedback', icon: '⭐', label: '用户评价', desc: '各阶段 AI 评价：准确度 / 省时 / 是否采纳 / 评语' },
  { type: 'case_feedback', icon: '🎯', label: '案例检索评价', desc: '案例有用性 + 匹配准确度（1-5 分）' },
  { type: 'ai_adoption', icon: '🤖', label: 'AI 采纳日志', desc: '各 AI 功能建议内容与采纳结果' },
  { type: 'sus_survey', icon: '📝', label: '系统评价（SUS 问卷）', desc: '10 题得分 + SUS 分数 + 中心 / 部门' },
  { type: 'activity_log', icon: '👥', label: '用户活跃明细', desc: '用户 / 角色 / 页面 / 动作 / 时间' },
  { type: 'llm_log', icon: '🔧', label: 'AI 调用日志', desc: '模型 / 耗时 / 状态，用于诊断' },
  { type: 'stage_dwell', icon: '📋', label: '阶段停留时长明细', desc: '各工单每阶段停留时长分段（超阈值段标 ⚠️）' },
  // 0824 导出补漏
  { type: 'archive_log', icon: '🗄️', label: '归档流转日志', desc: '已删工单的流转日志（审计留痕）' },
  { type: 'progress_log', icon: '📶', label: '工单进度记录', desc: '进度百分比历史（指派 / 更新 / 完成）' },
  { type: 'notifications', icon: '🔔', label: '站内通知记录', desc: '谁在何时被通知（角色 / 类别 / 已读）' },
  { type: 'users', icon: '👤', label: '用户清单（脱敏）', desc: '账号 / 角色 / 职位 / 钉钉绑定 / 启用状态' },
  { type: 'kb_feedback', icon: '👍', label: '知识库反馈记录', desc: '有用 / 无用反馈原始记录' },
  { type: 'dingtalk_log', icon: '📱', label: '钉钉发送日志', desc: '钉钉推送结果（成功 / 失败 / 原因）' },
]

function clearDates() {
  startDate.value = ''
  endDate.value = ''
  dateError.value = ''
}

// 复用 Analytics.vue 的 blob 下载模式：从 Content-Disposition 提取文件名
function triggerDownload(r: any, fallback: string) {
  const blob = r.data instanceof Blob ? r.data : new Blob([r.data])
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const cd = r.headers?.['content-disposition'] || ''
  const m = cd.match(/filename\*?=(?:UTF-8'')?(.+?)(?:;|$)/)
  a.download = m ? decodeURIComponent(m[1]) : fallback
  a.click()
  URL.revokeObjectURL(url)
}

async function doExport(item: { type: ExportType; label: string }) {
  errorMsg.value = ''
  if (startDate.value && endDate.value && startDate.value > endDate.value) {
    dateError.value = '开始日期不能晚于结束日期'
    return
  }
  dateError.value = ''
  exporting.value = item.type
  try {
    const r = await exportApi.exportData(item.type, startDate.value, endDate.value)
    triggerDownload(r, `${item.type}.csv`)
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || `「${item.label}」导出失败，请稍后重试`
  } finally {
    exporting.value = ''
  }
}

async function doExportZip() {
  errorMsg.value = ''
  if (startDate.value && endDate.value && startDate.value > endDate.value) {
    dateError.value = '开始日期不能晚于结束日期'
    return
  }
  dateError.value = ''
  exporting.value = 'attachments'
  try {
    const r = await exportApi.exportAttachmentsZip(startDate.value, endDate.value)
    triggerDownload(r, `attachments_${Date.now()}.zip`)
    toast.success('附件打包完成，已开始下载')
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '附件打包失败，请稍后重试'
  } finally {
    exporting.value = ''
  }
}

async function doExportAll() {
  errorMsg.value = ''
  if (startDate.value && endDate.value && startDate.value > endDate.value) {
    dateError.value = '开始日期不能晚于结束日期'
    return
  }
  dateError.value = ''
  exporting.value = 'all'
  try {
    const r = await exportApi.exportAllZip(startDate.value, endDate.value)
    triggerDownload(r, `export_all_${Date.now()}.zip`)
    toast.success('全部数据导出完成，已开始下载')
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '一键导出全部失败，请稍后重试'
  } finally {
    exporting.value = ''
  }
}
</script>
