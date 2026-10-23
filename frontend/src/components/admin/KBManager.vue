<!-- 0729 管理员知识库管理 — 表格列表 + 搜索筛选 + 删除 -->
<template>
  <div class="space-y-4">
    <!-- 筛选栏 -->
    <div class="bg-white rounded-lg border border-gray-200 p-4 flex flex-wrap items-end gap-3">
      <div>
        <label class="text-xs text-gray-500 mb-1 block">关键词搜索</label>
        <div class="flex gap-2">
          <input v-model="keyword" @keyup.enter="search" placeholder="搜索标题/关键词/根因/方案..."
            class="px-3 py-1.5 border border-gray-300 rounded-base text-sm w-72 focus:ring-2 focus:ring-primary/30" />
          <button @click="search" class="px-3 py-1.5 bg-primary text-white rounded-base text-sm hover:bg-primary/90 transition">
            🔍 搜索
          </button>
        </div>
      </div>
      <div>
        <label class="text-xs text-gray-500 mb-1 block">故障类别</label>
        <select v-model="category" @change="search"
          class="px-3 py-1.5 border border-gray-300 rounded-base text-sm bg-white">
          <option value="">全部类别</option>
          <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
        </select>
      </div>
      <span class="text-xs text-gray-400 ml-auto">{{ total }} 条知识条目</span>
    </div>

    <!-- 表格 -->
    <div class="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div v-if="loading" class="p-8 text-center text-gray-400">加载中...</div>
      <table v-else class="w-full text-sm">
        <thead>
          <tr class="bg-gray-50 border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wider">
            <th class="px-4 py-3 w-12">ID</th>
            <th class="px-4 py-3">标题</th>
            <th class="px-4 py-3 w-20">类别</th>
            <th class="px-4 py-3 w-24">设备型号</th>
            <th class="px-4 py-3 w-16 text-center">👍</th>
            <th class="px-4 py-3 w-16 text-center">👎</th>
            <th class="px-4 py-3 w-36">创建时间</th>
            <th class="px-4 py-3 w-20 text-center">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in entries" :key="entry.id"
            class="border-b border-gray-100 hover:bg-gray-50/50 transition">
            <td class="px-4 py-2.5 text-gray-400 mono text-xs">{{ entry.id }}</td>
            <td class="px-4 py-2.5">
              <div class="font-medium text-gray-800 truncate max-w-xs" :title="entry.title">{{ entry.title }}</div>
            </td>
            <td class="px-4 py-2.5">
              <span v-if="entry.fault_category" class="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded">{{ entry.fault_category }}</span>
            </td>
            <td class="px-4 py-2.5 text-gray-500 text-xs">{{ entry.equipment_model || '-' }}</td>
            <td class="px-4 py-2.5 text-center text-gray-500">{{ entry.useful_count }}</td>
            <td class="px-4 py-2.5 text-center text-gray-500">{{ entry.unhelpful_count }}</td>
            <td class="px-4 py-2.5 text-gray-400 mono text-xs">{{ formatDate(entry.created_at) }}</td>
            <td class="px-4 py-2.5 text-center">
              <button @click="confirmDelete(entry)"
                class="text-xs text-red-500 hover:text-red-700 hover:underline transition"
                title="删除知识条目">删除</button>
            </td>
          </tr>
          <tr v-if="entries.length === 0">
            <td colspan="8" class="px-4 py-8 text-center text-gray-400">暂无数据</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 分页 -->
    <div v-if="total > 0" class="flex items-center justify-between text-sm text-gray-500">
      <div class="flex items-center gap-1">
        <span>每页</span>
        <select v-model="pageSize" @change="search" class="px-2 py-0.5 border border-gray-300 rounded text-xs">
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
        </select>
        <span>条</span>
      </div>
      <div class="flex items-center gap-2">
        <button @click="page--; search()" :disabled="page <= 1"
          class="px-3 py-1 border border-gray-300 rounded text-xs disabled:opacity-40 hover:bg-gray-50 transition">上一页</button>
        <span>{{ page }} / {{ Math.ceil(total / pageSize) || 1 }}</span>
        <button @click="page++; search()" :disabled="page >= Math.ceil(total / pageSize)"
          class="px-3 py-1 border border-gray-300 rounded text-xs disabled:opacity-40 hover:bg-gray-50 transition">下一页</button>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <ConfirmDialog
      :visible="!!deleteTarget"
      title="删除知识条目"
      :message="deleteTarget ? `确定要删除知识条目「${(deleteTarget as any).title}」吗？此操作不可恢复。` : ''"
      @confirm="doDelete"
      @cancel="deleteTarget = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { searchKb, deleteKbEntry } from '@/api/knowledge'
import type { KBEntry } from '@/types/api'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const CATEGORIES = ['机械', '电气', '工艺', '光学', '软件', '其他']

const entries = ref<KBEntry[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const category = ref('')

const deleteTarget = ref<KBEntry | null>(null)

async function search() {
  loading.value = true
  try {
    const r = await searchKb({
      keyword: keyword.value,
      category: category.value,
      page: page.value,
      page_size: pageSize.value,
    })
    if (r.data?.success) {
      entries.value = r.data.data || []
      total.value = r.data.pagination?.total || 0
    }
  } catch (e: any) {
    console.error('KBManager search error:', e)
  } finally { loading.value = false }
}

function confirmDelete(entry: KBEntry) {
  deleteTarget.value = entry
}

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await deleteKbEntry(deleteTarget.value.id)
    deleteTarget.value = null
    search()
  } catch (e: any) {
    console.error('KBManager delete error:', e)
  }
}

function formatDate(d: string) {
  if (!d) return '-'
  return d.slice(0, 16).replace('T', ' ')
}

onMounted(() => { search() })
</script>
