# -*- coding: utf-8 -*-
"""0909 检索种子集回放对比脚本（只读调参度量衡；docs/05 §5.6「回归种子集回放」落地）

用法（在 backend 目录下）：
    python scripts/replay_retrieval_seed.py                          # strict 口径三通道对照
    python scripts/replay_retrieval_seed.py --save                   # 同上，另存 JSON 报告
    python scripts/replay_retrieval_seed.py --relax                  # hybrid 用四级级联（semantic_search_kb 召回口径）
    python scripts/replay_retrieval_seed.py --with-llm               # 附加 semantic_search_kb 全链路（实调 DeepSeek，慢）
    python scripts/replay_retrieval_seed.py --top-k 10               # 判定截断条数（默认 5）
    python scripts/replay_retrieval_seed.py --compare A.json B.json  # 对比两份报告（配置 diff + 指标 + 翻转）

种子集 backend/data/retrieval_seed.jsonl（一行一查询，# 注释行与空行忽略）：
    expect_ids   必须全部出现在 top-k（否则 miss）；空数组 = 期望检索为空（防误报）
    tolerate_ids 允许出现但不计噪音的已知边界 id
    category     预留故障类别（空 = 全类别检索）
判定口径：默认 strict（relax=False，与 find_similar_cases 直出路径同构——阈值类参数的
变化在此口径直接可见，不被级联放宽掩盖）；--relax 时空期望查询跳过空集判定（该口径
设计上允许级联弱候选，靠 LLM 精排滤）。
--with-llm 列为信息展示、不影响退出码：semantic_search_kb 存在「LLM 判空后仍用粗筛
候选补足 top_k」的已知边界（0908 CHANGELOG 备注），无关查询可能带出弱候选，每次回放
使其可见。
退出码：keyword/vector/hybrid 判定全 ✓ 且无非 tolerate 噪音 → 0，否则 1（可挂回归）。

副作用（与生产检索一致，非业务数据写入）：向量通道每查询 1 次 embedding API 调用；
llm_call_log 记 embedding_api / semantic_search_kb 行；--with-llm 每查询多 1 次 DeepSeek。
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_SEED = os.path.join(_BASE, "data", "retrieval_seed.jsonl")
REPORT_DIR = os.path.join(_BASE, "data", "replay_reports")

CHANNELS = ("keyword", "vector", "hybrid")
_SCORE_KEYS = ("keyword_score", "vector_score", "rrf_score")


def _reconfigure_stdout():
    # Windows 管道/重定向下默认 GBK，中文会乱码（交互控制台走宽字符 API 不受影响）
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def load_seeds(path: str) -> list[dict]:
    seeds = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"种子文件第 {line_no} 行 JSON 解析失败：{e}")
                sys.exit(2)
            if not str(d.get("query", "")).strip():
                print(f"种子文件第 {line_no} 行缺少 query 字段")
                sys.exit(2)
            d.setdefault("id", line_no)
            d.setdefault("category", "")
            d.setdefault("expect_ids", [])
            d.setdefault("tolerate_ids", [])
            d.setdefault("note", "")
            d.setdefault("source", "")
            seeds.append(d)
    return seeds


def build_report_header(relax: bool, with_llm: bool, top_k: int,
                        seed_path: str, seed_count: int) -> dict:
    from core import config as cfg
    from data.database import is_pgvector_enabled
    from ai_engine import embedding
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": {"caliber": "relax" if relax else "strict", "relax": relax,
                 "with_llm": with_llm, "top_k": top_k},
        "seed_file": os.path.relpath(seed_path, _BASE),
        "seed_count": seed_count,
        "config": {
            "FTS5_KEYWORD_MATCH_THRESHOLD": cfg.FTS5_KEYWORD_MATCH_THRESHOLD,
            "KEYWORD_DOMAIN_WORD_WEIGHT": cfg.KEYWORD_DOMAIN_WORD_WEIGHT,
            "VECTOR_MIN_SIMILARITY": cfg.VECTOR_MIN_SIMILARITY,
            "VECTOR_SOLO_MIN_SIMILARITY": cfg.VECTOR_SOLO_MIN_SIMILARITY,
            "VECTOR_TOP_K": cfg.VECTOR_TOP_K,
            "FTS5_COARSE_TOP_K": cfg.FTS5_COARSE_TOP_K,
            "RRF_K": cfg.RRF_K,
            "SEMANTIC_SEARCH_TOP_K": cfg.SEMANTIC_SEARCH_TOP_K,
            "SIMILAR_CASES_TOP_K": cfg.SIMILAR_CASES_TOP_K,
            "embed_model": os.environ.get("EMBEDDING_API_MODEL", "BAAI/bge-m3"),
        },
        "vector_channel_available": bool(embedding.is_available() and is_pgvector_enabled()),
    }


def run_query_channels(query: str, category: str, relax: bool,
                       vec_available: bool) -> dict[str, list[dict]]:
    """三通道并列回放：keyword（升级前基线）/ vector（向量单独）/ hybrid（生产混合）。

    复用生产实现（不复制逻辑）：search_kb_by_phenomenon / search_kb_by_vector /
    _embed_query_once（含查询扩展，与生产一致）/ _hybrid_retrieve。通道隔离口径不做
    类别级联回退（级联是 hybrid 层行为；种子 category 为空时无差别）。"""
    from data.database import search_kb_by_phenomenon, search_kb_by_vector
    from ai_engine.ai_engine import _embed_query_once, _hybrid_retrieve
    from core.config import VECTOR_TOP_K

    kw = search_kb_by_phenomenon(query, category_filter=category)

    # 向量通道缺席（无 key / 无 pgvector）时不发起无意义的 embedding API 调用
    qv = _embed_query_once(query) if vec_available else None
    vec = search_kb_by_vector(qv, top_k=VECTOR_TOP_K, category_filter=category) if qv else []

    hyb = _hybrid_retrieve(query, fault_category=category, relax=relax)
    return {"keyword": kw, "vector": vec, "hybrid": hyb}


def run_llm_channel(query: str, category: str, top_k: int) -> list[dict]:
    from ai_engine.ai_engine import semantic_search_kb
    return semantic_search_kb(query, top_k=top_k, fault_category=category)


def judge_channel(rows: list[dict], seed: dict, top_k: int, relax: bool) -> dict:
    """判定：hit = 期望全中且无非容忍噪音；空期望 strict 口径下 = 结果全为容忍 id。
    relax 口径下空期望查询 hit=None（跳过，级联设计上允许弱候选）。"""
    ids = [r.get("id") for r in rows[:top_k] if r.get("id") is not None]
    expect = set(seed["expect_ids"])
    tolerate = set(seed["tolerate_ids"])
    missing = sorted(expect - set(ids))
    noise = sorted(set(ids) - expect - tolerate)
    if not expect and relax:
        hit = None
    else:
        hit = (not missing) and (not noise)
    ranks = {i: ids.index(i) + 1 for i in expect if i in ids}
    return {"ids": ids, "hit": hit, "missing": missing, "noise": noise, "ranks": ranks}


def _absent_judgment() -> dict:
    return {"ids": [], "hit": None, "missing": [], "noise": [], "ranks": {}, "absent": True}


def compact_rows(rows: list[dict], top_k: int) -> list[dict]:
    out = []
    for r in rows[:top_k]:
        d = {"id": r.get("id"), "title": str(r.get("title") or "")[:30]}
        for k in _SCORE_KEYS:
            if k in r:
                d[k] = r[k]
        if "retrieval_channels" in r:
            d["retrieval_channels"] = r["retrieval_channels"]
        out.append(d)
    return out


def status_text(j: dict) -> str:
    if j.get("absent"):
        return "通道缺席，跳过"
    if j["hit"] is None:
        return "－跳过（relax 空期望）"
    if j["hit"]:
        rank = f" rank={min(j['ranks'].values())}" if j["ranks"] else ""
        return f"✓{rank}"
    bits = []
    if j["missing"]:
        bits.append(f"miss={j['missing']}")
    if j["noise"]:
        bits.append(f"噪音={j['noise']}")
    return "✗ " + ",".join(bits)


def fmt_ids(j: dict, rows_map: dict[int, dict]) -> str:
    if not j["ids"]:
        return "(空)"
    parts = []
    for i in j["ids"]:
        r = rows_map.get(i, {})
        sc = []
        for k, fmt in (("rrf_score", "rrf={}"), ("keyword_score", "kw={}"),
                       ("vector_score", "vec={:.3f}")):
            if k in r:
                sc.append(fmt.format(r[k]))
        if r.get("retrieval_channels"):
            sc.append("+".join(r["retrieval_channels"]))
        parts.append(f"#{i}" + ("(" + " ".join(sc) + ")" if sc else ""))
    return " ".join(parts)


def summarize(per_query: list[tuple[dict, dict]], channel: str) -> dict:
    judged = ok = skipped = 0
    top1_n = top1_ok = rank_n = 0
    rank_sum = 0.0
    noise_q = empty_n = empty_ok = empty_skipped = 0
    for seed, js in per_query:
        j = js[channel]
        if j["hit"] is None:
            skipped += 1
            if not seed["expect_ids"]:
                empty_skipped += 1
            continue
        judged += 1
        if j["hit"]:
            ok += 1
        if j["noise"]:
            noise_q += 1
        if seed["expect_ids"]:
            top1_n += 1
            if j["ids"] and j["ids"][0] in set(seed["expect_ids"]):
                top1_ok += 1
            if j["ranks"]:
                rank_sum += min(j["ranks"].values())
                rank_n += 1
        else:
            empty_n += 1
            if not j["noise"]:
                empty_ok += 1
    empty_total = empty_n + empty_skipped
    return {
        "hit_rate": f"{ok}/{judged}",
        "top1_rate": f"{top1_ok}/{top1_n}",
        "avg_rank": round(rank_sum / rank_n, 2) if rank_n else None,
        "noise_queries": noise_q,
        "empty_correct": (f"{empty_ok}/{empty_n}" if empty_n
                          else ("跳过" if empty_skipped else "0/0")),
        "skipped": skipped,
    }


def print_summary(per_query: list[tuple[dict, dict]], header: dict, channels: tuple) -> dict:
    summary = {ch: summarize(per_query, ch) for ch in channels}
    print("═" * 72)
    m = header["mode"]
    print(f"汇总（{m['caliber']} 口径，top_k={m['top_k']}，种子 {header['seed_count']} 条）")
    head = f"{'通道':<8}{'命中':>8}{'首位率':>9}{'平均名次':>9}{'噪音查询':>9}{'空集正确':>10}"
    print(head)
    for ch in channels:
        s = summary[ch]
        avg = s["avg_rank"] if s["avg_rank"] is not None else "-"
        print(f"{ch:<8}{s['hit_rate']:>8}{s['top1_rate']:>9}{avg:>9}"
              f"{s['noise_queries']:>9}{s['empty_correct']:>10}")
    return summary


def run_replay(args) -> int:
    seeds = load_seeds(args.seed)
    if not seeds:
        print(f"种子文件为空：{args.seed}")
        return 2
    header = build_report_header(args.relax, args.with_llm, args.top_k, args.seed, len(seeds))

    cfg = header["config"]
    print("─" * 72)
    print(f"检索种子集回放 | {header['generated_at']} | 口径={header['mode']['caliber']}"
          f" | top_k={args.top_k} | 种子={header['seed_file']}（{len(seeds)} 条）")
    print(f"配置快照：kw阈值={cfg['FTS5_KEYWORD_MATCH_THRESHOLD']} "
          f"词权={cfg['KEYWORD_DOMAIN_WORD_WEIGHT']} "
          f"vec阈值={cfg['VECTOR_MIN_SIMILARITY']} vecTopK={cfg['VECTOR_TOP_K']} "
          f"粗筛TopK={cfg['FTS5_COARSE_TOP_K']} RRF_K={cfg['RRF_K']} "
          f"模型={cfg['embed_model']}")
    if not header["vector_channel_available"]:
        print("⚠ 向量通道缺席（EMBEDDING_API_KEY 未配置或 pgvector 未启用）："
              "vector 列跳过判定，hybrid 行为 = 关键词现状（与生产降级一致）")

    channels = CHANNELS + (("llm",) if args.with_llm else ())
    per_query: list[tuple[dict, dict]] = []
    report_queries = []
    for seed in seeds:
        rows_map_all: dict[str, list[dict]] = {}
        js: dict[str, dict] = {}
        ch_rows = run_query_channels(seed["query"], seed["category"], args.relax,
                                     header["vector_channel_available"])
        rows_map_all.update(ch_rows)
        for ch in CHANNELS:
            if ch == "vector" and not header["vector_channel_available"]:
                js[ch] = _absent_judgment()
            else:
                js[ch] = judge_channel(rows_map_all[ch], seed, args.top_k, args.relax)
        if args.with_llm:
            # 信息展示列：semantic_search_kb 全链路（内部固定 relax 级联 + 判空补足），不计入退出码
            rows_map_all["llm"] = run_llm_channel(seed["query"], seed["category"], args.top_k)
            js["llm"] = judge_channel(rows_map_all["llm"], seed, args.top_k, relax=False)

        per_query.append((seed, js))

        expect_txt = f"期望={seed['expect_ids']}" if seed["expect_ids"] else "期望=空"
        tolerate_txt = f" 容忍={seed['tolerate_ids']}" if seed["tolerate_ids"] else ""
        print(f"[Q{seed['id']:>2}] {seed['query']}    {expect_txt}{tolerate_txt}")
        for ch in channels:
            j = js[ch]
            rows_map = {r.get("id"): r for r in rows_map_all.get(ch, [])[:args.top_k]}
            suffix = "" if ch != "llm" else "（信息展示，不计退出码）"
            print(f"  {ch:<8}: {status_text(j):<20} ids: {fmt_ids(j, rows_map)}{suffix}")
        if seed["note"]:
            print(f"      注：{seed['note']}")

        report_queries.append({
            "id": seed["id"], "query": seed["query"],
            "expect_ids": seed["expect_ids"], "tolerate_ids": seed["tolerate_ids"],
            "note": seed["note"],
            "channels": {ch: {**js[ch],
                              "rows": compact_rows(rows_map_all.get(ch, []), args.top_k)}
                         for ch in channels},
        })

    summary = print_summary(per_query, header, channels)

    bad: list[str] = []
    for seed, js in per_query:
        for ch in CHANNELS:
            if js[ch]["hit"] is False:
                bad.append(f"Q{seed['id']}({ch}) {status_text(js[ch])}")
    print("─" * 72)
    if bad:
        print(f"结论：{len(bad)} 处未过（退出码 1）：")
        for b in bad:
            print(f"  - {b}")
    else:
        print("结论：召回通道判定全绿（退出码 0）")

    if args.save:
        path = args.save
        if path == "AUTO":
            os.makedirs(REPORT_DIR, exist_ok=True)
            path = os.path.join(REPORT_DIR, f"replay_{time.strftime('%Y%m%d_%H%M%S')}.json")
        report = {"header": header, "summary": summary, "queries": report_queries}
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"报告已保存：{path}")
    return 1 if bad else 0


def compare_reports(path_a: str, path_b: str) -> int:
    with open(path_a, encoding="utf-8") as f:
        a = json.load(f)
    with open(path_b, encoding="utf-8") as f:
        b = json.load(f)

    def _meta(r: dict) -> str:
        h, m = r["header"], r["header"]["mode"]
        return (f"{h['generated_at']} | {m['caliber']} 口径 | top_k={m['top_k']} | "
                f"种子 {h['seed_count']} 条")

    print("═" * 72)
    print(f"A：{_meta(a)}  ← {_basename(path_a)}")
    print(f"B：{_meta(b)}  ← {_basename(path_b)}")

    cfg_a, cfg_b = a["header"].get("config", {}), b["header"].get("config", {})
    diffs = [(k, cfg_a.get(k), cfg_b.get(k))
             for k in sorted(set(cfg_a) | set(cfg_b)) if cfg_a.get(k) != cfg_b.get(k)]
    if diffs:
        print("参数变化：")
        for k, va, vb in diffs:
            print(f"  {k}: {va} → {vb}")
    else:
        print("参数无变化（同配置两次运行，差异来自语料变化 / LLM 波动 / 级联）")

    if a["header"]["mode"] != b["header"]["mode"]:
        print(f"⚠ 运行口径不同：A={a['header']['mode']} B={b['header']['mode']}，翻转仅供参考")

    channels = [ch for ch in CHANNELS + ("llm",)
                if ch in a.get("summary", {}) and ch in b.get("summary", {})]
    print("指标对照：")
    print(f"{'通道':<8}{'命中':>14}{'首位率':>15}{'平均名次':>15}{'噪音查询':>13}")
    for ch in channels:
        sa, sb = a["summary"][ch], b["summary"][ch]
        avg_a = sa["avg_rank"] if sa["avg_rank"] is not None else "-"
        avg_b = sb["avg_rank"] if sb["avg_rank"] is not None else "-"
        print(f"{ch:<8}{sa['hit_rate'] + ' → ' + sb['hit_rate']:>14}"
              f"{sa['top1_rate'] + ' → ' + sb['top1_rate']:>15}"
              f"{str(avg_a) + ' → ' + str(avg_b):>15}"
              f"{str(sa['noise_queries']) + ' → ' + str(sb['noise_queries']):>13}")

    qa = {q["id"]: q for q in a.get("queries", [])}
    qb = {q["id"]: q for q in b.get("queries", [])}
    common = [qid for qid in qa if qid in qb]
    only_a = [qid for qid in qa if qid not in qb]
    only_b = [qid for qid in qb if qid not in qa]
    for qid, label in ((only_a, "仅 A 有"), (only_b, "仅 B 有")):
        if qid:
            print(f"⚠ {label}种子：{qid}（种子集变更，比较需人工核对）")

    print("逐查询翻转（命中状态或 id 列表变化）：")
    flips = 0
    for qid in common:
        q1, q2 = qa[qid], qb[qid]
        changed = []
        for ch in channels:
            j1 = q1["channels"].get(ch, {})
            j2 = q2["channels"].get(ch, {})
            if j1.get("ids") != j2.get("ids") or j1.get("hit") != j2.get("hit"):
                def _s(j):
                    return "跳过" if j.get("hit") is None else ("✓" if j.get("hit") else "✗")
                changed.append(f"{ch}: {_s(j1)}{j1.get('ids', [])} → {_s(j2)}{j2.get('ids', [])}")
        if changed:
            flips += 1
            print(f"  [Q{qid}] {q1['query']}")
            for c in changed:
                print(f"      {c}")
    if not flips:
        print("  （无变化）")
    return 0


def _basename(path: str) -> str:
    return os.path.basename(path)


def main() -> int:
    _reconfigure_stdout()
    parser = argparse.ArgumentParser(description="检索种子集回放对比（只读，不写业务表）")
    parser.add_argument("--relax", action="store_true",
                        help="hybrid 用四级级联（semantic_search_kb 召回口径）；空期望查询跳过空集判定")
    parser.add_argument("--with-llm", action="store_true",
                        help="附加 semantic_search_kb 全链路实调（信息展示，不影响退出码）")
    parser.add_argument("--top-k", type=int, default=5, help="判定截断条数（默认 5）")
    parser.add_argument("--seed", default=DEFAULT_SEED, help="种子文件路径")
    parser.add_argument("--save", nargs="?", const="AUTO", metavar="PATH",
                        help="存 JSON 报告（不带值时用 data/replay_reports/ 缺省路径）")
    parser.add_argument("--compare", nargs=2, metavar=("A.json", "B.json"),
                        help="对比两份报告后退出（不执行回放）")
    args = parser.parse_args()
    if args.compare:
        return compare_reports(args.compare[0], args.compare[1])
    return run_replay(args)


if __name__ == "__main__":
    sys.exit(main())
