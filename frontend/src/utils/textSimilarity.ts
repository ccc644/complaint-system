// 0902 AI 采纳埋点 — 字段级文本匹配度（bigram Dice 相似度，0-100）
// 口径：AI 建议文本与用户实际提交文本的重复比例；≥ AI_ADOPTION_MATCH_THRESHOLD 记为采纳。
// 0902 用户确认：阈值先按 60（改此一处即可，前后端说明文字引用同一数值时需同步）。
// 阈值仅在此处定义（前端判定 adopted，后端只存结果）。
export const AI_ADOPTION_MATCH_THRESHOLD = 60

function normalize(s: string): string {
  return s.trim().replace(/\s+/g, '').toLowerCase()
}

function bigrams(s: string): string[] {
  if (s.length <= 1) return s.length ? [s] : []
  const out: string[] = []
  for (let i = 0; i < s.length - 1; i++) out.push(s.slice(i, i + 2))
  return out
}

/** 字符 bigram Dice 系数 ×100；归一化后完全相等=100，单字且不等=0（避免空集除零）。 */
export function bigramDice(a: string, b: string): number {
  const na = normalize(a)
  const nb = normalize(b)
  if (!na || !nb) return 0
  if (na === nb) return 100
  if (na.length < 2 || nb.length < 2) return 0
  const A = bigrams(na)
  const B = bigrams(nb)
  const count = new Map<string, number>()
  A.forEach(g => count.set(g, (count.get(g) || 0) + 1))
  let inter = 0
  B.forEach(g => {
    const c = count.get(g) || 0
    if (c > 0) {
      inter++
      count.set(g, c - 1)
    }
  })
  return Math.round((2 * inter * 100) / (A.length + B.length))
}
