# -*- coding: utf-8 -*-
"""
Embedding Provider — 向量生成（OpenAI 兼容 /embeddings 接口）
=============================================================
0908 RAG 阶段 1 新增（docs/05-RAG混合检索与Agent升级探索.md §5.3）。
DeepSeek 不提供 embeddings 接口（决策 D2），默认走硅基流动等 OpenAI 兼容服务的
bge 系模型；local 模式（离线内网部署）本期仅留接口不实现。

降级约定：provider 未配置 / pgvector 未启用 / API 失败 → 调用方（ai_engine 混合检索、
写入挂钩、回填脚本）按"向量通道缺席"处理，检索退回纯关键词模式并显式记日志，
绝不静默伪造向量（CLAUDE.md §4.1）。

配置（backend/.env，系统环境变量优先）：
    EMBEDDING_PROVIDER    api | local（默认 api）
    EMBEDDING_API_BASE    OpenAI 兼容服务地址（默认硅基流动）
    EMBEDDING_API_KEY     API Key
    EMBEDDING_API_MODEL   模型名（默认 BAAI/bge-m3，1024 维）
    EMBEDDING_LOCAL_MODEL 本地模型名（预留，本期未实现）
"""

import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger("embedding")

# backend/.env（模式同 core/llm_config.py；database.py 的懒加载在此不必等，模块导入即读）
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "api").strip().lower()
EMBEDDING_API_BASE = os.environ.get("EMBEDDING_API_BASE", "https://api.siliconflow.cn/v1").rstrip("/")
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "")
EMBEDDING_API_MODEL = os.environ.get("EMBEDDING_API_MODEL", "BAAI/bge-m3")
EMBEDDING_LOCAL_MODEL = os.environ.get("EMBEDDING_LOCAL_MODEL", "")

# 客户端单例（模型/地址变更时重建；模式同 ai_engine._get_openai_client）
_CLIENT_CACHE: tuple | None = None


def _get_client(timeout: int = 30):
    global _CLIENT_CACHE
    from openai import OpenAI
    cache_key = (EMBEDDING_API_KEY, EMBEDDING_API_BASE, EMBEDDING_API_MODEL)
    if _CLIENT_CACHE is None or _CLIENT_CACHE[1] != cache_key:
        _CLIENT_CACHE = (
            OpenAI(api_key=EMBEDDING_API_KEY, base_url=EMBEDDING_API_BASE, timeout=timeout),
            cache_key,
        )
    return _CLIENT_CACHE[0]


def is_configured() -> bool:
    """是否已配置可用 key（api 模式非空即可；硅基流动 key 以 sk- 开头）。"""
    if EMBEDDING_PROVIDER == "local":
        return False  # 本期未实现 local provider，视为不可用（显式降级，不假装可用）
    return bool(EMBEDDING_API_KEY)


def is_available() -> bool:
    """向量通道是否可用（provider 配置 + pgvector 扩展均已就绪）。"""
    if not is_configured():
        return False
    try:
        from data.database import is_pgvector_enabled
        return is_pgvector_enabled()
    except Exception:
        return False


def get_embed_model() -> str:
    """当前嵌入模型名（随向量写入 embed_model 列，换模型需全量重刷）。"""
    return EMBEDDING_API_MODEL if EMBEDDING_PROVIDER != "local" else EMBEDDING_LOCAL_MODEL


def _record_call(latency_ms: int, chars: int, status: str, err: str, triggered_by: str):
    """embedding 调用记 llm_call_log（与 LLM 调用同一观测口径；写入失败忽略）。"""
    try:
        from data.database import record_llm_call
        record_llm_call("embedding_api", get_embed_model(), latency_ms, chars,
                        status, err, triggered_by, 0)
    except Exception:
        pass


def embed_texts(texts: list[str], triggered_by: str = "") -> list[list[float]] | None:
    """批量生成向量。任何失败返回 None（调用方按通道缺席处理，不重试级联）。

    维度校验：返回维度必须与 core/config.py EMBEDDING_DIM 一致，不一致视为失败
    （防换模型未重刷时写入不可比的向量）。
    """
    from core.config import EMBEDDING_DIM, LLM_MAX_RETRIES

    if not texts:
        return []
    if EMBEDDING_PROVIDER == "local":
        logger.warning("[embedding] local provider 本期未实现（EMBEDDING_LOCAL_MODEL 预留），向量通道禁用")
        return None
    if not EMBEDDING_API_KEY:
        logger.warning("[embedding] EMBEDDING_API_KEY 未配置，向量通道禁用（检索退回纯关键词模式）")
        return None

    chars = sum(len(t) for t in texts)
    client = _get_client(timeout=60)
    RETRYABLE = ("RateLimitError", "ServiceUnavailableError",
                 "APITimeoutError", "APIConnectionError",
                 "ConnectionError", "Timeout", "ReadTimeout")
    last_error = ""

    for attempt in range(LLM_MAX_RETRIES):
        try:
            t0 = time.time()
            resp = client.embeddings.create(model=EMBEDDING_API_MODEL, input=list(texts))
            elapsed_ms = int((time.time() - t0) * 1000)
            vectors = [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
            if len(vectors) != len(texts):
                raise ValueError(f"API 返回条数不符：期望 {len(texts)}，实际 {len(vectors)}")
            bad = next((i for i, v in enumerate(vectors) if len(v) != EMBEDDING_DIM), None)
            if bad is not None:
                raise ValueError(
                    f"向量维度不符：第 {bad} 条为 {len(vectors[bad])} 维，"
                    f"与 EMBEDDING_DIM={EMBEDDING_DIM}（{EMBEDDING_API_MODEL}）不一致——"
                    "如已换模型，须重建 embedding 列并全量重刷")
            _record_call(elapsed_ms, chars, "success", "", triggered_by)
            return vectors
        except Exception as e:
            err_type = type(e).__name__
            last_error = f"{err_type}: {e}"
            if not any(t in err_type for t in RETRYABLE) or attempt == LLM_MAX_RETRIES - 1:
                break
            time.sleep(2 ** attempt)

    logger.error("[embedding] 向量生成失败（%s）：%.200s", triggered_by or "-", last_error)
    _record_call(0, chars, "error", last_error, triggered_by)
    return None
