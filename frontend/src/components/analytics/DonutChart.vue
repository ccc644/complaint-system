<!-- 0727 环形分布图 — ECharts 封装 -->
<template>
  <VChart :option="chartOption" :style="{ height: '320px' }" autoresize />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { PieChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { DistributionItem } from '@/types/api'

use([PieChart, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps<{
  data: DistributionItem[]
  title?: string
}>()

const COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#6366f1']

const chartOption = computed(() => ({
  tooltip: { trigger: 'item' as const },
  legend: { orient: 'vertical' as const, right: '5%', top: 'center', textStyle: { fontSize: 12 } },
  color: COLORS,
  series: [{
    name: props.title || '分布',
    type: 'pie' as const,
    radius: ['45%', '75%'],
    center: ['35%', '50%'],
    avoidLabelOverlap: false,
    itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
    label: { show: false },
    emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
    data: props.data.map((d) => ({ name: d.name, value: d.count })),
  }],
}))
</script>
