"""数据库操作层 — PostgreSQL 建表 + CRUD"""

import psycopg
import psycopg_pool
import os
import sys
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.adapt import Loader, Dumper
from psycopg import errors


# 0824 迁移 PG：全库 0/1 整型标志列 + 前端 bool 参数 → psycopg 默认适配为 PG boolean 会类型不匹配，
# 全局注册 bool → 1/0 整型 dump（与 SQLite 时代 bool 自动存整数行为一致）
class _BoolAsIntDumper(Dumper):
    def dump(self, obj):
        return b"1" if obj else b"0"

    def quote(self, obj):
        return b"1" if obj else b"0"


psycopg.adapters.register_dumper(bool, _BoolAsIntDumper)

# 0715 系统参数配置（项目根目录 config.py）
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.config import (
    FTS5_KEYWORD_MATCH_THRESHOLD, FTS5_SEARCH_LIMIT, SUS_SURVEY_COOLDOWN_DAYS,
    EMBEDDING_DIM, KEYWORD_DOMAIN_WORD_WEIGHT, VECTOR_MIN_SIMILARITY,
)

# 0811 数据解耦：DB 和 uploads 从 backend/data/ 移至项目根目录 data/
DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
DB_PATH = os.path.join(DB_DIR, "complaints.db")

# 0819 v3.0 角色体系重构 — 角色直接由管理员建号时下拉选择
ALL_ROLES = ["管理员", "客服", "客服主管", "办理人", "审批人", "承接人"]

# 0819 v3.0 流程状态（子类型由 complaints.sub_type 区分）
# 0825 新增第 8 状态「已撤回」：客服主管审核阶段撤回的终态，不入知识库，管理员可改状态恢复
CANONICAL_STATUSES = [
    "待客服处理",   # sub_type: rework=待修改 / customer_confirm=待客户确认
    "待客户排查",
    "客服主管审核", # sub_type: intake=客诉审核 / email=邮件审核
    "指派审批人",
    "指派承接人",
    "处理中",
    "已关闭",
    "已撤回",
]

# 待客服处理的子类型
SUB_TYPES_PENDING_CS = ("rework", "customer_confirm")
# 客服主管审核的子类型
SUB_TYPES_SUPERVISOR = ("intake", "email")

# 指派候选角色
APPROVER_CANDIDATE_ROLES = ["办理人", "审批人"]
ASSIGNEE_CANDIDATE_ROLES = ["办理人", "审批人", "承接人"]

# 0819 旧状态归一化映射已清空（v3.0 迁移会清理旧数据），保留函数避免全库调用点连锁修改
STATUS_NORMALIZE_MAP: dict[str, str] = {}


def normalize_status(s: str) -> str:
    """状态归一化（v3.0 起直接返回原值）。"""
    return STATUS_NORMALIZE_MAP.get(s, s)

CATEGORIES = ["机械", "电气", "工艺", "光学", "软件", "其他"]

PRIORITIES = ["P0", "P1", "P2", "P3"]


# 0824 迁移 PG：DATABASE_URL 懒加载自 backend/.env（模式同 core/smtp_config.py）
_env_path = Path(__file__).resolve().parent.parent / ".env"
_ENV_LOADED = False


def _ensure_env_loaded():
    """延迟加载 .env（确保 dotenv 只在首次需要时加载）。"""
    global _ENV_LOADED
    if not _ENV_LOADED and _env_path.exists():
        load_dotenv(_env_path)
        _ENV_LOADED = True


class _TsAsStrLoader(Loader):
    """把 TIMESTAMP 返回为 'YYYY-MM-DD HH:MM:SS' 字符串（截 [:19]），
    保证前端原样展示、不泄漏 ISO 'T'。"""

    def load(self, data: memoryview):
        if data is None:
            return None
        return bytes(data).decode("utf-8")[:19]


class _NumericAsFloatLoader(Loader):
    """numeric/Decimal → float（与 SQLite 时代统计字段为 float 的行为一致，
    避免 Pydantic 把 Decimal 序列化为字符串导致前端算术/渲染崩溃）。"""

    def load(self, data: memoryview):
        return float(bytes(data).decode())


# 0824 性能：每次请求新建 PG 连接固定开销 ~100ms（Windows 网络栈 + scram 认证），
# 引入 psycopg_pool 连接池（min 1 / max 8）；get_conn() 借出，调用方 close() 归还
_pool = None


def _pool_configure(conn):
    conn.adapters.register_loader("timestamp", _TsAsStrLoader)
    conn.adapters.register_loader("timestamptz", _TsAsStrLoader)
    conn.adapters.register_loader("numeric", _NumericAsFloatLoader)


def _get_pool():
    global _pool
    if _pool is None:
        _ensure_env_loaded()
        _pool = psycopg_pool.ConnectionPool(
            os.environ.get("DATABASE_URL", ""),
            min_size=1,
            max_size=8,
            kwargs={"row_factory": dict_row, "options": "-c TimeZone=Asia/Shanghai"},
            configure=_pool_configure,
            open=True,
        )
    return _pool


class _PooledConn:
    """连接池借出包装：转发连接操作，close() 归还池（调用方零改动）。"""

    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def cursor(self):
        return self._conn.cursor()

    def transaction(self):
        return self._conn.transaction()

    def close(self):
        # 0824 池化语义：只读调用方可能未 commit（事务悬挂），归还前丢弃，
        # 与 SQLite 时代 close() 丢弃未提交事务一致，避免池内连接悬置
        if self._conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            self._conn.rollback()
        self._pool.putconn(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def get_conn():
    _ensure_env_loaded()
    pool = _get_pool()
    # 0824 生产容错：DB 故障时快速失败（5s 超时抛 PoolTimeout → API 500），避免请求无限挂起
    return _PooledConn(pool, pool.getconn(timeout=5))


# 0714 内部辅助：Row 列表 → dict 列表
def _rows_to_dicts(rows) -> list[dict]:
    result = [dict(r) for r in rows]
    # 0824 迁移 PG：剥离 search_tsv 生成列（防泄漏到 SELECT * 响应）
    # 0908 RAG 阶段 1：同步剥离 embedding 向量列（pgvector 文本形态 ~10KB/条）
    for d in result:
        d.pop("search_tsv", None)
        d.pop("embedding", None)
    return result


def _kb_row_clean(d: dict) -> dict:
    """剥离 KB 行不应外泄的内部列（search_tsv 生成列 / embedding 向量文本）。
    0908 RAG 阶段 1：裸 dict(row) 的关键词检索路径统一走此清理。"""
    d.pop("search_tsv", None)
    d.pop("embedding", None)
    return d


# 0908 RAG 阶段 1：pgvector 可用性标志（init_db 探测 + 进程内惰性探测双通道；
# 标志是进程级状态，独立脚本（如回填）未跑 init_db 时由 _probe_pgvector() 补探测，
# 未装扩展时向量通道自动禁用，检索退回纯关键词模式，ai_engine 侧有显式日志）
_PGVECTOR_ENABLED = False
_PGVECTOR_PROBED = False


def _probe_pgvector() -> bool:
    """惰性探测 pgvector 扩展 + embedding 列是否就绪（每进程一次，结果缓存）。"""
    global _PGVECTOR_ENABLED, _PGVECTOR_PROBED
    if _PGVECTOR_PROBED:
        return _PGVECTOR_ENABLED
    _PGVECTOR_PROBED = True
    try:
        conn = get_conn()
        try:
            ext_row = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS ok"
            ).fetchone()
            col_row = conn.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'knowledge_base' AND column_name = 'embedding'"
            ).fetchone()
            _PGVECTOR_ENABLED = bool(ext_row and ext_row["ok"] and col_row)
        finally:
            conn.close()
    except Exception:
        _PGVECTOR_ENABLED = False
    return _PGVECTOR_ENABLED


def is_pgvector_enabled() -> bool:
    """pgvector 扩展 + embedding 列是否就绪（init_db 后直接用标志，否则惰性探测）。"""
    if _PGVECTOR_ENABLED:
        return True
    return _probe_pgvector()


# 0715 FTS5全文检索：jieba中文分词（替代2-gram，减少噪音词）
import jieba

# 0923 领域词库：自动化设备 组件/机型等术语整词切分（jieba 默认词典会把
# "上视相机"切成"上视/相机"等碎片，交集匹配丢召回），首次分词时加载一次
_JIEBA_USERDICT_LOADED = False


def _load_jieba_userdict_once():
    """加载领域词库（domain_dict.txt）。缺失或加载失败不阻断检索，退回默认词典。"""
    global _JIEBA_USERDICT_LOADED
    if _JIEBA_USERDICT_LOADED:
        return
    _JIEBA_USERDICT_LOADED = True
    try:
        from pathlib import Path
        dict_path = Path(__file__).parent / "domain_dict.txt"
        if dict_path.is_file():
            jieba.load_userdict(str(dict_path))
    except Exception:
        pass


def _jieba_tokenize(text: str) -> str:
    """用jieba分词后将长度≥2的词用空格连接，供FTS5索引和检索。
    例: "涂胶管路漏气" → "涂胶 管路 漏气"
    过滤单字和标点，仅保留有意义的词组。"""
    if not text:
        return ""
    _load_jieba_userdict_once()
    tokens = [t for t in jieba.cut(str(text)) if len(t) >= 2]
    return " ".join(tokens)


# 0824 安全加固：FTS5 保留字（OR/AND/NOT/NEAR 不区分大小写）
_FTS_RESERVED = {"or", "and", "not", "near"}


def _fts_safe_tokens(keyword: str) -> list[str]:
    """把用户检索词转成安全的 FTS5 短语 token 列表（防 FTS 语法注入）。
    jieba 有中文分词时用分词结果；纯英文/数字时按非词字符切分；
    剔除 FTS 保留字、单字与非法字符，防止 OR/AND/NEAR/^/*/rowid: 等操作符被激活。"""
    tok_str = _jieba_tokenize(keyword)
    raw = tok_str.split() if tok_str else re.findall(r"[\w一-鿿]+", keyword)
    tokens = []
    for t in raw:
        if len(t) < 2:
            continue
        low = t.lower()
        if low in _FTS_RESERVED:
            continue
        clean = re.sub(r"[^\w一-鿿]", "", t)
        if clean and clean.lower() not in _FTS_RESERVED:
            tokens.append(clean)
    return tokens


# 0908 RAG 阶段 1：领域词集合（domain_dict.txt 首列），用于关键词通道加权计分
_DOMAIN_WORDS: set | None = None


def _domain_words() -> set:
    """加载 domain_dict.txt 的词集合（惰性一次；缺失/失败返回空集合，
    加权计分退化为通用词计 1 分 = 原词数口径，行为不劣化）。"""
    global _DOMAIN_WORDS
    if _DOMAIN_WORDS is None:
        words = set()
        try:
            dict_path = Path(__file__).parent / "domain_dict.txt"
            if dict_path.is_file():
                for line in dict_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    words.add(line.split()[0])
        except Exception:
            pass
        _DOMAIN_WORDS = words
    return _DOMAIN_WORDS


def init_db():
    conn = get_conn()
    # 0824 迁移 PG：SQLite executescript → psycopg 多语句 execute（无参数）；类型按 PG 方言映射
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            complaint_no TEXT NOT NULL UNIQUE,
            customer_name TEXT NOT NULL DEFAULT '',
            equipment_model TEXT DEFAULT '',
            equipment_sn TEXT DEFAULT '',
            fault_category TEXT DEFAULT '',
            fault_phenomenon TEXT NOT NULL DEFAULT '',
            reproduction_steps TEXT DEFAULT '',
            priority TEXT DEFAULT '待确认',
            priority_confirmed_by TEXT DEFAULT '',
            status TEXT DEFAULT '待客户排查',
            assigned_to TEXT DEFAULT '',
            root_cause TEXT DEFAULT '',
            solution TEXT DEFAULT '',
            resolution_note TEXT DEFAULT '',
            customer_confirmed INTEGER DEFAULT 0,
            satisfaction INTEGER DEFAULT 0,
            is_rework INTEGER DEFAULT 0,
            created_by TEXT DEFAULT '',
            occurred_at TIMESTAMP,  -- 1019 客诉发生时间（仅业务记录，不参与编号；created_at 为真实录入时刻）
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),
            updated_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),
            closed_at TIMESTAMP,
            estimated_hours DOUBLE PRECISION DEFAULT 0,
            planned_start_time TEXT DEFAULT '',
            planned_end_time TEXT DEFAULT '',
            evaluated_by TEXT DEFAULT '',
            handler_name TEXT DEFAULT '',
            supervisor_rejection_note TEXT DEFAULT NULL,
            email_review_status TEXT DEFAULT NULL,
            email_review_note TEXT DEFAULT NULL,
            email_draft_content TEXT DEFAULT NULL,
            -- 1020 退回审批：承接人/审批人退回先申请，待对应审批人通过后才执行流转
            return_request_type TEXT DEFAULT NULL,      -- cannot_handle / approver_reject
            return_request_status TEXT DEFAULT NULL,    -- pending / approved / rejected
            return_request_reason TEXT DEFAULT NULL,
            return_request_by TEXT DEFAULT NULL,
            return_request_by_id BIGINT DEFAULT 0,
            return_request_at TIMESTAMP,
            return_review_note TEXT DEFAULT NULL,
            return_review_by TEXT DEFAULT NULL,
            return_review_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS knowledge_base (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            complaint_no TEXT DEFAULT '',
            title TEXT NOT NULL,
            fault_category TEXT DEFAULT '',
            equipment_model TEXT DEFAULT '',
            fault_keywords TEXT DEFAULT '',
            root_cause TEXT DEFAULT '',
            solution TEXT DEFAULT '',
            checklist TEXT DEFAULT '',
            lesson_learned TEXT DEFAULT '',
            contact_author TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),
            search_index TEXT DEFAULT '',
            search_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', search_index)) STORED
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            complaint_no TEXT DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            target_role TEXT NOT NULL DEFAULT '',
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')
        );

        CREATE TABLE IF NOT EXISTS progress_updates (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            complaint_id INTEGER NOT NULL,
            progress_pct INTEGER NOT NULL DEFAULT 0,
            note TEXT DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),
            FOREIGN KEY (complaint_id) REFERENCES complaints(id)
        );

        -- 0803 统一工单日志表（取代备注/进度离散记录）
        CREATE TABLE IF NOT EXISTS work_order_log (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            complaint_id INTEGER NOT NULL,
            event_type TEXT NOT NULL DEFAULT '',
            operator_name TEXT NOT NULL DEFAULT '',
            operator_role TEXT NOT NULL DEFAULT '',
            operator_dept TEXT NOT NULL DEFAULT '',
            old_status TEXT DEFAULT '',
            new_status TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),
            FOREIGN KEY (complaint_id) REFERENCES complaints(id)
        );

        -- 0820 工单日志归档表：删除工单前将全部日志（含删除事件）移入，保留审计留痕
        CREATE TABLE IF NOT EXISTS work_order_log_archive (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            original_log_id INTEGER,
            complaint_id INTEGER,
            complaint_no TEXT DEFAULT '',
            event_type TEXT NOT NULL DEFAULT '',
            operator_name TEXT NOT NULL DEFAULT '',
            operator_role TEXT NOT NULL DEFAULT '',
            operator_position TEXT DEFAULT '',
            old_status TEXT DEFAULT '',
            new_status TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            deleted_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')
        );

        -- 0715 LLM调用日志表（P0-2：基础设施硬化）
        CREATE TABLE IF NOT EXISTS llm_call_log (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            function_name TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            latency_ms INTEGER NOT NULL DEFAULT 0,
            prompt_chars INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'success',
            error_msg TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')
        );

        -- 0717 知识库反馈日志表（1分钟限频）
        CREATE TABLE IF NOT EXISTS kb_feedback_log (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            kb_id INTEGER NOT NULL,
            user_account TEXT NOT NULL DEFAULT '',
            feedback_type TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),
            FOREIGN KEY (kb_id) REFERENCES knowledge_base(id)
        );

        -- 0718 附件表（文件落盘，DB仅存元数据）
        CREATE TABLE IF NOT EXISTS attachments (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            complaint_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT '',
            file_size INTEGER NOT NULL DEFAULT 0,
            uploaded_by TEXT NOT NULL DEFAULT '',
            uploaded_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),
            FOREIGN KEY (complaint_id) REFERENCES complaints(id)
        );

        -- 0729 用户使用评价表
        CREATE TABLE IF NOT EXISTS user_feedback (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            username TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT '',
            complaint_no TEXT NOT NULL DEFAULT '',
            feedback_type TEXT NOT NULL,
            ai_accuracy INTEGER DEFAULT 0,
            ai_time_saved TEXT DEFAULT '',
            ai_adopted INTEGER DEFAULT 0,
            ai_comment TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')
        );

        -- 0819 v3.0 用户表（0824 迁移 PG：并入 init_db 主脚本，供 complaint_assignees 外键引用）
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            department TEXT DEFAULT '',
            is_dept_head INTEGER DEFAULT 0,
            updated_at TIMESTAMP,
            center TEXT DEFAULT '',
            position TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')
        );
    """)
    # 0824 迁移 PG：savepoint 隔离的容错执行（PG 语句失败会中止整个事务，须回滚到保存点后继续）
    def _safe_exec(sql):
        try:
            with conn.transaction():
                conn.execute(sql)
        except Exception:
            pass

    # 0714 辅助：安全添加列（幂等；0824 迁移 PG：ADD COLUMN IF NOT EXISTS）
    def _safe_add_column(tbl, col_def):
        _safe_exec(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS {col_def}")

    # 唯一索引：同一用户对同一工单同类评价仅一条
    _safe_exec(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_feedback_unique "
        "ON user_feedback(username, complaint_no, feedback_type)"
    )

    # 0730 评价表增加工单上下文 + AI 建议内容
    for col_def in [
        "fault_category TEXT DEFAULT ''",
        "equipment_model TEXT DEFAULT ''",
        "complaint_status TEXT DEFAULT ''",
        "responsible_dept TEXT DEFAULT ''",
        "ai_suggestion TEXT DEFAULT ''",
    ]:
        _safe_add_column("user_feedback", col_def)

    # ── 兼容旧库的列增量升级 ──
    for col in ["planned_start_time", "planned_end_time", "evaluated_by"]:
        _safe_add_column("complaints", col + " TEXT DEFAULT ''")
    _safe_add_column("complaints", "estimated_hours DOUBLE PRECISION DEFAULT 0")
    # 1019 客诉发生时间：与 created_at（系统录入时刻）分开
    _safe_add_column("complaints", "occurred_at TIMESTAMP")
    # 1020 退回审批字段
    for _ret_col in [
        "return_request_type TEXT DEFAULT NULL",
        "return_request_status TEXT DEFAULT NULL",
        "return_request_reason TEXT DEFAULT NULL",
        "return_request_by TEXT DEFAULT NULL",
        "return_request_by_id BIGINT DEFAULT 0",
        "return_request_at TIMESTAMP",
        "return_review_note TEXT DEFAULT NULL",
        "return_review_by TEXT DEFAULT NULL",
        "return_review_at TIMESTAMP",
    ]:
        _safe_add_column("complaints", _ret_col)
    # ── 0616 决议新增字段（D2~D5）──
    for col_def in [
        "software_version TEXT DEFAULT ''",
        "preliminary_category TEXT DEFAULT ''",
        "expected_complete_date TEXT DEFAULT ''",
        "impact_level TEXT DEFAULT ''",
    ]:
        _safe_add_column("complaints", col_def)
    # 0810 设备部位（涂胶阀、伺服驱动器等 自动化设备 具体组件）
    _safe_add_column("complaints", "device_part TEXT DEFAULT ''")
    # 0820 办理人（指派审批人的操作人）
    _safe_add_column("complaints", "handler_name TEXT DEFAULT ''")
    # 0723 负责部门（故障分类自动路由）
    _safe_add_column("complaints", "responsible_dept TEXT DEFAULT ''")
    # 0723-v2 通知表增加目标部门（部门级通知过滤）
    _safe_add_column("notifications", "target_dept TEXT DEFAULT ''")
    # 0729 通知分类：action_required / awareness / experience
    _safe_add_column("notifications", "notification_category TEXT DEFAULT 'awareness'")
    # 0730 通知目标用户：按姓名精准过滤（工程师指派通知只发给被指派者）
    _safe_add_column("notifications", "target_user TEXT DEFAULT ''")
    # 0803 通知目标是否为主管（1=只发给主管，0/空=全角色可见）
    _safe_add_column("notifications", "target_is_dept_head INTEGER DEFAULT 0")
    # 0720 备注记录（追加式日志，替代 evaluation_content / rejection_result）
    _safe_add_column("complaints", "remarks TEXT DEFAULT ''")
    # 0728 customer_email 列 — 客服录入客户邮箱，用于待客户确认时发送邮件
    _safe_add_column("complaints", "customer_email TEXT DEFAULT ''")
    # 0803 用户表新增 center 列（0819 弃用，仅保留列兼容）
    _safe_add_column("users", "center TEXT DEFAULT ''")
    # 0803 客服主管审核相关新列（兼容旧库）
    _safe_add_column("complaints", "supervisor_rejection_note TEXT DEFAULT NULL")
    _safe_add_column("complaints", "re_edited INTEGER DEFAULT 0")  # 客服编辑后设为 1，主管审核通过/拒绝时清空
    _safe_add_column("complaints", "email_review_status TEXT DEFAULT NULL")
    _safe_add_column("complaints", "email_review_note TEXT DEFAULT NULL")
    _safe_add_column("complaints", "email_draft_content TEXT DEFAULT NULL")

    # 0804 Phase 2: llm_call_log 增加用户上下文列（幂等）
    _safe_add_column("llm_call_log", "triggered_by TEXT DEFAULT ''")
    _safe_add_column("llm_call_log", "complaint_id INTEGER DEFAULT 0")

    # 0804 Phase 2: AI 采纳率追踪表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_adoption_log (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            complaint_no TEXT NOT NULL DEFAULT '',
            ai_function TEXT NOT NULL DEFAULT '',
            ai_suggestion TEXT DEFAULT '',
            adopted INTEGER DEFAULT 0,
            username TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')
        );
    """)

    # 0804 Phase 2: 用户活跃度追踪表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_activity_log (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            username TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT '',
            page_path TEXT DEFAULT '',
            action TEXT DEFAULT 'page_view',
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')
        );
    """)

    # 0805 Phase 3: 用户活跃度表增加 metadata 列（JSON 扩展数据，如操作计时）
    _safe_add_column("user_activity_log", "metadata TEXT DEFAULT '{}'")

    # 0805 Phase 3: AI 采纳日志增加建议值列（如 AI 排期建议工时）
    _safe_add_column("ai_adoption_log", "ai_suggested_value DOUBLE PRECISION DEFAULT NULL")

    # 0805 Phase 4: 案例级检索评价表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS case_feedback (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            username TEXT NOT NULL DEFAULT '',
            complaint_no TEXT NOT NULL DEFAULT '',
            kb_id INTEGER NOT NULL,
            kb_title TEXT DEFAULT '',
            source_type TEXT DEFAULT '',
            referenced INTEGER DEFAULT 0,
            match_accuracy INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),
            FOREIGN KEY (kb_id) REFERENCES knowledge_base(id)
        );
    """)
    _safe_exec(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_case_feedback_unique "
        "ON case_feedback(username, complaint_no, kb_id, source_type)"
    )

    # 0819 v3.0：旧状态迁移已删除（历史数据由 _run_v3_cleanup 一次性清理）
    # 0728 customer_note 列 — 客户备注（客户特殊要求或补充信息）
    _safe_add_column("complaints", "customer_note TEXT DEFAULT ''")
    # 0728 协作部门列表 — AI 分工建议一键通知后记录被通知的部门（JSON 数组）
    _safe_add_column("complaints", "collaborating_depts TEXT DEFAULT '[]'")
    # 0807 AI 推荐客户自排查建议（独立于 customer_note）
    _safe_add_column("complaints", "customer_self_check TEXT DEFAULT ''")
    # 0807 关联工单列表（JSON 数组 [{"id":1,"no":"CP-xxx"}]，录入时选择关联已有工单）
    _safe_add_column("complaints", "linked_complaint_ids TEXT DEFAULT '[]'")
    # 0807 审核场景区分 — intake（录入审核） vs self_check（自排查审核）
    _safe_add_column("complaints", "review_context TEXT DEFAULT 'intake'")
    # 0807 SUS 问卷：区分真实提交 vs 跳过（dismiss 不计入评分统计）
    _safe_add_column("sus_survey", "response_type TEXT NOT NULL DEFAULT 'submitted'")
    _safe_exec(
        "UPDATE sus_survey SET response_type = 'dismissed' "
        "WHERE response_type = 'submitted' "
        "AND q1 = 0 AND q2 = 0 AND q3 = 0 AND q4 = 0 AND q5 = 0 "
        "AND q6 = 0 AND q7 = 0 AND q8 = 0 AND q9 = 0 AND q10 = 0 "
        "AND sus_score = 0"
    )
    _safe_exec("UPDATE complaints SET review_context = 'intake' WHERE review_context IS NULL")
    # 0720 清理旧字段（已统一归入 remarks）
    for drop_col in ["evaluation_content", "rejection_result"]:
        _safe_exec(f"ALTER TABLE complaints DROP COLUMN IF EXISTS {drop_col}")
    # 0824 安全加固：删除密码可逆加密列（不再支持明文查看，登录仅依赖 password_hash）
    _safe_exec("ALTER TABLE users DROP COLUMN IF EXISTS password_encrypted")
    # progress_updates 索引
    _safe_exec(
        "CREATE INDEX IF NOT EXISTS idx_progress_complaint "
        "ON progress_updates(complaint_id, created_at)"
    )
    # knowledge_base 通讯作者列（已有库升级）
    _safe_add_column("knowledge_base", "contact_author TEXT DEFAULT ''")
    # 0715 FTS5全文检索：knowledge_base 增加 search_index 列（bigram分词文本）
    _safe_add_column("knowledge_base", "search_index TEXT DEFAULT ''")
    # 0716 知识库质量反馈字段（用于 👍/👎 评价闭环）
    _safe_add_column("knowledge_base", "useful_count INTEGER DEFAULT 0")
    _safe_add_column("knowledge_base", "unhelpful_count INTEGER DEFAULT 0")
    # 0723 知识库多维度评价：技术质量（T1-T3）+ 商业价值（B1-B3）
    _safe_add_column("knowledge_base", "accuracy_votes INTEGER DEFAULT 0")
    _safe_add_column("knowledge_base", "effectiveness_votes INTEGER DEFAULT 0")
    _safe_add_column("knowledge_base", "clarity_votes INTEGER DEFAULT 0")
    _safe_add_column("knowledge_base", "customer_impact_votes INTEGER DEFAULT 0")
    _safe_add_column("knowledge_base", "customer_satisfy_votes INTEGER DEFAULT 0")
    _safe_add_column("knowledge_base", "presales_value_votes INTEGER DEFAULT 0")
    # 0730 知识库增加故障现象字段
    _safe_add_column("knowledge_base", "fault_phenomenon TEXT DEFAULT ''")

    # 0908 RAG 阶段 1：pgvector 向量通道 — 扩展 + embedding 三列（幂等）。
    # 扩展未安装/无权限时 _safe_exec 经 savepoint 静默跳过，系统以纯关键词模式运行
    # （init_db 末尾能力探测打印显式告警；部署前置见 docs/04-部署与运维手册.md §2.6）。
    # embed_model 列记录向量所属模型——不同模型的向量做余弦无意义，换模型须全量重刷
    # （backfill_kb_embeddings.py 的 WHERE 条件天然支持，docs/05 §4.4 红线）
    _safe_exec("CREATE EXTENSION IF NOT EXISTS vector")
    _safe_add_column("knowledge_base", f"embedding vector({EMBEDDING_DIM})")
    _safe_add_column("knowledge_base", "embed_model TEXT DEFAULT ''")
    _safe_add_column("knowledge_base", "embedded_at TIMESTAMP")

    # 0717 kb_feedback_log 索引（加速限频查询）
    _safe_exec(
        "CREATE INDEX IF NOT EXISTS idx_feedback_log_user_kb "
        "ON kb_feedback_log(kb_id, user_account, created_at)"
    )

    # 0824 迁移 PG 索引补强：高频查询表防全表扫描（SQLite 时代未建）
    _safe_exec("CREATE INDEX IF NOT EXISTS idx_notifications_complaint ON notifications(complaint_no)")
    _safe_exec("CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at)")
    _safe_exec("CREATE INDEX IF NOT EXISTS idx_worklog_complaint ON work_order_log(complaint_id, created_at, id)")
    _safe_exec("CREATE INDEX IF NOT EXISTS idx_attachments_complaint ON attachments(complaint_id)")
    _safe_exec("CREATE INDEX IF NOT EXISTS idx_activity_created ON user_activity_log(created_at)")

    # 0715 LLM日志查询索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_log_created ON llm_call_log(created_at)")

    # 0824 迁移 PG：FTS5 虚拟表/同步触发器删除 → search_tsv 生成列 + GIN 索引（见 knowledge_base DDL）
    _safe_exec(
        "CREATE INDEX IF NOT EXISTS idx_kb_search_tsv "
        "ON knowledge_base USING GIN (search_tsv)"
    )

    # 0715 首次迁移：回填已有KB条目的 search_index（幂等；生成列 search_tsv 自动重算）
    rows = conn.execute(
        "SELECT id, title, fault_keywords, root_cause, solution, "
        "lesson_learned, fault_category, equipment_model, contact_author "
        "FROM knowledge_base WHERE search_index IS NULL OR search_index = ''"
    ).fetchall()
    for row in rows:
        search_text = " ".join(str(row[k] or "") for k in row.keys())
        bigram_text = _jieba_tokenize(search_text)
        conn.execute(
            "UPDATE knowledge_base SET search_index = %s WHERE id = %s",
            (bigram_text, row["id"])
        )

    # 0819 v3.0：responsible_dept 回填已删除（部门概念取消）

    # ── 0804 系统评估：SUS 系统可用性量表 ──
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sus_survey (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            username TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT '',
            center TEXT DEFAULT '',
            department TEXT DEFAULT '',
            q1 INTEGER NOT NULL DEFAULT 0,
            q2 INTEGER NOT NULL DEFAULT 0,
            q3 INTEGER NOT NULL DEFAULT 0,
            q4 INTEGER NOT NULL DEFAULT 0,
            q5 INTEGER NOT NULL DEFAULT 0,
            q6 INTEGER NOT NULL DEFAULT 0,
            q7 INTEGER NOT NULL DEFAULT 0,
            q8 INTEGER NOT NULL DEFAULT 0,
            q9 INTEGER NOT NULL DEFAULT 0,
            q10 INTEGER NOT NULL DEFAULT 0,
            sus_score DOUBLE PRECISION DEFAULT 0,
            response_type TEXT NOT NULL DEFAULT 'submitted',
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')
        );
    """)
    _safe_exec(
        "CREATE INDEX IF NOT EXISTS idx_sus_survey_user "
        "ON sus_survey(username, created_at)"
    )
    # 0923 问卷补充题（可选，不计入 SUS 分）：常用功能多选（逗号分隔存储）+ 改进建议开放题
    _safe_exec("ALTER TABLE sus_survey ADD COLUMN IF NOT EXISTS use_modules TEXT DEFAULT ''")
    _safe_exec("ALTER TABLE sus_survey ADD COLUMN IF NOT EXISTS improvement TEXT DEFAULT ''")

    # 0819 v3.0：旧优先级迁移已删除（历史数据由 _run_v3_cleanup 一次性清理）

    # 0811 SMTP 邮箱设置：系统配置键值表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')
        )
    """)

    # ═══════════════════ 0819 v3.0 角色体系重构：新表/新列/一次性清理 ═══════════════════

    # 新列（幂等）
    _safe_add_column("users", "position TEXT DEFAULT ''")
    _safe_add_column("work_order_log", "operator_position TEXT DEFAULT ''")
    _safe_add_column("complaints", "sub_type TEXT DEFAULT ''")
    _safe_add_column("complaints", "created_by_user_id INTEGER DEFAULT 0")
    _safe_add_column("notifications", "target_user_id INTEGER DEFAULT 0")

    # ═══════════════════ 0824 钉钉通知：用户绑定列 + 发送日志表 ═══════════════════
    # 用户绑定钉钉 UserID（Phase-1 管理员人工绑定，空=未绑定不推送）
    _safe_add_column("users", "dingtalk_userid TEXT DEFAULT ''")
    # 发送日志（仿 llm_call_log：写入失败不影响主流程）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dingtalk_send_log (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            complaint_no TEXT DEFAULT '',
            target_role TEXT DEFAULT '',
            target_user_ids TEXT DEFAULT '',
            dingtalk_userids TEXT DEFAULT '',
            message_type TEXT DEFAULT 'action_card',
            status TEXT DEFAULT 'pending',
            error_msg TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')
        )
    """)

    # 多人指派表：approver 类型单值有效；assignee（承接人+参与人）多值
    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaint_assignees (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            complaint_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            assignee_type TEXT NOT NULL DEFAULT 'assignee',
            assigned_by TEXT NOT NULL DEFAULT '',
            assigned_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai'),
            is_active INTEGER NOT NULL DEFAULT 1,
            is_primary INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_assignees_complaint
            ON complaint_assignees(complaint_id, assignee_type, is_active);
        CREATE INDEX IF NOT EXISTS idx_assignees_user
            ON complaint_assignees(user_id, is_active);
    """)
    # 0820 主要推进人：老库幂等加列
    _safe_add_column("complaint_assignees", "is_primary INTEGER NOT NULL DEFAULT 0")

    # 0820 办理人回填：老工单从 approver_assigned 日志补 handler_name（只填空值，幂等）
    # 0824 迁移 PG：相关子查询带 LIMIT 不支持 → DISTINCT ON
    conn.execute("""
        UPDATE complaints c SET handler_name = w.operator_name
        FROM (SELECT DISTINCT ON (complaint_id) complaint_id, operator_name
              FROM work_order_log WHERE event_type = 'approver_assigned'
              ORDER BY complaint_id, id DESC) w
        WHERE w.complaint_id = c.id AND (c.handler_name = '' OR c.handler_name IS NULL)
    """)

    # 一次性历史数据清理（v3 标记守卫，只跑一次）
    _run_v3_cleanup(conn)

    # 0908 RAG 阶段 1：pgvector 能力探测（扩展已装 + embedding 列已建）→ 模块级标志。
    # 探测失败/未就绪均为 False：向量通道禁用，检索退回纯关键词模式（显式告警，不静默）
    global _PGVECTOR_ENABLED, _PGVECTOR_PROBED
    _PGVECTOR_PROBED = True
    try:
        ext_row = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS ok"
        ).fetchone()
        col_row = conn.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'knowledge_base' AND column_name = 'embedding'"
        ).fetchone()
        _PGVECTOR_ENABLED = bool(ext_row and ext_row["ok"] and col_row)
    except Exception:
        _PGVECTOR_ENABLED = False
    if not _PGVECTOR_ENABLED:
        print("[init_db] pgvector 未启用（扩展未安装或 embedding 列缺失）——"
              "向量检索通道禁用，系统以纯关键词模式运行；启用步骤见 docs/04-部署与运维手册.md §2.6",
              flush=True)

    # ═══════════════════ 0910 客诉场景分类：录入必填新列 ═══════════════════
    # 工艺调试类/现场交付类/客户正式投诉类；存量工单为空（详情显示「—」，编辑弹窗可补填）
    _safe_add_column("complaints", "scene_category TEXT DEFAULT ''")

    conn.commit()
    conn.close()


def _run_v3_cleanup(conn):
    """0819 v3.0 一次性清理：删除旧角色用户与全部旧状态工单（含附件物理文件），
    保留 admin 账号与 knowledge_base。用 system_settings 标记守卫保证只执行一次。
    """
    try:
        row = conn.execute(
            "SELECT value FROM system_settings WHERE key='v3_role_migration_done'"
        ).fetchone()
    except Exception:
        row = None
    if row:
        return

    import shutil
    # 1) 删除工单附件物理目录
    try:
        complaint_nos = [r["complaint_no"] for r in conn.execute(
            "SELECT complaint_no FROM complaints"
        ).fetchall()]
        for no in complaint_nos:
            shutil.rmtree(os.path.join(DB_DIR, "uploads", no), ignore_errors=True)
    except Exception as e:
        print(f"[WARN] v3_cleanup: uploads removal failed: {e}")

    # 2) 删除工单关联明细
    for tbl in ("attachments", "progress_updates", "work_order_log",
                "notifications", "user_feedback", "case_feedback"):
        try:
            conn.execute(f"DELETE FROM {tbl}")
        except Exception:
            pass

    # 3) 删除全部工单
    try:
        conn.execute("DELETE FROM complaints")
    except Exception:
        pass

    # 4) 删除 admin 之外的用户，admin 重置为新角色体系
    try:
        conn.execute("DELETE FROM users WHERE username != 'admin'")
        conn.execute(
            "UPDATE users SET role='管理员', position='系统管理员', "
            "center='', department='', is_dept_head=0 WHERE username='admin'"
        )
    except Exception as e:
        print(f"[WARN] v3_cleanup: users cleanup failed: {e}")

    # 5) 标记完成（knowledge_base / llm_call_log / sus_survey / ai_adoption_log /
    #    user_activity_log / system_settings 均不动）
    try:
        conn.execute(
            "INSERT INTO system_settings(key, value, updated_at) "
            "VALUES('v3_role_migration_done', '1', now() AT TIME ZONE 'Asia/Shanghai') "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
            "updated_at = EXCLUDED.updated_at"
        )
    except Exception:
        pass


def _next_seq(date_str):
    """生成下一个序列号"""
    conn = get_conn()
    # 2026-08-26 客诉编号前缀由 KH 改为 KS（仅影响新建工单，历史 KH 编号不变）
    prefix = "KS-" + date_str
    row = conn.execute(
        "SELECT complaint_no FROM complaints WHERE complaint_no LIKE %s ORDER BY id DESC LIMIT 1",
        (prefix + "-%",),
    ).fetchone()
    conn.close()
    if row:
        last_seq = int(row["complaint_no"].split("-")[-1])
        return prefix + "-" + str(last_seq + 1).zfill(3)
    return prefix + "-001"


def generate_complaint_no(date_str: str | None = None):
    """0911 支持按指定日期（YYYYMMDD）取当日序号——批量导入传提出日期，
    编号与 created_at 对齐；缺省回退今天（手工录入路径行为不变）。"""
    return _next_seq(date_str or datetime.now().strftime("%Y%m%d"))


def create_complaint(data):
    conn = get_conn()
    # 1019 工单号日期段取「录入系统的时间」（created_at）；未传则今天。
    # 客诉发生时间（occurred_at）仅作业务记录，不参与编号。
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(data.get("created_at") or ""))
    data["complaint_no"] = generate_complaint_no(
        f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else None)
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["%s"] * len(data))
    rid = conn.execute(
        "INSERT INTO complaints (" + cols + ") VALUES (" + placeholders + ") RETURNING id",
        tuple(data.values()),
    ).fetchone()["id"]
    conn.commit()
    conn.close()
    return rid


# 0716 提交前相似工单检测（阶段1：同客户+同设备型号+30天内；阶段2：2字符滑动窗口比较故障现象）
def find_similar_complaints(customer_name, equipment_model, fault_phenomenon, days=30):
    """查找近N天内同客户+同设备型号的相似工单，用2字符滑动窗口比较故障现象相似度，按相似度降序"""
    conn = get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        """SELECT complaint_no, customer_name, equipment_model, fault_phenomenon,
                  fault_category, status, created_at
           FROM complaints
           WHERE customer_name = %s
             AND equipment_model = %s
             AND created_at >= %s
           ORDER BY created_at DESC""",
        (customer_name, equipment_model, cutoff),
    ).fetchall()
    conn.close()

    new_grams = get_2gram_slide(fault_phenomenon)

    results = []
    for row in rows:
        existing_text = row["fault_phenomenon"] or ""
        existing_grams = get_2gram_slide(existing_text)
        overlap = new_grams & existing_grams
        union = new_grams | existing_grams
        if not overlap:
            continue
        similarity = len(overlap) / len(union) if union else 0
        results.append({
            "complaint_no": row["complaint_no"],
            "customer_name": row["customer_name"],
            "equipment_model": row["equipment_model"],
            "fault_phenomenon": row["fault_phenomenon"],
            "fault_category": row["fault_category"],
            "status": row["status"],
            "created_at": row["created_at"],
            "similarity": round(similarity, 2),
            "overlap_grams": len(overlap),
            "total_grams": len(union),
        })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results


def get_2gram_slide(text: str) -> set:
    """全文2字符滑动窗口切片"""
    if not text or len(text) < 2:
        return set()
    gram_set = set()
    for i in range(len(text) - 1):
        gram = text[i:i+2]
        gram_set.add(gram)
    return gram_set


def get_complaint(complaint_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM complaints WHERE id = %s", (complaint_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_complaints(status_filter=None, category_filter=None):
    conn = get_conn()
    sql = "SELECT * FROM complaints"
    params = []
    conditions = []
    if status_filter and status_filter != "全部":
        conditions.append("status = %s")
        params.append(status_filter)
    if category_filter and category_filter != "全部":
        conditions.append("fault_category = %s")
        params.append(category_filter)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# ══ 0910 批量表单导入：机台历史匹配 + 去重查询 ══
def get_machine_history_info(equipment_sn: str):
    """按机台编号（忽略大小写）查历史工单，取出现最多的客户名/设备型号组合（导入自动匹配客户用）。"""
    if not equipment_sn:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT customer_name, equipment_model, COUNT(*) AS n FROM complaints "
        "WHERE lower(equipment_sn) = lower(%s) AND customer_name != '' "
        "GROUP BY customer_name, equipment_model ORDER BY n DESC LIMIT 1",
        (equipment_sn,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def find_dup_complaint_by_sn_phenomenon(equipment_sn: str, fault_phenomenon: str):
    """批量导入去重/覆盖：同机台 + 同问题描述全等的既有工单（无则 None）。
    1016 起返回 {"id", "complaint_no"}——覆盖旧单定位与前端「去修改」跳转都需要 id。"""
    if not fault_phenomenon:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT id, complaint_no FROM complaints "
        "WHERE lower(equipment_sn) = lower(%s) AND fault_phenomenon = %s "
        "ORDER BY id DESC LIMIT 1",
        (equipment_sn or "", fault_phenomenon),
    ).fetchone()
    conn.close()
    return {"id": row["id"], "complaint_no": row["complaint_no"]} if row else None


def find_complaints_by_equipment_sns(sns: list[str]) -> list[dict]:
    """0915 按设备编号集合查工单（批量导入同机台自动关联用，大小写不敏感），
    返回 [{id, complaint_no}]，按 created_at 升序（旧→新，与关联列表展示顺序一致）。"""
    sns = [s for s in {str(s or "").strip() for s in sns} if s]
    if not sns:
        return []
    conn = get_conn()
    lowered = [s.lower() for s in sns]
    placeholders = ",".join("%s" for _ in lowered)
    rows = conn.execute(
        f"SELECT id, complaint_no FROM complaints "
        f"WHERE lower(equipment_sn) IN ({placeholders}) "
        f"ORDER BY created_at ASC, id ASC",
        lowered,
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def append_linked_complaint(complaint_id: int, new_id: int, new_no: str) -> bool:
    """0915 既有工单的关联列表追加新工单（批量导入双向关联回写）。
    已含同 id 跳过；旧值非法 JSON 时重置为仅含新条目；只更新 linked_complaint_ids，不动 updated_at。
    返回是否实际写入。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT linked_complaint_ids FROM complaints WHERE id = %s", (complaint_id,)
    ).fetchone()
    if not row:
        conn.close()
        return False
    try:
        links = json.loads(row["linked_complaint_ids"] or "[]")
        if not isinstance(links, list):
            links = []
    except (ValueError, TypeError):
        links = []
    if any(isinstance(x, dict) and x.get("id") == new_id for x in links):
        conn.close()
        return False
    links.append({"id": new_id, "no": new_no})
    conn.execute(
        "UPDATE complaints SET linked_complaint_ids = %s WHERE id = %s",
        (json.dumps(links, ensure_ascii=False), complaint_id),
    )
    conn.commit()
    conn.close()
    return True



def update_complaint(complaint_id, data):
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sets = ", ".join(k + " = %s" for k in data)
    vals = list(data.values()) + [complaint_id]
    conn = get_conn()
    conn.execute("UPDATE complaints SET " + sets + " WHERE id = %s", vals)
    conn.commit()
    conn.close()


# 0728 按 complaint_no 读单个字段（用于轻量查询，避免全表扫描）
def get_complaint_field_by_no(complaint_no: str, field: str):
    """根据 complaint_no 读取单个字段值，不存在则返回 None。"""
    conn = get_conn()
    row = conn.execute(
        f"SELECT {field} FROM complaints WHERE complaint_no = %s",
        (complaint_no,),
    ).fetchone()
    conn.close()
    return row[field] if row else None


# 0728 按 complaint_no 更新字段
def update_complaint_by_no(complaint_no: str, data: dict):
    """根据 complaint_no 更新字段（用于协作部门等跨表场景）。"""
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sets = ", ".join(k + " = %s" for k in data)
    vals = list(data.values()) + [complaint_no]
    conn = get_conn()
    conn.execute("UPDATE complaints SET " + sets + " WHERE complaint_no = %s", vals)
    conn.commit()
    conn.close()


def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) AS count FROM complaints").fetchone()["count"]
    by_status = {
        r["status"]: r["cnt"]
        for r in conn.execute(
            "SELECT status, COUNT(*) as cnt FROM complaints GROUP BY status"
        ).fetchall()
    }
    recent = conn.execute(
        "SELECT complaint_no, customer_name, fault_category, status, created_at "
        "FROM complaints ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    conn.close()
    return {"total": total, "by_status": by_status, "recent": _rows_to_dicts(recent)}


# ── 通知管理 ─────────────────────────────────────
# 0713 查询临近客户期望完成日期的客诉（24小时内），且未发送过截止提醒
def get_complaints_approaching_deadline():
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.* FROM complaints c
        WHERE c.expected_complete_date != ''
          AND c.expected_complete_date IS NOT NULL
          AND c.status NOT IN ('已关闭', '已撤回')
          AND c.expected_complete_date::date <= (now() AT TIME ZONE 'Asia/Shanghai') + interval '24 hours'
          AND NOT EXISTS (
            SELECT 1 FROM notifications n
            WHERE n.complaint_no = c.complaint_no
              AND n.title LIKE '⏰%'
          )
        ORDER BY c.expected_complete_date
    """).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def create_notification(complaint_no, title, message, target_role, category: str = "awareness", target_user_id: int = 0):
    """0819 创建系统通知。
    target_role: 目标角色（六角色之一或 '全员'）；target_user_id: 精准到人（0=该角色全员）。
    """
    conn = get_conn()
    conn.execute(
        "INSERT INTO notifications (complaint_no, title, message, target_role, notification_category, target_user_id) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (complaint_no, title, message, target_role, category, target_user_id),
    )
    conn.commit()
    conn.close()


# 0819 v3.0：create_department_notifications / user_can_view_complaint 已删除（部门概念取消）


def _get_notification_scope(role: str, user_id: int = 0) -> tuple[str, list]:
    """0820 通知可见范围，返回 (where_sql, params)。
    管理员看全部（含角色定向）；其余角色看 本角色/全员广播 + 精准到本人的通知
    （跨角色可见——候选人池含多角色时，target_role 与收件人实际角色不符也能收到）。
    """
    if role == "管理员":
        return "1=1", []
    return (
        "(target_user_id = %s OR (target_user_id = 0 AND target_role IN (%s, '全员')))",
        [user_id, role],
    )


def _get_notification_mark_scope(role: str, user_id: int = 0) -> tuple[str, list]:
    """0820 通知「标为已读」的写范围。
    管理员只动广播行（target_user_id=0）——防止「全部已读」/打开工单清掉他人的精准未读；
    其余角色与可见范围一致（精准到本人 + 本角色/全员广播）。
    """
    if role == "管理员":
        return "target_user_id = 0", []
    return _get_notification_scope(role, user_id)


def get_unread_notifications(role: str, user_id: int = 0):
    """获取当前角色可见的未读通知（0820 角色+精准用户过滤，精准跨角色可见）。"""
    conn = get_conn()
    scope, scope_params = _get_notification_scope(role, user_id)
    rows = conn.execute(
        f"SELECT * FROM notifications WHERE {scope} AND is_read = 0 "
        "ORDER BY created_at DESC LIMIT 50",
        scope_params,
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def mark_notification_read(notif_id, role: str = "", user_id: int = 0):
    """0820 单条标已读：带可见范围校验（不可见则 0 行更新，防任意 id 越权标记）。"""
    conn = get_conn()
    if role:
        scope, scope_params = _get_notification_scope(role, user_id)
        conn.execute(
            f"UPDATE notifications SET is_read = 1 WHERE id = %s AND {scope}",
            [notif_id] + scope_params,
        )
    else:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE id = %s", (notif_id,))
    conn.commit()
    conn.close()


def mark_all_notifications_read(role: str, user_id: int = 0):
    """0819 按角色可见范围全部标为已读（0820 管理员只动广播行，保护他人精准未读）。"""
    conn = get_conn()
    scope, scope_params = _get_notification_mark_scope(role, user_id)
    conn.execute(
        f"UPDATE notifications SET is_read = 1 WHERE {scope}",
        scope_params,
    )
    conn.commit()
    conn.close()


def get_unread_count(role: str, user_id: int = 0):
    """0819 按角色可见范围统计未读通知数。"""
    conn = get_conn()
    scope, scope_params = _get_notification_scope(role, user_id)
    count = conn.execute(
        f"SELECT COUNT(*) AS count FROM notifications WHERE {scope} AND is_read = 0",
        scope_params,
    ).fetchone()["count"]
    conn.close()
    return count


def get_notification_category_counts(role: str, user_id: int = 0):
    """0819 返回当前角色按 category 分组的未读通知数。"""
    conn = get_conn()
    scope, scope_params = _get_notification_scope(role, user_id)
    rows = conn.execute(
        f"SELECT notification_category, COUNT(*) as cnt FROM notifications "
        f"WHERE {scope} AND is_read = 0 "
        "GROUP BY notification_category",
        scope_params,
    ).fetchall()
    conn.close()
    result = {}
    for r in rows:
        cat = r["notification_category"] or "awareness"
        result[cat] = r["cnt"]
    return result


def get_all_notifications(role: str, user_id: int = 0, page: int = 1, limit: int = 20, is_read: str | None = None):
    """0819 通知中心分页查询，支持全部/已读/未读过滤。"""
    conn = get_conn()
    scope, scope_params = _get_notification_scope(role, user_id)

    conditions = [scope]
    params: list = list(scope_params)

    if is_read == "0":
        conditions.append("is_read = 0")
    elif is_read == "1":
        conditions.append("is_read = 1")

    where = " AND ".join(conditions)

    total_row = conn.execute(
        f"SELECT COUNT(*) AS count FROM notifications WHERE {where}", params,
    ).fetchone()
    total = total_row["count"] if total_row else 0

    offset = (page - 1) * limit
    rows = conn.execute(
        f"SELECT * FROM notifications WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        params + [limit, offset],
    ).fetchall()
    conn.close()

    items = _rows_to_dicts(rows)
    for it in items:
        it["is_read"] = bool(it.get("is_read", 0))

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
    }


def get_complaint_id_by_no(complaint_no):
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM complaints WHERE complaint_no = %s", (complaint_no,)
    ).fetchone()
    conn.close()
    return row["id"] if row else None


def get_complaint_briefs_by_ids(ids: list[int]) -> list[dict]:
    """0915 批量获取工单概要（详情页关联工单弹窗表格用），
    返回 [{id, complaint_no, equipment_sn, priority, status, fault_phenomenon, solution}]。"""
    if not ids:
        return []
    conn = get_conn()
    placeholders = ",".join("%s" for _ in ids)
    rows = conn.execute(f"""
        SELECT id, complaint_no, equipment_sn, priority, status,
               fault_phenomenon, solution
        FROM complaints
        WHERE id IN ({placeholders})
        ORDER BY created_at DESC
    """, ids).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def mark_notifications_read_by_complaint(complaint_no, role: str, user_id: int = 0):
    """0819 点击工单时标记该工单相关通知为已读（0820 管理员只动广播行，保护他人精准未读）。"""
    conn = get_conn()
    scope, scope_params = _get_notification_mark_scope(role, user_id)
    conn.execute(
        f"UPDATE notifications SET is_read = 1 WHERE complaint_no = %s AND {scope}",
        [complaint_no] + scope_params,
    )
    conn.commit()
    conn.close()


# ── 数据删除 ─────────────────────────────────────
def delete_complaint(complaint_id):
    """删除工单及其关联数据（进度历史+附件+通知）。"""
    try:
        conn = get_conn()
        # 0820 删除前归档全部日志（含 API 侧刚写入的 deleted 事件），保留审计留痕
        complaint_no = conn.execute(
            "SELECT complaint_no FROM complaints WHERE id = %s", (complaint_id,)
        ).fetchone()
        if complaint_no:
            complaint_no = complaint_no["complaint_no"]
            conn.execute(
                """INSERT INTO work_order_log_archive
                   (original_log_id, complaint_id, complaint_no, event_type, operator_name,
                    operator_role, operator_position, old_status, new_status, detail, created_at)
                   SELECT id, complaint_id, %s, event_type, operator_name,
                          operator_role, operator_position, old_status, new_status, detail,
                          to_char(created_at, 'YYYY-MM-DD HH24:MI:SS')
                   FROM work_order_log WHERE complaint_id = %s""",
                (complaint_no, complaint_id),
            )
        # 先清子表，避免外键约束阻止删除主表
        conn.execute("DELETE FROM progress_updates WHERE complaint_id = %s", (complaint_id,))
        conn.execute("DELETE FROM notifications WHERE complaint_no = (SELECT complaint_no FROM complaints WHERE id = %s)", (complaint_id,))
        # 附件：删除物理文件
        atts = conn.execute("SELECT * FROM attachments WHERE complaint_id = %s", (complaint_id,)).fetchall()
        for a in atts:
            complaint = conn.execute("SELECT complaint_no FROM complaints WHERE id = %s", (complaint_id,)).fetchone()
            if complaint:
                fpath = os.path.join(DB_DIR, "uploads", complaint["complaint_no"], a["stored_name"])
                try: os.remove(fpath)
                except Exception: pass
        conn.execute("DELETE FROM attachments WHERE complaint_id = %s", (complaint_id,))
        # 0804 清理工单日志（含删除事件），避免 FK 约束阻止主表删除
        conn.execute("DELETE FROM work_order_log WHERE complaint_id = %s", (complaint_id,))
        # 0819 清理多人指派记录，避免 FK 约束阻止主表删除
        conn.execute("DELETE FROM complaint_assignees WHERE complaint_id = %s", (complaint_id,))
        # 最后删主表
        conn.execute("DELETE FROM complaints WHERE id = %s", (complaint_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# ── 知识库 CRUD ──────────────────────────────────
def get_kb_entry(kb_id: int) -> dict | None:
    """获取单条知识库条目。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM knowledge_base WHERE id = %s", (kb_id,)).fetchone()
    conn.close()
    return _kb_row_clean(dict(row)) if row else None


def create_kb_entry(data):
    # 0715 自动计算FTS5索引字段（bigram分词）
    search_text = " ".join(str(data.get(k, "") or "") for k in [
        "title", "fault_keywords", "root_cause", "solution",
        "lesson_learned", "fault_category", "equipment_model", "contact_author",
        "fault_phenomenon",
    ])
    data["search_index"] = _jieba_tokenize(search_text)

    conn = get_conn()
    cols = ", ".join(k for k in data if k != "id")
    vals = [v for k, v in data.items() if k != "id"]
    placeholders = ", ".join(["%s"] * len(vals))
    rid = conn.execute(
        "INSERT INTO knowledge_base (" + cols + ") VALUES (" + placeholders + ") RETURNING id",
        vals,
    ).fetchone()["id"]
    conn.commit()
    conn.close()
    return rid


# 0729 知识库管理：管理员删除知识条目（含关联反馈记录清除）
def delete_kb_entry(kb_id):
    """删除知识条目（管理员操作）。先清除关联反馈记录，再删除主记录。"""
    conn = get_conn()
    # 验证条目存在
    row = conn.execute("SELECT id FROM knowledge_base WHERE id = %s", (kb_id,)).fetchone()
    if not row:
        conn.close()
        return False
    # 先删关联反馈，再删主记录（FTS5触发器自动同步）
    conn.execute("DELETE FROM kb_feedback_log WHERE kb_id = %s", (kb_id,))
    conn.execute("DELETE FROM knowledge_base WHERE id = %s", (kb_id,))
    conn.commit()
    conn.close()
    return True


# 0715 FTS5全文检索重写：LIKE全表扫描 → FTS5 MATCH + bm25排序
def search_kb(keyword, category_filter="", min_overlap=None):
    """搜索知识库。
    min_overlap: 查询词与文档索引词最小交集数，默认取 config.FTS5_KEYWORD_MATCH_THRESHOLD。
                 传 0/1 可放宽阈值用于语义检索初筛，让 LLM 做最终语义判断。"""
    if min_overlap is None:
        min_overlap = FTS5_KEYWORD_MATCH_THRESHOLD
    conn = get_conn()
    if not keyword or not keyword.strip():
        # 空关键词 → 返回全部（向后兼容）
        sql = "SELECT * FROM knowledge_base"
        params = []
        if category_filter and category_filter != "全部":
            sql += " WHERE fault_category = %s"
            params.append(category_filter)
        sql += f" ORDER BY created_at DESC LIMIT {FTS5_SEARCH_LIMIT}"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return _rows_to_dicts(rows)

    # tsvector查询：jieba预分词 + to_tsquery OR语义 + 阈值≥3过滤（0824 迁移 PG：FTS5 → tsvector）
    # 0824 安全加固：token 化转义（剔除保留字/特殊字符），
    # 防止检索语法注入（OR/AND/NEAR/^/*/rowid: 等操作符被用户输入激活）
    query_tokens = set(_fts_safe_tokens(keyword))
    if not query_tokens:
        # 输入全为保留字/单字/标点，无有效检索词 → 返回空
        conn.close()
        return []
    query_fts = " | ".join(query_tokens)          # to_tsquery OR 语义

    where_parts = ["search_tsv @@ to_tsquery('simple', %s)"]
    params = [query_fts]
    if category_filter and category_filter != "全部":
        where_parts.append("knowledge_base.fault_category = %s")
        params.append(category_filter)

    try:
        rows = conn.execute(f"""
            SELECT knowledge_base.*, knowledge_base.search_index
            FROM knowledge_base
            WHERE {' AND '.join(where_parts)}
            ORDER BY ts_rank_cd(search_tsv, to_tsquery('simple', %s)) DESC
            LIMIT {FTS5_SEARCH_LIMIT}
        """, params + [query_fts]).fetchall()
    except Exception:
        # tsquery 特殊字符异常时降级LIKE（%/_ 通配符转义，防 LIKE 恒真/全表返回）
        like_kw = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_params = ["%" + like_kw + "%"] * 5
        sql = ("SELECT * FROM knowledge_base WHERE "
               "(title LIKE %s ESCAPE '\\' OR fault_keywords LIKE %s ESCAPE '\\' "
               "OR solution LIKE %s ESCAPE '\\' OR lesson_learned LIKE %s ESCAPE '\\' "
               "OR contact_author LIKE %s ESCAPE '\\')")
        if category_filter and category_filter != "全部":
            sql += " AND fault_category = %s"
            like_params.append(category_filter)
        sql += f" ORDER BY created_at DESC LIMIT {FTS5_SEARCH_LIMIT}"
        rows = conn.execute(sql, like_params).fetchall()
        conn.close()
        return _rows_to_dicts(rows)

    # 0715 jieba阈值过滤：查询词与文档索引词交集 ≥ 3 才视为有效匹配
    results = []
    for row in rows:
        doc_tokens = set((row["search_index"] or "").split())
        if query_tokens:
            overlap = len(query_tokens & doc_tokens)
            if overlap < min_overlap:
                continue
        results.append(_kb_row_clean(dict(row)))

    conn.close()
    return results


# 0730 现象专用搜索 — 仅匹配 fault_phenomenon 字段（Python jieba 内存匹配）
def search_kb_by_phenomenon(keyword, category_filter="", min_overlap=None):
    """搜索知识库 — 仅匹配 fault_phenomenon 字段。
    用于工单处理页的相似案例检索，避免故障现象匹配到其他案例的解决方案/根因。
    FTS5 默认 tokenizer 不支持中文分词，改用 Python jieba 内存 token 匹配。

    0908 RAG 阶段 1 领域词加权（docs/05 §5.5）：匹配分 = 领域词（domain_dict）重合 ×
    KEYWORD_DOMAIN_WORD_WEIGHT + 通用词重合 × 1，min_overlap 语义从"重合词数"改为
    "加权分"（0923 实测中"卡死"等单词领域命中即强相关，词数口径漏召回）；
    结果按匹配分降序，行内附带 keyword_score 供 RRF 融合与观测。"""
    if min_overlap is None:
        min_overlap = FTS5_KEYWORD_MATCH_THRESHOLD
    conn = get_conn()

    # 构建 SQL：拉取 fault_phenomenon 非空的所有记录
    # 0923 空壳过滤：根因与方案均为空的条目不参与检索——无内容可引用，
    # 命中只会给 LLM"伪历史案例"背书（知识库列表展示不受此过滤影响）
    sql = ("SELECT * FROM knowledge_base "
           "WHERE fault_phenomenon IS NOT NULL AND fault_phenomenon != '' "
           "AND (COALESCE(root_cause, '') != '' OR COALESCE(solution, '') != '')")
    params = []
    if category_filter and category_filter != "全部":
        sql += " AND fault_category = %s"
        params.append(category_filter)

    if not keyword or not keyword.strip():
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return _rows_to_dicts(rows)

    query_tokens_str = _jieba_tokenize(keyword)
    query_tokens = set(query_tokens_str.split()) if query_tokens_str else set()
    if not query_tokens:
        conn.close()
        return []

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    domain = _domain_words()
    results = []
    for row in rows:
        d = _kb_row_clean(dict(row))
        fp_tokens = set(_jieba_tokenize(d.get("fault_phenomenon", "") or "").split())
        overlap_tokens = query_tokens & fp_tokens
        score = sum(KEYWORD_DOMAIN_WORD_WEIGHT if t in domain else 1 for t in overlap_tokens)
        if score >= min_overlap:
            d["keyword_score"] = score
            results.append(d)
    results.sort(key=lambda d: d["keyword_score"], reverse=True)
    return results


# 0908 RAG 阶段 1：pgvector 向量通道 DAO（余弦相似度；类别优先/分级放开由调用方级联）
def search_kb_by_vector(query_vec: list[float], top_k: int = 20,
                        category_filter: str = "", min_similarity: float | None = None,
                        embed_model_name: str = "") -> list[dict]:
    """向量通道检索：knowledge_base.embedding 余弦相似度 Top-K。

    - 与关键词通道同构的空壳过滤（根因/方案均为空不参与检索）；
    - 仅比较 embed_model 一致的行（不同模型的向量余弦无意义，docs/05 §4.4）；
    - pgvector 未启用或入参为空直接返回 []（调用方按通道缺席处理）；
    - 行内附带 vector_score（余弦相似度）与 embed_model 的透传由 _kb_row_clean
      剥离 embedding 原始列（~10KB/条）。
    """
    if not _PGVECTOR_ENABLED or not query_vec:
        return []
    if min_similarity is None:
        min_similarity = VECTOR_MIN_SIMILARITY
    if not embed_model_name:
        embed_model_name = os.environ.get("EMBEDDING_API_MODEL", "BAAI/bge-m3")

    vec_literal = "[" + ",".join(f"{x:.6f}" for x in query_vec) + "]"
    conn = get_conn()
    try:
        sql = (
            "SELECT *, 1 - (embedding <=> %s::vector) AS vector_score "
            "FROM knowledge_base "
            "WHERE embedding IS NOT NULL "
            "AND COALESCE(embed_model, '') = %s "
            "AND fault_phenomenon IS NOT NULL AND fault_phenomenon != '' "
            "AND (COALESCE(root_cause, '') != '' OR COALESCE(solution, '') != '') "
            "AND 1 - (embedding <=> %s::vector) >= %s "
        )
        bind = [vec_literal, embed_model_name, vec_literal, min_similarity]
        if category_filter and category_filter != "全部":
            sql += "AND fault_category = %s "
            bind.append(category_filter)
        sql += f"ORDER BY embedding <=> %s::vector LIMIT {int(top_k)}"
        bind.append(vec_literal)
        rows = conn.execute(sql, bind).fetchall()
    except Exception as e:
        print(f"[search_kb_by_vector] 向量检索失败，通道本轮跳过：{type(e).__name__}: {e}", flush=True)
        conn.close()
        return []
    conn.close()
    results = []
    for row in rows:
        d = _kb_row_clean(dict(row))
        d["vector_score"] = row["vector_score"]
        results.append(d)
    return results


def update_kb_embedding(kb_id: int, vec: list[float], embed_model_name: str) -> bool:
    """写入/刷新 KB 条目向量（0908 RAG 阶段 1）。失败回滚返回 False（调用方记日志，
    回填脚本可后补）。"""
    if not _PGVECTOR_ENABLED:
        return False
    conn = get_conn()
    try:
        vec_literal = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
        conn.execute(
            "UPDATE knowledge_base SET embedding = %s::vector, embed_model = %s, "
            "embedded_at = (now() AT TIME ZONE 'Asia/Shanghai') WHERE id = %s",
            (vec_literal, embed_model_name, kb_id),
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[update_kb_embedding] KB#{kb_id} 向量写入失败：{type(e).__name__}: {e}", flush=True)
        return False
    finally:
        conn.close()


def list_kb_missing_embedding(embed_model_name: str) -> list[dict]:
    """回填脚本用：返回待生成向量的 KB 行（embedding 为空或模型不一致需重刷）。
    pgvector 未启用时返回 []（脚本侧会先检查并给出说明）。"""
    if not _PGVECTOR_ENABLED:
        return []
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, title, fault_category, equipment_model, fault_keywords, "
            "root_cause, solution, checklist, lesson_learned, contact_author, fault_phenomenon "
            "FROM knowledge_base "
            "WHERE embedding IS NULL OR COALESCE(embed_model, '') != %s "
            "ORDER BY id",
            (embed_model_name,),
        ).fetchall()
    except Exception:
        conn.close()
        return []
    conn.close()
    return [dict(r) for r in rows]


def get_all_kb():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM knowledge_base ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 0716 知识库质量反馈：👍 有帮助 +1
# 0717 增加 1 分钟限频：同一账号对同一 KB 条目 1 分钟内只能评价一次
KB_FEEDBACK_COOLDOWN_SECONDS = 60  # 冷却时间（秒）


# 0723 冷却检查增加可选的 feedback_type 参数，支持按维度独立冷却
def check_kb_feedback_cooldown(kb_id: int, user_account: str, feedback_type: str = "") -> int | None:
    """查询该用户对该 KB 条目（指定类型）最近一次评价距今的秒数。
    feedback_type 为空时查所有类型（向后兼容旧逻辑）。
    返回 None 表示从未评价过（可以评价）。"""
    try:
        conn = get_conn()
        if feedback_type:
            row = conn.execute(
                """SELECT EXTRACT(EPOCH FROM (now() AT TIME ZONE 'Asia/Shanghai' - created_at)) AS seconds_ago
                   FROM kb_feedback_log
                   WHERE kb_id = %s AND user_account = %s AND feedback_type = %s
                   ORDER BY created_at DESC LIMIT 1""",
                (kb_id, user_account, feedback_type),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT EXTRACT(EPOCH FROM (now() AT TIME ZONE 'Asia/Shanghai' - created_at)) AS seconds_ago
                   FROM kb_feedback_log
                   WHERE kb_id = %s AND user_account = %s
                   ORDER BY created_at DESC LIMIT 1""",
                (kb_id, user_account),
            ).fetchone()
        conn.close()
        if row and row["seconds_ago"] is not None:
            return int(row["seconds_ago"])
        return None
    except Exception:
        return None


def increment_kb_useful(kb_id: int, user_account: str = "") -> bool:
    """用户点击 👍 时 useful_count+1。
    返回 True 表示评价成功，False 表示在冷却期内被阻止。"""
    if user_account:
        cooldown = check_kb_feedback_cooldown(kb_id, user_account)
        if cooldown is not None and cooldown < KB_FEEDBACK_COOLDOWN_SECONDS:
            return False
    try:
        conn = get_conn()
        conn.execute(
            "UPDATE knowledge_base SET useful_count = useful_count + 1 WHERE id = %s",
            (kb_id,),
        )
        if user_account:
            conn.execute(
                "INSERT INTO kb_feedback_log (kb_id, user_account, feedback_type) VALUES (%s, %s, 'useful')",
                (kb_id, user_account),
            )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# 0716 知识库质量反馈：👎 无帮助 +1
# 0717 增加 1 分钟限频
def increment_kb_unhelpful(kb_id: int, user_account: str = "") -> bool:
    """用户点击 👎 时 unhelpful_count+1。
    返回 True 表示评价成功，False 表示在冷却期内被阻止。"""
    if user_account:
        cooldown = check_kb_feedback_cooldown(kb_id, user_account)
        if cooldown is not None and cooldown < KB_FEEDBACK_COOLDOWN_SECONDS:
            return False
    try:
        conn = get_conn()
        conn.execute(
            "UPDATE knowledge_base SET unhelpful_count = unhelpful_count + 1 WHERE id = %s",
            (kb_id,),
        )
        if user_account:
            conn.execute(
                "INSERT INTO kb_feedback_log (kb_id, user_account, feedback_type) VALUES (%s, %s, 'unhelpful')",
                (kb_id, user_account),
            )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# 0723 知识库多维度评价：统一维度评价入口
# dimension ∈ {'accuracy','effectiveness','clarity','customer_impact','presales_value'}
DIMENSION_COLUMN_MAP = {
    "accuracy": "accuracy_votes",
    "effectiveness": "effectiveness_votes",
    "clarity": "clarity_votes",
    "customer_impact": "customer_impact_votes",
    "presales_value": "presales_value_votes",
}


def increment_kb_dimension(kb_id: int, user_account: str, dimension: str) -> bool:
    """对知识库条目的特定维度进行评价。
    dimension: 'accuracy'|'effectiveness'|'clarity'|'customer_impact'|'presales_value'
    返回 True 表示评价成功，False 表示在冷却期内被阻止。"""
    column = DIMENSION_COLUMN_MAP.get(dimension)
    if not column:
        return False
    if user_account:
        cooldown = check_kb_feedback_cooldown(kb_id, user_account, dimension)
        if cooldown is not None and cooldown < KB_FEEDBACK_COOLDOWN_SECONDS:
            return False
    try:
        conn = get_conn()
        conn.execute(
            f"UPDATE knowledge_base SET {column} = {column} + 1 WHERE id = %s",
            (kb_id,),
        )
        if user_account:
            conn.execute(
                "INSERT INTO kb_feedback_log (kb_id, user_account, feedback_type) VALUES (%s, %s, %s)",
                (kb_id, user_account, dimension),
            )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# 0723 根据客诉编号查询客户满意度（用于知识库卡片展示，非评价维度）
def get_complaint_satisfaction_by_no(complaint_no: str) -> int | None:
    """查询指定客诉编号的客户满意度。返回 0-5 或 None（无数据）。"""
    if not complaint_no:
        return None
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT satisfaction FROM complaints WHERE complaint_no = %s AND satisfaction IS NOT NULL AND satisfaction > 0 LIMIT 1",
            (complaint_no,),
        ).fetchone()
        conn.close()
        if row:
            val = row["satisfaction"]
            if val is not None and int(val) > 0:
                return int(val)
        return None
    except Exception:
        return None


# 0716 知识库质量反馈：批量 👍（已废弃，0717 起不再使用）
def batch_increment_kb_useful(kb_ids: list[int], user_account: str = "") -> list[int]:
    """批量 👍（保留兼容，新代码应逐条调用 increment_kb_useful 并传 user_account）"""
    success = []
    for kid in kb_ids:
        if increment_kb_useful(kid, user_account):
            success.append(kid)
    return success


# 0716 知识库质量反馈：批量 👎（已废弃，0717 起不再使用）
def batch_increment_kb_unhelpful(kb_ids: list[int], user_account: str = "") -> list[int]:
    """批量 👎（保留兼容，新代码应逐条调用 increment_kb_unhelpful 并传 user_account）"""
    success = []
    for kid in kb_ids:
        if increment_kb_unhelpful(kid, user_account):
            success.append(kid)
    return success


# 0716 知识库质量看板：总览统计（0723 扩展维度统计）
def get_kb_quality_stats() -> dict:
    """知识库质量总览：总条数、高价值数、零反馈陈旧数、待修订数、平均好评率、维度统计"""
    conn = get_conn()
    row = conn.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN useful_count > 0 AND useful_count >= unhelpful_count + 2 THEN 1 END) AS high_value_count,
            COUNT(CASE WHEN useful_count + unhelpful_count = 0
                AND created_at < now() AT TIME ZONE 'Asia/Shanghai' - interval '3 months' THEN 1 END) AS stale_count,
            COUNT(CASE WHEN unhelpful_count > useful_count THEN 1 END) AS needs_review_count,
            ROUND(AVG(CASE WHEN useful_count + unhelpful_count > 0
                THEN useful_count * 100.0 / (useful_count + unhelpful_count) END), 1) AS avg_positive_pct,
            -- 0723 维度统计（0723-v2 移除 customer_satisfy，改为从工单满意度读取）
            COALESCE(SUM(accuracy_votes), 0) AS accuracy_total,
            COALESCE(SUM(effectiveness_votes), 0) AS effectiveness_total,
            COALESCE(SUM(clarity_votes), 0) AS clarity_total,
            COALESCE(SUM(customer_impact_votes), 0) AS customer_impact_total,
            COALESCE(SUM(presales_value_votes), 0) AS presales_value_total,
            COUNT(CASE WHEN accuracy_votes + effectiveness_votes + clarity_votes +
                             customer_impact_votes +
                             presales_value_votes > 0 THEN 1 END) AS dimension_eval_count,
            -- 0723-v2 顶级案例：技术分≥5 且 商业分≥3（不含 customer_satisfy）
            COUNT(CASE WHEN useful_count >= COALESCE(unhelpful_count, 0)
                AND (accuracy_votes * 3 + effectiveness_votes * 3 + clarity_votes * 2) >= 5
                AND (customer_impact_votes * 2 + presales_value_votes * 3) >= 3
                THEN 1 END) AS top_tier_count,
            -- 0723-v3 工程师推荐：工程师分≥阈值 且 好评≥差评
            COUNT(CASE WHEN useful_count >= COALESCE(unhelpful_count, 0)
                AND (accuracy_votes * 3 + effectiveness_votes * 3 + clarity_votes * 2) >= 3
                THEN 1 END) AS engineer_rec_count,
            -- 0723-v3 售前推荐：改用售前分阈值（customer_impact*2 + presales_value*3 >= 3）
            COUNT(CASE WHEN useful_count >= COALESCE(unhelpful_count, 0)
                AND (customer_impact_votes * 2 + presales_value_votes * 3) >= 3
                THEN 1 END) AS presales_rec_count
        FROM knowledge_base
    """).fetchone()
    conn.close()
    return dict(row) if row else {}


# 0716 知识库质量看板：高价值 TOP N（0723 扩展综合评分 = 技术分 + 商业分 + 好评）
# 0723-v3 拆分为工程师分 + 售前分 + 综合分 双视角评估
def get_kb_top_valuable(limit: int = 10) -> list[dict]:
    """高价值 TOP N：综合评分 DESC，好评率 >= 50%，至少 1 票。
    0723-v3 新增 engineer_score（工程师视角）和 presales_score（售前视角）子得分。"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT *,
            useful_count * 100.0 / NULLIF(useful_count + unhelpful_count, 0) AS positive_pct,
            -- 0723-v3 工程师分：技术质量维度（根因准确、方案有效、步骤清晰）
            (COALESCE(accuracy_votes, 0) * 3
             + COALESCE(effectiveness_votes, 0) * 3
             + COALESCE(clarity_votes, 0) * 2) AS engineer_score,
            -- 0723-v3 售前分：商业价值维度（客户影响、售前标杆）
            (COALESCE(customer_impact_votes, 0) * 2
             + COALESCE(presales_value_votes, 0) * 3) AS presales_score,
            -- 综合分 = 工程师分 + 售前分 + 通用好评（与旧公式等价）
            (COALESCE(accuracy_votes, 0) * 3
             + COALESCE(effectiveness_votes, 0) * 3
             + COALESCE(clarity_votes, 0) * 2
             + COALESCE(customer_impact_votes, 0) * 2
             + COALESCE(presales_value_votes, 0) * 3
             + COALESCE(useful_count, 0)) AS composite_score
        FROM knowledge_base
        WHERE useful_count > 0 AND useful_count >= unhelpful_count
        ORDER BY composite_score DESC
        LIMIT %s
    """, (limit,)).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 0716 知识库质量看板：待修订条目（unhelpful_count > useful_count）
def get_kb_needs_review() -> list[dict]:
    """待修订：差评多于好评"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT *, useful_count * 100.0 / NULLIF(useful_count + unhelpful_count, 0) AS positive_pct
        FROM knowledge_base
        WHERE unhelpful_count > useful_count
        ORDER BY (unhelpful_count - useful_count) DESC
    """).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 0716 知识库质量看板：陈旧条目（> N 月零反馈）
def get_kb_stale(months: int = 3) -> list[dict]:
    """陈旧：创建 > N 月，且 useful_count + unhelpful_count = 0"""
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT *
        FROM knowledge_base
        WHERE useful_count + unhelpful_count = 0
          AND created_at < now() AT TIME ZONE 'Asia/Shanghai' - interval '{months} months'
        ORDER BY created_at ASC
    """).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 0715 P0-2：记录LLM调用日志（不抛异常，避免影响主流程）
def record_llm_call(function_name: str, model: str, latency_ms: int,
                    prompt_chars: int, status: str, error_msg: str = "",
                    triggered_by: str = "", complaint_id: int = 0):
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO llm_call_log (function_name, model, latency_ms, prompt_chars, status, error_msg, "
            "triggered_by, complaint_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (function_name, model, latency_ms, prompt_chars, status, error_msg,
             triggered_by, complaint_id)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# 0824 钉钉通知：记录发送日志（仿 record_llm_call，不抛异常，避免影响主流程）
def record_dingtalk_send(complaint_no: str, target_role: str,
                         target_user_ids: str, dingtalk_userids: str,
                         status: str, error_msg: str = ""):
    try:
        conn = get_conn()
        conn.execute(
            "INSERT INTO dingtalk_send_log (complaint_no, target_role, target_user_ids, "
            "dingtalk_userids, message_type, status, error_msg) "
            "VALUES (%s, %s, %s, %s, 'action_card', %s, %s)",
            (complaint_no, target_role, target_user_ids, dingtalk_userids,
             status, error_msg),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ── 工程师进度更新（D9，0616 升级新增）─────────
def create_progress_update(complaint_id: int, progress_pct: int, note: str, updated_by: str):
    """工程师每周（或按节点）更新工单进度百分比。"""
    pct = max(0, min(100, int(progress_pct)))
    conn = get_conn()
    rid = conn.execute(
        "INSERT INTO progress_updates (complaint_id, progress_pct, note, updated_by) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (complaint_id, pct, note, updated_by),
    ).fetchone()["id"]
    conn.commit()
    conn.close()
    return rid


def list_progress_updates(complaint_id: int) -> list[dict]:
    """按时间倒序返回某工单的全部进度历史。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM progress_updates WHERE complaint_id = %s "
        "ORDER BY created_at DESC, id DESC",
        (complaint_id,),
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def latest_progress(complaint_id: int):
    """返回最新一条进度记录，无则 None。"""
    rows = list_progress_updates(complaint_id)
    return rows[0] if rows else None


# 0713 统计工程师处理工单耗时（首次提交进度 → 最后提交进度，单位：小时）
def get_engineer_processing_hours(complaint_id: int):
    """返回处理耗时（小时），仅有一条或无进度记录时返回 None。"""
    conn = get_conn()
    row = conn.execute("""
        SELECT
            MIN(created_at) AS first_update,
            MAX(created_at) AS last_update,
            ROUND(EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) / 3600.0, 1) AS hours
        FROM progress_updates
        WHERE complaint_id = %s
        HAVING MIN(created_at) != MAX(created_at)
    """, (complaint_id,)).fetchone()
    conn.close()
    if row and row["hours"] is not None:
        return row["hours"]
    return None


# 0713 查询某承接人当前处理中的工单（0819 改为 complaint_assignees 按显示名关联）
def get_engineer_active_complaints(engineer_name: str) -> list[dict]:
    """0819 查询某承接人（按显示名）当前「处理中」的工单列表。"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT c.* FROM complaint_assignees ca
           JOIN complaints c ON c.id = ca.complaint_id
           JOIN users u ON u.id = ca.user_id
           WHERE u.display_name = %s AND ca.assignee_type = 'assignee' AND ca.is_active = 1
             AND c.status = '处理中'""",
        (engineer_name,)
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 0728 AI 排期建议 — 承接人历史统计（0819 按 complaint_assignees 统计）
def get_engineer_avg_stats(engineer_name: str) -> dict:
    """0819 返回某承接人（按显示名）的历史统计：已关闭工单数、平均全程耗时（小时）。"""
    conn = get_conn()
    row = conn.execute("""
        SELECT COUNT(*) as total_closed,
               ROUND(AVG(EXTRACT(EPOCH FROM (c.closed_at - c.created_at)) / 3600.0), 1) as avg_hours
        FROM complaint_assignees ca
        JOIN complaints c ON c.id = ca.complaint_id
        JOIN users u ON u.id = ca.user_id
        WHERE u.display_name = %s AND ca.assignee_type = 'assignee'
          AND c.status = '已关闭' AND c.closed_at IS NOT NULL
    """, (engineer_name,)).fetchone()
    conn.close()
    return dict(row) if row else {"total_closed": 0, "avg_hours": 0}


# 0728 AI 排期建议 — 同类别平均耗时
def get_category_avg_hours(fault_category: str) -> dict:
    """返回同故障类别的已关闭工单平均全程耗时（小时）。"""
    conn = get_conn()
    row = conn.execute("""
        SELECT COUNT(*) as total_closed,
               ROUND(AVG(EXTRACT(EPOCH FROM (closed_at - created_at)) / 3600.0), 1) as avg_hours
        FROM complaints
        WHERE fault_category = %s AND status = '已关闭' AND closed_at IS NOT NULL
    """, (fault_category,)).fetchone()
    conn.close()
    return dict(row) if row else {"total_closed": 0, "avg_hours": 0}


# ── 客诉分析（运营洞察）聚合查询 ─────────────────────

# 0713 客诉分析页面的日期范围筛选辅助函数
# 0824 迁移 PG：strftime/datetime 修饰符 → to_char / date_trunc（月初归一语义保持）
def _build_date_filter(date_range: str, column: str = "created_at"):
    """根据时间范围生成 WHERE 子句，返回 (clause, params)。
    注意：所有日期计算必须先归一到每月 1 号再运算，避免月尾天数差异导致的错误。
    例如 7月31日 -1 month → 归一化为 7月1日（因6月无31日），"上月"结果与"本月"相同。
    """
    now_sh = "now() AT TIME ZONE 'Asia/Shanghai'"
    if date_range == "本月":
        return (
            f"to_char({column}, 'YYYY-MM') = to_char({now_sh}, 'YYYY-MM')",
            []
        )
    elif date_range == "上月":
        # 先归一到本月1号再减1天 → 上月最后一天 → 取月份
        return (
            f"to_char({column}, 'YYYY-MM') = to_char(date_trunc('month', {now_sh}) - interval '1 day', 'YYYY-MM')",
            []
        )
    elif date_range == "近3个月":
        return (
            f"{column} >= date_trunc('month', {now_sh}) - interval '2 months'",
            []
        )
    elif date_range == "近6个月":
        return (
            f"{column} >= date_trunc('month', {now_sh}) - interval '5 months'",
            []
        )
    else:  # "全部"
        return ("1=1", [])


# 0713 客诉分析 KPI 总览（0819 v3.0 新状态计数）
def get_analytics_kpi_overview(date_range: str) -> dict:
    conn = get_conn()
    where_clause, _ = _build_date_filter(date_range)
    row = conn.execute(f"""
        SELECT
            COUNT(*) AS total,
            ROUND(AVG(CASE WHEN satisfaction > 0 THEN satisfaction END), 2) AS avg_satisfaction,
            ROUND(SUM(is_rework) * 100.0 / NULLIF(COUNT(*), 0), 1) AS rework_rate_pct,
            ROUND(AVG(CASE WHEN closed_at IS NOT NULL
                THEN EXTRACT(EPOCH FROM (closed_at - created_at)) / 3600.0 END), 1) AS avg_processing_hours,
            SUM(CASE WHEN expected_complete_date != '' AND expected_complete_date IS NOT NULL
                AND expected_complete_date::date < (now() AT TIME ZONE 'Asia/Shanghai')::date
                AND status NOT IN ('已关闭', '已撤回') THEN 1 ELSE 0 END) AS overdue_count,
            COUNT(CASE WHEN status = '已关闭' THEN 1 END) AS closed_count,
            COUNT(CASE WHEN status = '已撤回' THEN 1 END) AS withdrawn_count,
            COUNT(CASE WHEN status = '待客服处理' THEN 1 END) AS pending_cs_count,
            COUNT(CASE WHEN status = '待客户排查' THEN 1 END) AS pending_customer_check_count,
            COUNT(CASE WHEN status = '客服主管审核' THEN 1 END) AS pending_review_count,
            COUNT(CASE WHEN status = '指派审批人' THEN 1 END) AS pending_approver_count,
            COUNT(CASE WHEN status = '指派承接人' THEN 1 END) AS pending_assign_count,
            COUNT(CASE WHEN status = '处理中' THEN 1 END) AS in_progress_count,
            COUNT(CASE WHEN status = '待客服处理' AND sub_type = 'customer_confirm' THEN 1 END) AS pending_customer_count
        FROM complaints
        WHERE {where_clause}
    """).fetchone()
    conn.close()
    return dict(row) if row else {}


# 0713 客诉分析 月度工单趋势
def get_analytics_monthly_trend(date_range: str) -> list[dict]:
    conn = get_conn()
    where_clause, _ = _build_date_filter(date_range)
    rows = conn.execute(f"""
        SELECT
            to_char(created_at, 'YYYY-MM') AS period,
            COUNT(*) AS total,
            COUNT(CASE WHEN status = '已关闭' THEN 1 END) AS closed_count
        FROM complaints
        WHERE {where_clause}
        GROUP BY period
        ORDER BY period
    """).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 1014 首页四卡统计：单条 COUNT 聚合（口径：总 = 处理中+待处理+已关闭+已撤回；待处理不含处理中）
def get_complaint_status_stats() -> dict:
    conn = get_conn()
    row = conn.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN status = '处理中' THEN 1 END) AS in_progress,
            COUNT(CASE WHEN status IN ('待客服处理', '待客户排查', '客服主管审核',
                                       '指派审批人', '指派承接人') THEN 1 END) AS pending,
            COUNT(CASE WHEN status = '已关闭' THEN 1 END) AS closed,
            COUNT(CASE WHEN status = '已撤回' THEN 1 END) AS withdrawn
        FROM complaints
    """).fetchone()
    conn.close()
    return dict(row) if row else {"total": 0, "in_progress": 0, "pending": 0, "closed": 0, "withdrawn": 0}


# 0713 客诉分析 当月每日工单趋势
def get_analytics_daily_trend(date_range: str) -> list[dict]:
    conn = get_conn()
    where_clause, _ = _build_date_filter(date_range)
    rows = conn.execute(f"""
        SELECT
            to_char(created_at, 'MM-DD') AS period,
            COUNT(*) AS total,
            COUNT(CASE WHEN status = '已关闭' THEN 1 END) AS closed_count
        FROM complaints
        WHERE {where_clause}
        GROUP BY period
        ORDER BY period
    """).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 0713 客诉分析 故障类别分布
def get_analytics_category_distribution(date_range: str) -> list[dict]:
    conn = get_conn()
    where_clause, _ = _build_date_filter(date_range)
    rows = conn.execute(f"""
        SELECT
            fault_category,
            COUNT(*) AS cnt
        FROM complaints
        WHERE {where_clause} AND fault_category != ''
        GROUP BY fault_category
        ORDER BY cnt DESC
    """).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 0713 客诉分析 优先级分布
def get_analytics_priority_distribution(date_range: str) -> list[dict]:
    conn = get_conn()
    where_clause, _ = _build_date_filter(date_range)
    rows = conn.execute(f"""
        SELECT
            priority,
            COUNT(*) AS cnt
        FROM complaints
        WHERE {where_clause}
        GROUP BY priority
    """).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 0713 客诉分析 状态分布
def get_analytics_status_distribution(date_range: str) -> list[dict]:
    conn = get_conn()
    where_clause, _ = _build_date_filter(date_range)
    rows = conn.execute(f"""
        SELECT
            status,
            COUNT(*) AS cnt
        FROM complaints
        WHERE {where_clause}
        GROUP BY status
    """).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 0713 客诉分析 TOP N 客户排名
def get_analytics_customer_top(date_range: str, limit: int = 10) -> list[dict]:
    conn = get_conn()
    where_clause, _ = _build_date_filter(date_range)
    rows = conn.execute(f"""
        SELECT
            customer_name,
            COUNT(*) AS cnt
        FROM complaints
        WHERE {where_clause} AND customer_name != ''
        GROUP BY customer_name
        ORDER BY cnt DESC
        LIMIT %s
    """, (limit,)).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 0713 客诉分析 TOP N 设备型号排名
def get_analytics_equipment_top(date_range: str, limit: int = 10) -> list[dict]:
    conn = get_conn()
    where_clause, _ = _build_date_filter(date_range)
    rows = conn.execute(f"""
        SELECT
            equipment_model,
            COUNT(*) AS cnt
        FROM complaints
        WHERE {where_clause} AND equipment_model != ''
        GROUP BY equipment_model
        ORDER BY cnt DESC
        LIMIT %s
    """, (limit,)).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# ── 用户账号管理 ─────────────────────────────────────

# 0714 密码哈希（SHA-256 + 固定 salt）
def _hash_password(password: str) -> str:
    salt = "kh_cs_2026"
    return hashlib.sha256((password + salt).encode()).hexdigest()


# 0714 初始化用户表及默认账号（幂等）
# 0819 v3.0：角色直接存 users.role（建号时下拉选择），默认账号仅 admin
# 0824 迁移 PG：users 主 DDL 已并入 init_db()（complaint_assignees 外键依赖），此处保留幂等副本
def init_users():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'Asia/Shanghai')
        )
    """)
    # 兼容旧库：缺失列幂等追加（center/department/is_dept_head 已弃用，仅保留列）
    for col_def in [
        "role TEXT DEFAULT ''",
        "department TEXT DEFAULT ''",
        "is_dept_head INTEGER DEFAULT 0",
        "updated_at TIMESTAMP",
        "center TEXT DEFAULT ''",
        "position TEXT DEFAULT ''",
        "dingtalk_userid TEXT DEFAULT ''",
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_def}")
        except Exception:
            pass

    # 0819 默认账号：仅 admin（已存在时不重置密码，仅补全缺失字段）
    pwd_hash = _hash_password("admin123")
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role, position) "
            "VALUES (%s, %s, %s, %s, %s)",
            ("admin", pwd_hash, "系统管理员", "管理员", "系统管理员"),
        )
    except errors.UniqueViolation:
        # 0824 迁移 PG：失败后事务已中止，须先 rollback 再继续（已存在则补全 role/position，不触碰密码与显示名）
        conn.rollback()
        conn.execute(
            "UPDATE users SET role = CASE WHEN role IS NULL OR role = '' THEN '管理员' ELSE role END, "
            "position = CASE WHEN position IS NULL OR position = '' THEN '系统管理员' ELSE position END "
            "WHERE username = 'admin'"
        )
    conn.commit()
    conn.close()


# 0714 验证账号密码；0819 取消中心校验，仅账号+密码+启用状态
def verify_user(username: str, password: str, center: str = "") -> dict | None:
    """验证账号密码（center 参数已弃用，保留签名兼容旧调用）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE username = %s AND is_active = 1",
        (username,),
    ).fetchone()
    conn.close()
    if row and row["password_hash"] == _hash_password(password):
        return dict(row)
    return None


# ═══════════════════════════════════════ 0723 用户管理 CRUD（0819 角色+职位） ═══════════════════════════════════════

def list_users(role_filter: str = "", dept_filter: str = "",
               include_inactive: bool = False) -> list[dict]:
    """列出用户，支持按角色筛选，可选包含已停用用户（dept_filter 已弃用，保留签名兼容）。"""
    conn = get_conn()
    if include_inactive:
        sql = "SELECT * FROM users WHERE 1=1"
    else:
        sql = "SELECT * FROM users WHERE is_active = 1"
    params = []
    if role_filter:
        sql += " AND role = %s"
        params.append(role_filter)
    sql += " ORDER BY is_active DESC, role, username"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_user_by_id(user_id: int) -> dict | None:
    """按 ID 获取用户。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_username(username: str) -> dict | None:
    """按用户名获取用户（含已停用）。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = %s", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_users_by_display_names(names: list[str]) -> dict[str, dict]:
    """1016 按姓名精确匹配启用用户（工单预警指名人名单用），返回 {display_name: 用户行}。
    匹配不到的姓名不进结果，由调用方收集为 missing 提示。"""
    names = [n.strip() for n in (names or []) if n and n.strip()]
    if not names:
        return {}
    conn = get_conn()
    placeholders = ",".join("%s" for _ in names)
    rows = conn.execute(
        f"SELECT id, username, display_name, role, position FROM users "
        f"WHERE is_active = 1 AND display_name IN ({placeholders})",
        names,
    ).fetchall()
    conn.close()
    return {r["display_name"]: dict(r) for r in rows}


def get_users_by_roles(roles: list[str]) -> list[dict]:
    """0819 按角色列表查询启用用户（指派下拉数据源），
    返回 id/username/display_name/role/position。"""
    if not roles:
        return []
    conn = get_conn()
    placeholders = ",".join("%s" for _ in roles)
    rows = conn.execute(
        f"SELECT id, username, display_name, role, position FROM users "
        f"WHERE is_active = 1 AND role IN ({placeholders}) "
        "ORDER BY role, position, display_name",
        roles,
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_users_dingtalk_bindings(roles: list[str] | None = None,
                                user_ids: list[int] | None = None) -> list[dict]:
    """0824 钉钉通知：查询启用且已绑定钉钉的用户。
    roles：按角色过滤（None=不限）；user_ids：按用户ID过滤。
    返回 id/username/display_name/role/position/dingtalk_userid。"""
    conn = get_conn()
    sql = ("SELECT id, username, display_name, role, position, dingtalk_userid "
           "FROM users WHERE is_active = 1 AND dingtalk_userid != ''")
    params: list = []
    if roles:
        placeholders = ",".join("%s" for _ in roles)
        sql += f" AND role IN ({placeholders})"
        params.extend(roles)
    if user_ids:
        placeholders = ",".join("%s" for _ in user_ids)
        sql += f" AND id IN ({placeholders})"
        params.extend(user_ids)
    rows = conn.execute(sql + " ORDER BY id", params).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def create_user(username: str, password: str, display_name: str,
                role: str, position: str = "",
                dingtalk_userid: str = "") -> int | None:
    """0819 创建新用户（角色+职位；0824 增钉钉UserID绑定），返回 user_id；用户名已存在则返回 None。"""
    conn = get_conn()
    pwd_hash = _hash_password(password)
    try:
        uid = conn.execute(
            "INSERT INTO users (username, password_hash, display_name, role, position, dingtalk_userid) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (username, pwd_hash, display_name, role, position, dingtalk_userid),
        ).fetchone()["id"]
        conn.commit()
        conn.close()
        return uid
    except errors.UniqueViolation:
        # 0824 迁移 PG：失败后事务已中止，须先 rollback 再关闭连接
        conn.rollback()
        conn.close()
        return None


def update_user(user_id: int, **kwargs) -> bool:
    """0819 更新用户属性（display_name, role, position, is_active；0824 增 dingtalk_userid）。"""
    allowed = {"display_name", "role", "position", "is_active", "dingtalk_userid"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    updates["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [user_id]
    conn = get_conn()
    conn.execute(f"UPDATE users SET {set_clause} WHERE id = %s", values)
    conn.commit()
    conn.close()
    return True


def deactivate_user(user_id: int) -> bool:
    """软删除用户（is_active = 0）。管理员账号不允许停用。"""
    conn = get_conn()
    row = conn.execute("SELECT username, role FROM users WHERE id = %s", (user_id,)).fetchone()
    if not row:
        conn.close()
        return False
    if row["username"] == "admin":
        conn.close()
        return False  # 禁止停用主管理员
    conn.execute("UPDATE users SET is_active = 0, updated_at = %s WHERE id = %s",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()
    return True


def delete_user(user_id: int) -> bool:
    """硬删除用户（管理员操作）。主管理员不可删除。0819 先清其指派记录（外键）。"""
    conn = get_conn()
    row = conn.execute("SELECT username FROM users WHERE id = %s", (user_id,)).fetchone()
    if not row:
        conn.close()
        return False
    if row["username"] == "admin":
        conn.close()
        return False
    conn.execute("DELETE FROM complaint_assignees WHERE user_id = %s", (user_id,))
    conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()
    return True


def reset_password(user_id: int, new_password: str) -> bool:
    """重置用户密码（更新哈希）。"""
    pwd_hash = _hash_password(new_password)
    conn = get_conn()
    conn.execute(
        "UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s",
        (pwd_hash, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id),
    )
    conn.commit()
    conn.close()
    return True


# 0819 v3.0：部门查询函数已删除（部门概念取消）

# ═══════════════════════════════════════ 0803 统一工单日志 DAO ═══════════════════════════════════════

def create_work_order_log(
    complaint_id: int,
    event_type: str,
    operator_name: str,
    operator_role: str,
    operator_dept: str = "",
    old_status: str = "",
    new_status: str = "",
    detail: str = "",
    metadata: str = "{}",
    operator_position: str = "",
) -> int:
    """写入一条工单日志（所有状态转换/操作都必须调用）。
    0819 operator_dept 弃用（列保留），新增 operator_position（职位留痕）。
    返回新日志 ID，用于 audit trail 和时间线展示。
    """
    conn = get_conn()
    log_id = conn.execute(
        "INSERT INTO work_order_log (complaint_id, event_type, operator_name, operator_role, operator_dept, old_status, new_status, detail, metadata, operator_position) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (complaint_id, event_type, operator_name, operator_role, operator_dept, old_status, new_status, detail, metadata, operator_position),
    ).fetchone()["id"]
    conn.commit()
    conn.close()
    return log_id


def list_work_order_log(complaint_id: int) -> list[dict]:
    """查询某工单的完整操作日志，按时间升序排列（0820 加 id 决胜，同秒多条日志顺序稳定）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM work_order_log WHERE complaint_id = %s ORDER BY created_at ASC, id ASC",
        (complaint_id,),
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# 0819 v3.0：部门相关函数（get_dept_heads/get_engineers_by_dept/get_dept_by_category/
# get_current_user_dept/get_departments/get_center_dept_map）已删除（部门概念取消）

# ═══════════════════════════════════════ 0819 多人指派 DAO ═══════════════════════════════════════

def set_assignee(complaint_id: int, user_id: int, assignee_type: str, assigned_by: str) -> int:
    """指派单个审批人/承接人。同类型旧记录先置 is_active=0（审批人单值自动换人）。"""
    conn = get_conn()
    conn.execute(
        "UPDATE complaint_assignees SET is_active = 0 "
        "WHERE complaint_id = %s AND assignee_type = %s AND is_active = 1",
        (complaint_id, assignee_type),
    )
    aid = conn.execute(
        "INSERT INTO complaint_assignees (complaint_id, user_id, assignee_type, assigned_by) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (complaint_id, user_id, assignee_type, assigned_by),
    ).fetchone()["id"]
    conn.commit()
    conn.close()
    return aid


def add_assignees(complaint_id: int, user_ids: list[int], assigned_by: str) -> int:
    """批量追加承接人/参与人（assignee 类型多值）。返回新增数量。"""
    if not user_ids:
        return 0
    conn = get_conn()
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO complaint_assignees (complaint_id, user_id, assignee_type, assigned_by) "
            "VALUES (%s, %s, 'assignee', %s)",
            [(complaint_id, uid, assigned_by) for uid in user_ids],
        )
    conn.commit()
    conn.close()
    return len(user_ids)


def deactivate_assignees(complaint_id: int) -> None:
    """「处理不了」回退时把全部有效指派记录置 0（历史保留，顺带清主要推进人标志）。"""
    conn = get_conn()
    conn.execute(
        "UPDATE complaint_assignees SET is_active = 0, is_primary = 0 "
        "WHERE complaint_id = %s AND is_active = 1",
        (complaint_id,),
    )
    conn.commit()
    conn.close()


def get_active_approver(complaint_id: int) -> dict | None:
    """获取当前有效审批人（含用户信息）。"""
    conn = get_conn()
    row = conn.execute("""
        SELECT ca.*, u.display_name, u.role, u.position
        FROM complaint_assignees ca
        LEFT JOIN users u ON u.id = ca.user_id
        WHERE ca.complaint_id = %s AND ca.assignee_type = 'approver' AND ca.is_active = 1
        ORDER BY ca.id DESC LIMIT 1
    """, (complaint_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_historical_approver_user_ids(complaint_id: int) -> list[int]:
    """0821 获取该工单历史上所有被指派过的审批人 user_id（含已失效 is_active=0 记录，去重）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT user_id FROM complaint_assignees "
        "WHERE complaint_id = %s AND assignee_type = 'approver'",
        (complaint_id,),
    ).fetchall()
    conn.close()
    return [r["user_id"] for r in rows]


def get_active_assignees(complaint_id: int) -> list[dict]:
    """获取当前有效承接人/参与人（含用户信息）。"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT ca.*, u.display_name, u.role, u.position
        FROM complaint_assignees ca
        LEFT JOIN users u ON u.id = ca.user_id
        WHERE ca.complaint_id = %s AND ca.assignee_type = 'assignee' AND ca.is_active = 1
        ORDER BY ca.id ASC
    """, (complaint_id,)).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_assignees_map(complaint_ids: list[int]) -> dict[int, list[dict]]:
    """批量获取工单的有效指派快照（防列表 N+1），
    返回 {complaint_id: [{user_id, display_name, role, position, assignee_type}]}。"""
    if not complaint_ids:
        return {}
    conn = get_conn()
    placeholders = ",".join("%s" for _ in complaint_ids)
    rows = conn.execute(f"""
        SELECT ca.complaint_id, ca.user_id, ca.assignee_type, ca.assigned_by,
               ca.is_primary,
               u.display_name, u.role, u.position
        FROM complaint_assignees ca
        LEFT JOIN users u ON u.id = ca.user_id
        WHERE ca.complaint_id IN ({placeholders}) AND ca.is_active = 1
        ORDER BY ca.assignee_type, ca.id
    """, complaint_ids).fetchall()
    conn.close()
    mapping: dict[int, list[dict]] = {}
    for r in rows:
        mapping.setdefault(r["complaint_id"], []).append(dict(r))
    return mapping


def get_rejected_approver_info_map(complaint_ids: list[int]) -> dict[int, dict | None]:
    """0820 批量查询「指派审批人」退回重派信息（看板列表防 N+1）。
    规则：取每工单最新一条 new_status='指派审批人' 的日志（MAX(id) 即时间序），
    若 event_type IN ('approver_rejected','cannot_handle') 则返回 {event_type,
    operator_name, operator_position, detail, created_at}，否则不在结果中。
    """
    if not complaint_ids:
        return {}
    conn = get_conn()
    placeholders = ",".join("%s" for _ in complaint_ids)
    rows = conn.execute(f"""
        SELECT w.id, w.complaint_id, w.event_type, w.operator_name,
               w.operator_position, w.detail, w.created_at
        FROM work_order_log w
        JOIN (
            SELECT complaint_id, MAX(id) AS max_id
            FROM work_order_log
            WHERE complaint_id IN ({placeholders}) AND new_status = '指派审批人'
            GROUP BY complaint_id
        ) t ON w.id = t.max_id
    """, complaint_ids).fetchall()
    conn.close()
    mapping: dict[int, dict | None] = {}
    for r in rows:
        if r["event_type"] in ("approver_rejected", "cannot_handle"):
            mapping[r["complaint_id"]] = dict(r)
    return mapping


def is_active_assignee(complaint_id: int, user_id: int) -> bool:
    """判断用户是否为该工单当前有效承接人/参与人。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM complaint_assignees "
        "WHERE complaint_id = %s AND user_id = %s AND assignee_type = 'assignee' AND is_active = 1 LIMIT 1",
        (complaint_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None


def is_active_approver(complaint_id: int, user_id: int) -> bool:
    """0821 判断用户是否为该工单当前有效审批人（操作隔离用）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM complaint_assignees "
        "WHERE complaint_id = %s AND user_id = %s AND assignee_type = 'approver' AND is_active = 1 LIMIT 1",
        (complaint_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None


# ── 1009 离职交接 DAO ──────────────────────────────

def get_active_assignments_for_user(user_id: int) -> list[dict]:
    """离职交接：用户当前全部有效指派（approver/assignee），附工单号与状态供预览展示。"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT ca.complaint_id, ca.assignee_type, ca.is_primary,
               c.complaint_no, c.status
        FROM complaint_assignees ca
        JOIN complaints c ON c.id = ca.complaint_id
        WHERE ca.user_id = %s AND ca.is_active = 1
        ORDER BY ca.complaint_id, ca.assignee_type
    """, (user_id,)).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_complaints_created_by_user(user_id: int) -> list[dict]:
    """离职交接：用户作为录入客服创建的工单（created_by_user_id 匹配，含全部状态）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, complaint_no, status FROM complaints WHERE created_by_user_id = %s ORDER BY id",
        (user_id,),
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def deactivate_user_assignments(complaint_id: int, user_id: int) -> None:
    """离职交接：仅停用某用户在某工单上的有效指派行（历史保留，不动同单其他人的指派）。"""
    conn = get_conn()
    conn.execute(
        "UPDATE complaint_assignees SET is_active = 0 "
        "WHERE complaint_id = %s AND user_id = %s AND is_active = 1",
        (complaint_id, user_id),
    )
    conn.commit()
    conn.close()


def transfer_complaints_creator(from_user_id: int, to_user_id: int) -> int:
    """离职交接：录入客服归属批量换绑（仅 created_by_user_id；显示名 created_by 是留痕不改）。
    返回受影响工单数。"""
    conn = get_conn()
    n = conn.execute(
        "UPDATE complaints SET created_by_user_id = %s WHERE created_by_user_id = %s",
        (to_user_id, from_user_id),
    ).rowcount
    conn.commit()
    conn.close()
    return n


# ── 0820 主要推进人 DAO ────────────────────────────

def set_primary_assignee(complaint_id: int, user_id: int) -> None:
    """先清该工单 assignee 类型 active 行的 is_primary，再置目标为 1。"""
    conn = get_conn()
    conn.execute(
        "UPDATE complaint_assignees SET is_primary = 0 "
        "WHERE complaint_id = %s AND assignee_type = 'assignee' AND is_active = 1",
        (complaint_id,),
    )
    conn.execute(
        "UPDATE complaint_assignees SET is_primary = 1 "
        "WHERE complaint_id = %s AND user_id = %s AND assignee_type = 'assignee' AND is_active = 1",
        (complaint_id, user_id),
    )
    conn.commit()
    conn.close()


def get_primary_assignee(complaint_id: int) -> dict | None:
    """当前主要推进人（含用户信息）；无则 None。"""
    conn = get_conn()
    row = conn.execute("""
        SELECT ca.*, u.display_name, u.role, u.position
        FROM complaint_assignees ca
        LEFT JOIN users u ON u.id = ca.user_id
        WHERE ca.complaint_id = %s AND ca.assignee_type = 'assignee'
          AND ca.is_active = 1 AND ca.is_primary = 1
        LIMIT 1
    """, (complaint_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def is_primary_assignee(complaint_id: int, user_id: int) -> bool:
    """用户是否为该工单当前主要推进人。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM complaint_assignees "
        "WHERE complaint_id = %s AND user_id = %s AND assignee_type = 'assignee' "
        "AND is_active = 1 AND is_primary = 1 LIMIT 1",
        (complaint_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None


def get_complaint_assignee_user_ids(user_id: int) -> set[int]:
    """0819 某用户当前参与（指派承接人/处理中）的全部工单 ID 集合（我的工单筛选）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT complaint_id FROM complaint_assignees "
        "WHERE user_id = %s AND assignee_type = 'assignee' AND is_active = 1",
        (user_id,),
    ).fetchall()
    conn.close()
    return {r["complaint_id"] for r in rows}


def get_complaint_approver_user_ids(user_id: int) -> set[int]:
    """0820 某用户作为有效审批人的全部工单 ID 集合（我的工单筛选）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT complaint_id FROM complaint_assignees "
        "WHERE user_id = %s AND assignee_type = 'approver' AND is_active = 1",
        (user_id,),
    ).fetchall()
    conn.close()
    return {r["complaint_id"] for r in rows}


def get_assignee_active_complaints(user_id: int) -> list[dict]:
    """0819 某承接人当前处理中的工单（冲突检测用）。"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.id, c.complaint_no, c.customer_name, c.status
        FROM complaint_assignees ca
        JOIN complaints c ON c.id = ca.complaint_id
        WHERE ca.user_id = %s AND ca.assignee_type = 'assignee' AND ca.is_active = 1
          AND c.status = '处理中'
        ORDER BY c.id
    """, (user_id,)).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# ────────────────────────────────────────────── 0718 附件管理 ──────────────────────────────────────────────

# 0718 附件类型白名单
ATTACHMENT_WHITELIST = [
    "jpg", "jpeg", "png", "gif", "bmp", "webp",
    "pdf", "log", "txt", "csv", "xlsx", "xls", "docx", "doc",
]

# 0718 附件限制
ATTACHMENT_MAX_PER_UPLOAD = 5    # 单次提交最多5个
ATTACHMENT_MAX_PER_COMPLAINT = 20  # 工单全程最多20个
ATTACHMENT_MAX_SIZE_MB = 10      # 单文件最大10MB


def _get_mime_type(ext: str) -> str:
    """根据扩展名返回 MIME 类型。"""
    _mime_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "gif": "image/gif", "bmp": "image/bmp", "webp": "image/webp",
        "pdf": "application/pdf", "log": "text/plain", "txt": "text/plain",
        "csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
    }
    return _mime_map.get(ext.lower(), "application/octet-stream")


def save_attachment(complaint_id: int, filename: str, stored_name: str,
                    mime_type: str, file_size: int, uploaded_by: str) -> int:
    """保存附件元数据到 DB，返回新记录的 id。"""
    conn = get_conn()
    aid = conn.execute(
        """INSERT INTO attachments (complaint_id, filename, stored_name, mime_type, file_size, uploaded_by)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (complaint_id, filename, stored_name, mime_type, file_size, uploaded_by),
    ).fetchone()["id"]
    conn.commit()
    conn.close()
    return aid


def get_attachments(complaint_id: int) -> list[dict]:
    """获取指定工单的所有附件列表。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM attachments WHERE complaint_id = %s ORDER BY uploaded_at",
        (complaint_id,),
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def delete_attachment(attachment_id: int):
    """删除附件记录（由调用方负责删除磁盘文件）。"""
    conn = get_conn()
    conn.execute("DELETE FROM attachments WHERE id = %s", (attachment_id,))
    conn.commit()
    conn.close()


def count_attachments(complaint_id: int) -> int:
    """统计某工单已有附件数。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS count FROM attachments WHERE complaint_id = %s",
        (complaint_id,),
    ).fetchone()
    conn.close()
    return row["count"] if row else 0


# ── 0729 用户使用评价 ──────────────────────────────────
def create_user_feedback(username: str, role: str, complaint_no: str,
                         feedback_type: str, ai_accuracy: int,
                         ai_time_saved: str, ai_adopted: int,
                         ai_comment: str,
                         fault_category: str = "",
                         equipment_model: str = "",
                         complaint_status: str = "",
                         responsible_dept: str = "",
                         ai_suggestion: str = "") -> dict:
    """提交用户使用评价。返回 {"success": bool, "message": str}"""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO user_feedback (username, role, complaint_no, feedback_type,
                                       ai_accuracy, ai_time_saved, ai_adopted, ai_comment,
                                       fault_category, equipment_model, complaint_status,
                                       responsible_dept, ai_suggestion)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (username, role, complaint_no, feedback_type,
              ai_accuracy, ai_time_saved, ai_adopted, ai_comment,
              fault_category, equipment_model, complaint_status,
              responsible_dept, ai_suggestion))
        conn.commit()
        return {"success": True, "message": "评价提交成功，感谢反馈！"}
    except Exception as e:
        err = str(e)
        if "UNIQUE" in err.upper() or "unique" in err:
            return {"success": False, "message": "您已对此操作进行过评价，不可重复提交"}
        return {"success": False, "message": f"提交失败: {err}"}
    finally:
        conn.close()


def check_feedback_exists(username: str, complaint_no: str, feedback_type: str) -> bool:
    """检查用户是否已对某工单的某操作类型提交过评价。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM user_feedback WHERE username = %s AND complaint_no = %s AND feedback_type = %s",
        (username, complaint_no, feedback_type),
    ).fetchone()
    conn.close()
    return row is not None


def get_pending_feedback_types(username: str, complaint_no: str, role: str) -> list[str]:
    """返回用户在某个工单上尚未评价的操作类型列表（0819 新角色映射）。"""
    role_actions = {
        "客服": ["intake", "confirm", "investigate"],
        "客服主管": ["intake_review", "email_review"],
        "办理人": ["assign_approver"],
        "审批人": ["assign_assignees"],
        "承接人": ["resolve"],
        "管理员": ["intake", "intake_review", "email_review", "assign_approver", "assign_assignees", "resolve", "confirm"],
    }
    all_types = role_actions.get(role, [])
    conn = get_conn()
    rows = conn.execute(
        "SELECT feedback_type FROM user_feedback WHERE username = %s AND complaint_no = %s",
        (username, complaint_no),
    ).fetchall()
    conn.close()
    done = set(r["feedback_type"] for r in rows)
    return [t for t in all_types if t not in done]


def get_feedback_summary(date_range: str = "近3个月") -> dict:
    """管理员查看评价统计。返回各 feedback_type 的均值。"""
    start_date = None
    end_date = None
    if date_range == "本月":
        start_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')"
    elif date_range == "上月":
        start_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai') - interval '1 month'"
        end_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')"  # 0820 补上界，防止混入本月数据
    elif date_range == "近3个月":
        start_date = "now() AT TIME ZONE 'Asia/Shanghai' - interval '3 months'"
    elif date_range == "近6个月":
        start_date = "now() AT TIME ZONE 'Asia/Shanghai' - interval '6 months'"

    conn = get_conn()
    where_clause = f" AND created_at >= {start_date}" if start_date else ""
    if end_date:
        where_clause += f" AND created_at < {end_date}"

    total = conn.execute(f"SELECT COUNT(*) AS count FROM user_feedback WHERE 1=1{where_clause}").fetchone()["count"]
    avg_accuracy = conn.execute(
        f"SELECT AVG(ai_accuracy) FROM user_feedback WHERE ai_accuracy > 0{where_clause}"
    ).fetchone()["avg"] or 0

    time_saved_map = {}
    for val in ["significant", "moderate", "slight", "none", "negative"]:
        cnt = conn.execute(
            f"SELECT COUNT(*) AS count FROM user_feedback WHERE ai_time_saved = %s{where_clause}", (val,),
        ).fetchone()["count"]
        time_saved_map[val] = cnt

    adopted_count = conn.execute(
        f"SELECT COUNT(*) AS count FROM user_feedback WHERE ai_adopted = 1{where_clause}"
    ).fetchone()["count"]
    not_adopted_count = conn.execute(
        f"SELECT COUNT(*) AS count FROM user_feedback WHERE ai_adopted = -1{where_clause}"
    ).fetchone()["count"]
    na_count = conn.execute(
        f"SELECT COUNT(*) AS count FROM user_feedback WHERE ai_adopted = 0{where_clause}"
    ).fetchone()["count"]

    conn.close()
    return {
        "total": total,
        "avg_accuracy": round(avg_accuracy, 2),
        "time_saved": time_saved_map,
        "adopted": adopted_count,
        "not_adopted": not_adopted_count,
        "na": na_count,
    }


# 0819 v3.0：旧客服主管审核 DAO（supervisor_approve/reject/skip_to_eval、
# 审核队列查询）已删除 — 状态机重写后由 services/complaint_service.py 直接读写

def set_email_review_status(complaint_id: int, status: str, note: str | None = None,
                            draft_content: str | None = None) -> dict | None:
    """更新邮件审核状态（pending / approved / rejected / NULL）、备注和草稿内容。
    当 draft_content 未传时保留已有的 email_draft_content，不会清空。
    返回更新后的工单 dict，工单不存在返回 None。
    """
    conn = get_conn()
    row = conn.execute("SELECT id FROM complaints WHERE id = %s", (complaint_id,)).fetchone()
    if not row:
        conn.close()
        return None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if draft_content is not None:
        conn.execute(
            "UPDATE complaints SET email_review_status = %s, email_review_note = %s, "
            "email_draft_content = %s, updated_at = %s WHERE id = %s",
            (status, note, draft_content, now, complaint_id),
        )
    else:
        # 0804 不传 draft_content 时保留已有的草稿内容，不清空
        conn.execute(
            "UPDATE complaints SET email_review_status = %s, email_review_note = %s, updated_at = %s WHERE id = %s",
            (status, note, now, complaint_id),
        )
    conn.commit()
    result = conn.execute("SELECT * FROM complaints WHERE id = %s", (complaint_id,)).fetchone()
    conn.close()
    return dict(result) if result else None


def get_complaints_for_supervisor_review() -> list[dict]:
    """0819 已弃用：审核队列并入看板「客服主管审核」列（保留空实现兼容）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM complaints WHERE status = '客服主管审核' AND sub_type = 'intake' ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_complaints_pending_email_review() -> list[dict]:
    """0819 已弃用：邮件审核并入看板「客服主管审核(email)」列（保留空实现兼容）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM complaints WHERE status = '客服主管审核' AND sub_type = 'email' ORDER BY updated_at ASC"
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# ═══════════════════════════════════════ 0804 系统评估 SUS 问卷 DAO ═══════════════════════════════════════

def submit_sus_survey(username: str, role: str, answers: list[int], score: float,
                      center: str = "", department: str = "",
                      use_modules: str = "", improvement: str = "") -> int:
    """提交 SUS 问卷，返回新记录 ID。

    0923 补充题：use_modules 为逗号分隔的常用功能（API 层白名单校验后拼接）、
    improvement 为改进建议开放题（≤500字）；两者均可选，不计入 SUS 分。"""
    conn = get_conn()
    sid = conn.execute(
        """INSERT INTO sus_survey (username, role, center, department,
           q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, sus_score, response_type,
           use_modules, improvement)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'submitted', %s, %s) RETURNING id""",
        (username, role, center, department, *answers, score, use_modules, improvement),
    ).fetchone()["id"]
    conn.commit()
    conn.close()
    return sid


def check_sus_survey_cooldown(username: str, cooldown_days: int = SUS_SURVEY_COOLDOWN_DAYS) -> bool:
    """检查用户是否在冷却期内（最近 cooldown_days 天内已提交或关闭过）。"""
    # 0824 迁移 PG：SQLite 参数化日期修饰符 → Python 侧算 cutoff 字符串
    cutoff = (datetime.now() - timedelta(days=cooldown_days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(*) AS count FROM sus_survey
           WHERE username = %s
           AND created_at > %s""",
        (username, cutoff),
    ).fetchone()
    conn.close()
    return row["count"] > 0


def dismiss_sus_survey(username: str, role: str, center: str = "", department: str = "") -> int:
    """记录用户关闭/跳过问卷（写入全0答案，触发冷却，标记为 dismissed）。返回新记录 ID。"""
    conn = get_conn()
    sid = conn.execute(
        """INSERT INTO sus_survey (username, role, center, department,
           q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, sus_score, response_type)
           VALUES (%s, %s, %s, %s, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'dismissed') RETURNING id""",
        (username, role, center, department),
    ).fetchone()["id"]
    conn.commit()
    conn.close()
    return sid


def get_sus_survey_stats() -> dict:
    """SUS 问卷统计：仅计入真实提交（response_type='submitted'），跳过记录不计入评分。
    0824 增反馈率：提交数 /（提交+关闭跳过）— 弹窗展示后未操作者不可观测，下限口径。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS total, ROUND(AVG(sus_score)::numeric, 1) AS avg_score "
        "FROM sus_survey WHERE response_type = 'submitted'"
    ).fetchone()

    # 0824 反馈率：dismissed 记录数（关闭弹窗触发冷却的跳过行为）
    dismissed = conn.execute(
        "SELECT COUNT(*) AS cnt FROM sus_survey WHERE response_type = 'dismissed'"
    ).fetchone()["cnt"]

    dist_rows = conn.execute("""
        SELECT
            CASE WHEN sus_score >= 80.3 THEN '优秀 (≥80.3)'
                 WHEN sus_score >= 68   THEN '良好 (68-80.2)'
                 WHEN sus_score >= 51   THEN '一般 (51-67.9)'
                 ELSE '差 (<51)' END AS score_range,
            COUNT(*) AS cnt
        FROM sus_survey WHERE response_type = 'submitted'
        GROUP BY score_range ORDER BY MIN(sus_score) DESC
    """).fetchall()

    role_rows = conn.execute(
        "SELECT role, ROUND(AVG(sus_score)::numeric, 1) AS avg_score, COUNT(*) AS cnt "
        "FROM sus_survey WHERE response_type = 'submitted' "
        "GROUP BY role ORDER BY cnt DESC"
    ).fetchall()

    # 0923 补充题：常用功能分布（use_modules 逗号分隔 → Python 侧拆分计数）
    mod_rows = conn.execute(
        "SELECT use_modules FROM sus_survey "
        "WHERE response_type = 'submitted' AND COALESCE(use_modules, '') != ''"
    ).fetchall()
    module_counts: dict = {}
    for r in mod_rows:
        for m in (r["use_modules"] or "").split(","):
            m = m.strip()
            if m:
                module_counts[m] = module_counts.get(m, 0) + 1
    module_usage = [{"module": k, "count": v}
                    for k, v in sorted(module_counts.items(), key=lambda x: -x[1])]

    # 0923 补充题：最近改进建议（最多 20 条，仅真实提交）
    imp_rows = conn.execute(
        """SELECT username, role, center, improvement, created_at FROM sus_survey
           WHERE response_type = 'submitted' AND COALESCE(improvement, '') != ''
           ORDER BY created_at DESC LIMIT 20"""
    ).fetchall()
    conn.close()

    submitted = row["total"] if row else 0
    invited = submitted + dismissed
    return {
        "total_responses": submitted,
        "avg_score": (row["avg_score"] if row and row["avg_score"] is not None else 0),
        "score_distribution": _rows_to_dicts(dist_rows),
        "by_role": _rows_to_dicts(role_rows),
        # 0824 反馈率（下限口径：仅含明确提交/关闭者）
        "dismissed_count": dismissed,
        "invited_count": invited,
        "feedback_rate_pct": round(submitted * 100.0 / invited, 1) if invited > 0 else None,
        # 0923 补充题：常用功能分布 + 最近改进建议
        "module_usage": module_usage,
        "recent_improvements": _rows_to_dicts(imp_rows),
    }


# ═══════════════════════════════════════ 0804 Phase 2: AI 采纳率 + 活跃度 DAO ═══════════════════════════════════════

def record_ai_adoption(complaint_no: str, ai_function: str, ai_suggestion: str,
                       adopted: bool, username: str, ai_suggested_value: float = None) -> int:
    """记录 AI 建议采纳结果，返回新记录 ID。ai_suggested_value 为 AI 建议的具体数值（如工时）。"""
    conn = get_conn()
    sid = conn.execute(
        "INSERT INTO ai_adoption_log (complaint_no, ai_function, ai_suggestion, adopted, username, ai_suggested_value) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (complaint_no, ai_function, ai_suggestion, 1 if adopted else 0, username, ai_suggested_value),
    ).fetchone()["id"]
    conn.commit()
    conn.close()
    return sid


def get_ai_adoption_stats(date_range: str = "全部") -> list[dict]:
    """AI 各功能采纳率统计。0902 增平均文本匹配度（仅字段级匹配度埋点的功能有值）。

    ai_suggested_value 双语义：文本类功能存匹配度(0-100)，suggest_schedule 存建议工时——
    AVG 必须按 ai_function 过滤，防止工时混入平均匹配度。
    """
    where_clause, _ = _build_date_filter(date_range, "created_at")
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT ai_function,
               COUNT(*) AS total,
               SUM(adopted) AS adopted_count,
               ROUND(SUM(adopted) * 100.0 / COUNT(*), 1) AS adoption_rate_pct,
               ROUND(AVG(CASE WHEN ai_function IN ('diagnose', 'self_check', 'email_draft', 'prefill')
                          THEN ai_suggested_value END)::numeric, 1) AS avg_match_pct
        FROM ai_adoption_log
        WHERE {where_clause}
        GROUP BY ai_function
        ORDER BY total DESC
    """).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def record_user_activity(username: str, role: str, page_path: str, action: str = "page_view",
                         metadata: str = "{}") -> int:
    """记录用户活跃度，返回新记录 ID。metadata 为 JSON 扩展数据（如操作计时）。"""
    conn = get_conn()
    sid = conn.execute(
        "INSERT INTO user_activity_log (username, role, page_path, action, metadata) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (username, role, page_path, action, metadata),
    ).fetchone()["id"]
    conn.commit()
    conn.close()
    return sid


def get_activity_stats(limit: int = 10) -> dict:
    """用户活跃度统计：DAU/WAU/MAU、页面热度、角色活跃度。
    0902 个人活跃度返回条数改由参数控制（默认 Top10，前端「查看全部」传大值）。"""
    conn = get_conn()

    dau = conn.execute(
        "SELECT COUNT(DISTINCT username) AS count FROM user_activity_log "
        "WHERE created_at::date = (now() AT TIME ZONE 'Asia/Shanghai')::date"
    ).fetchone()["count"] or 0

    wau = conn.execute(
        "SELECT COUNT(DISTINCT username) AS count FROM user_activity_log "
        "WHERE created_at >= now() AT TIME ZONE 'Asia/Shanghai' - interval '7 days'"
    ).fetchone()["count"] or 0

    mau = conn.execute(
        "SELECT COUNT(DISTINCT username) AS count FROM user_activity_log "
        "WHERE created_at >= now() AT TIME ZONE 'Asia/Shanghai' - interval '30 days'"
    ).fetchone()["count"] or 0

    page_heat = conn.execute("""
        SELECT page_path, COUNT(*) AS cnt
        FROM user_activity_log
        WHERE created_at >= now() AT TIME ZONE 'Asia/Shanghai' - interval '30 days'
        GROUP BY page_path ORDER BY cnt DESC LIMIT 10
    """).fetchall()

    role_activity = conn.execute("""
        SELECT role, COUNT(DISTINCT username) AS unique_users, COUNT(*) AS total_visits
        FROM user_activity_log
        WHERE created_at >= now() AT TIME ZONE 'Asia/Shanghai' - interval '30 days'
        GROUP BY role
    """).fetchall()

    # 0819 个人活跃度（近30天）：按访问次数排序，LEFT JOIN 取显示名；条数由 limit 控制
    user_activity = conn.execute("""
        SELECT ua.username,
               COALESCE(u.display_name, ua.username) AS display_name,
               ua.role,
               COUNT(*) AS total_visits,
               COUNT(DISTINCT ua.created_at::date) AS active_days,
               MAX(ua.created_at) AS last_active
        FROM user_activity_log ua
        LEFT JOIN users u ON u.username = ua.username
        WHERE ua.created_at >= now() AT TIME ZONE 'Asia/Shanghai' - interval '30 days'
        GROUP BY ua.username, u.display_name, ua.role
        ORDER BY total_visits DESC
        LIMIT %s
    """, (limit,)).fetchall()

    conn.close()
    return {
        "dau": dau,
        "wau": wau,
        "mau": mau,
        "page_heat": _rows_to_dicts(page_heat),
        "role_activity": _rows_to_dicts(role_activity),
        "user_activity": _rows_to_dicts(user_activity),
    }


# ═══════════════════════════════════════ 0805 Phase 3: 操作计时 + 阶段评价 + 排期准确度 DAO ═══════════════════════════════════════

def get_timing_stats(date_range: str = "近3个月") -> dict:
    """从 user_activity_log 的 metadata JSON 中提取操作计时统计。
    返回各 action_name 的平均/P50/P95 耗时 + 样本数。
    """
    start_date = None
    end_date = None
    if date_range == "本月":
        start_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')"
    elif date_range == "上月":
        start_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai') - interval '1 month'"
        end_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')"  # 0820 补上界
    elif date_range == "近3个月":
        start_date = "now() AT TIME ZONE 'Asia/Shanghai' - interval '3 months'"
    elif date_range == "近6个月":
        start_date = "now() AT TIME ZONE 'Asia/Shanghai' - interval '6 months'"

    where = f" WHERE action = 'timing' AND created_at >= {start_date}" if start_date else " WHERE action = 'timing'"
    if end_date:
        where += f" AND created_at < {end_date}"
    conn = get_conn()
    rows = conn.execute(
        f"SELECT metadata FROM user_activity_log{where}"
    ).fetchall()
    conn.close()

    import json
    by_action: dict[str, list[float]] = {}
    for r in rows:
        try:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
        except (json.JSONDecodeError, TypeError):
            continue
        name = meta.get("action_name", "unknown")
        dur = meta.get("duration_ms", 0)
        if dur > 0:
            by_action.setdefault(name, []).append(dur / 1000.0)  # 转秒

    # 中文映射
    name_map = {
        "complaint_intake": "录入表单",
        "engineer_assign": "指派操作",
        "ticket_resolve": "工单处理",
    }

    result = []
    for name, vals in by_action.items():
        svals = sorted(vals)
        n = len(svals)
        result.append({
            "action_name": name,
            "action_label": name_map.get(name, name),
            "count": n,
            "avg_seconds": round(sum(svals) / n, 1),
            "p50_seconds": round(svals[int(n * 0.5)], 1),
            "p95_seconds": round(svals[int(n * 0.95)] if int(n * 0.95) < n else svals[-1], 1),
        })
    return result


def get_feedback_by_stage(date_range: str = "近3个月") -> dict:
    """按 feedback_type 分组评价统计 + 全局汇总。"""
    start_date = None
    end_date = None
    if date_range == "本月":
        start_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')"
    elif date_range == "上月":
        start_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai') - interval '1 month'"
        end_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')"  # 0820 补上界
    elif date_range == "近3个月":
        start_date = "now() AT TIME ZONE 'Asia/Shanghai' - interval '3 months'"
    elif date_range == "近6个月":
        start_date = "now() AT TIME ZONE 'Asia/Shanghai' - interval '6 months'"

    conn = get_conn()
    where_clause = f" AND created_at >= {start_date}" if start_date else ""
    if end_date:
        where_clause += f" AND created_at < {end_date}"

    # 各阶段明细
    stage_rows = conn.execute(f"""
        SELECT feedback_type,
               COUNT(*) AS total,
               AVG(CASE WHEN ai_accuracy > 0 THEN ai_accuracy ELSE NULL END) AS avg_accuracy,
               SUM(CASE WHEN ai_adopted = 1 THEN 1 ELSE 0 END) AS adopted,
               SUM(CASE WHEN ai_adopted = -1 THEN 1 ELSE 0 END) AS not_adopted,
               SUM(CASE WHEN ai_adopted = 0 THEN 1 ELSE 0 END) AS na
        FROM user_feedback
        WHERE 1=1{where_clause}
        GROUP BY feedback_type
        ORDER BY
            CASE feedback_type
                WHEN 'intake' THEN 1
                WHEN 'evaluate' THEN 2
                WHEN 'assign' THEN 3
                WHEN 'resolve' THEN 4
                WHEN 'confirm' THEN 5
                ELSE 6
            END
    """).fetchall()

    # 各阶段省时分布
    time_saved_by_stage = {}
    time_where = f" AND created_at >= {start_date}" if start_date else ""
    for val in ["significant", "moderate", "slight", "none", "negative"]:
        sub = conn.execute(f"""
            SELECT feedback_type, COUNT(*) AS cnt
            FROM user_feedback
            WHERE ai_time_saved = %s{time_where}
            GROUP BY feedback_type
        """, (val,)).fetchall()
        time_saved_by_stage[val] = {r["feedback_type"]: r["cnt"] for r in sub}

    # 0824 反馈率分母：同期创建的工单数 + 有评价的工单数（去重）
    c_where = f" AND created_at >= {start_date}" if start_date else ""
    if end_date:
        c_where += f" AND created_at < {end_date}"
    complaint_count = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM complaints WHERE 1=1{c_where}"
    ).fetchone()["cnt"]
    fb_where = f" AND created_at >= {start_date}" if start_date else ""
    if end_date:
        fb_where += f" AND created_at < {end_date}"
    evaluated_count = conn.execute(
        f"SELECT COUNT(DISTINCT complaint_no) AS cnt FROM user_feedback "
        f"WHERE complaint_no != ''{fb_where}"
    ).fetchone()["cnt"]

    conn.close()

    stages = []
    for r in stage_rows:
        d = dict(r)
        d["avg_accuracy"] = round(d["avg_accuracy"] or 0, 2)
        d["time_saved"] = {}
        for val in ["significant", "moderate", "slight", "none", "negative"]:
            d["time_saved"][val] = time_saved_by_stage[val].get(r["feedback_type"], 0)
        stages.append(d)

    return {"by_stage": stages,
            "overall": get_feedback_summary(date_range),
            # 0824 反馈率（评价过的工单数 / 同期创建工单数）
            "complaint_count": complaint_count,
            "evaluated_count": evaluated_count,
            "feedback_rate_pct": round(evaluated_count * 100.0 / complaint_count, 1) if complaint_count > 0 else None}


def get_schedule_accuracy_stats(date_range: str = "近3个月") -> dict:
    """AI 排期建议准确度：对比建议工时 vs 实际处理工时（已关闭工单）。"""
    start_date = None
    end_date = None
    if date_range == "本月":
        start_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')"
    elif date_range == "上月":
        start_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai') - interval '1 month'"
        end_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')"  # 0820 补上界
    elif date_range == "近3个月":
        start_date = "now() AT TIME ZONE 'Asia/Shanghai' - interval '3 months'"
    elif date_range == "近6个月":
        start_date = "now() AT TIME ZONE 'Asia/Shanghai' - interval '6 months'"

    where = f" AND a.created_at >= {start_date}" if start_date else ""
    if end_date:
        where += f" AND a.created_at < {end_date}"
    conn = get_conn()

    # JOIN ai_adoption_log(suggest_schedule) + complaints(已关闭) 计算偏差
    rows = conn.execute(f"""
        SELECT a.complaint_no, a.ai_suggested_value,
               (EXTRACT(EPOCH FROM (c.closed_at - c.created_at)) / 3600.0)::double precision AS actual_hours
        FROM ai_adoption_log a
        JOIN complaints c ON a.complaint_no = c.complaint_no
        WHERE a.ai_function = 'suggest_schedule'
          AND a.ai_suggested_value IS NOT NULL
          AND a.ai_suggested_value > 0
          AND c.closed_at IS NOT NULL
          AND c.status = '已关闭'{where}
        ORDER BY a.created_at DESC
    """).fetchall()

    # 统计总的 suggest_schedule 建议次数
    total_suggestions = conn.execute("""
        SELECT COUNT(*) AS count FROM ai_adoption_log
        WHERE ai_function = 'suggest_schedule'""" + (
            f" AND created_at >= {start_date}" if start_date else ""
        )
    ).fetchone()["count"]
    conn.close()

    deviations = []
    for r in rows:
        actual = r["actual_hours"]
        suggested = r["ai_suggested_value"]
        if actual and suggested and actual > 0:
            dev = abs(actual - suggested)
            deviations.append({
                "complaint_no": r["complaint_no"],
                "suggested_hours": round(suggested, 1),
                "actual_hours": round(actual, 1),
                "deviation_hours": round(dev, 1),
            })

    n = len(deviations)
    sorted_devs = sorted([d["deviation_hours"] for d in deviations])
    avg_dev = round(sum(sorted_devs) / n, 1) if n > 0 else 0
    p50_dev = sorted_devs[int(n * 0.5)] if n > 0 else 0
    p95_idx = int(n * 0.95)
    p95_dev = sorted_devs[p95_idx] if p95_idx < n else (sorted_devs[-1] if n > 0 else 0)

    # 偏差分布
    buckets = {"< 2h": 0, "2-5h": 0, "5-10h": 0, "> 10h": 0}
    for d in sorted_devs:
        if d < 2:
            buckets["< 2h"] += 1
        elif d < 5:
            buckets["2-5h"] += 1
        elif d < 10:
            buckets["5-10h"] += 1
        else:
            buckets["> 10h"] += 1

    return {
        "total_suggestions": total_suggestions,
        "comparable_count": n,
        "avg_deviation_hours": avg_dev,
        "p50_deviation_hours": p50_dev,
        "p95_deviation_hours": p95_dev,
        "deviation_distribution": [
            {"bucket": k, "count": v} for k, v in buckets.items()
        ],
        "details": deviations[:20],  # 最近 20 条明细
    }


# ═══════════════════════════════════════ 0805 Phase 4: 案例检索评价 DAO ═══════════════════════════════════════

def record_case_feedback(username: str, complaint_no: str, kb_id: int, kb_title: str,
                          source_type: str, referenced: bool, match_accuracy: int) -> int:
    """提交/修改案例检索评价。UNIQUE 约束重复提交时 UPDATE 覆盖旧值。"""
    conn = get_conn()
    try:
        sid = conn.execute("""
            INSERT INTO case_feedback (username, complaint_no, kb_id, kb_title, source_type, referenced, match_accuracy)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(username, complaint_no, kb_id, source_type)
            DO UPDATE SET referenced=EXCLUDED.referenced, match_accuracy=EXCLUDED.match_accuracy,
                          kb_title=EXCLUDED.kb_title
            RETURNING id
        """, (username, complaint_no, kb_id, kb_title, source_type,
              1 if referenced else 0, match_accuracy)).fetchone()["id"]
        conn.commit()
    except Exception:
        conn.rollback()
        existing = conn.execute(
            "SELECT id FROM case_feedback WHERE username=%s AND complaint_no=%s AND kb_id=%s AND source_type=%s",
            (username, complaint_no, kb_id, source_type)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE case_feedback SET referenced=%s, match_accuracy=%s, kb_title=%s, created_at=now() AT TIME ZONE 'Asia/Shanghai' WHERE id=%s",
                (1 if referenced else 0, match_accuracy, kb_title, existing["id"])
            )
            conn.commit()
            sid = existing["id"]
        else:
            sid = conn.execute(
                "INSERT INTO case_feedback (username, complaint_no, kb_id, kb_title, source_type, referenced, match_accuracy) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (username, complaint_no, kb_id, kb_title, source_type, 1 if referenced else 0, match_accuracy)
            ).fetchone()["id"]
            conn.commit()
    conn.close()
    return sid


def get_case_feedback(complaint_no: str) -> dict:
    """查询某工单下所有案例评价（供前端回显），按 kb_id+source_type 为 key。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM case_feedback WHERE complaint_no = %s ORDER BY created_at DESC",
        (complaint_no,)
    ).fetchall()
    conn.close()
    result = {}
    for r in rows:
        d = dict(r)
        key = f"{d['kb_id']}_{d['source_type']}"
        result[key] = d
    return result


def get_kb_case_feedback_stats(kb_id: int = None) -> dict | list:
    """知识库条目的案例评价汇总。传 kb_id 返回单个 dict，不传返回 list。"""
    conn = get_conn()
    if kb_id:
        row = conn.execute("""
            SELECT kb_id, COUNT(*) AS total_feedback,
                   SUM(CASE WHEN referenced=1 THEN 1 ELSE 0 END) AS reference_count,
                   ROUND(AVG(CASE WHEN match_accuracy>0 THEN match_accuracy ELSE NULL END), 1) AS avg_match_accuracy
            FROM case_feedback WHERE kb_id = %s
            GROUP BY kb_id
        """, (kb_id,)).fetchone()
        conn.close()
        if not row:
            return {"kb_id": kb_id, "total_feedback": 0, "reference_count": 0, "reference_pct": 0, "avg_match_accuracy": 0}
        d = dict(row)
        d["reference_pct"] = round(d["reference_count"] * 100.0 / d["total_feedback"], 1) if d["total_feedback"] > 0 else 0
        return d
    else:
        rows = conn.execute("""
            SELECT kb_id, COUNT(*) AS total_feedback,
                   SUM(CASE WHEN referenced=1 THEN 1 ELSE 0 END) AS reference_count,
                   ROUND(AVG(CASE WHEN match_accuracy>0 THEN match_accuracy ELSE NULL END), 1) AS avg_match_accuracy
            FROM case_feedback GROUP BY kb_id
            ORDER BY total_feedback DESC
        """).fetchall()
        conn.close()
        return _rows_to_dicts(rows)


def get_case_feedback_stats(date_range: str = "近3个月") -> dict:
    """案例评价全局统计 + 按 source_type 对比 + TOP KB。"""
    start_date = None
    end_date = None
    if date_range == "本月":
        start_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')"
    elif date_range == "上月":
        start_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai') - interval '1 month'"
        end_date = "date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')"  # 0820 补上界
    elif date_range == "近3个月":
        start_date = "now() AT TIME ZONE 'Asia/Shanghai' - interval '3 months'"
    elif date_range == "近6个月":
        start_date = "now() AT TIME ZONE 'Asia/Shanghai' - interval '6 months'"

    conn = get_conn()
    where = f" AND created_at >= {start_date}" if start_date else ""
    if end_date:
        where += f" AND created_at < {end_date}"

    total = conn.execute(
        f"SELECT COUNT(*) AS count FROM case_feedback WHERE 1=1{where}"
    ).fetchone()["count"]

    referenced_count = conn.execute(
        f"SELECT COUNT(*) AS count FROM case_feedback WHERE referenced=1{where}"
    ).fetchone()["count"]

    avg_match = conn.execute(
        f"SELECT AVG(match_accuracy) AS avg FROM case_feedback WHERE match_accuracy>0{where}"
    ).fetchone()["avg"] or 0

    by_source = conn.execute(f"""
        SELECT source_type,
               COUNT(*) AS total,
               SUM(CASE WHEN referenced=1 THEN 1 ELSE 0 END) AS referenced_count,
               ROUND(AVG(CASE WHEN match_accuracy>0 THEN match_accuracy ELSE NULL END), 1) AS avg_match
        FROM case_feedback WHERE 1=1{where}
        GROUP BY source_type ORDER BY total DESC
    """).fetchall()

    top_kb = conn.execute(f"""
        SELECT kb_id, kb_title,
               COUNT(*) AS total_feedback,
               SUM(CASE WHEN referenced=1 THEN 1 ELSE 0 END) AS reference_count,
               ROUND(AVG(CASE WHEN match_accuracy>0 THEN match_accuracy ELSE NULL END), 1) AS avg_match_accuracy
        FROM case_feedback WHERE 1=1{where}
        GROUP BY kb_id, kb_title ORDER BY total_feedback DESC LIMIT 10
    """).fetchall()

    conn.close()

    denom = total if total > 0 else 1
    return {
        "total": total,
        "referenced_count": referenced_count,
        "reference_pct": round(referenced_count * 100.0 / denom, 1),
        "avg_match_accuracy": round(avg_match, 1),
        "by_source": _rows_to_dicts(by_source),
        "top_kb": _rows_to_dicts(top_kb),
    }


# ═══════════════════ 0824 评估体系补强：通知触达 / AI采纳效果 / KB检索漏斗 ═══════════════════

def _eval_range_filter(date_range: str, column: str = "created_at") -> str:
    """评估统计通用日期范围过滤（raw SQL 片段，返回含 AND 前缀的子句或空串）。
    与 get_case_feedback_stats 等既有统计的 date_range 语义一致。"""
    fragments = {
        "本月": f"{column} >= date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')",
        "上月": (f"{column} >= date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai') - interval '1 month' "
                 f"AND {column} < date_trunc('month', now() AT TIME ZONE 'Asia/Shanghai')"),
        "近3个月": f"{column} >= now() AT TIME ZONE 'Asia/Shanghai' - interval '3 months'",
        "近6个月": f"{column} >= now() AT TIME ZONE 'Asia/Shanghai' - interval '6 months'",
    }
    frag = fragments.get(date_range, "")
    return f" AND {frag}" if frag else ""


def get_notification_reach_stats(date_range: str = "近3个月") -> dict:
    """0824 通知触达统计：站内待处理通知未读率 + 长期未读（>7天）+ 按角色分解。
    仅统计 action_required 类别（推送对象真正需要行动的通知）。"""
    where = _eval_range_filter(date_range)
    long_unread = (" AND is_read = 0 AND created_at < "
                   "now() AT TIME ZONE 'Asia/Shanghai' - interval '7 days'")
    conn = get_conn()

    def _q(extra: str = "") -> dict:
        return dict(conn.execute(
            f"SELECT COUNT(*) AS total, "
            f"SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) AS unread "
            f"FROM notifications WHERE notification_category = 'action_required'"
            f"{where}{extra}"
        ).fetchone())

    overall = _q()
    stale = _q(long_unread)

    by_role_rows = conn.execute(f"""
        SELECT target_role,
               COUNT(*) AS total,
               SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) AS unread,
               SUM(CASE WHEN is_read = 0 AND created_at <
                    now() AT TIME ZONE 'Asia/Shanghai' - interval '7 days' THEN 1 ELSE 0 END) AS long_unread
        FROM notifications
        WHERE notification_category = 'action_required'{where}
        GROUP BY target_role ORDER BY total DESC
    """).fetchall()
    conn.close()

    total = overall.get("total") or 0
    unread = overall.get("unread") or 0
    return {
        "total": total,
        "unread": unread,
        "unread_rate_pct": round(unread * 100.0 / total, 1) if total > 0 else 0.0,
        "long_unread": stale.get("total") or 0,
        "long_unread_rate_pct": round((stale.get("total") or 0) * 100.0 / total, 1) if total > 0 else 0.0,
        "by_role": _rows_to_dicts(by_role_rows),
    }


def get_dingtalk_push_stats(date_range: str = "近3个月") -> dict:
    """0824 钉钉推送统计：按状态计数 + 推送成功率（success/(success+failed)）。
    dry_run/no_recipient/no_complaint 不计入成功率分母。"""
    where = _eval_range_filter(date_range)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT status, COUNT(*) AS cnt FROM dingtalk_send_log WHERE 1=1{where} GROUP BY status"
    ).fetchall()
    conn.close()
    by_status = {r["status"]: r["cnt"] for r in rows}
    success = by_status.get("success", 0)
    failed = by_status.get("failed", 0)
    return {
        "by_status": by_status,
        "total": sum(by_status.values()),
        "success": success,
        "failed": failed,
        "success_rate_pct": round(success * 100.0 / (success + failed), 1) if (success + failed) > 0 else None,
    }


def get_ai_adoption_impact_stats(date_range: str = "近3个月") -> dict:
    """0824 AI 采纳效果闭环：采纳过 AI 建议的工单 vs 未采纳工单的
    平均处理时长（创建→关闭，仅已关闭）与一次解决率（is_rework=0）对比。"""
    where = _eval_range_filter(date_range, "c.created_at")
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT CASE WHEN a.any_adopted = 1 THEN 'adopted' ELSE 'not_adopted' END AS grp,
               COUNT(*) AS complaint_count,
               ROUND(AVG(CASE WHEN c.status = '已关闭' AND c.closed_at IS NOT NULL THEN
                    EXTRACT(EPOCH FROM (c.closed_at - c.created_at)) / 3600.0 END)::numeric, 1) AS avg_hours_closed,
               SUM(CASE WHEN c.status = '已关闭' AND c.closed_at IS NOT NULL THEN 1 ELSE 0 END) AS closed_count,
               ROUND(SUM(CASE WHEN c.is_rework = 0 THEN 1 ELSE 0 END) * 100.0
                    / NULLIF(COUNT(*), 0), 1) AS first_time_fix_pct
        FROM complaints c
        JOIN (
            SELECT complaint_no, MAX(adopted) AS any_adopted
            FROM ai_adoption_log GROUP BY complaint_no
        ) a ON a.complaint_no = c.complaint_no
        WHERE 1=1{where}
        GROUP BY grp
    """).fetchall()
    conn.close()

    out = {"adopted": None, "not_adopted": None}
    for r in rows:
        d = dict(r)
        out[d.pop("grp")] = d
    return out


def get_kb_reach_funnel_stats(date_range: str = "近3个月") -> dict:
    """0824 KB 检索漏斗：检索次数（活跃埋点）→ 相似案例查看 → 案例评价 → 引用采纳 + KB 有用率。
    检索埋点自上线起累计，此前无数据（前端需提示）。"""
    where = _eval_range_filter(date_range)
    conn = get_conn()

    def _act(action: str) -> int:
        return conn.execute(
            f"SELECT COUNT(*) AS cnt FROM user_activity_log "
            f"WHERE action = %s{where}", (action,)
        ).fetchone()["cnt"]

    kb_search = _act("kb_search")
    similar_view = _act("similar_cases_view")

    cf_row = conn.execute(
        f"SELECT COUNT(*) AS total, "
        f"SUM(CASE WHEN referenced = 1 THEN 1 ELSE 0 END) AS referenced "
        f"FROM case_feedback WHERE 1=1{where}"
    ).fetchone()
    kb_row = conn.execute(
        f"SELECT COUNT(*) AS total, "
        f"SUM(CASE WHEN feedback_type = 'useful' THEN 1 ELSE 0 END) AS useful "
        f"FROM kb_feedback_log WHERE 1=1{where}"
    ).fetchone()
    conn.close()

    cf_total = cf_row["total"] or 0
    kb_total = kb_row["total"] or 0
    return {
        "kb_search_count": kb_search,
        "similar_view_count": similar_view,
        "case_evaluated": cf_total,
        "case_referenced": cf_row["referenced"] or 0,
        "reference_pct": round((cf_row["referenced"] or 0) * 100.0 / cf_total, 1) if cf_total > 0 else 0.0,
        "kb_feedback_total": kb_total,
        "kb_useful_rate_pct": round((kb_row["useful"] or 0) * 100.0 / kb_total, 1) if kb_total > 0 else None,
    }


# ── 0811 系统设置 DAO ──────────────────────────────────────────

def get_setting(key: str) -> str | None:
    """读取单个系统设置项。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM system_settings WHERE key = %s", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else None


def get_settings(*keys: str) -> dict[str, str]:
    """批量读取系统设置项。"""
    if not keys:
        return {}
    conn = get_conn()
    placeholders = ",".join("%s" for _ in keys)
    rows = conn.execute(
        f"SELECT key, value FROM system_settings WHERE key IN ({placeholders})",
        keys,
    ).fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def set_setting(key: str, value: str) -> None:
    """写入/更新单个系统设置项。"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO system_settings (key, value, updated_at) "
        "VALUES (%s, %s, now() AT TIME ZONE 'Asia/Shanghai') "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
        "updated_at = EXCLUDED.updated_at",
        (key, value),
    )
    conn.commit()
    conn.close()


def set_settings_batch(data: dict[str, str]) -> None:
    """批量写入/更新系统设置项。"""
    if not data:
        return
    conn = get_conn()
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO system_settings (key, value, updated_at) "
            "VALUES (%s, %s, now() AT TIME ZONE 'Asia/Shanghai') "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
            "updated_at = EXCLUDED.updated_at",
            [(k, v) for k, v in data.items()],
        )
    conn.commit()
    conn.close()


# ═══════════════════════════════════════ 0819 系统管理导出中心 DAO ═══════════════════════════════════════

def _build_abs_date_filter(start_date: str = None, end_date: str = None,
                           column: str = "created_at") -> tuple[str, list]:
    """精确到天的可选日期范围过滤（闭区间）。
    start_date/end_date 为 YYYY-MM-DD，任一为空表示该方向不限。
    """
    clauses = []
    params = []
    if start_date:
        clauses.append(f"{column} >= %s")
        params.append(f"{start_date} 00:00:00")
    if end_date:
        next_day = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        clauses.append(f"{column} < %s")
        params.append(f"{next_day} 00:00:00")
    return (" AND ".join(clauses) if clauses else "1=1", params)


def get_attachments_name_map(complaint_ids: list[int]) -> dict[int, str]:
    """批量获取工单附件文件名（顿号拼接），供导出时追溯附件。"""
    if not complaint_ids:
        return {}
    conn = get_conn()
    placeholders = ",".join("%s" for _ in complaint_ids)
    rows = conn.execute(
        f"SELECT complaint_id, filename FROM attachments "
        f"WHERE complaint_id IN ({placeholders}) ORDER BY id",
        complaint_ids,
    ).fetchall()
    conn.close()
    mapping: dict[int, list[str]] = {}
    for r in rows:
        mapping.setdefault(r["complaint_id"], []).append(r["filename"])
    return {cid: "、".join(names) for cid, names in mapping.items()}


def get_complaints_for_admin_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：客诉工单全字段明细（末尾附加 attachment_names 附件文件名列）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM complaints WHERE {where_clause} ORDER BY created_at ASC", params
    ).fetchall()
    conn.close()
    data = _rows_to_dicts(rows)
    if data:
        att_map = get_attachments_name_map([r["id"] for r in data])
        for r in data:
            r["attachment_names"] = att_map.get(r["id"], "")
    return data


def get_work_order_log_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：工单流转日志（join 工单号）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date, "wl.created_at")
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT wl.id, c.complaint_no, wl.event_type, wl.operator_name, wl.operator_role,
               wl.operator_position, wl.old_status, wl.new_status, wl.detail, wl.created_at
        FROM work_order_log wl
        LEFT JOIN complaints c ON c.id = wl.complaint_id
        WHERE {where_clause}
        ORDER BY wl.created_at ASC, wl.id ASC
    """, params).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_kb_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：知识库全量明细。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM knowledge_base WHERE {where_clause} ORDER BY created_at ASC", params
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_user_feedback_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：用户评价明细（AI 各阶段评价）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM user_feedback WHERE {where_clause} ORDER BY created_at ASC", params
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_case_feedback_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：案例检索评价明细（案例有用性 + 匹配准确度）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM case_feedback WHERE {where_clause} ORDER BY created_at ASC", params
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_ai_adoption_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：AI 采纳日志明细。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM ai_adoption_log WHERE {where_clause} ORDER BY created_at ASC", params
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_sus_survey_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：系统评价（SUS 问卷）明细。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM sus_survey WHERE {where_clause} ORDER BY created_at ASC", params
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_user_activity_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：用户活跃明细。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM user_activity_log WHERE {where_clause} ORDER BY created_at ASC", params
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_llm_call_log_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：AI 调用日志明细（诊断用）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM llm_call_log WHERE {where_clause} ORDER BY created_at ASC", params
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_attachments_for_zip(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：日期范围内工单的附件元数据（含工单号，供 ZIP 打包）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date, "c.created_at")
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT a.id, a.complaint_id, c.complaint_no, a.filename, a.stored_name,
               a.file_size, a.uploaded_by, a.uploaded_at
        FROM attachments a
        JOIN complaints c ON c.id = a.complaint_id
        WHERE {where_clause}
        ORDER BY c.complaint_no ASC, a.id ASC
    """, params).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


# ═══════════════════ 0824 导出补漏：归档日志/进度/通知/用户/KB反馈/钉钉日志 ═══════════════════

def get_work_order_log_archive_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：已删工单的归档流转日志（审计留痕，archive 自带工单号无需 join）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM work_order_log_archive WHERE {where_clause} ORDER BY id ASC", params
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_progress_updates_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：工单进度记录（进度百分比历史，join 工单号）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date, "p.created_at")
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT p.id, c.complaint_no, p.complaint_id, p.progress_pct, p.note,
               p.updated_by, p.created_at
        FROM progress_updates p
        LEFT JOIN complaints c ON c.id = p.complaint_id
        WHERE {where_clause}
        ORDER BY p.created_at ASC, p.id ASC
    """, params).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_notifications_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：站内通知记录（谁在何时被通知的审计）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM notifications WHERE {where_clause} ORDER BY created_at ASC, id ASC", params
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_users_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：用户清单（脱敏 — 不含 password_hash）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT id, username, display_name, role, position, dingtalk_userid, "
        f"is_active, created_at FROM users WHERE {where_clause} ORDER BY id ASC", params
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_kb_feedback_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：知识库有用/无用反馈原始记录（join KB 标题）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date, "k.created_at")
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT k.id, kb.title AS kb_title, k.kb_id, k.user_account, k.feedback_type, k.created_at
        FROM kb_feedback_log k
        LEFT JOIN knowledge_base kb ON kb.id = k.kb_id
        WHERE {where_clause}
        ORDER BY k.created_at ASC, k.id ASC
    """, params).fetchall()
    conn.close()
    return _rows_to_dicts(rows)


def get_dingtalk_log_for_export(start_date: str = None, end_date: str = None) -> list[dict]:
    """管理员导出：钉钉通知发送日志（推送审计）。"""
    where_clause, params = _build_abs_date_filter(start_date, end_date)
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM dingtalk_send_log WHERE {where_clause} ORDER BY created_at ASC, id ASC", params
    ).fetchall()
    conn.close()
    return _rows_to_dicts(rows)
