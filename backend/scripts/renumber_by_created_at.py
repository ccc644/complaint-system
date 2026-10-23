# -*- coding: utf-8 -*-
"""1019 工单编号重排：编号日期段改为「录入系统的时间」。

规则：KS-YYYYMMDD-NNN 的日期段取 complaints.created_at（真实录入时刻）的日期，
      同一日期内按 (created_at, id) 顺序重新编号，并从该日期已有最大序号之后续排。
      客诉发生时间 occurred_at 不参与编号。

同步更新所有引用旧单号的位置：
  - 各表中 complaint_no 列（通知/知识库/钉钉日志/评价/AI采纳/归档等）；
  - work_order_log / work_order_log_archive 的 detail 文本；
  - knowledge_base 的 title / lesson_learned；
  - complaints.linked_complaint_ids（JSON 里的 no 字段）。

用法（后端已停止状态下，backend 目录执行）：
    python scripts/renumber_by_created_at.py --dry-run
    python scripts/renumber_by_created_at.py
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import get_conn  # noqa: E402

KS_RE = re.compile(r"^KS-(\d{8})-(\d+)$")


def _parse(no: str):
    m = KS_RE.match(no or "")
    return (m.group(1), int(m.group(2))) if m else (None, None)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="按录入时间重排工单编号并同步引用")
    ap.add_argument("--dry-run", action="store_true", help="只打印将发生的变更，不写库")
    args = ap.parse_args()

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, complaint_no, created_at, occurred_at FROM complaints ORDER BY created_at, id"
        ).fetchall()

        # 找出编号日期段与录入日期不一致的工单
        affected = []
        for r in rows:
            no_date, _seq = _parse(r["complaint_no"])
            created = r["created_at"]
            created_date = (created.strftime("%Y%m%d") if hasattr(created, "strftime")
                            else str(created)[:10].replace("-", ""))
            if no_date and no_date != created_date:
                affected.append((r, created_date))

        if not affected:
            print("无需重排：所有工单编号日期段已与录入时间一致。")
            return 0

        # 每个目标日期从当前已有最大序号开始续排（排除待重排的工单）
        affected_ids = {r["id"] for r, _ in affected}
        next_seq: dict[str, int] = {}
        for r in rows:
            no_date, seq = _parse(r["complaint_no"])
            if no_date and r["id"] not in affected_ids:
                next_seq[no_date] = max(next_seq.get(no_date, 0), seq)

        mapping = []  # (old, new, row)
        for r, d in affected:
            next_seq[d] = next_seq.get(d, 0) + 1
            mapping.append((r["complaint_no"], f"KS-{d}-{next_seq[d]:03d}", r))

        print(f"将重排 {len(mapping)} 条工单：")
        print(f"{'旧编号':<18} {'新编号':<18} {'录入时间':<21} {'客诉发生时间'}")
        print("-" * 78)
        for old, new, r in mapping:
            print(f"{old:<18} {new:<18} {str(r['created_at'])[:19]:<21} {str(r['occurred_at'] or '—')[:19]}")

        if args.dry_run:
            print("\n[dry-run] 未写库。")
            return 0

        # ① 先改成临时编号，避免唯一约束冲突
        for old, _new, _r in mapping:
            conn.execute(
                "UPDATE complaints SET complaint_no = %s WHERE complaint_no = %s",
                (f"TMP-{old}", old),
            )

        # ② 写最终编号
        for old, new, _r in mapping:
            conn.execute(
                "UPDATE complaints SET complaint_no = %s WHERE complaint_no = %s",
                (new, f"TMP-{old}"),
            )

        # ③ 同步各表 complaint_no 列（动态发现，排除主表）
        tables = [t["table_name"] for t in conn.execute(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema='public' AND column_name='complaint_no' "
            "AND table_name <> 'complaints'"
        ).fetchall()]
        for old, new, _r in mapping:
            for t in tables:
                conn.execute(
                    f'UPDATE "{t}" SET complaint_no = %s WHERE complaint_no = %s', (new, old)
                )

        # ④ 文本/JSON 里的旧单号替换（加右边界，防止 KS-...-001 误伤 KS-...-0010）
        text_targets = [
            ("work_order_log", "detail"),
            ("work_order_log_archive", "detail"),
            ("knowledge_base", "title"),
            ("knowledge_base", "lesson_learned"),
            ("complaints", "linked_complaint_ids"),
        ]
        existing = {(r["table_name"], r["column_name"]) for r in conn.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='public'"
        ).fetchall()}
        for old, new, _r in mapping:
            pattern = old + r"(?!\d)"
            for t, c in text_targets:
                if (t, c) not in existing:
                    continue
                sql = f'UPDATE "{t}" SET "{c}" = regexp_replace("{c}", %s, %s, \'g\')'
                conn.execute(sql, (pattern, new))

        conn.commit()
        print(f"\n完成：重排 {len(mapping)} 条，引用表 {len(tables)} 个 + 文本字段已同步。")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
