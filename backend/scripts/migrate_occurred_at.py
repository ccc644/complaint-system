# -*- coding: utf-8 -*-
"""1019 一次性迁移：拆分「客诉发生时间」与「系统录入时间」。

背景：此前批量导入把 Excel 的提出日期直接写进 complaints.created_at，导致
      「创建时间」显示的是客诉发生日期，真实录入时刻只留在工单日志里。

迁移内容：
  1) 新增 complaints.occurred_at（幂等）；
  2) 存量 occurred_at = 原 created_at（原值实际是客诉发生日期）；
  3) created_at 用 work_order_log 中最早的 created 事件时间回填为真实录入时刻
     （无 created 日志的工单保持原值）。

用法（后端已停止状态下，backend 目录执行）：
    python scripts/migrate_occurred_at.py --dry-run   # 只预览，不提交
    python scripts/migrate_occurred_at.py             # 执行并提交
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import get_conn  # noqa: E402

PREVIEW_LIMIT = 20

# 工单号 → (原 created_at, 创建日志真实时刻)
_SELECT = """
SELECT c.id, c.complaint_no, c.created_at,
       (SELECT MIN(l.created_at) FROM work_order_log l
         WHERE l.complaint_id = c.id AND l.event_type = 'created') AS real_created
FROM complaints c
ORDER BY c.id
"""


def _fmt(v):
    if not v:
        return "—"
    return v.strftime("%Y-%m-%d %H:%M:%S") if hasattr(v, "strftime") else str(v)[:19]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台中文输出
    ap = argparse.ArgumentParser(description="拆分客诉发生时间与系统录入时间")
    ap.add_argument("--dry-run", action="store_true", help="只打印变更预览，不写库")
    args = ap.parse_args()

    conn = get_conn()
    try:
        conn.execute("ALTER TABLE complaints ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMP")

        rows = conn.execute(_SELECT).fetchall()
        need_backfill = sum(1 for r in rows if r["real_created"])
        print(f"工单共 {len(rows)} 条；其中 {need_backfill} 条可用创建日志回填真实录入时间。")
        print(f"{'工单号':<20} {'原 created_at':<21} {'→ occurred_at':<21} {'→ created_at(回填)':<21}")
        print("-" * 88)
        for r in rows[:PREVIEW_LIMIT]:
            old = r["created_at"]
            real = r["real_created"]
            print(f"{r['complaint_no']:<20} {_fmt(old):<21} {_fmt(old):<21} {_fmt(real or old):<21}")
        if len(rows) > PREVIEW_LIMIT:
            print(f"... 其余 {len(rows) - PREVIEW_LIMIT} 条同理")

        if args.dry_run:
            print("\n[dry-run] 未写库。去掉 --dry-run 执行迁移。")
            return 0

        # 1) 原 created_at（客诉发生日期）→ occurred_at
        conn.execute(
            "UPDATE complaints SET occurred_at = created_at WHERE occurred_at IS NULL"
        )
        # 2) 真实录入时刻回填 created_at（取最早的 created 事件）
        updated = conn.execute(
            """
            UPDATE complaints c
               SET created_at = l.real_created
              FROM (SELECT complaint_id, MIN(created_at) AS real_created
                      FROM work_order_log
                     WHERE event_type = 'created'
                     GROUP BY complaint_id) l
             WHERE l.complaint_id = c.id
               AND l.real_created IS NOT NULL
               AND c.created_at IS DISTINCT FROM l.real_created
            RETURNING c.id
            """
        ).fetchall()
        conn.execute(
            "UPDATE complaints SET occurred_at = created_at WHERE occurred_at IS NULL"
        )
        conn.commit()
        print(f"\n完成：occurred_at 已补齐；created_at 按创建日志回填 {len(updated)} 条。")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
