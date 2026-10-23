// 0727 Phase 3 分析看板 Pinia Store
import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as analyticsApi from '@/api/analytics'
import type { AnalyticsKpi, TrendPoint, DistributionItem, KbQualityStats, KBEntry } from '@/types/api'

type CaseFeedbackSourceStats = {
  source_type: string
  total: number
  referenced_count: number
  avg_match: number | null
}

type CaseFeedbackKbStats = {
  kb_id: number
  kb_title: string | null
  total_feedback: number
  reference_count: number
  avg_match_accuracy: number | null
}

type CaseFeedbackStats = {
  total: number
  referenced_count: number
  reference_pct: number
  avg_match_accuracy: number
  by_source: CaseFeedbackSourceStats[]
  top_kb: CaseFeedbackKbStats[]
}

export const useAnalyticsStore = defineStore('analytics', () => {
  const kpi = ref<AnalyticsKpi | null>(null)
  const trend = ref<TrendPoint[]>([])
  const distribution = ref<DistributionItem[]>([])
  const kbQuality = ref<KbQualityStats | null>(null)
  const kbTopValuable = ref<KBEntry[]>([])
  const kbNeedsReview = ref<KBEntry[]>([])
  const kbStale = ref<KBEntry[]>([])
  const caseFeedbackStats = ref<CaseFeedbackStats | null>(null)  // 0805 Phase 4: 案例检索评价统计

  const dateRange = ref('近3个月')
  const distributionDimension = ref('category')
  const trendGranularity = ref('monthly')
  const loading = ref(false)

  async function fetchKpi() {
    const r = await analyticsApi.getKpiOverview(dateRange.value)
    if (r.data?.success) kpi.value = r.data.data
  }

  async function fetchTrend() {
    const r = await analyticsApi.getTrend(dateRange.value, trendGranularity.value)
    if (r.data?.success) trend.value = r.data.data
  }

  async function fetchDistribution() {
    const r = await analyticsApi.getDistribution(dateRange.value, distributionDimension.value)
    if (r.data?.success) distribution.value = r.data.data
  }

  async function fetchKbQuality() {
    const r = await analyticsApi.getKbQualityDashboard()
    if (r.data?.success) {
      kbQuality.value = r.data.data?.stats
      kbTopValuable.value = r.data.data?.top_valuable || []
      kbNeedsReview.value = r.data.data?.needs_review || []
      kbStale.value = r.data.data?.stale || []
    }
  }

  async function fetchCaseFeedbackStats() {
    const r = await import('@/api/eval').then(m => m.getCaseFeedbackStats(dateRange.value))
    if (r.data?.success) caseFeedbackStats.value = r.data.data
  }

  async function fetchAll(range?: string) {
    if (range) dateRange.value = range
    loading.value = true
    try {
      await Promise.all([
        fetchKpi(), fetchTrend(), fetchDistribution(),
        fetchKbQuality(), fetchCaseFeedbackStats(),
      ])
    } catch (e: any) {
      console.error('fetchAll analytics error:', e)
    } finally { loading.value = false }
  }

  return {
    kpi, trend, distribution,
    kbQuality, kbTopValuable, kbNeedsReview, kbStale, caseFeedbackStats,
    dateRange, distributionDimension, trendGranularity, loading,
    fetchAll, fetchKpi, fetchTrend, fetchDistribution,
    fetchKbQuality, fetchCaseFeedbackStats,
  }
})
