<!-- 0727 趋势折线图 — ECharts 封装，支持 monthly/daily -->
<template>
  <VChart :option="chartOption" :style="{ height: '320px' }" autoresize />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { TrendPoint } from '@/types/api'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{
  data: TrendPoint[]
  granularity?: string
}>()

const chartOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  legend: { data: ['总量', '已关闭'], bottom: 0 },
  grid: { left: '3%', right: '4%', bottom: '12%', top: '8%', containLabel: true },
  xAxis: {
    type: 'category' as const,
    data: props.data.map((d) => d.period),
    axisLabel: { rotate: props.granularity === 'daily' ? 45 : 0, fontSize: 11 },
  },
  yAxis: { type: 'value' as const, minInterval: 1 },
  series: [
    {
      name: '总量', type: 'line' as const, data: props.data.map((d) => d.total),
      smooth: true, symbol: 'circle', symbolSize: 6,
      itemStyle: { color: '#3b82f6' },
    },
    {
      name: '已关闭', type: 'line' as const, data: props.data.map((d) => d.closed_count),
      smooth: true, symbol: 'circle', symbolSize: 6,
      itemStyle: { color: '#22c55e' },
    },
  ],
}))
</script>
