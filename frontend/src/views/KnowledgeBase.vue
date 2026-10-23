<!-- 0727 Phase 3 知识库 — 检索案例 + 新增知识
     来源：pages/4_知识库.py（v2.1 Streamlit）-->
<template>
  <AppLayout>
    <div class="p-4 sm:p-6 space-y-4">
      <h1 class="text-2xl font-bold">📚 知识库</h1>

      <!-- Tab 切换 -->
      <div class="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit">
        <button
          v-for="tab in tabs" :key="tab.key"
          @click="activeTab = tab.key"
          :class="['px-4 py-1.5 rounded-md text-sm font-medium transition',
            activeTab === tab.key ? 'bg-white shadow text-primary' : 'text-gray-500 hover:text-gray-700']"
        >{{ tab.label }}</button>
      </div>

      <!-- ========== Tab 1：检索案例 ========== -->
      <template v-if="activeTab === 'search'">
        <!-- 搜索栏 -->
        <div class="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
          <div class="flex flex-wrap gap-3 items-end">
            <div class="flex-1 min-w-full sm:min-w-[200px]">
              <label class="text-xs text-gray-500 mb-1 block">关键词搜索</label>
              <input v-model="store.searchParams.keyword" @keyup.enter="doSearchOnEnter"
                placeholder="输入关键词（支持 FTS5 全文检索）..."
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <div>
              <label class="text-xs text-gray-500 mb-1 block">故障类别</label>
              <select v-model="store.searchParams.category" @change="doSearchOnChange"
                class="px-3 py-1.5 border border-gray-300 rounded text-sm">
                <option value="">全部类别</option>
                <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
              </select>
            </div>
            <div>
              <label class="text-xs text-gray-500 mb-1 block">质量筛选</label>
              <select v-model="store.searchParams.qualityFilter" @change="doSearchOnChange"
                class="px-3 py-1.5 border border-gray-300 rounded text-sm">
                <option value="">全部</option>
                <option value="high_value">⭐ 高价值</option>
                <option value="top_tier">🏆 顶级案例</option>
                <option value="engineer_rec">🔧 工程师推荐</option>
                <option value="presales_rec">💼 售前推荐</option>
                <option value="needs_review">⚠️ 待修订</option>
                <option value="stale">🗑️ 陈旧条目</option>
              </select>
            </div>
            <div>
              <label class="text-xs text-gray-500 mb-1 block">排序</label>
              <select v-model="store.searchParams.sortBy" @change="doSearchOnChange"
                class="px-3 py-1.5 border border-gray-300 rounded text-sm">
                <option value="">默认排序</option>
                <option value="newest">最新优先</option>
                <option value="most_useful">最有帮助</option>
                <option value="composite">综合评分最高</option>
                <option value="engineer">🔧 工程师优先</option>
                <option value="presales">💼 售前优先</option>
              </select>
            </div>
            <div class="flex gap-2 items-end">
              <button @click="doSearchOnClick"
                class="px-4 py-1.5 bg-primary text-white rounded text-sm hover:bg-primary/90 transition font-medium">
                🔍 搜索
              </button>
              <button @click="showAiSearch = !showAiSearch"
                class="px-3 py-1.5 border border-purple-300 text-purple-700 rounded text-sm hover:bg-purple-50 transition"
                :class="{ 'bg-purple-100': showAiSearch }">
                🤖 AI 语义搜索
              </button>
            </div>
            <!-- AI 语义搜索区（折叠，默认不显示） -->
            <div v-if="showAiSearch" class="pt-3 border-t border-gray-100">
              <!-- 0729 AI 免责提示 -->
              <p class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3 flex items-start gap-1.5">
                <span class="shrink-0">⚠️</span>
                <span><strong>AI 建议仅供参考</strong> — 语义搜索结果为 AI 对自然语言的理解，可能与实际知识库内容存在偏差。</span>
              </p>
              <div class="flex gap-2 items-end">
                <input v-model="aiQuery" @keyup.enter="doAiSearch"
                  placeholder="用自然语言描述故障，AI 从知识库中找到语义最相近的条目..."
                  class="flex-1 px-3 py-1.5 border border-purple-300 rounded text-sm" />
                <button @click="doAiSearch" :disabled="aiSearching || !aiQuery.trim()"
                  class="px-4 py-1.5 bg-purple-600 text-white rounded text-sm hover:bg-purple-700 disabled:opacity-50 transition">
                  🤖 {{ aiSearching ? '搜索中...' : '搜索' }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 结果 -->
        <div v-if="store.loading" class="text-center text-gray-400 py-8">加载中...</div>
        <div v-else-if="!store.results.length" class="text-center text-gray-400 py-8">暂无知识条目</div>
        <div v-else class="space-y-3">
          <KBCard v-for="entry in store.results" :key="entry.id" :entry="entry" />
        </div>

        <!-- 分页 — 始终显示，方便切换每页条数 -->
        <div class="flex items-center justify-center gap-2">
          <button @click="store.page--; doSearch(false)" :disabled="store.page <= 1"
            class="px-3 py-1 text-sm border rounded disabled:opacity-30">上一页</button>
          <span class="text-sm text-gray-500">{{ store.page }} / {{ Math.ceil(store.total / store.pageSize) || 1 }}</span>
          <button @click="store.page++; doSearch(false)" :disabled="store.page >= Math.ceil(store.total / store.pageSize)"
            class="px-3 py-1 text-sm border rounded disabled:opacity-30">下一页</button>
          <select v-model="store.pageSize" @change="store.page = 1; doSearch()"
            class="px-2 py-1 border rounded text-sm ml-4">
            <option :value="10">10条/页</option>
            <option :value="20">20条/页</option>
            <option :value="50">50条/页</option>
          </select>
        </div>
      </template>

      <!-- ========== Tab 2：新增知识 ========== -->
      <template v-if="activeTab === 'add'">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <!-- 左侧：AI 解析 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
            <h3 class="font-semibold text-sm">🤖 智能解析</h3>
            <!-- 0729 AI 免责提示 -->
            <p class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-start gap-1.5">
              <span class="shrink-0">⚠️</span>
              <span><strong>AI 建议仅供参考</strong> — AI 自动提取的知识字段为初步解析结果，保存前请人工核对内容准确性。</span>
            </p>
            <DeepSeekStatus />
            <textarea v-model="pasteText" rows="8"
              placeholder="粘贴非结构化文本（聊天记录、邮件、会议纪要等），AI 自动提取知识条目字段..."
              class="w-full px-3 py-2 border border-gray-300 rounded text-sm resize-y"></textarea>
            <div class="flex gap-2">
              <button @click="() => doAiParse()" :disabled="aiParsing || !pasteText.trim()"
                class="flex-1 px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50 transition">
                🔍 {{ aiParsing ? '解析中...' : 'AI 智能解析' }}
              </button>
              <button @click="doAiParseWithFallback" :disabled="aiParsing || !pasteText.trim()"
                class="px-4 py-2 border border-gray-300 rounded text-sm hover:bg-gray-50 transition"
                title="LLM 失败时自动降级到规则引擎">含规则降级</button>
            </div>
            <div v-if="parseResult" class="p-3 rounded text-sm space-y-1"
              :class="parseResult.source === 'deepseek' ? 'bg-blue-50' : parseResult.source === 'rules' ? 'bg-yellow-50' : 'bg-red-50'">
              <div class="font-medium" :class="parseResult.source === 'deepseek' ? 'text-blue-800' : parseResult.source === 'rules' ? 'text-yellow-800' : 'text-red-700'">
                {{ parseResult.source === 'deepseek' ? '✅ AI 解析成功' : parseResult.source === 'rules' ? '⚠️ 规则引擎降级解析' : '❌ 解析失败' }}
              </div>
              <div v-if="parseResult.source === 'failed'" class="text-red-600">{{ parseResult.error }}</div>
              <div v-else class="text-xs">已提取 {{ countParsedFields(parseResult) }} 个字段</div>
            </div>
            <button v-if="parseResult && parseResult.source !== 'failed'"
              @click="applyParse"
              class="w-full px-4 py-1.5 bg-green-600 text-white rounded text-sm hover:bg-green-700 transition">
              📝 填充到表单
            </button>
          </div>

          <!-- 右侧：手动录入 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4 space-y-3">
            <h3 class="font-semibold text-sm">📝 手动录入</h3>
            <div>
              <label class="text-xs text-gray-500">标题 *</label>
              <input v-model="form.title" class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div>
                <label class="text-xs text-gray-500">故障类别</label>
                <select v-model="form.fault_category"
                  class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm">
                  <option value="">选择类别</option>
                  <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
                </select>
              </div>
              <div>
                <label class="text-xs text-gray-500">设备型号</label>
                <input v-model="form.equipment_model" class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
              </div>
            </div>
            <div>
              <!-- 0730 故障现象 -->
              <label class="text-xs text-gray-500">故障现象</label>
              <textarea v-model="form.fault_phenomenon" rows="3"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm"
                placeholder="客户描述的原始故障现象"></textarea>
            </div>
            <div>
              <label class="text-xs text-gray-500">故障关键词（逗号分隔）</label>
              <input v-model="form.fault_keywords" class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
            </div>
            <div>
              <label class="text-xs text-gray-500">根因分析</label>
              <textarea v-model="form.root_cause" rows="4"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm"></textarea>
            </div>
            <div>
              <label class="text-xs text-gray-500">解决方案</label>
              <textarea v-model="form.solution" rows="4"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm"></textarea>
            </div>
            <div>
              <label class="text-xs text-gray-500">检查清单</label>
              <textarea v-model="form.checklist" rows="3"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm"></textarea>
            </div>
            <div>
              <label class="text-xs text-gray-500">经验教训</label>
              <textarea v-model="form.lesson_learned" rows="4"
                class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm"></textarea>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div>
                <label class="text-xs text-gray-500">联系人/作者</label>
                <input v-model="form.contact_author" class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
              </div>
              <div>
                <label class="text-xs text-gray-500">关联工单号</label>
                <input v-model="form.complaint_no" class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm" />
              </div>
            </div>
            <button @click="doCreate" :disabled="creating || !form.title.trim()"
              class="w-full px-4 py-2 bg-primary text-white rounded text-sm hover:bg-primary/90 disabled:opacity-50 transition font-medium">
              {{ creating ? '提交中...' : '💾 保存到知识库' }}
            </button>
            <div v-if="createMsg" :class="['text-xs', createOk ? 'text-green-600' : 'text-red-500']">{{ createMsg }}</div>
          </div>
        </div>
      </template>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import KBCard from '@/components/knowledge/KBCard.vue'
import DeepSeekStatus from '@/components/common/DeepSeekStatus.vue'
import { useKnowledgeStore } from '@/stores/knowledge'
import * as aiApi from '@/api/ai'

const CATEGORIES = ['机械', '电气', '工艺', '光学', '软件', '其他']

const store = useKnowledgeStore()
const activeTab = ref<'search' | 'add'>('search')
const tabs = [
  { key: 'search' as const, label: '🔍 检索案例' },
  { key: 'add' as const, label: '➕ 新增知识' },
]

const aiSearching = ref(false)
const showAiSearch = ref(false)
const aiQuery = ref('')

async function doSearch(resetPage: boolean = true) {
  if (resetPage) store.page = 1
  await store.search()
}

// 包装函数给模板事件使用
function doSearchOnChange(_e: Event) { doSearch() }
function doSearchOnClick(_e: PointerEvent) { doSearch() }
function doSearchOnEnter(_e: KeyboardEvent) { doSearch() }

async function doAiSearch() {
  const q = aiQuery.value.trim() || store.searchParams.keyword || '故障'
  if (!aiQuery.value.trim()) aiQuery.value = q
  aiSearching.value = true
  try {
    const r = await aiApi.semanticSearch(q, 10)
    if (r.data?.success && r.data.data?.length) {
      store.results = r.data.data
      store.total = r.data.data.length
    }
  } catch (e: any) { console.error('AI search error:', e) }
  finally { aiSearching.value = false }
}

const pasteText = ref('')
const parseResult = ref<any>(null)
const aiParsing = ref(false)

async function doAiParse(fallback = false) {
  aiParsing.value = true
  parseResult.value = null
  try {
    const r = await aiApi.extractKnowledge(pasteText.value, fallback)
    if (r.data?.success) parseResult.value = r.data.data
  } catch (e: any) {
    parseResult.value = { source: 'failed', error: e?.response?.data?.detail || '解析失败' }
  } finally { aiParsing.value = false }
}

function doAiParseWithFallback() { doAiParse(true) }

function countParsedFields(result: any): number {
  const keys = ['title', 'fault_category', 'equipment_model', 'fault_keywords', 'fault_phenomenon', 'root_cause', 'solution', 'checklist', 'lesson_learned', 'contact_author']
  return keys.filter((k: string) => result[k]).length
}

const form = reactive({
  title: '', fault_category: '', equipment_model: '', fault_keywords: '',
  fault_phenomenon: '',
  root_cause: '', solution: '', checklist: '', lesson_learned: '',
  contact_author: '', complaint_no: '',
})

function applyParse() {
  if (!parseResult.value) return
  const r = parseResult.value
  form.title = r.title || ''
  form.fault_category = r.fault_category || ''
  form.equipment_model = r.equipment_model || ''
  form.fault_keywords = r.fault_keywords || ''
  form.fault_phenomenon = r.fault_phenomenon || ''
  form.root_cause = r.root_cause || ''
  form.solution = r.solution || ''
  form.checklist = r.checklist || ''
  form.lesson_learned = r.lesson_learned || ''
  form.contact_author = r.contact_author || ''
}

const creating = ref(false)
const createMsg = ref('')
const createOk = ref(false)

async function doCreate() {
  creating.value = true; createMsg.value = ''
  try {
    const r = await store.createEntry({ ...form })
    if (r?.success) {
      createOk.value = true
      createMsg.value = '✅ 知识条目已保存'
      Object.keys(form).forEach(k => (form as any)[k] = '')
      pasteText.value = ''
      parseResult.value = null
    } else {
      createOk.value = false
      createMsg.value = r?.message || '保存失败'
    }
  } catch (e: any) {
    createOk.value = false
    createMsg.value = e?.response?.data?.detail || '网络错误'
  } finally { creating.value = false }
}

onMounted(() => { doSearch() })
</script>
