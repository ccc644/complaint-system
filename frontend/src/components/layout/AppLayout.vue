<!-- 0724 应用布局壳 — 侧边栏 + 顶栏 + 内容区
     0819 移动端：侧边栏抽屉化（汉堡按钮 + 遮罩 + 路由变化/Esc 自动关闭），桌面 md: 以上不变 -->
<template>
  <div class="flex h-screen overflow-hidden">
    <AppSidebar :open="sidebarOpen" />
    <div class="flex-1 flex flex-col overflow-hidden">
      <AppHeader @toggle-sidebar="sidebarOpen = true" />
      <main class="flex-1 overflow-auto bg-gray-50">
        <slot />
      </main>
    </div>
    <!-- 0819 移动端抽屉遮罩：md:hidden 保证桌面端永不出现 -->
    <Transition name="fade">
      <div v-if="sidebarOpen" class="fixed inset-0 z-40 bg-black/50 md:hidden"
        aria-hidden="true" @click="sidebarOpen = false" />
    </Transition>
    <!-- 0804 全局 SUS 问卷弹窗：所有用户登录后按冷却期自动弹出 -->
    <SusSurveyModal v-model:visible="showSusModal" @success="onSusSubmitted" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import AppSidebar from './AppSidebar.vue'
import AppHeader from './AppHeader.vue'
import SusSurveyModal from '@/components/common/SusSurveyModal.vue'
import { useWebSocket } from '@/composables/useWebSocket'
import * as evalApi from '@/api/eval'

// 初始化 WebSocket 实时推送（自动连接/重连/刷新数据）
useWebSocket()

const route = useRoute()
const showSusModal = ref(false)

// ── 0819 移动端抽屉开关 ─────────────────────────
const sidebarOpen = ref(false)

// 路由变化自动关闭抽屉（菜单项点击跳转后收起）
watch(() => route.fullPath, () => { sidebarOpen.value = false })
// 抽屉打开时锁定背景滚动
watch(sidebarOpen, (v) => { document.body.style.overflow = v ? 'hidden' : '' })

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && sidebarOpen.value) sidebarOpen.value = false
}

onMounted(async () => {
  document.addEventListener('keydown', onKeydown)
  // 检查 SUS 冷却状态，冷却期外自动弹出问卷
  try {
    const r = await evalApi.checkSusCooldown()
    if (r.data?.success && r.data.data?.can_submit) {
      // 延迟 1 秒弹出，避免与页面加载动画冲突
      setTimeout(() => { showSusModal.value = true }, 1000)
    }
  } catch {
    // 静默失败，不影响正常使用
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})

function onSusSubmitted(_score: number) {
  // 提交成功后弹窗已自动关闭，无需额外处理
}
</script>

<style scoped>
/* 0819 遮罩淡入淡出（纯透明度，无渐变） */
.fade-enter-active, .fade-leave-active { transition: opacity .2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
