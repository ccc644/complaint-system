<!-- 0819 用户下拉选择组件 — 按角色过滤从系统用户中选取
     single: 单选（select 下拉）；multi: 多选（0820 改为下拉面板 + 姓名搜索）-->
<template>
  <div class="space-y-1.5">
    <select v-if="single" :value="singleValue" @change="onSingleChange"
      class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm bg-white">
      <option value="">{{ placeholder || '请选择' }}</option>
      <option v-for="u in options" :key="u.id" :value="u.id">
        {{ u.display_name }}（{{ u.position }}）
      </option>
    </select>

    <!-- 0820 多选：下拉按钮 + 搜索面板（点击外部关闭）
         0821 inlineSearch：主框即搜索输入框（已选用户为可移除 chips），面板内不再显示独立搜索框 -->
    <div v-else class="relative" ref="rootRef">
      <template v-if="inlineSearch">
        <!-- 已选用户 chips（可点击 X 移除） -->
        <div v-if="selectedUsers.length" class="flex flex-wrap gap-1.5 mb-1.5">
          <span v-for="u in selectedUsers" :key="u.id"
            class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-primary/10 text-primary text-xs">
            {{ u.display_name }}
            <button type="button" @click="onToggle(u.id)" title="移除"
              class="text-primary/60 hover:text-primary transition">
              <X :size="12" />
            </button>
          </span>
        </div>
        <input v-model="searchText" type="text" @focus="open = true"
          placeholder="🔍 搜索姓名/账号/职位..."
          class="w-full px-3 py-1.5 border border-gray-300 rounded text-sm bg-white focus:ring-2 focus:ring-primary/30" />
      </template>
      <button v-else type="button" @click="open = !open"
        class="w-full flex items-center gap-1.5 px-3 py-1.5 border border-gray-300 rounded text-sm bg-white text-left hover:border-gray-400 transition">
        <span v-if="!selectedUsers.length" class="text-gray-400">请选择…</span>
        <template v-else>
          <span v-for="u in selectedUsers.slice(0, 2)" :key="u.id"
            class="inline-flex items-center px-1.5 py-0.5 rounded bg-primary/10 text-primary text-xs truncate">
            {{ u.display_name }}
          </span>
          <span v-if="selectedUsers.length > 2" class="text-xs text-gray-400 shrink-0">+{{ selectedUsers.length - 2 }}</span>
        </template>
        <ChevronDown :size="14" class="ml-auto shrink-0 text-gray-400" />
      </button>

      <div v-if="open"
        class="absolute left-0 right-0 top-full mt-1 z-20 bg-white border border-gray-200 rounded shadow-lg flex flex-col">
        <div v-if="!inlineSearch" class="p-2 border-b border-gray-100">
          <input v-model="searchText" placeholder="🔍 搜索姓名/账号/职位..."
            class="w-full px-2 py-1 border border-gray-200 rounded text-xs focus:ring-2 focus:ring-primary/30" />
        </div>
        <div class="max-h-48 overflow-y-auto p-1">
          <div v-if="loading" class="text-xs text-gray-400 py-2 text-center">加载中...</div>
          <div v-else-if="!filteredOptions.length" class="text-xs text-gray-400 py-2 text-center">
            {{ options.length ? '无匹配用户' : '暂无可选用户（请先创建对应角色账号）' }}
          </div>
          <label v-for="u in filteredOptions" :key="u.id"
            class="flex items-center gap-2 px-2 py-1 rounded hover:bg-gray-50 cursor-pointer text-sm">
            <input type="checkbox" :checked="selectedIds.includes(u.id)"
              @change="onToggle(u.id)" class="rounded w-4 h-4 accent-primary" />
            <span class="text-gray-700">{{ u.display_name }}</span>
            <span class="text-xs text-gray-400 truncate">{{ u.position }}</span>
          </label>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { ChevronDown, X } from 'lucide-vue-next'
import { getUserOptions } from '@/api/users'
import type { UserOption } from '@/types/api'

const props = defineProps<{
  roles: string[]      // 候选角色列表
  single?: boolean     // true=单选下拉；false=多选下拉面板
  inlineSearch?: boolean  // 0821 多选模式下主框即搜索输入框（承接人/追加参与人实例使用）
  placeholder?: string    // 0826 单选模式首项提示文案（默认「请选择」）
  modelValue?: number | number[]  // 单选传 number；多选传 number[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: number | number[]): void
  // 0820 选项加载完成事件（供父组件做「主要推进人」姓名映射）
  (e: 'options-loaded', users: UserOption[]): void
}>()

const options = ref<UserOption[]>([])
const loading = ref(false)
const open = ref(false)
const searchText = ref('')
const rootRef = ref<HTMLElement | null>(null)

// 0826 modelValue=0（未选）归一为 ''，命中占位 option——否则浏览器匹配不到选项会把闭合框渲染成空白
const singleValue = computed(() =>
  typeof props.modelValue === 'number' && props.modelValue > 0 ? props.modelValue : ''
)
const selectedIds = computed<number[]>(() =>
  Array.isArray(props.modelValue) ? props.modelValue : []
)
const selectedUsers = computed(() =>
  options.value.filter(u => selectedIds.value.includes(u.id))
)
const filteredOptions = computed(() => {
  const kw = searchText.value.trim().toLowerCase()
  if (!kw) return options.value
  return options.value.filter(u =>
    u.display_name.toLowerCase().includes(kw) ||
    u.username.toLowerCase().includes(kw) ||
    (u.position || '').toLowerCase().includes(kw)
  )
})

async function load() {
  loading.value = true
  try {
    const r = await getUserOptions(props.roles)
    if (r.data?.success) {
      options.value = r.data.data || []
      emit('options-loaded', options.value)
    }
  } catch (e) {
    console.error('UserSelect load error:', e)
  } finally {
    loading.value = false
  }
}

function onSingleChange(e: Event) {
  const val = Number((e.target as HTMLSelectElement).value)
  emit('update:modelValue', val || 0)
}

function onToggle(id: number) {
  const cur = new Set(selectedIds.value)
  if (cur.has(id)) cur.delete(id)
  else cur.add(id)
  emit('update:modelValue', Array.from(cur))
}

// 0820 点击组件外部关闭面板
function onClickOutside(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) open.value = false
}

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))

watch(() => props.roles, load, { immediate: true })
</script>
