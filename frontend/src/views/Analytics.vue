<!-- 0727 Phase 3 客诉分析 — KPI + 趋势 + 分布 + 工程师统计 + KB 质量仪表盘
     来源：pages/5_客诉分析.py（v2.1 Streamlit）-->
<template>
  <AppLayout>
    <div class="p-6 space-y-6">
      <div class="flex items-center justify-between flex-wrap gap-3">
        <h1 class="text-2xl font-bold">📈 客诉分析</h1>
        <div class="flex items-center gap-3">
          <!-- 时间范围 -->
          <select v-model="store.dateRange" @change="onDateRangeChange"
            class="px-3 py-1.5 border border-gray-300 rounded text-sm">
            <option v-for="r in DATE_RANGES" :key="r" :value="r">{{ r }}</option>
          </select>
        </div>
      </div>

      <div v-if="store.loading && !store.kpi" class="text-center text-gray-400 py-16">加载中...</div>

      <template v-else>
        <!-- ===== KPI 卡片 — 行 1：工单状态分布（0819 新状态） ===== -->
        <div>
          <h3 class="text-sm font-semibold text-gray-700 mb-2">📊 工单状态分布</h3>
          <div class="grid grid-cols-3 md:grid-cols-6 gap-3">
            <KpiCard icon="📋" label="总工单数" :value="store.kpi?.total" color="blue" />
            <KpiCard icon="✅" label="已关闭" :value="store.kpi?.closed_count" color="green" />
            <KpiCard icon="↩️" label="已撤回" :value="store.kpi?.withdrawn_count" color="gray" />
            <KpiCard icon="🔧" label="处理中" :value="store.kpi?.in_progress_count" color="yellow" />
            <KpiCard icon="🧾" label="待客服处理" :value="store.kpi?.pending_cs_count" color="gray" />
            <KpiCard icon="🧑‍💼" label="客服主管审核" :value="store.kpi?.pending_review_count" color="gray" />
            <KpiCard icon="🔍" label="待客户排查" :value="store.kpi?.pending_customer_check_count" color="gray" />
          </div>
        </div>

        <!-- ===== KPI 卡片 — 行 2：质量与效率 ===== -->
        <div>
          <h3 class="text-sm font-semibold text-gray-700 mb-2">📈 质量与效率</h3>
          <div class="grid grid-cols-3 md:grid-cols-6 gap-3">
            <KpiCard icon="👤" label="待指派审批人" :value="store.kpi?.pending_approver_count" color="gray" />
            <KpiCard icon="👥" label="待指派承接人" :value="store.kpi?.pending_assign_count" color="gray" />
            <KpiCard icon="🤝" label="待客户确认" :value="store.kpi?.pending_customer_count" color="gray" />
            <KpiCard icon="⭐" label="平均满意度" :value="store.kpi?.avg_satisfaction" color="yellow" format="star" />
            <KpiCard icon="⏱️" label="平均处理耗时" :value="store.kpi?.avg_processing_hours" color="blue" format="hours" />
            <KpiCard icon="⚠️" label="逾期数" :value="store.kpi?.overdue_count" color="red" />
          </div>
        </div>

        <!-- ===== 趋势 + 状态分布（2 列）===== -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-semibold">📈 工单趋势</h3>
              <select v-model="store.trendGranularity" @change="store.fetchTrend()"
                class="px-2 py-0.5 border border-gray-300 rounded text-xs">
                <option value="monthly">每月</option>
                <option value="daily">每日</option>
              </select>
            </div>
            <TrendChart :data="store.trend" :granularity="store.trendGranularity" />
          </div>
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-2">📊 状态分布</h3>
            <DonutChart v-if="statusDist.length" :data="statusDist" title="工单状态" />
            <div v-else class="text-gray-400 text-sm py-8 text-center">暂无数据</div>
          </div>
        </div>

        <!-- ===== 分布分析 ===== -->
        <div class="bg-white rounded-lg border border-gray-200 p-4">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-semibold">🔍 分布分析</h3>
            <select v-model="store.distributionDimension" @change="store.fetchDistribution()"
              class="px-3 py-1.5 border border-gray-300 rounded text-sm">
              <option value="category">故障类别</option>
              <option value="priority">优先级</option>
              <option value="customer">TOP 10 客户</option>
              <option value="equipment">TOP 10 设备型号</option>
            </select>
          </div>
          <DonutChart v-if="store.distribution.length" :data="distData"
            :title="dimLabel" />
          <div v-else class="text-gray-400 text-sm py-8 text-center">暂无数据</div>
        </div>

        <!-- ===== 知识库质量仪表盘 ===== -->
        <div class="border-t-2 border-primary/20 pt-6 space-y-4">
          <h2 class="text-xl font-bold">📚 知识库质量仪表盘</h2>

          <!-- KB 质量 KPI -->
          <div class="grid grid-cols-3 md:grid-cols-5 gap-3">
            <KpiCard icon="📚" label="总知识条目" :value="store.kbQuality?.total" color="blue" />
            <KpiCard icon="⭐" label="高价值条目" :value="store.kbQuality?.high_value_count" color="green" />
            <KpiCard icon="⚠️" label="待修订条目" :value="store.kbQuality?.needs_review_count" color="red" />
            <KpiCard icon="🗑️" label="陈旧条目" :value="store.kbQuality?.stale_count" color="gray" />
            <KpiCard icon="👍" label="平均好评率" :value="store.kbQuality?.avg_positive_pct" color="yellow" format="percent" />
          </div>

          <!-- 维度投票统计 -->
          <div class="grid grid-cols-5 gap-3">
            <KpiCard icon="🎯" label="根因准确" :value="store.kbQuality?.accuracy_total" color="blue" />
            <KpiCard icon="🔧" label="方案有效" :value="store.kbQuality?.effectiveness_total" color="green" />
            <KpiCard icon="📋" label="步骤清晰" :value="store.kbQuality?.clarity_total" color="yellow" />
            <KpiCard icon="⚡" label="客户影响" :value="store.kbQuality?.customer_impact_total" color="purple" />
            <KpiCard icon="💼" label="售前标杆" :value="store.kbQuality?.presales_value_total" color="red" />
          </div>

          <div class="grid grid-cols-2 gap-3 text-xs text-gray-600">
            <div class="bg-white border rounded p-3 text-center">
              🔧 工程师推荐条目：<strong>{{ store.kbQuality?.engineer_rec_count || 0 }}</strong>
            </div>
            <div class="bg-white border rounded p-3 text-center">
              💼 售前推荐条目：<strong>{{ store.kbQuality?.presales_rec_count || 0 }}</strong>
            </div>
          </div>

          <!-- 0805 Phase 4: 案例检索质量 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h4 class="text-sm font-semibold mb-3">🔍 案例检索质量</h4>
            <div v-if="!store.caseFeedbackStats || !store.caseFeedbackStats.total" class="text-xs text-gray-400 py-4 text-center">
              暂无案例检索评价数据（需在工单处理时对检索案例进行评价）
            </div>
            <template v-else>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <KpiCard icon="📝" label="案例评价总数" :value="store.caseFeedbackStats.total" color="blue" />
                <KpiCard icon="👍" label="可参考率" :value="store.caseFeedbackStats.reference_pct" color="green" format="percent" />
                <KpiCard icon="⭐" label="平均匹配准确度" :value="store.caseFeedbackStats.avg_match_accuracy" color="yellow" />
                <KpiCard icon="📊" label="数据来源数" :value="(store.caseFeedbackStats.by_source || []).length" color="gray" />
              </div>
              <!-- 按来源对比表 -->
              <table v-if="store.caseFeedbackStats.by_source?.length" class="w-full text-xs">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-1 pr-4">来源</th>
                    <th class="py-1 pr-4 text-right">评价数</th>
                    <th class="py-1 pr-4 text-right">可参考率</th>
                    <th class="py-1 pr-4 text-right">平均匹配度</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="s in store.caseFeedbackStats.by_source" :key="s.source_type" class="border-b last:border-0">
                    <td class="py-1 pr-4 font-medium">{{ s.source_type === 'fts5_auto' ? '自动匹配' : s.source_type === 'ai_solution' ? 'AI 方案推荐' : s.source_type }}</td>
                    <td class="py-1 pr-4 text-right tnum">{{ s.total }}</td>
                    <td class="py-1 pr-4 text-right tnum" :class="(s.referenced_count * 100 / (s.total || 1)) >= 60 ? 'text-green-600' : 'text-yellow-600'">{{ s.total > 0 ? Math.round(s.referenced_count * 100 / s.total) : 0 }}%</td>
                    <td class="py-1 pr-4 text-right tnum">{{ s.avg_match }}</td>
                  </tr>
                </tbody>
              </table>
              <!-- TOP KB 引用排行 -->
              <div v-if="store.caseFeedbackStats.top_kb?.length" class="mt-3">
                <h5 class="text-xs font-medium text-gray-600 mb-1">🏆 TOP 10 被引用知识</h5>
                <table class="w-full text-xs">
                  <thead>
                    <tr class="border-b text-left text-gray-500">
                      <th class="py-1 pr-2">标题</th>
                      <th class="py-1 pr-2 text-right">引用次数</th>
                      <th class="py-1 pr-2 text-right">可参考率</th>
                      <th class="py-1 pr-2 text-right">平均匹配度</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="k in store.caseFeedbackStats.top_kb" :key="k.kb_id" class="border-b last:border-0 hover:bg-gray-50">
                      <td class="py-1 pr-2 truncate max-w-[250px]">{{ k.kb_title || 'KB#' + k.kb_id }}</td>
                      <td class="py-1 pr-2 text-right tnum">{{ k.total_feedback }}</td>
                      <td class="py-1 pr-2 text-right tnum" :class="(k.reference_count * 100 / (k.total_feedback || 1)) >= 60 ? 'text-green-600' : 'text-yellow-600'">{{ k.total_feedback > 0 ? Math.round(k.reference_count * 100 / k.total_feedback) : 0 }}%</td>
                      <td class="py-1 pr-2 text-right tnum">{{ k.avg_match_accuracy }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
          </div>

          <!-- TOP 10 高价值 + 待修订 -->
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div class="bg-white rounded-lg border border-gray-200 p-4">
              <h4 class="text-sm font-semibold mb-2">🏆 TOP 10 高价值知识</h4>
              <div v-if="!store.kbTopValuable.length" class="text-xs text-gray-400 py-4 text-center">暂无</div>
              <table v-else class="w-full text-xs">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-1">标题</th>
                    <th class="py-1">类别</th>
                    <th class="py-1 text-right">👍/👎</th>
                    <th class="py-1 text-right">好评率</th>
                    <th class="py-1 text-right">综合评分</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="e in store.kbTopValuable" :key="e.id" class="border-b last:border-0 hover:bg-gray-50">
                    <td class="py-1 pr-2 truncate max-w-[200px]">{{ e.title }}</td>
                    <td class="py-1 pr-2">{{ e.fault_category || '-' }}</td>
                    <td class="py-1 pr-2 text-right">{{ e.useful_count }}/{{ e.unhelpful_count }}</td>
                    <td class="py-1 pr-2 text-right">{{ (e as any)._positive_pct || (e.useful_count+e.unhelpful_count > 0 ? Math.round(e.useful_count/(e.useful_count+e.unhelpful_count)*100) : 0) }}%</td>
                    <td class="py-1 pr-2 text-right font-medium">{{ (e as any)._composite_score || (e as any).composite_score || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="bg-white rounded-lg border border-gray-200 p-4">
              <h4 class="text-sm font-semibold mb-2">⚠️ 待修订条目</h4>
              <div v-if="!store.kbNeedsReview.length" class="text-xs text-gray-400 py-4 text-center">暂无</div>
              <div v-else class="space-y-2">
                <div v-for="e in store.kbNeedsReview" :key="e.id" class="text-xs flex justify-between items-center border-b pb-1 last:border-0">
                  <span class="truncate flex-1">{{ e.title }}</span>
                  <span class="text-red-500 ml-2">👎{{ e.unhelpful_count }} &gt; 👍{{ e.useful_count }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 陈旧条目 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h4 class="text-sm font-semibold mb-2">🗑️ 陈旧条目（&gt;3 个月零反馈）</h4>
            <div v-if="!store.kbStale.length" class="text-xs text-gray-400 py-4 text-center">暂无陈旧条目</div>
            <div v-else class="flex flex-wrap gap-2">
              <span v-for="e in store.kbStale" :key="e.id"
                class="text-xs px-2 py-1 bg-gray-100 rounded">{{ e.title }} ({{ e.created_at?.slice(0, 10) }})</span>
            </div>
          </div>
        </div>

        <!-- 计算说明 -->
        <div class="text-xs text-gray-400 border-t pt-4">
          <p>💡 计算说明：工程师评分 = 根因准确×3 + 方案有效×3 + 步骤清晰×2 | 售前评分 = 客户影响×2 + 售前标杆×3 | 综合评分 = 工程师评分 + 售前评分 + 有用数</p>
        </div>
      </template>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import KpiCard from '@/components/analytics/KpiCard.vue'
import TrendChart from '@/components/analytics/TrendChart.vue'
import DonutChart from '@/components/analytics/DonutChart.vue'
import { useAnalyticsStore } from '@/stores/analytics'
import * as analyticsApi from '@/api/analytics'

const DATE_RANGES = ['本月', '上月', '近3个月', '近6个月', '全部']

const store = useAnalyticsStore()

const dimLabel = computed(() => {
  const m: Record<string, string> = { category: '故障类别', priority: '优先级', customer: 'TOP 10 客户', equipment: 'TOP 10 设备型号' }
  return m[store.distributionDimension] || ''
})

// 0727 分布数据键名归一化：后端返回 fault_category/priority/customer_name/equipment_model + cnt，
// DonutChart 需要 name/count —— 在此映射
const distData = computed(() => {
  const dim = store.distributionDimension
  const keyMap: Record<string, string> = {
    category: 'fault_category', priority: 'priority',
    customer: 'customer_name', equipment: 'equipment_model',
  }
  const key = keyMap[dim] || 'name'
  return store.distribution.map((d: any) => ({ name: (d as any)[key] || '—', count: d.cnt || 0 }))
})

const statusDist = computed(() => {
  // 0819 从 KPI 中的状态字段构造状态分布数据
  if (!store.kpi) return []
  const mapping: [string, string][] = [
    ['待客服处理', 'pending_cs_count'],
    ['待客户排查', 'pending_customer_check_count'],
    ['客服主管审核', 'pending_review_count'],
    ['指派审批人', 'pending_approver_count'],
    ['指派承接人', 'pending_assign_count'],
    ['处理中', 'in_progress_count'],
    ['已关闭', 'closed_count'],
    ['已撤回', 'withdrawn_count'],
  ]
  return mapping.map(([name, key]) => ({ name, count: (store.kpi as any)[key] || 0 })).filter(d => d.count > 0)
})

async function onDateRangeChange() {
  await store.fetchAll()
}

onMounted(() => { store.fetchAll() })
</script>
