# -*- coding: utf-8 -*-
"""0824 SQLite → PostgreSQL 数据迁移脚本（方案 P8）

用法（在 backend 目录下）：
    python scripts/migrate_sqlite_to_pg.py [--sqlite ../data/complaints.db] [--force]

前置条件：
    - PG 已启动；backend/.env 已配置 DATABASE_URL（complaint 账号连接 complaint_db）
    - 目标 PG 库表需为空（脚本自动 init_db 建结构；非空须 --force TRUNCATE 清空重导）

行为：
    1. 预检：SQLite 源文件存在、DATABASE_URL 可连、目标表为空（或 --force）
    2. 调 init_db()/init_users() 建结构（幂等，含 search_tsv 生成列 + GIN 索引）
    3. 按 FK 安全序复制 17 张业务表（users → complaints → ... → system_settings）
    4. TIMESTAMP 列空串 '' → NULL；其余列原样透传；knowledge_base 排除 search_tsv 生成列
    5. 每表 setval 对齐自增序列 + 行数断言（不一致即中止并报明细）
    6. 汇总打印（各表行数、complaint_no 清单、唯一性抽查）

安全：SQLite 源全程只读（mode=ro），迁移失败回滚 = 重建 PG schema 重新导入。
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── 17 张业务表，按外键依赖序复制 ──────────────────────────────
TABLE_ORDER = [
    "users",
    "complaints",
    "knowledge_base",
    "progress_updates",
    "work_order_log",
    "work_order_log_archive",
    "attachments",
    "notifications",
    "kb_feedback_log",
    "user_feedback",
    "case_feedback",
    "complaint_assignees",
    "ai_adoption_log",
    "user_activity_log",
    "sus_survey",
    "llm_call_log",
    "system_settings",
]


def get_pg_conn():
    """复用 database.get_conn()（含 dict_row + 时间戳 Loader + 懒加载 .env）。"""
    from data.database import get_conn
    return get_conn()


def get_sqlite_conn(path: str):
    """只读打开 SQLite 源（text_factory=str 保证中文/编码透传）。"""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.text_factory = str
    return conn


def get_columns(sqlite_conn, pg_conn, table: str):
    """取列清单：SQLite 与 PG 列名交集（按 PG 顺序），排除 search_tsv 生成列。
    返回 (cols, ts_cols)，ts_cols 为 PG 侧 timestamp 类型列名集合。"""
    sqlite_cols = {r[1] for r in sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()}
    pg_rows = pg_conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = %s ORDER BY ordinal_position",
        (table,),
    ).fetchall()
    cols = []
    ts_cols = set()
    for r in pg_rows:
        name = r["column_name"]
        if name == "search_tsv":      # 生成列：排除，由 PG 自动重算
            continue
        if name not in sqlite_cols:
            continue
        cols.append(name)
        if r["data_type"].startswith("timestamp"):
            ts_cols.add(name)
    return cols, ts_cols


def copy_table(sqlite_conn, pg_conn, table: str, cols: list, ts_cols: set, batch: int = 500) -> int:
    """复制单表数据。TIMESTAMP 列 '' → NULL；其余原样。返回复制行数。"""
    rows = sqlite_conn.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    if not rows:
        return 0

    def _convert(r):
        if not ts_cols:
            return tuple(r)
        return tuple(None if (i in ts_idx and (v == "" or v is None)) else v
                     for i, v in enumerate(r))

    ts_idx = {cols.index(c) for c in ts_cols}
    converted = [_convert(r) for r in rows]

    insert = (
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(['%s'] * len(cols))})"
    )
    with pg_conn.cursor() as cur:
        for i in range(0, len(converted), batch):
            cur.executemany(insert, converted[i:i + batch])
    return len(rows)


def setval_sequences(pg_conn, table: str):
    """对齐自增序列（BIGINT IDENTITY → 当前 MAX(id)）。无 id 列的表（system_settings）跳过。"""
    has_id = pg_conn.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = 'id'",
        (table,),
    ).fetchone()
    if not has_id:
        return
    max_id = pg_conn.execute(f"SELECT COALESCE(MAX(id), 0) AS m FROM {table}").fetchone()["m"]
    if max_id:
        pg_conn.execute(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), %s, true)",
            (table, max_id),
        ).fetchone()


def assert_row_counts(sqlite_conn, pg_conn) -> list[tuple[str, int, int]]:
    """逐表行数断言，返回 (表名, SQLite 行数, PG 行数) 明细。"""
    detail = []
    for t in TABLE_ORDER:
        s = sqlite_conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        p = pg_conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
        detail.append((t, s, p))
        if s != p:
            raise AssertionError(f"行数不一致 {t}: SQLite={s} PG={p}")
    return detail


def check_pg_state(pg_conn) -> list[str]:
    """init_db 前预检：返回已存在且含数据的表列表（表可能尚未创建）。"""
    non_empty = []
    for t in TABLE_ORDER:
        exists = pg_conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = %s", (t,)
        ).fetchone()
        if exists:
            c = pg_conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"]
            if c:
                non_empty.append(f"{t}({c})")
    return non_empty


def main():
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL 数据迁移")
    parser.add_argument("--sqlite", default=None, help="SQLite 源文件路径（默认 ../data/complaints.db）")
    parser.add_argument("--force", action="store_true", help="目标 PG 非空时 TRUNCATE CASCADE 清空重导")
    args = parser.parse_args()

    default_sqlite = str(Path(__file__).resolve().parent.parent.parent / "data" / "complaints.db")
    sqlite_path = args.sqlite or default_sqlite
    if not os.path.exists(sqlite_path):
        print(f"[错误] SQLite 源文件不存在: {sqlite_path}")
        sys.exit(1)

    print(f"[1/6] 打开 SQLite 源（只读）: {sqlite_path}")
    sqlite_conn = get_sqlite_conn(sqlite_path)

    print("[2/6] 连接 PG（DATABASE_URL from backend/.env）...")
    try:
        pg_conn = get_pg_conn()
    except Exception as e:
        print(f"[错误] PG 连接失败（检查 backend/.env 的 DATABASE_URL）: {e}")
        sys.exit(1)

    # 预检必须在 init_db 之前（init_db 会写入 admin 用户与 v3 迁移标记，属正常结构初始化）
    non_empty = check_pg_state(pg_conn)
    # 0824 锁教训：预检 SELECT 在事务中持有 AccessShareLock，会阻塞 init_db 的
    # ALTER TABLE（需 ACCESS EXCLUSIVE）→ 预检后立即释放事务
    pg_conn.rollback()
    if non_empty and not args.force:
        print(f"[错误] 目标 PG 已含数据（{', '.join(non_empty)}），"
              f"确认清空后重跑或加 --force")
        sys.exit(1)

    print("[3/6] init_db()/init_users() 建结构（幂等）...")
    from data.database import init_db, init_users
    init_db()
    init_users()

    if non_empty and args.force:
        print(f"  目标 PG 非空（{', '.join(non_empty)}），--force 清空重导...")
        # 单条 TRUNCATE 全表 CASCADE：无 FK 的表（notifications/user_feedback/archive）也一并清空
        pg_conn.execute(f"TRUNCATE {', '.join(TABLE_ORDER)} CASCADE")
        pg_conn.commit()

    # init 产生的默认数据（init_users 的 admin / init_db 的 v3 迁移标记）与 SQLite 源重复，
    # 复制前清除，改由源库数据导入（--force 已清空时为 no-op）
    pg_conn.execute("DELETE FROM users WHERE username = 'admin'")
    pg_conn.execute("DELETE FROM system_settings WHERE key = 'v3_role_migration_done'")
    pg_conn.commit()

    print("[4/6] 按 FK 安全序复制 17 张表...")
    for t in TABLE_ORDER:
        cols, ts_cols = get_columns(sqlite_conn, pg_conn, t)
        n = copy_table(sqlite_conn, pg_conn, t, cols, ts_cols)
        setval_sequences(pg_conn, t)
        print(f"  {t}: {n} 行（列 {len(cols)}：{', '.join(cols[:6])}{'...' if len(cols) > 6 else ''}）")
    pg_conn.commit()

    print("[5/6] 行数断言...")
    detail = assert_row_counts(sqlite_conn, pg_conn)
    print("  全部一致 OK")

    print("[6/6] 汇总")
    print("=" * 50)
    for t, s, p in detail:
        print(f"  {t}: SQLite {s} → PG {p}")
    # 唯一性抽查（UNIQUE 约束已保证插入成功即唯一，此处仅打印工单清单）
    nos = [r["complaint_no"] for r in pg_conn.execute(
        "SELECT complaint_no FROM complaints ORDER BY id"
    ).fetchall()]
    print(f"  工单清单（{len(nos)} 条）: {', '.join(nos)}")
    users = pg_conn.execute("SELECT username, role FROM users ORDER BY id").fetchall()
    print(f"  用户（{len(users)} 个）: {', '.join(u['username'] + '(' + u['role'] + ')' for u in users)}")
    print("=" * 50)
    print("迁移完成。SQLite 源未做任何修改（回滚 = 重建 PG schema 重新导入）。")

    sqlite_conn.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
