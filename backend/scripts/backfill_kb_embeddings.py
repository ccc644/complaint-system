# -*- coding: utf-8 -*-
"""0908 RAG 阶段 1：knowledge_base 向量回填脚本（幂等、可续跑、分批限速）

用法（在 backend 目录下）：
    python scripts/backfill_kb_embeddings.py [--dry-run]

回填范围：embedding IS NULL 或 embed_model != 当前配置模型（换模型全量重刷，
docs/05-RAG混合检索与Agent升级探索.md §4.4 红线：不同模型的向量不可比）。

前置条件：
    - pgvector 扩展已安装且 init_db 已建列（应用启动一次即可）
    - backend/.env 已配置 EMBEDDING_API_KEY
失败行为：某批 API 失败即中止并提示（已写入的行保留，重跑自动跳过）。
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import EMBEDDING_BATCH_SIZE

BATCH_SLEEP_SECONDS = 1.0


def main() -> int:
    parser = argparse.ArgumentParser(description="KB 向量回填（幂等可续跑）")
    parser.add_argument("--dry-run", action="store_true", help="只列出待回填行数，不调用 API")
    args = parser.parse_args()

    from ai_engine import embedding
    from data.database import list_kb_missing_embedding, update_kb_embedding, is_pgvector_enabled
    from ai_engine.ai_engine import kb_embed_text

    if not is_pgvector_enabled():
        print("[1/3] pgvector 未启用（扩展未安装或 embedding 列缺失），无可回填。")
        print("      启用步骤见 docs/04-部署与运维手册.md §2.6；启用后先启动一次应用执行 init_db。")
        return 1
    if not embedding.is_configured():
        print("[1/3] EMBEDDING_API_KEY 未配置（backend/.env），无法生成向量。")
        return 1

    model = embedding.get_embed_model()
    rows = list_kb_missing_embedding(model)
    print(f"[1/3] 当前模型 {model}；待回填 {len(rows)} 条（含向量缺失与模型不一致的行）")
    if not rows:
        print("=" * 50)
        print("无需回填，全部就绪。")
        return 0
    if args.dry_run:
        for r in rows:
            print(f"  - KB#{r['id']} {r['title'][:40]}")
        print("[dry-run] 未调用 API，未写入。")
        return 0

    done = failed = 0
    for i in range(0, len(rows), EMBEDDING_BATCH_SIZE):
        batch = rows[i:i + EMBEDDING_BATCH_SIZE]
        texts = [kb_embed_text(r) for r in batch]
        vecs = embedding.embed_texts(texts, triggered_by="backfill")
        if not vecs:
            print(f"[2/3] 第 {i // EMBEDDING_BATCH_SIZE + 1} 批 API 失败，中止"
                  f"（已完成 {done} 条保留，重跑自动续传）。")
            failed = len(rows) - done
            break
        for r, v in zip(batch, vecs):
            if update_kb_embedding(r["id"], v, model):
                done += 1
            else:
                failed += 1
        print(f"[2/3] 进度 {min(i + EMBEDDING_BATCH_SIZE, len(rows))}/{len(rows)}")
        if i + EMBEDDING_BATCH_SIZE < len(rows):
            time.sleep(BATCH_SLEEP_SECONDS)

    remain = len(list_kb_missing_embedding(model))
    print("=" * 50)
    print(f"[3/3] 回填完成：成功 {done} / 失败 {failed} / 剩余待补 {remain}")
    return 0 if (failed == 0 and remain == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
