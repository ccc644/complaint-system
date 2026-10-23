<!-- 0804 系统评估 — 管理员专用评估看板
     阶段效率 + AI效能 + 业务质量 + SUS问卷 四大维度 -->
<template>
  <AppLayout>
    <div class="p-6 space-y-6">
      <!-- 标题栏 -->
      <div class="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 class="text-2xl font-bold">📊 系统评估</h1>
          <p class="text-sm text-gray-500 mt-1">系统价值量化评估 · 全部基于现有工单数据聚合</p>
        </div>
        <select v-model="store.dateRange" @change="store.setDateRange(($event.target as HTMLSelectElement).value)"
          class="px-3 py-1.5 border border-gray-300 rounded text-sm bg-white">
          <option v-for="r in DATE_RANGES" :key="r" :value="r">{{ r }}</option>
        </select>
      </div>

      <!-- Tab 切换 -->
      <div class="flex gap-1 border-b border-gray-200">
        <button v-for="tab in TABS" :key="tab.key" @click="store.setActiveTab(tab.key)"
          :class="['px-4 py-2.5 text-sm font-medium transition -mb-px',
            store.activeTab === tab.key
              ? 'text-primary border-b-2 border-primary'
              : 'text-gray-500 hover:text-gray-700 border-b-2 border-transparent']">
          {{ tab.icon }} {{ tab.label }}
        </button>
      </div>

      <!-- 加载状态 -->
      <div v-if="store.loading && !hasData" class="text-center text-gray-400 py-16">加载中...</div>
      <div v-else-if="store.error" class="text-center text-red-500 py-8 bg-red-50 rounded-lg border border-red-200">
        {{ store.error }}
      </div>

      <template v-else>
        <!-- ═══════════ Tab 1：阶段效率 ═══════════ -->
        <div v-if="store.activeTab === 'stage'" class="space-y-5">
          <!-- KPI 卡片 -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard icon="📋" label="分析阶段数" :value="stageSummary.stageCount" color="blue" />
            <KpiCard icon="⏱️" label="最长平均耗时" :value="stageSummary.maxAvgHours" color="yellow" format="hours" />
            <KpiCard icon="⚠️" label="卡顿阶段数" :value="stageSummary.blockageCount" color="red" />
            <KpiCard icon="📊" label="总阶段跨度" :value="stageSummary.totalSamples" color="gray" />
          </div>

          <!-- 阶段耗时柱状图 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">⏱ 阶段平均停留时长（小时）</h3>
            <VChart v-if="stageDurationChartData.length" :option="stageDurationOption" :style="{ height: '360px' }" autoresize />
            <div v-else class="text-gray-400 text-sm py-8 text-center">暂无阶段耗时数据</div>
          </div>

          <!-- 卡顿率表格 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">⚠️ 阶段卡顿率</h3>
            <div v-if="!store.stageBlockage.length" class="text-gray-400 text-sm py-4 text-center">暂无卡顿数据</div>
            <table v-else class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-gray-500">
                  <th class="py-2 pr-4">阶段</th>
                  <th class="py-2 pr-4 text-right">总工单</th>
                  <th class="py-2 pr-4 text-right">卡顿工单</th>
                  <th class="py-2 pr-4 text-right">卡顿率</th>
                  <th class="py-2 pr-4 text-right">阈值 (h)</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="b in store.stageBlockage" :key="b.stage" class="border-b last:border-0 hover:bg-gray-50">
                  <td class="py-2 pr-4 font-medium">{{ b.stage }}</td>
                  <td class="py-2 pr-4 text-right tnum">{{ b.total }}</td>
                  <td class="py-2 pr-4 text-right tnum" :class="b.blocked > 0 ? 'text-red-600' : ''">{{ b.blocked }}</td>
                  <td class="py-2 pr-4 text-right tnum font-medium" :class="b.blockage_rate_pct > 30 ? 'text-red-600' : b.blockage_rate_pct > 10 ? 'text-yellow-600' : 'text-green-600'">
                    {{ b.blockage_rate_pct }}%
                  </td>
                  <td class="py-2 pr-4 text-right tnum text-gray-400">{{ b.threshold_hours }}h</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 0902 按人统计：卡顿率/卡顿段数/平均停留/处理段总数（推进人口径，可按阶段筛选+排序） -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <div class="flex items-center justify-between flex-wrap gap-3 mb-3">
              <h3 class="text-sm font-semibold">👤 按人统计（推进人口径）</h3>
              <div class="flex items-center gap-2 flex-wrap">
                <select v-model="store.operatorBlockageStage" @change="store.setOperatorBlockageStage(store.operatorBlockageStage)"
                  class="px-2 py-1.5 border border-gray-300 rounded text-xs bg-white">
                  <option value="">全部阶段</option>
                  <option v-for="col in STAGE_DWELL_COLUMNS" :key="col" :value="col">{{ col }}</option>
                </select>
                <select v-model="operatorBlockageSort" class="px-2 py-1.5 border border-gray-300 rounded text-xs bg-white">
                  <option value="blockage_desc">卡顿率 ↓</option>
                  <option value="blocked_desc">卡顿段数 ↓</option>
                  <option value="avg_dwell_desc">平均停留 ↓</option>
                  <option value="total_desc">处理段总数 ↓</option>
                  <option value="name_asc">人员 ↑</option>
                </select>
              </div>
            </div>
            <div v-if="!sortedOperatorBlockage.length" class="text-gray-400 text-sm py-4 text-center">暂无数据</div>
            <table v-else class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-gray-500">
                  <th class="py-2 pr-4">人员</th>
                  <th class="py-2 pr-4 text-right">处理段总数</th>
                  <th class="py-2 pr-4 text-right">卡顿段数</th>
                  <th class="py-2 pr-4 text-right">卡顿率</th>
                  <th class="py-2 pr-4 text-right">平均停留 (h)</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="o in paginatedOperatorBlockage" :key="o.operator" class="border-b last:border-0 hover:bg-gray-50">
                  <td class="py-2 pr-4">
                    <div class="font-medium">{{ o.operator }}</div>
                    <div class="text-xs text-gray-400">{{ [o.role, o.position].filter(Boolean).join(' / ') || '—' }}</div>
                  </td>
                  <td class="py-2 pr-4 text-right tnum">{{ o.total_segments }}</td>
                  <td class="py-2 pr-4 text-right tnum" :class="o.blocked_segments > 0 ? 'text-red-600' : ''">{{ o.blocked_segments }}</td>
                  <td class="py-2 pr-4 text-right tnum font-medium" :class="o.blockage_rate_pct > 30 ? 'text-red-600' : o.blockage_rate_pct > 10 ? 'text-yellow-600' : 'text-green-600'">
                    {{ o.blockage_rate_pct }}%
                  </td>
                  <td class="py-2 pr-4 text-right tnum">{{ o.avg_dwell_hours }}</td>
                </tr>
              </tbody>
            </table>
            <div v-if="operatorBlockageTotalPages > 1" class="flex items-center justify-end gap-2 text-sm text-gray-500 mt-3">
              <button @click="operatorBlockagePage = Math.max(1, operatorBlockagePage - 1)" :disabled="operatorBlockagePage <= 1"
                class="px-3 py-1 border border-gray-300 rounded text-xs disabled:opacity-40 hover:bg-gray-50 transition">上一页</button>
              <span class="tnum">{{ operatorBlockagePage }} / {{ operatorBlockageTotalPages }}</span>
              <button @click="operatorBlockagePage = Math.min(operatorBlockageTotalPages, operatorBlockagePage + 1)" :disabled="operatorBlockagePage >= operatorBlockageTotalPages"
                class="px-3 py-1 border border-gray-300 rounded text-xs disabled:opacity-40 hover:bg-gray-50 transition">下一页</button>
            </div>
          </div>

          <!-- 0821 工单状态停留时长明细表（每页 15 条；回退重进阶段多段以 | 并排展示；超阈值红色提示） -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <div class="flex items-center justify-between flex-wrap gap-3 mb-3">
              <h3 class="text-sm font-semibold">📋 工单状态停留时长明细</h3>
              <div class="flex items-center gap-2 flex-wrap">
                <select v-model="store.stageDwellOperator" @change="store.setStageDwellOperator(store.stageDwellOperator)"
                  class="px-2 py-1.5 border border-gray-300 rounded text-xs bg-white">
                  <option value="">全部推进人</option>
                  <option v-for="op in store.stageDwellOperators" :key="op" :value="op">{{ op }}</option>
                </select>
                <select v-model="store.stageDwellSort" @change="store.setStageDwellSort(store.stageDwellSort)"
                  class="px-2 py-1.5 border border-gray-300 rounded text-xs bg-white">
                  <option value="complaint_no_asc">工单号 ↑</option>
                  <option value="complaint_no_desc">工单号 ↓</option>
                  <option v-for="col in STAGE_DWELL_COLUMNS" :key="col" :value="`stage:${col}_desc`">{{ col }}时长 ↓</option>
                </select>
                <input v-model="store.stageDwellKeyword" @keyup.enter="store.setStageDwellKeyword(store.stageDwellKeyword)"
                  placeholder="搜索工单号 / 客户名" class="px-2 py-1.5 border border-gray-300 rounded text-xs w-44" />
                <button @click="store.setStageDwellKeyword(store.stageDwellKeyword)"
                  class="px-2 py-1.5 border border-gray-300 rounded text-xs hover:bg-gray-50 transition">搜索</button>
              </div>
            </div>
            <div v-if="!store.stageDwellItems.length" class="text-gray-400 text-sm py-4 text-center">暂无停留时长数据</div>
            <template v-else>
              <div class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead>
                    <tr class="border-b text-left text-gray-500">
                      <th class="py-2 pr-4 whitespace-nowrap">工单号</th>
                      <th class="py-2 pr-4 whitespace-nowrap">客户</th>
                      <th v-for="col in STAGE_DWELL_COLUMNS" :key="col" class="py-2 pr-4 whitespace-nowrap">
                        {{ col }}{{ store.stageDwellThresholds[col] ? `（${store.stageDwellThresholds[col]}h）` : '' }}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="item in store.stageDwellItems" :key="item.complaint_no" class="border-b last:border-0 hover:bg-gray-50 align-top">
                      <td class="py-2 pr-4 font-medium mono text-xs whitespace-nowrap">{{ item.complaint_no }}</td>
                      <td class="py-2 pr-4 whitespace-nowrap">{{ item.customer_name || '—' }}</td>
                      <td v-for="col in STAGE_DWELL_COLUMNS" :key="col" class="py-2 pr-4">
                        <template v-if="item.stages[col]?.segments?.length">
                          <!-- 0902 多段（打回重进）竖排堆叠：每段一行「时长 推进人」，列宽稳定不横向撑爆 -->
                          <div v-for="seg in item.stages[col].segments" :key="seg.hours + (seg.advance?.name || '')" class="whitespace-nowrap">
                            <span class="tnum" :class="seg.blocked ? 'text-red-600 font-medium' : 'text-gray-700'">{{ seg.hours }}h</span>
                            <span v-if="seg.advance?.name" class="text-xs text-gray-500 ml-1">{{ seg.advance.name }}</span>
                          </div>
                        </template>
                        <span v-else class="text-gray-300">—</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div v-if="store.stageDwellPagination.total > 0" class="flex items-center justify-between text-sm text-gray-500 mt-3 flex-wrap gap-2">
                <span>共 {{ store.stageDwellPagination.total }} 条</span>
                <div class="flex items-center gap-2">
                  <button @click="store.setStageDwellPage(store.stageDwellPage - 1)" :disabled="store.stageDwellPage <= 1"
                    class="px-3 py-1 border border-gray-300 rounded text-xs disabled:opacity-40 hover:bg-gray-50 transition">上一页</button>
                  <span class="tnum">{{ store.stageDwellPage }} / {{ Math.max(1, Math.ceil(store.stageDwellPagination.total / store.stageDwellPagination.limit)) }}</span>
                  <button @click="store.setStageDwellPage(store.stageDwellPage + 1)"
                    :disabled="store.stageDwellPage >= Math.ceil(store.stageDwellPagination.total / store.stageDwellPagination.limit)"
                    class="px-3 py-1 border border-gray-300 rounded text-xs disabled:opacity-40 hover:bg-gray-50 transition">下一页</button>
                  <input v-model.number="dwellJumpPage" type="number" min="1"
                    class="w-14 px-2 py-1 border border-gray-300 rounded text-xs tnum" />
                  <button @click="onDwellJumpPage" class="px-2 py-1 border border-gray-300 rounded text-xs hover:bg-gray-50 transition">跳转</button>
                </div>
              </div>
            </template>
          </div>

          <!-- 效率对比 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-sm font-semibold">🔍 效率对比分析</h3>
              <select v-model="store.compareDimension" @change="store.setCompareDimension(($event.target as HTMLSelectElement).value)"
                class="px-3 py-1.5 border border-gray-300 rounded text-sm bg-white">
                <option value="priority">按优先级</option>
                <option value="category">按故障分类</option>
                <option value="engineer">按承接人</option>
              </select>
            </div>
            <VChart v-if="efficiencyCompareData.length" :option="efficiencyCompareOption" :style="{ height: '360px' }" autoresize />
            <div v-else class="text-gray-400 text-sm py-8 text-center">暂无效率对比数据</div>
          </div>
        </div>

        <!-- ═══════════ Tab 2：AI 效能 ═══════════ -->
        <div v-if="store.activeTab === 'ai'" class="space-y-5">
          <!-- AI KPI 卡片 -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard icon="🤖" label="AI 功能数" :value="aiSummary.functionCount" color="blue" />
            <KpiCard icon="📞" label="总调用次数" :value="aiSummary.totalCalls" color="blue" />
            <KpiCard icon="✅" label="总成功率" :value="aiSummary.overallSuccessRate" color="green" format="percent" />
            <KpiCard icon="⚡" label="平均延迟" :value="aiSummary.avgLatency" color="yellow" />
          </div>

          <!-- AI 功能详情表格 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">🤖 AI 功能调用详情</h3>
            <div v-if="!store.llmHealth.length" class="text-gray-400 text-sm py-8 text-center">暂无 AI 调用记录（系统尚无 LLM 调用日志数据）</div>
            <div v-else class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-2 pr-4">功能名</th>
                    <th class="py-2 pr-4 text-right">调用次数</th>
                    <th class="py-2 pr-4 text-right">成功率</th>
                    <th class="py-2 pr-4 text-right">平均延迟</th>
                    <th class="py-2 pr-4 text-right">P50（中位数）</th>
                    <th class="py-2 pr-4 text-right">P95（95分位）</th>
                    <th class="py-2 pr-4 text-right">P99（99分位）</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in store.llmHealth" :key="item.function_name" class="border-b last:border-0 hover:bg-gray-50">
                    <td class="py-2 pr-4 font-medium text-xs">{{ aiFunctionDisplay(item.function_name) }}</td>
                    <td class="py-2 pr-4 text-right tnum">{{ item.total_calls }}</td>
                    <td class="py-2 pr-4 text-right tnum" :class="item.success_rate_pct >= 95 ? 'text-green-600' : item.success_rate_pct >= 80 ? 'text-yellow-600' : 'text-red-600'">
                      {{ item.success_rate_pct }}%
                    </td>
                    <td class="py-2 pr-4 text-right tnum">{{ item.avg_latency_ms }}ms</td>
                    <td class="py-2 pr-4 text-right tnum text-gray-400">{{ item.p50_latency_ms }}ms</td>
                    <td class="py-2 pr-4 text-right tnum text-gray-400">{{ item.p95_latency_ms }}ms</td>
                    <td class="py-2 pr-4 text-right tnum text-gray-400">{{ item.p99_latency_ms }}ms</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- AI 采纳率 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">🎯 AI 建议采纳率</h3>
            <div v-if="!store.aiAdoptionStats.length" class="text-gray-400 text-sm py-8 text-center">暂无采纳追踪数据（需使用 AI 智能填表并提交工单后产生数据）</div>
            <div v-else class="space-y-3">
              <div class="grid grid-cols-3 gap-3">
                <KpiCard icon="🎯" label="总建议数" :value="aiAdoptionSummary.total" color="blue" />
                <KpiCard icon="✅" label="采纳数" :value="aiAdoptionSummary.adopted" color="green" />
                <KpiCard icon="📊" label="采纳率" :value="aiAdoptionSummary.rate" color="yellow" format="percent" />
              </div>
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-2 pr-4">AI 功能</th>
                    <th class="py-2 pr-4 text-right">总建议</th>
                    <th class="py-2 pr-4 text-right">采纳</th>
                    <th class="py-2 pr-4 text-right">采纳率</th>
                    <th class="py-2 pr-4 text-right">平均匹配度</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="a in store.aiAdoptionStats" :key="a.ai_function" class="border-b last:border-0 hover:bg-gray-50">
                    <td class="py-2 pr-4 font-medium text-xs">{{ aiFunctionDisplay(a.ai_function) }}</td>
                    <td class="py-2 pr-4 text-right tnum">{{ a.total }}</td>
                    <td class="py-2 pr-4 text-right tnum text-green-600">{{ a.adopted_count }}</td>
                    <td class="py-2 pr-4 text-right tnum font-medium" :class="a.adoption_rate_pct >= 70 ? 'text-green-600' : a.adoption_rate_pct >= 40 ? 'text-yellow-600' : 'text-red-600'">{{ a.adoption_rate_pct }}%</td>
                    <td class="py-2 pr-4 text-right tnum text-gray-600">{{ a.avg_match_pct != null ? `${a.avg_match_pct}%` : '—' }}</td>
                  </tr>
                </tbody>
              </table>
              <p class="text-xs text-gray-400">匹配度 = AI 建议与实际提交文本的 bigram 相似度（%），≥60% 记为采纳；仅智能填表/自排查/分工评估/邮件草稿等文本类功能统计。</p>
            </div>
          </div>

          <!-- AI 邮件草稿使用率 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">📧 AI 邮件草稿使用率</h3>
            <div v-if="!store.emailDraftUsage" class="text-gray-400 text-sm py-8 text-center">暂无数据</div>
            <div v-else class="grid grid-cols-2 md:grid-cols-4 gap-3">
              <KpiCard icon="📧" label="有草稿工单" :value="store.emailDraftUsage.draft_tickets" color="blue" />
              <KpiCard icon="📊" label="草稿使用率" :value="store.emailDraftUsage.draft_usage_rate_pct" color="green" format="percent" />
              <KpiCard icon="🤖" label="AI 生成调用" :value="store.emailDraftUsage.llm_draft_calls" color="yellow" />
              <KpiCard icon="✅" label="AI 生成成功率" :value="store.emailDraftUsage.llm_draft_success_rate_pct" color="green" format="percent" />
            </div>
          </div>

          <!-- 0805 Phase 3: AI 各阶段用户评价 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">⭐ AI 各阶段用户评价</h3>
            <div v-if="!store.feedbackByStage || !store.feedbackByStage.by_stage?.length" class="text-gray-400 text-sm py-8 text-center">
              暂无用户评价数据（需在工单各阶段操作后提交 AI 评价）
            </div>
            <template v-else>
              <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
                <KpiCard icon="📝" label="总评价数" :value="store.feedbackByStage.overall?.total ?? 0" color="blue" />
                <KpiCard icon="📮" label="工单反馈率" :value="store.feedbackByStage.feedback_rate_pct !== null && store.feedbackByStage.feedback_rate_pct !== undefined ? store.feedbackByStage.feedback_rate_pct + '%' : '—'" color="blue" text />
                <KpiCard icon="⭐" label="平均星数" :value="store.feedbackByStage.overall?.avg_accuracy ?? 0" color="yellow" />
                <KpiCard icon="✅" label="采纳数" :value="store.feedbackByStage.overall?.adopted ?? 0" color="green" />
                <KpiCard icon="❌" label="未采纳数" :value="store.feedbackByStage.overall?.not_adopted ?? 0" color="red" />
              </div>
              <p v-if="small(store.feedbackByStage.overall?.total)" class="text-xs text-amber-600 mb-3">⚠️ 评价样本不足 {{ MIN_SAMPLE }} 条，均分与采纳率仅供参考；工单反馈率 = 有评价的工单数（{{ store.feedbackByStage.evaluated_count ?? 0 }}）/ 同期工单数（{{ store.feedbackByStage.complaint_count ?? 0 }}）。</p>
              <!-- 各阶段星数均分柱状图 -->
              <div class="mb-4">
                <h4 class="text-xs font-medium text-gray-600 mb-2">各阶段 AI 准确度均分（1-5 星）</h4>
                <VChart v-if="feedbackStageChartData.length" :option="feedbackStageOption" :style="{ height: '250px' }" autoresize />
              </div>
              <!-- 各阶段省时评价分布 -->
              <div class="mb-4">
                <h4 class="text-xs font-medium text-gray-600 mb-2">各阶段 AI 省时效果分布</h4>
                <VChart v-if="timeSavedChartData.series.length" :option="timeSavedOption" :style="{ height: '280px' }" autoresize />
              </div>
              <!-- 各阶段明细表 -->
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-2 pr-4">阶段</th>
                    <th class="py-2 pr-4 text-right">评价数</th>
                    <th class="py-2 pr-4 text-right">平均星数</th>
                    <th class="py-2 pr-4 text-right">采纳</th>
                    <th class="py-2 pr-4 text-right">未采纳</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="s in store.feedbackByStage.by_stage" :key="s.feedback_type" class="border-b last:border-0 hover:bg-gray-50">
                    <td class="py-2 pr-4 font-medium">{{ stageLabelMap[s.feedback_type] || s.feedback_type }}</td>
                    <td class="py-2 pr-4 text-right tnum">{{ s.total }}</td>
                    <td class="py-2 pr-4 text-right tnum" :class="(s.avg_accuracy || 0) >= 4 ? 'text-green-600' : (s.avg_accuracy || 0) >= 3 ? 'text-yellow-600' : 'text-red-600'">{{ s.avg_accuracy?.toFixed(1) || '—' }}<span v-if="small(s.total)" class="text-amber-500 text-xs ml-1" title="样本量不足30，仅供参考">⚠️</span></td>
                    <td class="py-2 pr-4 text-right tnum text-green-600">{{ s.adopted }}</td>
                    <td class="py-2 pr-4 text-right tnum text-red-500">{{ s.not_adopted }}</td>
                  </tr>
                </tbody>
              </table>
            </template>
          </div>

          <!-- 0805 Phase 3: AI 排期准确度 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">🎯 AI 排期准确度</h3>
            <div v-if="!store.scheduleAccuracy || !store.scheduleAccuracy.comparable_count" class="text-gray-400 text-sm py-8 text-center">
              暂无排期准确度数据（需在指派承接人时使用 AI 排期建议，且对应工单已关闭后产生数据）
            </div>
            <template v-else>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <KpiCard icon="🧠" label="AI 建议次数" :value="store.scheduleAccuracy.total_suggestions" color="blue" />
                <KpiCard icon="📊" label="可比较工单" :value="store.scheduleAccuracy.comparable_count" color="green" />
                <KpiCard icon="📐" label="平均偏差" :value="store.scheduleAccuracy.avg_deviation_hours" color="yellow" format="hours" />
                <KpiCard icon="⚠️" label="P95（95分位）偏差" :value="store.scheduleAccuracy.p95_deviation_hours" color="red" format="hours" />
              </div>
              <!-- 偏差分布柱状图 -->
              <VChart v-if="scheduleDevChartData.length" :option="scheduleDevOption" :style="{ height: '250px' }" autoresize />
            </template>
          </div>

          <!-- 0824 AI 采纳效果对比（闭环：采纳组 vs 未采纳组） -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-1">🤝 AI 采纳效果对比</h3>
            <p class="text-xs text-gray-400 mb-3">采纳过 AI 建议的工单 vs 从未采纳的工单：平均处理时长（仅已关闭）与一次解决率。样本差异大时结论仅供参考。</p>
            <div v-if="!store.adoptionImpact || (!store.adoptionImpact.adopted && !store.adoptionImpact.not_adopted)"
              class="text-gray-400 text-sm py-8 text-center">暂无数据（需在工单处理中记录 AI 建议采纳结果）</div>
            <table v-else class="w-full text-sm max-w-2xl">
              <thead>
                <tr class="border-b text-left text-gray-500">
                  <th class="py-2 pr-4">指标</th>
                  <th class="py-2 pr-4 text-right">采纳组</th>
                  <th class="py-2 pr-4 text-right">未采纳组</th>
                </tr>
              </thead>
              <tbody>
                <tr class="border-b last:border-0">
                  <td class="py-2 pr-4 font-medium">工单数</td>
                  <td class="py-2 pr-4 text-right tnum">{{ store.adoptionImpact.adopted?.complaint_count ?? '—' }}<span v-if="small(store.adoptionImpact.adopted?.complaint_count)" class="text-amber-500 text-xs ml-1">⚠️</span></td>
                  <td class="py-2 pr-4 text-right tnum">{{ store.adoptionImpact.not_adopted?.complaint_count ?? '—' }}<span v-if="small(store.adoptionImpact.not_adopted?.complaint_count)" class="text-amber-500 text-xs ml-1">⚠️</span></td>
                </tr>
                <tr class="border-b last:border-0">
                  <td class="py-2 pr-4 font-medium">平均处理时长（h，仅已关闭）</td>
                  <td class="py-2 pr-4 text-right tnum">{{ store.adoptionImpact.adopted?.avg_hours_closed ?? '—' }}</td>
                  <td class="py-2 pr-4 text-right tnum">{{ store.adoptionImpact.not_adopted?.avg_hours_closed ?? '—' }}</td>
                </tr>
                <tr class="border-b last:border-0">
                  <td class="py-2 pr-4 font-medium">一次解决率</td>
                  <td class="py-2 pr-4 text-right tnum text-green-600">{{ store.adoptionImpact.adopted ? store.adoptionImpact.adopted.first_time_fix_pct + '%' : '—' }}</td>
                  <td class="py-2 pr-4 text-right tnum">{{ store.adoptionImpact.not_adopted ? store.adoptionImpact.not_adopted.first_time_fix_pct + '%' : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 0824 KB 检索漏斗 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-1">🔍 KB 检索漏斗</h3>
            <p class="text-xs text-gray-400 mb-3">检索 → 相似案例查看 → 评价 → 引用。检索埋点自上线（0824）起累计，此前无数据。</p>
            <div v-if="!store.kbFunnel" class="text-gray-400 text-sm py-8 text-center">暂无数据</div>
            <template v-else>
              <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-3">
                <KpiCard icon="🔎" label="KB 搜索次数" :value="store.kbFunnel.kb_search_count" color="blue" />
                <KpiCard icon="📄" label="相似案例查看" :value="store.kbFunnel.similar_view_count" color="blue" />
                <KpiCard icon="🎯" label="案例评价数" :value="store.kbFunnel.case_evaluated" color="yellow" />
                <KpiCard icon="✅" label="引用率" :value="store.kbFunnel.reference_pct" color="green" format="percent" />
                <KpiCard icon="👍" label="KB 有用率" :value="store.kbFunnel.kb_useful_rate_pct !== null ? store.kbFunnel.kb_useful_rate_pct + '%' : '—'" color="green" text />
              </div>
              <p class="text-xs text-gray-400">📊 漏斗解读：搜索多但评价少 → 引导工程师在案例卡片提交评价；评价中引用占比低 → 检索命中率待优化。</p>
            </template>
          </div>
        </div>

        <!-- ═══════════ Tab 3：业务质量 ═══════════ -->
        <div v-if="store.activeTab === 'quality'" class="space-y-5">
          <!-- 质量 KPI -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard icon="🔧" label="一次解决率" :value="store.businessQuality?.first_time_fix_rate ?? 0" color="green" format="percent" />
            <KpiCard icon="🔄" label="返修率" :value="store.businessQuality?.overall_rework_rate ?? 0" color="yellow" format="percent" />
            <KpiCard icon="🚫" label="拒收率" :value="store.businessQuality?.overall_rejection_rate ?? 0" color="red" format="percent" />
            <KpiCard icon="⭐" label="平均满意度（满分5）" :value="Number((store.businessQuality?.avg_satisfaction ?? 0).toFixed(1))" color="yellow" />
          </div>

          <!-- 返工率按分类 -->
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div class="bg-white rounded-lg border border-gray-200 p-4">
              <h3 class="text-sm font-semibold mb-3">🔄 返修率按分类</h3>
              <VChart v-if="reworkChartData.length" :option="reworkOption" :style="{ height: '300px' }" autoresize />
              <div v-else class="text-gray-400 text-sm py-8 text-center">暂无数据</div>
            </div>
            <div class="bg-white rounded-lg border border-gray-200 p-4">
              <h3 class="text-sm font-semibold mb-3">🚫 拒收率按分类</h3>
              <VChart v-if="rejectionChartData.length" :option="rejectionOption" :style="{ height: '300px' }" autoresize />
              <div v-else class="text-gray-400 text-sm py-8 text-center">暂无数据</div>
            </div>
          </div>

          <!-- 满意度分布 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">⭐ 客户满意度分布</h3>
            <VChart v-if="satChartData.length" :option="satisfactionOption" :style="{ height: '280px' }" autoresize />
            <div v-else class="text-gray-400 text-sm py-8 text-center">暂无已关闭工单的满意度数据</div>
          </div>

          <!-- 0824 通知触达：站内未读 + 钉钉推送 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-1">🔔 通知触达</h3>
            <p class="text-xs text-gray-400 mb-3">站内「待处理」类通知的未读与长期未读（>7 天）；钉钉推送成功率（dry_run/无收件人不计入）。</p>
            <div v-if="!store.notificationReach" class="text-gray-400 text-sm py-8 text-center">暂无数据</div>
            <template v-else>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <KpiCard icon="📨" label="待处理通知总数" :value="store.notificationReach.station.total" color="blue" />
                <KpiCard icon="📭" label="未读率" :value="store.notificationReach.station.unread_rate_pct" color="yellow" format="percent" />
                <KpiCard icon="⏰" label="长期未读(>7天)" :value="store.notificationReach.station.long_unread" color="red" />
                <KpiCard icon="📱" label="钉钉推送成功率" :value="store.notificationReach.dingtalk.success_rate_pct !== null ? store.notificationReach.dingtalk.success_rate_pct + '%' : '未启用'" color="green" text />
              </div>
              <table v-if="store.notificationReach.station.by_role?.length" class="w-full text-sm max-w-2xl">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-2 pr-4">目标角色</th>
                    <th class="py-2 pr-4 text-right">待处理通知</th>
                    <th class="py-2 pr-4 text-right">未读</th>
                    <th class="py-2 pr-4 text-right">长期未读</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in store.notificationReach.station.by_role" :key="r.target_role" class="border-b last:border-0 hover:bg-gray-50">
                    <td class="py-2 pr-4 font-medium">{{ r.target_role || '—' }}</td>
                    <td class="py-2 pr-4 text-right tnum">{{ r.total }}</td>
                    <td class="py-2 pr-4 text-right tnum" :class="r.unread > 0 ? 'text-yellow-600' : 'text-gray-400'">{{ r.unread }}</td>
                    <td class="py-2 pr-4 text-right tnum" :class="r.long_unread > 0 ? 'text-red-500' : 'text-gray-400'">{{ r.long_unread }}</td>
                  </tr>
                </tbody>
              </table>
            </template>
          </div>
        </div>

        <!-- ═══════════ Tab 4：SUS 问卷 ═══════════ -->
        <div v-if="store.activeTab === 'sus'" class="space-y-5">
          <!-- SUS 统计 KPI -->
          <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
            <KpiCard icon="📋" label="回收问卷数" :value="store.susStats?.total_responses ?? 0" color="blue" />
            <KpiCard icon="📊" label="平均 SUS 分" :value="store.susStats?.avg_score ?? 0" color="green" />
            <KpiCard icon="✅" label="及格率 (≥68)" :value="susPassRate" color="yellow" format="percent" />
            <KpiCard icon="📨" label="问卷反馈率" :value="store.susStats?.feedback_rate_pct !== null && store.susStats?.feedback_rate_pct !== undefined ? store.susStats.feedback_rate_pct + '%' : '—'" color="blue" text />
            <KpiCard icon="📝" label="可提交问卷" :value="store.susCanSubmit ? '是' : '冷却期'" color="blue" text />
          </div>
          <!-- 0824 样本量预警 -->
          <p v-if="small(store.susStats?.total_responses)" class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            ⚠️ 样本量不足（{{ store.susStats?.total_responses }} 份 < {{ MIN_SAMPLE }}）：SUS 分数波动大，结论仅供参考。反馈率为下限口径（仅统计明确提交/关闭弹窗者）。
          </p>

          <!-- SUS 分数分布表 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">📈 SUS 分数分布</h3>
            <div v-if="!store.susStats || !store.susStats.score_distribution?.length" class="text-gray-400 text-sm py-8 text-center">暂无 SUS 问卷数据</div>
            <table v-else class="w-full text-sm max-w-md">
              <thead>
                <tr class="border-b text-left text-gray-500">
                  <th class="py-2 pr-4">等级</th>
                  <th class="py-2 pr-4 text-right">数量</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="d in store.susStats.score_distribution" :key="d.score_range" class="border-b last:border-0">
                  <td class="py-2 pr-4 font-medium">{{ d.score_range }}</td>
                  <td class="py-2 pr-4 text-right tnum">{{ d.cnt }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- SUS 按角色分布 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">👥 按角色 SUS 平均分</h3>
            <div v-if="!store.susStats || !store.susStats.by_role?.length" class="text-gray-400 text-sm py-4 text-center">暂无数据</div>
            <table v-else class="w-full text-sm max-w-md">
              <thead>
                <tr class="border-b text-left text-gray-500">
                  <th class="py-2 pr-4">角色</th>
                  <th class="py-2 pr-4 text-right">提交数</th>
                  <th class="py-2 pr-4 text-right">平均分</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in store.susStats.by_role" :key="r.role" class="border-b last:border-0">
                  <td class="py-2 pr-4 font-medium">{{ r.role }}</td>
                  <td class="py-2 pr-4 text-right tnum">{{ r.cnt }}</td>
                  <td class="py-2 pr-4 text-right tnum font-medium">{{ r.avg_score }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 0923 补充题：常用功能分布 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-1">🧩 常用功能分布（问卷补充题）</h3>
            <p class="text-xs text-gray-500 mb-3">答卷人勾选的常用模块 — 用于按使用模式解读 SUS 分数（低分集中在哪些模块的用户）。</p>
            <div v-if="!store.susStats?.module_usage?.length" class="text-gray-400 text-sm py-4 text-center">暂无数据（新版问卷提交后展示）</div>
            <div v-else class="flex flex-wrap gap-2 max-w-xl">
              <div v-for="m in store.susStats.module_usage" :key="m.module"
                class="flex items-center gap-1.5 bg-gray-50 border border-gray-200 rounded-full px-3 py-1 text-sm">
                <span>{{ m.module }}</span>
                <span class="text-xs text-gray-400 tnum">{{ m.count }} 人</span>
              </div>
            </div>
          </div>

          <!-- 0923 补充题：最近改进建议 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-1">💬 改进建议（最近 20 条）</h3>
            <p class="text-xs text-gray-500 mb-3">答卷人开放反馈 — 直接指路改进优先级。</p>
            <div v-if="!store.susStats?.recent_improvements?.length" class="text-gray-400 text-sm py-4 text-center">暂无建议（新版问卷提交后展示）</div>
            <ul v-else class="space-y-2 max-w-2xl">
              <li v-for="(f, i) in store.susStats.recent_improvements" :key="i"
                class="text-sm border-b border-gray-50 last:border-0 pb-2 last:pb-0">
                <span class="text-gray-800">{{ f.improvement }}</span>
                <span class="text-xs text-gray-400 ml-2">
                  — {{ f.role }} {{ f.username }}{{ f.created_at ? ` · ${String(f.created_at).slice(0, 10)}` : '' }}
                </span>
              </li>
            </ul>
          </div>

          <!-- SUS 问卷区域 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">📝 SUS 可用性问卷</h3>
            <p class="text-xs text-gray-500 mb-3">System Usability Scale — 10 题标准问卷，评估系统整体易用性。</p>
            <button v-if="!store.susCanSubmit" disabled
              class="px-4 py-2 bg-gray-200 text-gray-500 rounded text-sm cursor-not-allowed">
              🕐 冷却期内{{ store.susCooldownDays != null ? `，${store.susCooldownDays} 天后可重新提交` : '' }}
            </button>
            <button v-else @click="showSusModal = true"
              class="px-4 py-2 bg-primary text-white rounded text-sm font-medium hover:bg-primary/90 transition">
              📝 填写问卷
            </button>
          </div>

          <!-- SUS 分数解释 -->
          <div class="text-xs text-gray-400 border-t pt-4">
            <p>💡 <strong>SUS 分数解释</strong>：&gt;80.3 优秀 (A) | 68-80.3 良好 (B) | 51-68 一般 (C) | &lt;51 差 (F)。及格线为 68 分。</p>
            <p>📐 <strong>计分公式</strong>：SUS = ((奇数题得分-1) + (5-偶数题得分)) × 2.5，满分 100。</p>
          </div>

          <!-- SUS 弹窗组件 -->
          <SusSurveyModal v-model:visible="showSusModal" @success="onSusSubmitted" />
        </div>

        <!-- ═══════════ Tab 5：用户活跃 ═══════════ -->
        <div v-if="store.activeTab === 'activity'" class="space-y-5">
          <!-- 活跃度 KPI -->
          <div class="grid grid-cols-3 gap-3">
            <KpiCard icon="📅" label="日活 (DAU)" :value="store.activityStats?.dau ?? 0" color="blue" />
            <KpiCard icon="📆" label="周活 (WAU)" :value="store.activityStats?.wau ?? 0" color="green" />
            <KpiCard icon="🗓️" label="月活 (MAU)" :value="store.activityStats?.mau ?? 0" color="purple" />
          </div>

          <!-- 页面热度 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-3">🔥 页面热度排名（近30天）</h3>
            <div v-if="!store.activityStats || !store.activityStats.page_heat?.length" class="text-gray-400 text-sm py-8 text-center">暂无活跃度数据（需用户浏览页面后产生数据）</div>
            <table v-else class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-gray-500">
                  <th class="py-2 pr-4">页面路径</th>
                  <th class="py-2 pr-4 text-right">访问量</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(p, i) in store.activityStats.page_heat" :key="i" class="border-b last:border-0 hover:bg-gray-50">
                  <td class="py-2 pr-4 font-mono text-xs">{{ p.page_path || '—' }}</td>
                  <td class="py-2 pr-4 text-right tnum font-medium">{{ p.cnt }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 0819 个人活跃度 Top10（原角色活跃度改为按个人统计） -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-sm font-semibold">👤 个人活跃度 Top10（近30天）</h3>
              <button @click="activityModalVisible = true"
                class="px-2 py-1 border border-gray-300 rounded text-xs hover:bg-gray-50 transition">📄 查看全部</button>
            </div>
            <div v-if="!store.activityStats || !store.activityStats.user_activity?.length" class="text-gray-400 text-sm py-4 text-center">暂无数据</div>
            <table v-else class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-gray-500">
                  <th class="py-2 pr-4 w-8">#</th>
                  <th class="py-2 pr-4">用户</th>
                  <th class="py-2 pr-4">角色</th>
                  <th class="py-2 pr-4 text-right">访问次数</th>
                  <th class="py-2 pr-4 text-right">活跃天数</th>
                  <th class="py-2 pr-4">最近活跃</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(u, i) in activityTop10" :key="u.username" class="border-b last:border-0 hover:bg-gray-50">
                  <td class="py-2 pr-4 font-bold text-gray-400 tnum">{{ i + 1 }}</td>
                  <td class="py-2 pr-4">
                    <div class="font-medium">{{ u.display_name || u.username }}</div>
                    <div class="text-xs text-gray-400 mono">{{ u.username }}</div>
                  </td>
                  <td class="py-2 pr-4 text-xs text-gray-600">{{ u.role }}</td>
                  <td class="py-2 pr-4 text-right tnum font-medium">{{ u.total_visits }}</td>
                  <td class="py-2 pr-4 text-right tnum">{{ u.active_days }}</td>
                  <td class="py-2 pr-4 text-xs text-gray-500 mono">{{ (u.last_active || '').slice(0, 16) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 0902 个人活跃度全量弹窗（查看全部 + 排序切换） -->
          <Teleport to="body">
            <div v-if="activityModalVisible" class="fixed inset-0 z-50 flex items-center justify-center">
              <div class="absolute inset-0 bg-black/50" @click="activityModalVisible = false" />
              <div class="relative bg-white rounded-xl shadow-2xl w-full max-w-3xl mx-4 max-h-[80vh] overflow-y-auto z-10">
                <div class="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between rounded-t-xl">
                  <h2 class="text-lg font-bold">👤 个人活跃度全量（近30天）</h2>
                  <div class="flex items-center gap-2">
                    <select v-model="activitySortKey" class="px-2 py-1.5 border border-gray-300 rounded text-xs bg-white">
                      <option value="visits">访问次数 ↓</option>
                      <option value="days">活跃天数 ↓</option>
                      <option value="recent">最近活跃 ↓</option>
                      <option value="name">用户名 ↑</option>
                    </select>
                    <button @click="activityModalVisible = false" class="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition">
                      <span class="text-xl leading-none">&times;</span>
                    </button>
                  </div>
                </div>
                <div class="px-6 py-4">
                  <div v-if="!sortedActivityUsers.length" class="text-gray-400 text-sm py-8 text-center">暂无数据</div>
                  <table v-else class="w-full text-sm">
                    <thead>
                      <tr class="border-b text-left text-gray-500">
                        <th class="py-2 pr-4 w-8">#</th>
                        <th class="py-2 pr-4">用户</th>
                        <th class="py-2 pr-4">角色</th>
                        <th class="py-2 pr-4 text-right">访问次数</th>
                        <th class="py-2 pr-4 text-right">活跃天数</th>
                        <th class="py-2 pr-4">最近活跃</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(u, i) in sortedActivityUsers" :key="u.username" class="border-b last:border-0 hover:bg-gray-50">
                        <td class="py-2 pr-4 font-bold text-gray-400 tnum">{{ i + 1 }}</td>
                        <td class="py-2 pr-4">
                          <div class="font-medium">{{ u.display_name || u.username }}</div>
                          <div class="text-xs text-gray-400 mono">{{ u.username }}</div>
                        </td>
                        <td class="py-2 pr-4 text-xs text-gray-600">{{ u.role }}</td>
                        <td class="py-2 pr-4 text-right tnum font-medium">{{ u.total_visits }}</td>
                        <td class="py-2 pr-4 text-right tnum">{{ u.active_days }}</td>
                        <td class="py-2 pr-4 text-xs text-gray-500 mono">{{ (u.last_active || '').slice(0, 16) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </Teleport>

          <!-- 0805 Phase 3: 操作耗时分析 -->
          <div class="bg-white rounded-lg border border-gray-200 p-4">
            <h3 class="text-sm font-semibold mb-1">⏱ 关键操作耗时分析</h3>
            <p class="text-xs text-gray-400 mb-3">统计用户完成关键操作所用时长：录入表单=进入录入页到提交；指派操作=打开工单到提交指派；工单处理=打开工单到提交处理结果。数据来自操作计时埋点。</p>
            <div v-if="!store.timingStats || !store.timingStats.length" class="text-gray-400 text-sm py-8 text-center">
              暂无操作耗时数据（需在录入工单、指派审批人/承接人、处理工单等操作后产生数据）
            </div>
            <template v-else>
              <div class="grid grid-cols-3 gap-3 mb-4">
                <KpiCard v-for="t in store.timingStats" :key="t.action_name"
                  :icon="timingIconMap[t.action_name] || '⏱'"
                  :label="t.action_label + '（平均）'"
                  :value="formatSeconds(t.avg_seconds)"
                  color="blue"
                  format="text" />
              </div>
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b text-left text-gray-500">
                    <th class="py-2 pr-4">操作</th>
                    <th class="py-2 pr-4 text-right">样本数</th>
                    <th class="py-2 pr-4 text-right">平均</th>
                    <th class="py-2 pr-4 text-right">P50（中位数）</th>
                    <th class="py-2 pr-4 text-right">P95（95分位）</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="t in store.timingStats" :key="t.action_name" class="border-b last:border-0 hover:bg-gray-50">
                    <td class="py-2 pr-4 font-medium">{{ t.action_label }}</td>
                    <td class="py-2 pr-4 text-right tnum">{{ t.count }}</td>
                    <td class="py-2 pr-4 text-right tnum">{{ formatSeconds(t.avg_seconds) }}</td>
                    <td class="py-2 pr-4 text-right tnum text-gray-500">{{ formatSeconds(t.p50_seconds) }}</td>
                    <td class="py-2 pr-4 text-right tnum" :class="t.p95_seconds > 300 ? 'text-red-600' : 'text-gray-500'">{{ formatSeconds(t.p95_seconds) }}</td>
                  </tr>
                </tbody>
              </table>
            </template>
          </div>
        </div>
      </template>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import AppLayout from '@/components/layout/AppLayout.vue'
import KpiCard from '@/components/analytics/KpiCard.vue'
import SusSurveyModal from '@/components/common/SusSurveyModal.vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { useEvalStore } from '@/stores/eval'
import { useAuthStore } from '@/stores/auth'

use([BarChart, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer])

const DATE_RANGES = ['本月', '上月', '近3个月', '近6个月', '全部']
const TABS = [
  { key: 'stage', icon: '⏱', label: '阶段效率' },
  { key: 'ai', icon: '🤖', label: 'AI 效能' },
  { key: 'quality', icon: '📈', label: '业务质量' },
  { key: 'sus', icon: '📋', label: 'SUS 问卷' },
  { key: 'activity', icon: '👥', label: '用户活跃' },
]

// 0824 小样本预警：低于该样本量的比率/均分仅作参考
const MIN_SAMPLE = 30
function small(n: number | null | undefined): boolean {
  const v = n ?? 0
  return v > 0 && v < MIN_SAMPLE
}

const store = useEvalStore()
const showSusModal = ref(false)

function onSusSubmitted(_score: number) {
  store.susCanSubmit = false
  store.fetchSusStats()
}

// 0821 AI 功能名中文解释（原名（中文），未知值回退原名）
const aiFunctionLabelMap: Record<string, string> = {
  classify: '智能分类',
  suggest_schedule: 'AI 排期建议',
  // 0902 新增字段级匹配度埋点（ai_adoption_log 的 ai_function 取值）
  prefill: '智能填表预填',
  self_check: '客户自排查建议',
  diagnose: 'AI 分工建议评估',
  email_draft: '邮件草稿',
  // llm_call_log 的 function_name（AI 健康统计）
  suggest_priority_llm: '优先级建议',
  classify_complaint_llm: '客诉智能分类',
  extract_knowledge_llm: '知识抽取',
  semantic_search_kb: '知识库语义检索',
  extract_complaint_from_text: '文本提取客诉',
  diagnose_complaint: '故障智能诊断',
  llm_suggest: 'AI 建议生成',
  generate_email_draft: '邮件草稿生成',
  case_search_solution: '案例搜索方案',
  suggest_customer_self_check: '客户自排查建议',
  llm_chat: '通用对话',
}

function aiFunctionDisplay(name: string): string {
  const label = aiFunctionLabelMap[name]
  return label ? `${name}（${label}）` : name
}

// 0821 工单状态停留时长明细表（阶段列按新流程，含待客户排查独立列；阈值取自后端）
const STAGE_DWELL_COLUMNS = ['待客服处理', '待客户排查', '客服主管审核', '指派审批人', '指派承接人', '处理中']
const dwellJumpPage = ref(1)

// 0902 按人统计卡：本地排序（人员行数小，服务端返回全量）
const operatorBlockageSort = ref('blockage_desc')
const sortedOperatorBlockage = computed(() => {
  const items = [...(store.operatorBlockage?.items ?? [])]
  const nameCmp = (a: typeof items[number], b: typeof items[number]) => a.operator.localeCompare(b.operator, 'zh')
  const key = operatorBlockageSort.value
  if (key === 'blocked_desc') items.sort((a, b) => b.blocked_segments - a.blocked_segments || nameCmp(a, b))
  else if (key === 'avg_dwell_desc') items.sort((a, b) => b.avg_dwell_hours - a.avg_dwell_hours || nameCmp(a, b))
  else if (key === 'total_desc') items.sort((a, b) => b.total_segments - a.total_segments || nameCmp(a, b))
  else if (key === 'name_asc') items.sort(nameCmp)
  else items.sort((a, b) => b.blockage_rate_pct - a.blockage_rate_pct || nameCmp(a, b))
  return items
})

// 0902 按人卡分页（每页 8 条；排序/筛选变化重置页码，日期范围缩小列表时自动钳制）
const OPERATOR_BLOCKAGE_PAGE_SIZE = 8
const operatorBlockagePage = ref(1)
watch([operatorBlockageSort, () => store.operatorBlockageStage], () => { operatorBlockagePage.value = 1 })
const operatorBlockageTotalPages = computed(() => Math.max(1, Math.ceil(sortedOperatorBlockage.value.length / OPERATOR_BLOCKAGE_PAGE_SIZE)))
const paginatedOperatorBlockage = computed(() => {
  const page = Math.min(operatorBlockagePage.value, operatorBlockageTotalPages.value)
  const start = (page - 1) * OPERATOR_BLOCKAGE_PAGE_SIZE
  return sortedOperatorBlockage.value.slice(start, start + OPERATOR_BLOCKAGE_PAGE_SIZE)
})

function onDwellJumpPage() {
  store.setStageDwellPage(dwellJumpPage.value)
}

// 0902 个人活跃度：主表 Top10 切片 + 查看全部弹窗（客户端排序）
const activityModalVisible = ref(false)
const activitySortKey = ref('visits')
const activityTop10 = computed(() => (store.activityStats?.user_activity ?? []).slice(0, 10))
const sortedActivityUsers = computed(() => {
  const items = [...(store.activityStats?.user_activity ?? [])]
  if (activitySortKey.value === 'days') items.sort((a, b) => b.active_days - a.active_days)
  else if (activitySortKey.value === 'recent') items.sort((a, b) => (b.last_active || '').localeCompare(a.last_active || ''))
  else if (activitySortKey.value === 'name') items.sort((a, b) => (a.display_name || a.username).localeCompare(b.display_name || b.username, 'zh'))
  else items.sort((a, b) => b.total_visits - a.total_visits)
  return items
})

const hasData = computed(() => {
  if (store.activeTab === 'stage') return store.stageDuration.length > 0 || store.stageBlockage.length > 0
  if (store.activeTab === 'ai') return store.llmHealth.length > 0
  if (store.activeTab === 'quality') return store.businessQuality !== null
  if (store.activeTab === 'sus') return store.susStats !== null
  if (store.activeTab === 'activity') return store.activityStats !== null || store.timingStats.length > 0
  return false
})

// ── 阶段效率 计算属性 ──
const stageSummary = computed(() => {
  const items = store.stageDuration
  const blockageItems = store.stageBlockage
  return {
    stageCount: items.length || blockageItems.length || 0,
    maxAvgHours: items.length ? Math.max(...items.map(d => d.avg_hours)) : 0,
    blockageCount: blockageItems.filter(b => b.blockage_rate_pct > 0).length,
    totalSamples: items.reduce((s, d) => s + d.count, 0),
  }
})

const stageDurationChartData = computed(() =>
  store.stageDuration.map(d => ({ name: d.stage, avg: d.avg_hours, p50: d.p50_hours, p95: d.p95_hours }))
)

const stageDurationOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  legend: { data: ['avg（平均）', 'P50（中位数）', 'P95（95分位）'], top: 0 },
  grid: { left: 120, right: 30, top: 40, bottom: 30 },
  xAxis: { type: 'value' as const, name: '小时', axisLabel: { fontSize: 11 } },
  yAxis: { type: 'category' as const, data: stageDurationChartData.value.map(d => d.name), axisLabel: { fontSize: 11 } },
  series: [
    { name: 'avg（平均）', type: 'bar', data: stageDurationChartData.value.map(d => d.avg), itemStyle: { color: '#3b82f6' } },
    { name: 'P50（中位数）', type: 'bar', data: stageDurationChartData.value.map(d => d.p50), itemStyle: { color: '#f59e0b' } },
    { name: 'P95（95分位）', type: 'bar', data: stageDurationChartData.value.map(d => d.p95), itemStyle: { color: '#ef4444' } },
  ],
}))

const efficiencyCompareData = computed(() => store.efficiencyCompare)

const efficiencyCompareOption = computed(() => {
  const dims = efficiencyCompareData.value.map(d => d.dimension_value)
  const stages = new Set<string>()
  efficiencyCompareData.value.forEach(d => d.stages.forEach(s => stages.add(s.stage)))
  const stageList = Array.from(stages)
  const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316']
  return {
    tooltip: { trigger: 'axis' as const },
    legend: { data: stageList, top: 0 },
    grid: { left: 80, right: 30, top: 40, bottom: 60 },
    xAxis: { type: 'category' as const, data: dims, axisLabel: { fontSize: 11, rotate: dims.length > 5 ? 30 : 0 } },
    yAxis: { type: 'value' as const, name: '小时' },
    series: stageList.map((s, i) => ({
      name: s, type: 'bar',
      data: efficiencyCompareData.value.map(d => d.stages.find(ss => ss.stage === s)?.avg_hours ?? 0),
      itemStyle: { color: colors[i % colors.length] },
    })),
  }
})

// ── AI 效能 计算属性 ──
const aiSummary = computed(() => ({
  functionCount: store.llmHealth.length,
  totalCalls: store.llmHealth.reduce((s, d) => s + d.total_calls, 0),
  overallSuccessRate: store.llmHealth.length
    ? store.llmHealth.reduce((s, d) => s + d.success_count, 0) * 100 / Math.max(1, store.llmHealth.reduce((s, d) => s + d.total_calls, 0))
    : 0,
  avgLatency: store.llmHealth.length
    ? Math.round(store.llmHealth.reduce((s, d) => s + d.avg_latency_ms * d.total_calls, 0) / Math.max(1, store.llmHealth.reduce((s, d) => s + d.total_calls, 0)))
    : 0,
}))

// ── 业务质量 计算属性 ──
const reworkChartData = computed(() =>
  (store.businessQuality?.rework_by_category ?? []).map(d => ({ name: d.fault_category, value: d.rework_rate_pct }))
)

const reworkOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  grid: { left: 60, right: 30, top: 10, bottom: 40 },
  xAxis: { type: 'category' as const, data: reworkChartData.value.map(d => d.name) },
  yAxis: { type: 'value' as const, name: '%' },
  series: [{ type: 'bar', data: reworkChartData.value.map(d => d.value), itemStyle: { color: '#f59e0b' } }],
}))

const rejectionChartData = computed(() =>
  (store.businessQuality?.rejection_by_category ?? []).map(d => ({ name: d.fault_category, value: d.rejection_rate_pct }))
)

const rejectionOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  grid: { left: 60, right: 30, top: 10, bottom: 40 },
  xAxis: { type: 'category' as const, data: rejectionChartData.value.map(d => d.name) },
  yAxis: { type: 'value' as const, name: '%' },
  series: [{ type: 'bar', data: rejectionChartData.value.map(d => d.value), itemStyle: { color: '#ef4444' } }],
}))

const satChartData = computed(() =>
  (store.businessQuality?.satisfaction_dist ?? []).map(d => ({ name: d.satisfaction + ' 星', value: d.cnt }))
)

const satisfactionOption = computed(() => ({
  tooltip: { trigger: 'item' as const },
  legend: { top: 0 },
  series: [{
    type: 'pie', radius: ['45%', '75%'], center: ['50%', '55%'],
    data: satChartData.value.map(d => ({ name: d.name, value: d.value })),
    label: { formatter: '{b}: {c}' },
    emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.2)' } },
  }],
}))

// ── SUS 问卷 计算属性 ──
const susPassRate = computed(() => {
  const stats = store.susStats
  if (!stats || !stats.total_responses) return 0
  const passed = stats.score_distribution
    .filter(d => d.score_range.startsWith('优秀') || d.score_range.startsWith('良好'))
    .reduce((s, d) => s + d.cnt, 0)
  return passed * 100 / stats.total_responses
})

// ── AI 采纳率 计算属性 ──
const aiAdoptionSummary = computed(() => {
  const data = store.aiAdoptionStats
  if (!data.length) return { total: 0, adopted: 0, rate: 0 }
  const total = data.reduce((s: number, d: any) => s + d.total, 0)
  const adopted = data.reduce((s: number, d: any) => s + d.adopted_count, 0)
  return { total, adopted, rate: total > 0 ? Math.round(adopted * 100 / total) : 0 }
})

// ── 0805 Phase 3: AI 阶段评价 计算属性 ──
const stageLabelMap: Record<string, string> = {
  intake: '智能填表',
  evaluate: '评估阶段',
  assign: '指派操作',
  resolve: '处理方案',
  confirm: '客户确认',
}

const feedbackStageChartData = computed(() =>
  (store.feedbackByStage?.by_stage ?? []).map((s: any) => ({
    name: stageLabelMap[s.feedback_type] || s.feedback_type,
    value: s.avg_accuracy || 0,
  }))
)

const feedbackStageOption = computed(() => ({
  tooltip: { trigger: 'axis' as const, formatter: (p: any) => `${p[0].name}<br/>平均星数: ${p[0].value?.toFixed(2)}` },
  grid: { left: 40, right: 20, top: 10, bottom: 50 },
  xAxis: { type: 'category' as const, data: feedbackStageChartData.value.map((d: any) => d.name), axisLabel: { fontSize: 11 } },
  yAxis: { type: 'value' as const, name: '星', min: 1, max: 5 },
  series: [{
    type: 'bar', data: feedbackStageChartData.value.map((d: any) => d.value),
    itemStyle: { color: '#8b5cf6' },
    markLine: { silent: true, data: [{ yAxis: 4, name: '4星', label: { formatter: '4星' } }], lineStyle: { color: '#10b981', type: 'dashed' } },
  }],
}))

// 各阶段省时效果堆叠柱状图
const timeSavedLabels = ['显著省时', '适度省时', '略微省时', '无节省', '反而更慢']
const timeSavedKeys = ['significant', 'moderate', 'slight', 'none', 'negative']
const timeSavedColors = ['#10b981', '#34d399', '#fcd34d', '#d1d5db', '#f87171']

const timeSavedChartData = computed(() => {
  const stages = store.feedbackByStage?.by_stage ?? []
  return {
    stages: stages.map((s: any) => stageLabelMap[s.feedback_type] || s.feedback_type),
    series: timeSavedKeys.map((key, i) => ({
      name: timeSavedLabels[i],
      type: 'bar',
      stack: 'total',
      data: stages.map((s: any) => (s.time_saved?.[key]) || 0),
      itemStyle: { color: timeSavedColors[i] },
    })),
  }
})

const timeSavedOption = computed(() => ({
  tooltip: { trigger: 'axis' as const, axisPointer: { type: 'shadow' as const } },
  legend: { data: timeSavedLabels, top: 0, textStyle: { fontSize: 11 } },
  grid: { left: 40, right: 20, top: 35, bottom: 50 },
  xAxis: { type: 'category' as const, data: timeSavedChartData.value.stages, axisLabel: { fontSize: 11 } },
  yAxis: { type: 'value' as const, name: '人次', minInterval: 1 },
  series: timeSavedChartData.value.series,
}))

// ── 0805 Phase 3: AI 排期准确度 计算属性 ──
const scheduleDevChartData = computed(() =>
  (store.scheduleAccuracy?.deviation_distribution ?? []).map((d: any) => ({ name: d.bucket, value: d.count }))
)

const scheduleDevOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  grid: { left: 50, right: 20, top: 10, bottom: 30 },
  xAxis: { type: 'category' as const, data: scheduleDevChartData.value.map((d: any) => d.name), name: '偏差范围' },
  yAxis: { type: 'value' as const, name: '工单数', minInterval: 1 },
  series: [{ type: 'bar', data: scheduleDevChartData.value.map((d: any) => d.value), itemStyle: { color: '#f59e0b' } }],
}))

// ── 0805 Phase 3: 操作耗时辅助 ──
const timingIconMap: Record<string, string> = {
  complaint_intake: '📝',
  engineer_assign: '📌',
  ticket_resolve: '🔧',
}

function formatSeconds(sec: number): string {
  if (!sec || sec <= 0) return '—'
  if (sec < 60) return Math.round(sec) + '秒'
  if (sec < 3600) return (sec / 60).toFixed(1) + '分钟'
  return (sec / 3600).toFixed(1) + '小时'
}

// ── 挂载 ──
onMounted(() => {
  store.fetchTabData()
})
</script>
