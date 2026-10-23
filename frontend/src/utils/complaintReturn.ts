// 0901 退回来源解析 — 区分「主管退回」与「办理人退回」
// 约定：办理人退回时 supervisor_rejection_note 存为「办理人 姓名：原因」（handler_reject 写入），
// 主管退回为裸原因（supervisor_intake_review 写入，格式不变）。
// 看板卡片 / 编辑弹窗 / 详情页统一经此解析展示，避免来源混淆。
export interface ReturnNoteInfo {
  sourceLabel: string  // 标题用：「主管退回修改」/「办理人 张三 退回修改」
  reasonLabel: string  // 前缀用：「主管退回原因」/「办理人 张三 退回原因」
  reason: string       // 裸原因
}

export function parseReturnNote(note: string | null | undefined): ReturnNoteInfo | null {
  if (!note) return null
  const m = note.match(/^办理人 (.+?)：/)
  if (m) {
    return {
      sourceLabel: `办理人 ${m[1]} 退回修改`,
      reasonLabel: `办理人 ${m[1]} 退回原因`,
      reason: note.slice(m[0].length),
    }
  }
  return { sourceLabel: '主管退回修改', reasonLabel: '主管退回原因', reason: note }
}
