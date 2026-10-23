<!-- 0824 导出中心独立页 — 管理员按日期范围导出各类数据（CSV / 附件 ZIP）
     原为系统管理（UserManagement）内嵌 Tab，0824 拆分为独立页面（同日收回客服主管权限，仅管理员） -->
<template>
  <AppLayout>
    <div class="p-6 space-y-6">
      <div class="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 class="text-2xl font-bold">📤 导出中心</h1>
          <p class="text-sm text-gray-500 mt-1">管理员 · 按日期范围导出客诉、日志与附件数据</p>
        </div>
      </div>
      <ExportCenter />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import AppLayout from '@/components/layout/AppLayout.vue'
import ExportCenter from '@/components/admin/ExportCenter.vue'
</script>
