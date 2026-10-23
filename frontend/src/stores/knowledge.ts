// 0727 Phase 3 知识库 Pinia Store
import { ref, reactive } from 'vue'
import { defineStore } from 'pinia'
import * as kbApi from '@/api/knowledge'
import type { KBEntry } from '@/types/api'

export const useKnowledgeStore = defineStore('knowledge', () => {
  const results = ref<KBEntry[]>([])
  const loading = ref(false)
  const page = ref(1)
  const pageSize = ref(20)
  const total = ref(0)

  const searchParams = reactive({
    keyword: '',
    category: '',
    qualityFilter: '',
    sortBy: '',
  })

  const qualityStats = ref<any>(null)
  const topValuable = ref<KBEntry[]>([])
  const needsReview = ref<KBEntry[]>([])
  const staleEntries = ref<KBEntry[]>([])

  async function search() {
    loading.value = true
    try {
      const r = await kbApi.searchKb({
        keyword: searchParams.keyword,
        category: searchParams.category,
        quality_filter: searchParams.qualityFilter,
        sort_by: searchParams.sortBy,
        page: page.value,
        page_size: pageSize.value,
      })
      if (r.data?.success) {
        results.value = r.data.data || []
        total.value = r.data.pagination?.total || 0
      }
    } catch (e: any) {
      console.error('searchKb error:', e)
    } finally { loading.value = false }
  }

  async function createEntry(data: any) {
    const r = await kbApi.createKbEntry(data)
    return r.data
  }

  async function voteUseful(id: number) {
    const r = await kbApi.voteUseful(id)
    return r.data?.success
  }

  async function voteUnhelpful(id: number) {
    const r = await kbApi.voteUnhelpful(id)
    return r.data?.success
  }

  async function voteDimension(id: number, dimension: string) {
    const r = await kbApi.voteDimension(id, dimension)
    return r.data?.success
  }

  async function fetchQualityStats() {
    const r = await kbApi.getKbQualityStats()
    if (r.data?.success) {
      qualityStats.value = r.data.data?.stats
      topValuable.value = r.data.data?.top_valuable || []
      needsReview.value = r.data.data?.needs_review || []
      staleEntries.value = r.data.data?.stale || []
    }
  }

  // 0729 管理员删除知识条目
  async function deleteEntry(id: number) {
    const r = await kbApi.deleteKbEntry(id)
    return r.data?.success
  }

  return {
    results, loading, page, pageSize, total, searchParams,
    qualityStats, topValuable, needsReview, staleEntries,
    search, createEntry, voteUseful, voteUnhelpful, voteDimension, fetchQualityStats,
    deleteEntry,
  }
})
