<!-- 0724 登录页面 — 账号 + 密码
     0819 v3.0：取消中心选择，登录仅账号+密码 -->
<template>
  <div class="login-bg">
    <div class="flex items-center justify-center min-h-screen">
      <div class="login-card">
        <h1 class="text-3xl font-bold text-white text-center mb-2">AI 客诉处理系统</h1>
        <p class="text-white/70 text-center text-sm mb-6">Semiconductor Complaint Management</p>

        <form @submit.prevent="handleLogin" class="space-y-4">
          <div>
            <label class="block text-white text-sm mb-1">账号</label>
            <input v-model="username" type="text" required
              class="w-full px-3 py-2 rounded-base bg-white/15 border border-white/20 text-white
                     placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="请输入账号" />
          </div>
          <div>
            <label class="block text-white text-sm mb-1">密码</label>
            <input v-model="password" type="password" required
              class="w-full px-3 py-2 rounded-base bg-white/15 border border-white/20 text-white
                     placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="请输入密码" />
          </div>

          <!-- 0901 7 天自动登录：勾选后凭证存入浏览器保险箱，钉钉卡片/新标签免输密码；不勾则每次登录 -->
          <label class="flex items-center gap-2 text-white/80 text-sm select-none cursor-pointer">
            <input v-model="remember" type="checkbox"
              class="w-4 h-4 accent-[var(--color-primary)] cursor-pointer" />
            7 天内自动登录
          </label>

          <div v-if="errorMsg" class="text-red-400 text-sm text-center bg-red-500/10 rounded-base py-2">
            {{ errorMsg }}
          </div>

          <button type="submit" :disabled="loading"
            class="w-full py-2.5 bg-primary hover:bg-primary/90 text-white font-semibold rounded-base
                   transition disabled:opacity-50 disabled:cursor-not-allowed">
            {{ loading ? '登录中...' : '登 录' }}
          </button>
        </form>

        <!-- 0902 钉钉内页面过小时的备用入口提示（网址在 src/config.ts 的 LOGIN_BROWSER_URLS 配置，可多个） -->
        <div v-if="LOGIN_BROWSER_URLS.length" class="mt-5 pt-4 border-t border-white/15">
          <p class="text-white/70 text-xs leading-relaxed mb-2">
            💡 钉钉内页面显示过小？可复制以下网址到浏览器打开：
          </p>
          <div v-for="url in LOGIN_BROWSER_URLS" :key="url" class="flex items-center gap-2 mb-1.5">
            <span class="text-white/85 text-xs mono truncate flex-1" :title="url">{{ url }}</span>
            <button type="button" @click="copyLoginUrl(url)"
              class="shrink-0 px-2 py-0.5 text-xs rounded-base bg-white/15 border border-white/20 text-white hover:bg-white/25 transition">
              {{ copiedUrl === url ? '✓ 已复制' : '复制' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { LOGIN_BROWSER_URLS } from '@/config'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const remember = ref(false)  // 0901 默认不勾选：安全优先，需要免密直达的用户自行勾选
const loading = ref(false)
const errorMsg = ref('')
const copiedUrl = ref('')

// 0902 复制登录备用网址：clipboard API 优先，钉钉 webview 等非安全上下文用 execCommand 兜底
async function copyLoginUrl(url: string) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(url)
    } else {
      const ta = document.createElement('textarea')
      ta.value = url
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    copiedUrl.value = url
    setTimeout(() => { if (copiedUrl.value === url) copiedUrl.value = '' }, 2000)
  } catch {
    copiedUrl.value = ''
  }
}

async function handleLogin() {
  errorMsg.value = ''
  loading.value = true
  try {
    const res = await auth.login(username.value, password.value, remember.value)
    if (res.success) {
      // 0824 钉钉深链：登录后回跳原目标页（仅允许站内路径，防开放重定向）
      const raw = route.query.redirect
      const target = typeof raw === 'string' && raw.startsWith('/') && !raw.startsWith('//')
        ? raw
        : '/'
      router.push(target)
    } else {
      errorMsg.value = res.message || '登录失败'
    }
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || '登录失败，请检查账号密码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-bg {
  background: linear-gradient(135deg, #1e1b4b 0%, #312e81 40%, #4c1d95 100%);
  min-height: 100vh;
}
.login-card {
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(16px);
  padding: 32px 28px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  width: 380px;
  max-width: 90vw;
}
</style>
