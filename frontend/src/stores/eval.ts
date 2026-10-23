// 0804 系统评估 Pinia Store
import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as evalApi from '@/api/eval'
import type {
  StageDurationItem,
  StageBlockageItem,
  StageDwellItem,
  OperatorBlockageStats,
  AiAdoptionStatItem,
  LLMHealthItem,
  EfficiencyCompareItem,
  BusinessQuality,
  SusSurveyStats,
  NotificationReachStats,
  AdoptionImpactStats,
  KbFunnelStats,
  ActivityStats,
} from '@/types/api'

export const useEvalStore = defineStore('eval', () => {
  // ── 状态 ──
  const stageDuration = ref<StageDurationItem[]>([])
  const stageBlockage = ref<StageBlockageItem[]>([])
  // 0821 工单状态停留时长明细（分页/排序/搜索状态放 store，经 fetchTabData 统一刷新）
  const stageDwellItems = ref<StageDwellItem[]>([])
  const stageDwellPage = ref(1)
  const stageDwellKeyword = ref('')
  const stageDwellSort = ref('complaint_no_asc')
  // 0902 推进人筛选（选项列表由明细接口返回）
  const stageDwellOperator = ref('')
  const stageDwellOperators = ref<string[]>([])
  const stageDwellPagination = ref<{ page: number; limit: number; total: number }>({ page: 1, limit: 15, total: 0 })
  const stageDwellThresholds = ref<Record<string, number>>({})
  const STAGE_DWELL_LIMIT = 15
  // 0902 按人卡顿统计（推进人口径，可按阶段筛选）
  const operatorBlockage = ref<OperatorBlockageStats | null>(null)
  const operatorBlockageStage = ref('')
  const llmHealth = ref<LLMHealthItem[]>([])
  const efficiencyCompare = ref<EfficiencyCompareItem[]>([])
  const businessQuality = ref<BusinessQuality | null>(null)
  const susStats = ref<SusSurveyStats | null>(null)
  const susCanSubmit = ref<boolean>(true)
  // 0902 冷却天数改从 check 接口读取（后端 config SUS_SURVEY_COOLDOWN_DAYS），不再前端硬编码
  const susCooldownDays = ref<number | null>(null)
  const aiAdoptionStats = ref<AiAdoptionStatItem[]>([])
  const activityStats = ref<ActivityStats | null>(null)
  const emailDraftUsage = ref<any>(null)
  // 0805 Phase 3: 操作计时 + 阶段评价 + 排期准确度
  const timingStats = ref<any[]>([])
  const feedbackByStage = ref<any>(null)
  const scheduleAccuracy = ref<any>(null)
  // 0824 评估体系补强：通知触达 / AI采纳效果 / KB检索漏斗
  const notificationReach = ref<NotificationReachStats | null>(null)
  const adoptionImpact = ref<AdoptionImpactStats | null>(null)
  const kbFunnel = ref<KbFunnelStats | null>(null)

  const dateRange = ref('近3个月')
  const compareDimension = ref('priority')
  const activeTab = ref('stage')
  const loading = ref(false)
  const error = ref('')

  // ── 获取函数 ──
  async function fetchStageDuration() {
    const r = await evalApi.getStageDuration(dateRange.value)
    if (r.data?.success) stageDuration.value = r.data.data
  }

  async function fetchStageBlockage() {
    const r = await evalApi.getStageBlockage(dateRange.value)
    if (r.data?.success) stageBlockage.value = r.data.data
  }

  // 0902 按人卡顿统计
  async function fetchOperatorBlockage() {
    const r = await evalApi.getOperatorBlockage(dateRange.value, operatorBlockageStage.value)
    if (r.data?.success) operatorBlockage.value = r.data.data
  }

  function setOperatorBlockageStage(s: string) {
    operatorBlockageStage.value = s
    fetchOperatorBlockage()
  }

  // 0821 工单状态停留时长明细
  async function fetchStageDwellDetails() {
    const r = await evalApi.getStageDwellDetails({
      date_range: dateRange.value,
      page: stageDwellPage.value,
      limit: STAGE_DWELL_LIMIT,
      keyword: stageDwellKeyword.value,
      sort: stageDwellSort.value,
      operator: stageDwellOperator.value,
    })
    if (r.data?.success) {
      stageDwellItems.value = r.data.data.items || []
      stageDwellThresholds.value = r.data.data.thresholds || {}
      stageDwellOperators.value = r.data.data.operators || []
      stageDwellPagination.value = r.data.data.pagination
      const totalPages = Math.max(1, Math.ceil(r.data.data.pagination.total / STAGE_DWELL_LIMIT))
      if (stageDwellPage.value > totalPages) {
        stageDwellPage.value = 1
        await fetchStageDwellDetails()
      }
    }
  }

  function setStageDwellPage(p: number) {
    stageDwellPage.value = Math.max(1, p)
    fetchStageDwellDetails()
  }

  function setStageDwellSort(s: string) {
    stageDwellSort.value = s
    stageDwellPage.value = 1
    fetchStageDwellDetails()
  }

  function setStageDwellKeyword(k: string) {
    stageDwellKeyword.value = k
    stageDwellPage.value = 1
    fetchStageDwellDetails()
  }

  function setStageDwellOperator(o: string) {
    stageDwellOperator.value = o
    stageDwellPage.value = 1
    fetchStageDwellDetails()
  }

  async function fetchLLMHealth() {
    const r = await evalApi.getLLMHealth(dateRange.value)
    if (r.data?.success) llmHealth.value = r.data.data
  }

  async function fetchEfficiencyCompare() {
    const r = await evalApi.getEfficiencyCompare(dateRange.value, compareDimension.value)
    if (r.data?.success) efficiencyCompare.value = r.data.data
  }

  async function fetchBusinessQuality() {
    const r = await evalApi.getBusinessQuality(dateRange.value)
    if (r.data?.success) businessQuality.value = r.data.data
  }

  async function fetchSusStats() {
    const r = await evalApi.getSusStats()
    if (r.data?.success) susStats.value = r.data.data
  }

  async function checkSusCooldown() {
    const r = await evalApi.checkSusCooldown()
    if (r.data?.success) {
      susCanSubmit.value = r.data.data.can_submit
      susCooldownDays.value = r.data.data.cooldown_days ?? null
    }
  }

  async function fetchAiAdoptionStats() {
    const r = await evalApi.getAiAdoptionStats(dateRange.value)
    if (r.data?.success) aiAdoptionStats.value = r.data.data
  }

  async function fetchActivityStats() {
    // 0902 拉取全量（上限 500）：主表切片 Top10，弹窗「查看全部」复用同一份数据
    const r = await evalApi.getActivityStats(500)
    if (r.data?.success) activityStats.value = r.data.data
  }

  async function fetchEmailDraftUsage() {
    const r = await evalApi.getEmailDraftUsage(dateRange.value)
    if (r.data?.success) emailDraftUsage.value = r.data.data
  }

  // 0805 Phase 3
  async function fetchTimingStats() {
    const r = await evalApi.getTimingStats(dateRange.value)
    if (r.data?.success) timingStats.value = r.data.data
  }

  async function fetchFeedbackByStage() {
    const r = await evalApi.getFeedbackByStage(dateRange.value)
    if (r.data?.success) feedbackByStage.value = r.data.data
  }

  async function fetchScheduleAccuracy() {
    const r = await evalApi.getScheduleAccuracy(dateRange.value)
    if (r.data?.success) scheduleAccuracy.value = r.data.data
  }

  // 0824 评估体系补强
  async function fetchNotificationReach() {
    const r = await evalApi.getNotificationReach(dateRange.value)
    if (r.data?.success) notificationReach.value = r.data.data
  }

  async function fetchAdoptionImpact() {
    const r = await evalApi.getAdoptionImpact(dateRange.value)
    if (r.data?.success) adoptionImpact.value = r.data.data
  }

  async function fetchKbFunnel() {
    const r = await evalApi.getKbFunnel(dateRange.value)
    if (r.data?.success) kbFunnel.value = r.data.data
  }

  // ── 聚合加载 ──
  async function fetchTabData() {
    loading.value = true
    error.value = ''
    try {
      if (activeTab.value === 'stage') {
        await Promise.all([fetchStageDuration(), fetchStageBlockage(), fetchStageDwellDetails(), fetchOperatorBlockage()])
      } else if (activeTab.value === 'ai') {
        await Promise.all([fetchLLMHealth(), fetchEfficiencyCompare(), fetchAiAdoptionStats(), fetchEmailDraftUsage(), fetchFeedbackByStage(), fetchScheduleAccuracy(), fetchAdoptionImpact(), fetchKbFunnel()])
      } else if (activeTab.value === 'quality') {
        await Promise.all([fetchBusinessQuality(), fetchNotificationReach()])
      } else if (activeTab.value === 'sus') {
        await Promise.all([fetchSusStats(), checkSusCooldown()])
      } else if (activeTab.value === 'activity') {
        await Promise.all([fetchActivityStats(), fetchTimingStats()])
      }
    } catch (e: any) {
      error.value = e?.message || '加载失败'
      console.error('[evalStore] fetchTabData error:', e)
    } finally {
      loading.value = false
    }
  }

  function setActiveTab(tab: string) {
    activeTab.value = tab
    fetchTabData()
  }

  function setDateRange(range: string) {
    dateRange.value = range
    stageDwellPage.value = 1
    stageDwellOperator.value = ''
    fetchTabData()
  }

  function setCompareDimension(dim: string) {
    compareDimension.value = dim
    fetchEfficiencyCompare()
  }

  return {
    stageDuration,
    stageBlockage,
    operatorBlockage,
    operatorBlockageStage,
    stageDwellItems,
    stageDwellPage,
    stageDwellKeyword,
    stageDwellSort,
    stageDwellOperator,
    stageDwellOperators,
    stageDwellPagination,
    stageDwellThresholds,
    STAGE_DWELL_LIMIT,
    llmHealth,
    efficiencyCompare,
    businessQuality,
    susStats,
    susCanSubmit,
    susCooldownDays,
    aiAdoptionStats,
    activityStats,
    emailDraftUsage,
    timingStats,
    feedbackByStage,
    scheduleAccuracy,
    notificationReach,
    adoptionImpact,
    kbFunnel,
    dateRange,
    compareDimension,
    activeTab,
    loading,
    error,
    fetchStageDuration,
    fetchStageBlockage,
    fetchOperatorBlockage,
    setOperatorBlockageStage,
    fetchStageDwellDetails,
    setStageDwellPage,
    setStageDwellSort,
    setStageDwellKeyword,
    setStageDwellOperator,
    fetchLLMHealth,
    fetchEfficiencyCompare,
    fetchBusinessQuality,
    fetchSusStats,
    checkSusCooldown,
    fetchAiAdoptionStats,
    fetchActivityStats,
    fetchEmailDraftUsage,
    fetchTimingStats,
    fetchFeedbackByStage,
    fetchScheduleAccuracy,
    fetchNotificationReach,
    fetchAdoptionImpact,
    fetchKbFunnel,
    fetchTabData,
    setActiveTab,
    setDateRange,
    setCompareDimension,
  }
})
