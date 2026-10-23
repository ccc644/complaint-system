<!-- 0911 用户模糊搜索输入框 — 批量导入预览表格行内用（责任人/提出人）
     保持文本语义（提交端按姓名服务端重查）；multi=按 /、，, 分段只匹配末段、选中替换末段。
     下拉 Teleport+fixed 定位（表格容器 overflow 裁剪不到），滚动/点击外部/ESC 关闭。 -->
<template>
  <div class="relative">
    <input ref="inputRef" :value="modelValue" type="text" :placeholder="placeholder"
      class="w-full px-1.5 py-0.5 border border-gray-300 rounded-base text-xs"
      @input="onInput" @focus="openList" @keydown.escape="open = false" />
    <Teleport to="body">
      <div v-if="open && matches.length" ref="dropRef"
        class="fixed z-50 bg-white border border-gray-200 rounded-base shadow-lg py-1 w-56 max-h-48 overflow-y-auto"
        :style="{ top: rect.top + 'px', left: rect.left + 'px' }">
        <button v-for="u in matches" :key="u.id" type="button"
          class="w-full text-left px-2.5 py-1.5 hover:bg-primary/5 flex items-baseline gap-2"
          @mousedown.prevent="selectUser(u)">
          <span class="text-xs text-gray-800">{{ u.display_name }}</span>
          <span class="text-[10px] text-gray-400 truncate">{{ u.position || u.role }}</span>
        </button>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { UserOption } from '@/types/api'

const props = withDefaults(defineProps<{
  modelValue: string
  options: UserOption[]
  multi?: boolean       // 责任人多人：按 /、，, 分段，只对末段模糊匹配
  placeholder?: string
}>(), { multi: false, placeholder: '' })

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const open = ref(false)
const rect = ref({ top: 0, left: 0 })
const inputRef = ref<HTMLInputElement>()
const dropRef = ref<HTMLElement>()

// 与后端 re.split(r"[/、，,]") 一致的分段
function lastSeg(v: string): { prefix: string; kw: string } {
  if (!props.multi) return { prefix: '', kw: v.trim() }
  const idx = Math.max(v.lastIndexOf('/'), v.lastIndexOf('、'), v.lastIndexOf('，'), v.lastIndexOf(','))
  if (idx < 0) return { prefix: '', kw: v.trim() }
  return { prefix: v.slice(0, idx + 1), kw: v.slice(idx + 1).trim() }
}

const matches = computed<UserOption[]>(() => {
  const k = lastSeg(props.modelValue).kw.toLowerCase()
  return props.options
    .filter(u => !k
      || u.display_name.toLowerCase().includes(k)
      || u.username.toLowerCase().includes(k)
      || (u.position || '').toLowerCase().includes(k))
    .slice(0, 8)
})

function position() {
  const el = inputRef.value
  if (!el) return
  const r = el.getBoundingClientRect()
  // 接近视口底则向上弹
  rect.value = r.bottom + 196 > window.innerHeight
    ? { top: Math.max(8, r.top - 200), left: r.left }
    : { top: r.bottom + 4, left: r.left }
}

function openList() {
  position()
  open.value = true
}

function onInput(e: Event) {
  emit('update:modelValue', (e.target as HTMLInputElement).value)
  position()
  open.value = true
}

function selectUser(u: UserOption) {
  emit('update:modelValue', lastSeg(props.modelValue).prefix + u.display_name)
  open.value = false
  inputRef.value?.focus()
}

function onDocClick(e: MouseEvent) {
  const t = e.target as Node
  if (inputRef.value?.contains(t) || dropRef.value?.contains(t)) return
  open.value = false
}

function close() { open.value = false }

onMounted(() => {
  document.addEventListener('click', onDocClick)
  window.addEventListener('scroll', close, true) // capture：表格容器滚动也关闭
  window.addEventListener('resize', close)
})
onUnmounted(() => {
  document.removeEventListener('click', onDocClick)
  window.removeEventListener('scroll', close, true)
  window.removeEventListener('resize', close)
})
</script>
