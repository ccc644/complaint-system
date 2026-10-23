// 0914 日期时间展示工具 — ISO「2026-09-14T10:30」→「2026-09-14 10:30」
// （与 ComplaintTable/KBManager 既有本地 formatDate 同口径，供排期时间等处复用）
export function formatDateTime(d?: string | null): string {
  if (!d) return ''
  return d.slice(0, 16).replace('T', ' ')
}
