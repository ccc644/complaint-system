<!-- 0910 批量表单导入面板 — 客诉录入页 Tab2（一次一个文件：上传解析 → 预览修改 → 确认导入） -->
<template>
  <div class="space-y-4">
    <!-- ① 上传 -->
    <div class="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
      <h3 class="font-semibold text-sm flex items-center gap-1.5"><Upload :size="16" /> 上传问题表单（.xlsx / .xls，一次一个文件；跟踪表/清单/统计表均可）</h3>
      <div class="text-xs bg-gray-50 border border-gray-200 rounded-base px-3 py-2 leading-relaxed">
        <div class="text-red-600 font-semibold mb-1">⚠️ 上传的 Excel 表头请按以下系统字段命名（仅「问题描述」列必需，缺「状态」列时全部行进客服主管审核，认不出的列不进行抓取；也可点「下载导入模板」获取标准表头）：</div>
        <div class="text-gray-700">
          <strong>问题描述</strong><span class="text-red-500">（必需）</span>、<strong>提出时间</strong>（YYYY-MM-DD）、<strong>厂内编号</strong><span class="text-red-500">（出货后仍必须填写，同机台自动关联依据）</span>、<strong>出厂编号</strong>（设备编号口径：客诉场景=工艺调试类取厂内编号，其余取出厂编号）、<strong>设备型号</strong>（无需填写：自动取厂内编号第一个「-」前内容，缺省取出厂编号）、<strong>客户名称</strong>（选填，缺省按机台自动匹配）、<strong>故障分类</strong>（机械/电气/工艺/光学/软件/其他）、<strong>客诉场景分类</strong>（选填：工艺调试类/现场交付类/客户正式投诉类/客诉诉求）、<strong>优先等级</strong>（高/中/低 → P0/P1/P2）、<strong>影响程度</strong>、<strong>进度</strong>（按百分比驱动）、<strong>计划完成日期</strong>（落工单排期结束时间）、<strong>实际完成时间</strong>（已完成行优先作为关闭时间）、<strong>承接人</strong>（多人用 / 或 、 分隔，逐一匹配系统用户）、<strong>提出人</strong>（必填系统用户，为空/不在系统该行无法导入）、<strong>解决方案或改善措施</strong>、<strong>状态</strong>（已完成/进行中/未开始）、<strong>风险等级</strong>（仅入备注）、<strong>备注</strong>（表内备注原文直接导入）
        </div>
        <div class="mt-1 text-gray-500"><span class="text-red-600 font-medium">导入规则：</span>已完成→已关闭+知识库归档；进行中→责任人匹配到系统用户→处理中（承接人），否则→客服主管审核；未开始→客服主管审核。工单编号按提出日期当日序号生成；表单备注不落工单栏位——待审核行进工单日志、处理中行进进度提交、已关闭行进知识库（经验教训），<span class="text-gray-700">解决方案任何状态都直接同步导入工单「解决方案」字段</span>。<span class="text-gray-700">同机台（厂内/出厂编号相同，大小写不敏感）的工单导入时自动互相关联</span>；老表「设备序列号/机台编号」单列仍可识别</div>
      </div>
      <div class="flex items-center gap-3 flex-wrap">
        <input ref="fileInputRef" type="file" accept=".xlsx,.xls" class="hidden" :disabled="parsing || committing" @change="onFile" />
        <button type="button" @click="fileInputRef?.click()" :disabled="parsing || committing"
          class="px-3 py-1.5 bg-primary text-white rounded-base hover:bg-primary/90 disabled:opacity-50 text-sm font-medium flex items-center gap-1.5">
          <FolderOpen :size="14" /> 选择文件
        </button>
        <!-- 0914 导出标准模板（表头=系统字段名 + 示例行 + 下拉 + 填写说明） -->
        <button type="button" @click="downloadTemplate" :disabled="templateDownloading"
          class="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-base hover:bg-gray-200 disabled:opacity-50 text-sm font-medium flex items-center gap-1.5">
          <Download :size="14" /> {{ templateDownloading ? '生成中…' : '下载导入模板' }}
        </button>
        <span v-if="selectedName" class="text-sm text-gray-600 break-all">{{ selectedName }}</span>
        <span v-if="parsing" class="text-sm text-gray-500">解析中…</span>
        <span v-if="templateError" class="text-sm text-red-600">{{ templateError }}</span>
      </div>
      <div v-if="parseError" class="text-sm p-2.5 rounded-base bg-red-50 text-red-600 border border-red-200 whitespace-pre-wrap">{{ parseError }}</div>
    </div>

    <!-- ② 预览 -->
    <template v-if="preview">
      <!-- 文件级信息 -->
      <div class="bg-white rounded-lg border border-gray-200 p-4 space-y-2">
        <div class="flex items-center gap-2 flex-wrap text-sm">
          <span class="font-semibold">📄 {{ preview.filename }}</span>
          <span class="text-xs bg-blue-50 text-blue-700 border border-blue-200 px-1.5 py-0.5 rounded">机台：{{ preview.machine || '—' }}</span>
          <span class="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">识别 {{ preview.sheets_matched }} 个工作表</span>
          <span v-if="preview.sheets_ignored.length" class="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded"
            :title="'未识别表头被忽略：' + preview.sheets_ignored.join('、')">忽略 {{ preview.sheets_ignored.length }} 个</span>
        </div>
        <div class="flex gap-2 flex-wrap text-xs">
          <span class="px-2 py-1 rounded-base bg-green-50 text-green-700 border border-green-200">可导入共 {{ preview.summary.total }} 行</span>
          <span class="px-2 py-1 rounded-base bg-gray-50 text-gray-600 border border-gray-200">→已关闭 {{ preview.summary.closed }}</span>
          <span class="px-2 py-1 rounded-base bg-blue-50 text-blue-700 border border-blue-200">→处理中 {{ preview.summary.processing }}</span>
          <span class="px-2 py-1 rounded-base bg-amber-50 text-amber-700 border border-amber-200">→主管审核 {{ preview.summary.review }}</span>
          <span v-if="preview.summary.duplicates" class="px-2 py-1 rounded-base bg-red-50 text-red-600 border border-red-200">疑似重复 {{ preview.summary.duplicates }}</span>
          <span v-if="preview.invalid_rows.length" class="px-2 py-1 rounded-base bg-red-50 text-red-600 border border-red-200">无法导入 {{ preview.invalid_rows.length }}</span>
        </div>
        <div v-for="(w, i) in preview.warnings" :key="i" class="text-xs text-amber-700">⚠️ {{ w }}</div>
      </div>

      <!-- 无法导入行（序号+原因） -->
      <div v-if="preview.invalid_rows.length" class="bg-red-50 border border-red-200 rounded-lg p-3 space-y-1">
        <div class="text-sm font-semibold text-red-700">❌ 以下序号无法录入，已跳过：</div>
        <div v-for="(x, i) in preview.invalid_rows" :key="i" class="text-xs text-red-600">
          序号 <strong>{{ x.src_seq || x.src_row }}</strong>：{{ x.reason }}
        </div>
      </div>

      <!-- 行表格（可编辑） -->
      <div class="bg-white rounded-lg border border-gray-200 overflow-x-auto">
        <table class="w-full text-xs">
          <thead>
            <tr class="bg-gray-50 text-gray-600 text-left">
              <th class="px-2 py-2 w-8"></th>
              <th class="px-2 py-2 w-10">序号</th>
              <th class="px-2 py-2 min-w-[180px]">问题描述</th>
              <th class="px-2 py-2 w-24">分类</th>
              <th class="px-2 py-2 w-28">客诉场景</th>
              <th class="px-2 py-2 w-24">责任人</th>
              <th class="px-2 py-2 w-20">提出人</th>
              <th class="px-2 py-2 w-24">提出日期</th>
              <th class="px-2 py-2 w-28">计划完成日期</th>
              <th class="px-2 py-2 w-14">优先级</th>
              <th class="px-2 py-2 w-32">源状态 → 目标</th>
              <th class="px-2 py-2 w-36">客户名称</th>
              <th class="px-2 py-2 min-w-[120px]">提示</th>
              <th class="px-2 py-2 w-10">详情</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in preview.rows" :key="i" class="border-t border-gray-100 align-top"
              :class="row.include ? '' : 'opacity-50'">
              <td class="px-2 py-2"><input v-model="row.include" type="checkbox" class="w-4 h-4 accent-primary"
                :title="(row.duplicate_of || row.duplicate_in_file) ? '勾选=用本行覆盖旧工单' + (row.duplicate_of ? ' ' + row.duplicate_of : '（文件内先导入的那条）') : ''" /></td>
              <td class="px-2 py-2 font-mono tnum">{{ row.src_seq }}</td>
              <td class="px-2 py-2" :title="row.fault_phenomenon">{{ row.fault_phenomenon.slice(0, 60) }}{{ row.fault_phenomenon.length > 60 ? '…' : '' }}</td>
              <td class="px-2 py-2">
                <select v-model="row.fault_category" class="w-full px-1 py-0.5 border border-gray-300 rounded-base bg-white text-xs">
                  <option value="">不分类</option>
                  <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
                </select>
              </td>
              <!-- 0914 客诉场景（可选导入：留空则导入后编辑弹窗补填） -->
              <td class="px-2 py-2">
                <select v-model="row.scene_category" class="w-full px-1 py-0.5 border border-gray-300 rounded-base bg-white text-xs">
                  <option value="">不填</option>
                  <option v-for="s in SCENE_CATEGORY_OPTIONS" :key="s" :value="s">{{ s }}</option>
                </select>
              </td>
              <td class="px-2 py-2">
                <UserSuggestInput v-model="row.responsible" :options="userOptions" multi placeholder="可编辑" />
                <div v-if="row.responsible_matched.length" class="text-[10px] text-green-600">✓ {{ row.responsible_matched.join('、') }}</div>
              </td>
              <td class="px-2 py-2">
                <UserSuggestInput v-model="row.proposer" :options="userOptions" placeholder="可编辑" />
                <div v-if="row.proposer_matched" class="text-[10px] text-green-600">✓ 系统用户</div>
              </td>
              <td class="px-2 py-2 mono tnum">{{ row.created_date }}</td>
              <td class="px-2 py-2 mono tnum">{{ row.expected_complete_date || '—' }}</td>
              <td class="px-2 py-2">{{ row.priority }}</td>
              <td class="px-2 py-2">
                <div class="text-gray-400 mb-0.5">{{ row.src_status || '—' }} →</div>
                <select v-model="row.target_status" class="w-full px-1 py-0.5 border border-gray-300 rounded-base bg-white text-xs">
                  <option v-for="s in TARGET_STATUSES" :key="s" :value="s">{{ s }}</option>
                </select>
              </td>
              <td class="px-2 py-2">
                <input v-model="row.customer_name" type="text" placeholder="选填"
                  class="w-full px-1.5 py-0.5 border border-gray-300 rounded-base text-xs" />
                <div v-if="row.customer_matched" class="text-[10px] text-gray-400 mt-0.5">按机台自动匹配</div>
              </td>
              <td class="px-2 py-2 space-y-0.5">
                <!-- 1016 疑似重复可操作提示：勾选本行=覆盖旧单（人为选择）；「去修改」新标签页打开旧工单编辑 -->
                <div v-if="row.duplicate_of || row.duplicate_in_file" class="text-[10px] text-red-600">
                  疑似重复：{{ row.duplicate_of || '文件内先导入行' }}（勾选本行=覆盖）
                  <button v-if="row.duplicate_id" type="button" @click="openDupDetail(row)"
                    class="text-primary underline ml-1">✏️ 去修改 →</button>
                </div>
                <div v-for="(w, j) in row.warnings" :key="j" class="text-[10px] text-amber-600">{{ w }}</div>
              </td>
              <td class="px-2 py-2">
                <button type="button" @click="detailRow = row" title="查看全部字段"
                  class="text-gray-400 hover:text-primary transition-colors"><Eye :size="15" /></button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="flex items-center gap-3 flex-wrap">
        <button @click="doCommit" :disabled="committing || selectedCount === 0"
          class="px-5 py-2.5 bg-primary text-white rounded-base hover:bg-primary/90 disabled:opacity-50 text-sm font-semibold">
          {{ committing ? '导入中…' : `💾 确认导入（勾选 ${selectedCount} 行）` }}
        </button>
        <button @click="resetAll" :disabled="committing"
          class="px-4 py-2 bg-gray-100 text-gray-700 rounded-base hover:bg-gray-200 text-sm">重新选择文件</button>
        <span v-if="commitError" class="text-sm text-red-600">{{ commitError }}</span>
      </div>
    </template>

    <!-- ③ 结果 -->
    <div v-if="result" class="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
      <div class="font-semibold text-green-700">✅ 导入完成：成功 {{ result.success_count }} 条<span v-if="updatedCount">（其中覆盖既有工单 {{ updatedCount }} 条）</span>，跳过 {{ result.skipped }} 条，知识库归档 {{ result.kb_created }} 条</div>
      <div class="flex gap-2 flex-wrap text-xs">
        <span v-for="(n, s) in result.by_status" :key="s" class="px-2 py-1 rounded-base bg-gray-50 text-gray-600 border border-gray-200">{{ s }}：{{ n }}</span>
      </div>
      <div v-if="result.failed.length" class="bg-red-50 border border-red-200 rounded-base p-3 space-y-1">
        <div class="text-sm font-semibold text-red-700">❌ 以下序号导入失败：</div>
        <div v-for="(f, i) in result.failed" :key="i" class="text-xs text-red-600">序号 <strong>{{ f.src_seq || f.src_row }}</strong>：{{ f.reason }}</div>
      </div>
      <div class="max-h-56 overflow-y-auto border border-gray-100 rounded-base">
        <table class="w-full text-xs">
          <thead>
            <tr class="bg-gray-50 text-gray-600 text-left">
              <th class="px-2 py-1.5">序号</th><th class="px-2 py-1.5">工单号</th><th class="px-2 py-1.5">状态</th><th class="px-2 py-1.5">KB</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(c, i) in result.created" :key="i" class="border-t border-gray-100">
              <td class="px-2 py-1.5 mono tnum">{{ c.src_seq }}</td>
              <td class="px-2 py-1.5 mono">{{ c.complaint_no }}</td>
              <td class="px-2 py-1.5">{{ c.status }} <span v-if="c.updated" class="ml-1 px-1 rounded bg-amber-100 text-amber-700 border border-amber-200">覆盖</span></td>
              <td class="px-2 py-1.5">{{ c.kb_id ? '✓ #' + c.kb_id : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <button @click="resetAll" class="px-4 py-2 bg-primary text-white rounded-base hover:bg-primary/90 text-sm font-medium">📥 再导入一份</button>
    </div>

    <!-- 行详情弹窗（全部字段，含表格中放不下的列） -->
    <Teleport to="body">
      <div v-if="detailRow" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/40" @click="detailRow = null"></div>
        <div class="relative bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[85vh] overflow-y-auto p-5 space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold">序号 {{ detailRow.src_seq }} 详情</h3>
            <button type="button" @click="detailRow = null" class="text-gray-400 hover:text-gray-600"><X :size="18" /></button>
          </div>
          <!-- 严格按词汇表字段展示（0915 机台编号拆出厂前/后，1014 口径名 厂内编号/出厂编号）；Excel 中不匹配词汇表的列不抓取也不在此显示 -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div><span class="text-gray-500">状态：</span>{{ detailRow.src_status || '—' }}</div>
            <div><span class="text-gray-500">提出日期：</span><span class="mono tnum">{{ detailRow.created_date || '—' }}</span></div>
            <div><span class="text-gray-500">厂内编号：</span>{{ detailRow.machine_pre || '—' }}</div>
            <div><span class="text-gray-500">出厂编号：</span>{{ detailRow.machine_post || '—' }}</div>
            <div class="sm:col-span-2"><span class="text-gray-500">落库设备编号：</span><span class="mono">{{ detailRow.equipment_sn || '—' }}</span><span class="text-gray-400 text-xs">（1016 口径：客诉场景=工艺调试类取厂内编号，其余取出厂编号；同机台工单自动互相关联）</span></div>
            <div><span class="text-gray-500">设备型号（自动）：</span>{{ detailRow.equipment_model || '—' }}</div>
            <div><span class="text-gray-500">客户名称：</span>{{ detailRow.customer_name || '—' }}<span v-if="detailRow.customer_matched" class="text-gray-400 text-xs">（按机台自动匹配）</span></div>
            <div><span class="text-gray-500">所属部门：</span>{{ detailRow.fault_category || '不分类' }}</div>
            <div><span class="text-gray-500">客诉场景：</span>{{ detailRow.scene_category || '—（导入后可编辑补填）' }}</div>
            <div class="sm:col-span-2"><span class="text-gray-500">问题描述：</span><span class="whitespace-pre-wrap">{{ detailRow.fault_phenomenon || '—' }}</span></div>
            <div class="sm:col-span-2"><span class="text-gray-500">解决方案：</span><span class="whitespace-pre-wrap">{{ detailRow.solution || '—' }}</span></div>
            <div><span class="text-gray-500">责任人：</span>{{ detailRow.responsible || '—' }}<span v-if="detailRow.responsible_matched.length" class="text-green-600 text-xs"> ✓ {{ detailRow.responsible_matched.join('、') }}</span></div>
            <div><span class="text-gray-500">提出人：</span>{{ detailRow.proposer || '—' }}<span v-if="detailRow.proposer_matched" class="text-green-600 text-xs"> ✓ 系统用户</span></div>
            <div><span class="text-gray-500">风险等级：</span>{{ detailRow.risk || '—' }}</div>
            <div><span class="text-gray-500">优先等级：</span>{{ detailRow.priority_orig || '—' }}</div>
            <div><span class="text-gray-500">进度：</span>{{ detailRow.progress || '—' }}</div>
            <div><span class="text-gray-500">影响：</span>{{ detailRow.impact_level || '—' }}</div>
            <div class="sm:col-span-2"><span class="text-gray-500">计划完成日期：</span><span class="mono tnum">{{ detailRow.expected_complete_date || '—' }}</span></div>
            <div class="sm:col-span-2"><span class="text-gray-500">备注：</span><span class="whitespace-pre-wrap">{{ detailRow.remarks || '—' }}</span></div>
            <div v-if="detailRow.duplicate_of || detailRow.duplicate_in_file" class="sm:col-span-2 text-red-600">
              疑似重复：已存在工单 {{ detailRow.duplicate_of || '（文件内先导入行）' }}——勾选本行并导入=用本行覆盖该工单
              <button v-if="detailRow.duplicate_id" type="button" @click="openDupDetail(detailRow)"
                class="text-primary underline ml-1">✏️ 去修改 →</button>
            </div>
            <div v-if="detailRow.warnings.length" class="sm:col-span-2 text-amber-600 space-y-0.5">
              <div v-for="(w, j) in detailRow.warnings" :key="j">⚠️ {{ w }}</div>
            </div>
          </div>
          <div class="text-right">
            <button type="button" @click="detailRow = null" class="px-4 py-1.5 bg-gray-100 text-gray-700 rounded-base hover:bg-gray-200 text-sm">关闭</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Upload, FolderOpen, Download, Eye, X } from 'lucide-vue-next'
import { parseBatchImport, commitBatchImport, downloadBatchImportTemplate } from '@/api/complaints'
import { getUserOptions } from '@/api/users'
import UserSuggestInput from './UserSuggestInput.vue'
import { SCENE_CATEGORY_OPTIONS } from '@/types/api'
import type { BatchParseResponse, BatchCommitResponse, BatchPreviewRow, UserOption } from '@/types/api'

// 与系统故障分类一致（视觉等已在后端映射为光学）
const CATEGORIES = ['机械', '电气', '工艺', '光学', '软件', '其他']
const TARGET_STATUSES = ['已关闭', '处理中', '客服主管审核'] as const

const router = useRouter()

// 1016 疑似重复行「去修改」：新标签页打开既有工单详情（详情页有「编辑工单」按钮；不离开当前预览）
function openDupDetail(row: BatchPreviewRow) {
  if (!row.duplicate_id) return
  window.open(router.resolve(`/work-order/${row.duplicate_id}`).href, '_blank')
}

// 0911 责任人/提出人模糊搜索候选：与后端 ALL_ROLES 匹配口径一致（全部 6 角色）
const userOptions = ref<UserOption[]>([])
onMounted(async () => {
  try {
    const r = await getUserOptions(['管理员', '客服', '客服主管', '办理人', '审批人', '承接人'])
    if (r.data?.success) userOptions.value = r.data.data || []
  } catch { /* 加载失败仅退化为普通输入框，不阻断导入 */ }
})

const fileInputRef = ref<HTMLInputElement>()
const selectedName = ref('')
const parsing = ref(false)
const parseError = ref('')
const preview = ref<BatchParseResponse | null>(null)
const committing = ref(false)
const commitError = ref('')
const result = ref<BatchCommitResponse | null>(null)
const detailRow = ref<BatchPreviewRow | null>(null)

const selectedCount = computed(() => preview.value?.rows.filter(r => r.include).length ?? 0)
// 1016 本次导入中覆盖既有工单的行数（结果汇总展示）
const updatedCount = computed(() => result.value?.created.filter(c => c.updated).length ?? 0)

// 0914 下载导入模板（blob 流，复用 ExportCenter.vue 的下载模式）
const templateDownloading = ref(false)
const templateError = ref('')

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

async function downloadTemplate() {
  templateError.value = ''
  templateDownloading.value = true
  try {
    const r = await downloadBatchImportTemplate()
    triggerDownload(r, '批量导入模板.xlsx')
  } catch (e: any) {
    templateError.value = e?.response?.data?.detail || '模板下载失败，请稍后重试'
  } finally {
    templateDownloading.value = false
  }
}

async function onFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  parseError.value = ''
  preview.value = null
  result.value = null
  detailRow.value = null
  selectedName.value = f.name
  parsing.value = true
  try {
    const r = await parseBatchImport(f)
    if (r.data?.success && r.data.data) {
      preview.value = r.data.data
    } else {
      parseError.value = r.data?.message || '解析失败'
    }
  } catch (err: any) {
    parseError.value = err?.response?.data?.detail || '解析失败，请检查文件格式'
  } finally {
    parsing.value = false
  }
}

async function doCommit() {
  if (!preview.value) return
  commitError.value = ''
  committing.value = true
  try {
    const r = await commitBatchImport({
      context: { filename: preview.value.filename },
      rows: preview.value.rows,
    })
    if (r.data?.success && r.data.data) {
      result.value = r.data.data
      preview.value = null
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } else {
      commitError.value = r.data?.message || '导入失败'
    }
  } catch (err: any) {
    commitError.value = err?.response?.data?.detail || '导入失败'
  } finally {
    committing.value = false
  }
}

function resetAll() {
  preview.value = null
  result.value = null
  parseError.value = ''
  commitError.value = ''
  selectedName.value = ''
  detailRow.value = null
  if (fileInputRef.value) fileInputRef.value.value = ''
}
</script>
