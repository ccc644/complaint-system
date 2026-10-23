"""
AI 建议引擎 — MVP 阶段使用规则匹配
后续可无缝替换为 LLM API 调用
"""

import re
import os, sys
import textwrap
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.config import (
    FTS5_COARSE_TOP_K, LLM_MAX_RETRIES,
    SEMANTIC_SEARCH_TOP_K, SIMILAR_CASES_TOP_K,
    RRF_K, VECTOR_TOP_K, VECTOR_SOLO_MIN_SIMILARITY,
)
from data.database import get_all_complaints, search_kb

# 0714 AI 调用来源常量（避免裸字符串散布）
SOURCE_DEEPSEEK = "deepseek"
SOURCE_RULES = "rules"
SOURCE_FAILED = "failed"

# ── 关键词 → 故障分类映射 ─────────────────────────
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "机械": [
        "异响", "振动", "磨损", "断裂", "卡死", "松动", "变形",
        "精度", "位置", "导轨", "丝杆", "轴承", "气缸", "皮带",
        "齿轮", "传动", "夹紧", "对位不准", "位移",
    ],
    "电气": [
        "短路", "断路", "烧坏", "电压", "电流", "信号", "通讯",
        "报警", "急停", "电源", "传感器", "驱动器", "电机",
        "线路", "接触不良", "保险", "漏电", "电磁阀",
    ],
    "工艺": [
        "气泡", "溢胶", "涂胶", "固化", "温度", "压力",
        "脱模", "翘曲", "偏移", "划痕", "残留", "粘接",
        "厚度", "均匀性", "空洞", "焊接",
    ],
    "光学": [
        "对位", "识别", "相机", "光源", "图像", "Mark",
        "误判", "拍照", "CCD", "镜头", "视觉", "照明",
        "对焦", "灰度", "轮廓",
    ],
    "软件": [
        "死机", "闪退", "报错", "重启", "代码", "参数",
        "配置", "版本", "Bug", "界面", "卡顿", "数据库",
        "日志", "崩溃", "更新",
    ],
}

# ── 优先级规则 ────────────────────────────────────
PRIORITY_RULES: dict[str, list[str]] = {
    "P0": [
        "批量", "停产", "安全", "全部", "无法生产",
        "全面", "紧急", "火灾", "爆炸", "人身安全",
        "产线停", "全线", "有偿定制",
    ],
    "P1": [
        "频繁", "反复", "影响效率", "良率下降", "连续",
        "多台", "不稳定", "波动", "偏高",
    ],
    "P2": [
        "偶尔", "单台", "建议", "优化", "小问题",
        "个别", "轻微", "观察",
    ],
    "P3": [
        "咨询", "文档", "说明书", "规格", "参数查询",
        "不影响生产", "不急", "保养",
    ],
}

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "待确认": 4}


# 0923 数据校准：真实机型谱系与领域术语表（源自 60 单真实工单回溯，
# classify/diagnose/case_search 等多处 prompt 共用，避免各 prompt 重复硬编虚构机型）
DOMAIN_CONTEXT = """\
## 设备与术语背景（真实机型谱系）
- 机型系列：EQ-200 / EQ-200A；EQ-220A / EQ-300 / EQ-300A / EQ-380F；EQ-400SP / EQ-400 / EQ-400A / EQ-400C / EQ-500；EQ-600。
- 常用组件术语 → 所属子系统：
  · 机械：取放头/焊接头、吸头/吸头架、顶升销/顶升销座/顶升销滑台、中转台/翻转台、物料台/工作台、接料台/轨道、载具/料盘、导轨/丝杆/直线电机/光栅尺、防撞垫、涂胶夹持/压料机构
  · 电气：伺服/驱动器、光源控制器、传感器/感应器、涂胶器、电源/跳闸/漏电、网线/网口/交换机
  · 光学：上视相机（uplook camera）、物料相机/贴装相机、镜头/镜筒、光源/灯光、PR 模板/示教、基准 标定
  · 工艺：胶水粘度/脱泡/固化、涂胶量、贴片精度/偏移、产能节拍 UPH、来料（芯片/框架/LCC）
  · 软件：示教界面、程式/编程、框架扫码联网/存本地、参数记忆、报警弹窗、软件版本（V1.2.6.6 / v3.0 等）
"""


# 0908 RAG 阶段 1：查询扩展词族（docs/05 §5.5 + 决策 D7）——同子系统/同语义簇的术语。
# 查询命中组内任一词时，向量通道的查询文本追加同组其余词，提升语义召回语境完整度
# （"死机/宕机/卡死""吸头/Nozzle"这类零词元重合的同义表述正是召回短板）。
# 仅用于向量通道，不污染关键词通道的词元交集；手工维护，源自 DOMAIN_CONTEXT + domain_dict。
QUERY_EXPANSION_GROUPS: list[list[str]] = [
    # 机械 — 取放/取放头
    ["吸头", "吸头架", "nozzle", "取物料", "物料", "wafer", "中转台", "翻转台"],
    ["取放头", "焊接头", "顶升销", "顶升销座", "顶升销滑台", "贴装", "贴装", "取料"],
    ["导轨", "丝杆", "直线电机", "光栅尺", "轴承", "联轴器", "传动", "机械手"],
    ["防撞", "撞击", "碰撞", "撞机"],
    # 电气
    ["电源", "跳闸", "漏电", "上电", "断电", "掉电", "保险", "空开", "急停"],
    ["伺服", "驱动器", "电机", "编码器", "轴卡", "伺服报警"],
    ["传感器", "感应器", "光电开关", "接近开关", "检测开关"],
    ["网线", "网口", "交换机", "通讯", "网络断开", "连接超时"],
    # 光学
    ["上视相机", "uplook", "贴装相机", "物料相机", "相机", "镜头", "镜筒", "CCD", "视觉"],
    ["光源", "灯光", "光源控制器", "照明", "灰度", "亮度"],
    ["识别", "Mark", "PR", "示教", "模板", "对位", "对焦", "定位"],
    # 工艺
    ["涂胶", "涂胶量", "胶水", "粘度", "溢胶", "漏胶", "涂胶器", "压料", "脱泡", "固化"],
    ["偏移", "贴片精度", "精度", "位置度", "偏位", "吸偏"],
    ["良率", "不良率", "UPH", "产能", "节拍", "效率"],
    # 软件
    ["死机", "宕机", "卡死", "卡顿", "无响应", "失去响应", "崩溃", "闪退", "重启"],
    ["程式", "编程", "程序", "配方", "参数记忆", "切换程式"],
    ["报警", "弹窗", "报错", "错误代码", "异常提示", "故障提示"],
    ["扫码", "框架扫码", "联网", "存本地", "条码"],
    # 机型系列（同系列互通）
    ["EQ-200", "EQ-200A"],
    ["EQ-220A", "EQ-300", "EQ-300A", "EQ-380F"],
    ["EQ-400SP", "EQ-400", "EQ-400A", "EQ-400C", "EQ-500"],
]

# 追加词总量上限（防多词族连环命中把查询文本冲淡）
QUERY_EXPANSION_MAX_APPEND = 30


def _expand_query_for_vector(query: str) -> str:
    """向量通道查询扩展（0908 RAG 阶段 1）：命中词族任一词 → 追加同组其余词。
    追加词去重且不与原查询重复，总量封顶 QUERY_EXPANSION_MAX_APPEND；
    未命中任何词族时原样返回。"""
    if not query:
        return query
    appended: list[str] = []
    for group in QUERY_EXPANSION_GROUPS:
        if not any(w in query for w in group):
            continue
        for w in group:
            if w not in query and w not in appended:
                appended.append(w)
                if len(appended) >= QUERY_EXPANSION_MAX_APPEND:
                    return query + " " + " ".join(appended)
    return query + " " + " ".join(appended) if appended else query


# ── 分类建议 ──────────────────────────────────────
def suggest_category(fault_phenomenon: str) -> tuple[str, list[str]]:
    """
    根据故障现象文本，返回 (建议分类, 匹配到的关键词列表)
    """
    if not fault_phenomenon:
        return ("其他", [])

    text = fault_phenomenon
    matched: dict[str, list[str]] = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        found = [kw for kw in keywords if kw in text]
        if found:
            matched[cat] = found

    if not matched:
        return ("其他", [])

    # 返回匹配关键词最多的类别
    best = max(matched, key=lambda c: len(matched[c]))  # type: ignore
    return (best, matched[best])


def suggest_category_with_reason(fault_phenomenon: str) -> dict:
    """返回含理由的结构化建议"""
    cat, keywords = suggest_category(fault_phenomenon)
    reason = f"匹配到关键词：{'、'.join(keywords)}" if keywords else "未匹配到明确关键词，建议人工确认"
    # 列出各分类匹配情况供参考
    all_matches = {}
    for c, kws in CATEGORY_KEYWORDS.items():
        found = [kw for kw in kws if kw in fault_phenomenon]
        if found:
            all_matches[c] = found
    return {
        "category": cat,
        "keywords": keywords,
        "reason": reason,
        "all_matches": all_matches,
    }


def suggest_preliminary_category(fault_phenomenon: str, allow_rule_fallback: bool = False) -> dict:
    """
    0616 决议 D3：客诉初步判定分类。

    策略：**默认只走 DeepSeek LLM，失败不自动降级**（除非客户确认）。
    - allow_rule_fallback=False（默认）：LLM 失败时返回 source="failed"，
      category 为空，附带 error 字段。UI 决定如何提示用户。
    - allow_rule_fallback=True：LLM 失败时降级到规则，source="rules"。

    返回字段：category / confidence / keywords / reason / source / error(仅 failed)
    """
    # 优先走 LLM
    llm_result = classify_complaint_llm(fault_phenomenon)
    if llm_result:
        # 0722 置信度由 LLM 实际输出，不再硬编码 0.9
        return {
            "category": llm_result["category"],
            "confidence": llm_result.get("confidence", 0.7),
            "keywords": [],
            "reason": llm_result["reason"],
            "source": "deepseek",
        }
    # LLM 失败
    if not allow_rule_fallback:
        return {
            "category": "",
            "confidence": 0.0,
            "keywords": [],
            "reason": "",
            "source": "failed",
            "error": get_last_llm_error() or "LLM 调用失败（未知原因）",
        }
    # 显式降级到规则
    cat, keywords = suggest_category(fault_phenomenon)
    confidence = min(1.0, len(keywords) / 5.0) if keywords else 0.0
    reason = (
        f"匹配到 {len(keywords)} 个关键词：{'、'.join(keywords)}"
        if keywords else "未匹配到明确关键词，建议人工确认"
    )
    return {
        "category": cat,
        "confidence": round(confidence, 2),
        "keywords": keywords,
        "reason": reason,
        "source": "rules",
    }


# ── 优先级建议 ────────────────────────────────────
def suggest_priority(fault_phenomenon: str, customer_note: str = "") -> dict:
    """
    根据故障现象和客户备注，返回优先级建议。
    取匹配最严重的等级（P0 > P1 > P2 > P3）。
    """
    text = f"{fault_phenomenon} {customer_note}"
    matched_levels: dict[str, list[str]] = {}
    for level, rules in PRIORITY_RULES.items():
        found = [r for r in rules if r in text]
        if found:
            matched_levels[level] = found

    if not matched_levels:
        return {"priority": "P2", "reason": "未匹配到明确紧急特征，默认建议 P2（常规处理）", "matched_rules": []}

    best = min(matched_levels, key=lambda x: PRIORITY_ORDER.get(x, 99))
    return {
        "priority": best,
        "reason": f"匹配到{best}类特征：{'、'.join(matched_levels[best])}",
        "matched_rules": matched_levels[best],
    }


# 0722 LLM 优先级建议：替代规则引擎关键词匹配，LLM 失败时自动降级
def suggest_priority_llm(fault_phenomenon: str, customer_note: str = "") -> dict:
    """
    用 LLM 分析故障现象和客户备注，返回优先级建议。

    成功返回 {priority, reason, confidence, source: "deepseek"}；
    失败自动降级到规则引擎 {priority, reason, matched_rules, source: "rules"}。
    """
    text = f"故障现象：{fault_phenomenon.strip()}"
    if customer_note and customer_note.strip():
        text += f"\n客户备注：{customer_note.strip()}"

    # [提示词优化 2026-08-03] system/user 分离，加边界 few-shot 和歧义兜底规则
    system_msg = textwrap.dedent("""\
        你是自动化设备售后工单优先级判定专家。
        自动化设备 是封装产线核心瓶颈设备，单机停线即可能导致整线停产，判定时须充分考虑其产线瓶颈属性。

        ## 判定标准（逐级对照，取最匹配的一级）

        **P0 — 紧急（需立即响应，30分钟内介入）**
        - 整线或关键工位停产，预计恢复时间 > 2小时
        - 人身安全事故或严重安全隐患（触电、机械夹伤、有毒气体泄漏）
        - 已确认的批量不良（≥5片或不良率 > 2%），可能涉及客退/索赔
        - 核心部件严重损坏无法自行修复（如贴片主轴、涂胶系统、视觉模组）
        - 客户明确表示投诉升级、要求赔偿、或触发合同 SLA 罚款条款
        - 关键工艺数据/配方/校准参数丢失且无备份，设备无法运行
        - 关键字触发：`紧急` `立刻` `马上` `停线` `停产` `批量报废` `赔偿` `客诉` `安全`

        **P1 — 高（4小时内安排处理）**
        - 单一设备故障，有替代设备可分担但整体产能下降 ≥ 30%
        - 同类型故障≥2次未找到根因（即使单次可恢复，重复发生应升级）
        - 新装机或刚验收设备出现故障（客户敏感期，影响客户信任）
        - 交期临近（≤ 3天）的设备突发故障
        - 影响关键客户（战略客户/Top 5 营收客户）的非 P0 级故障
        - 客户明确要求加急处理
        - 关键字触发：`重复` `再次` `又坏了` `交期` `验收` `新机`

        **P2 — 中（正常排期处理）**
        - 偶发故障且可自行恢复（重启/复位后正常）
        - 设备可正常运行但效率或精度轻微下降（< 10%）
        - 预防性维护需求、定期保养、耗材更换提醒
        - 非关键辅助功能异常（如指示灯、外壳、标签）不影响主生产流程
        - 一般性技术咨询、操作疑问、参数优化建议
        - 关键字触发：`可恢复` `重启` `不影响` `保养` `咨询`

        **P3 — 低（低优先级，可延期处理）**
        - 非紧急的技术咨询、操作疑问、文档需求
        - 功能建议、体验优化、界面改进请求
        - 客户明确表示不着急、可安排在计划维护窗口内处理
        - 已确认不影响生产的已知小缺陷
        - 关键字触发：`不急` `文档` `建议` `不影响` `小问题`

        ## 判定原则（优先级从高到低）
        1. **安全优先**：涉及人身安全的，一律 P0
        2. **影响范围**：全线停产 > 单机瓶颈工位 > 多机中一台 > 不影响生产
        3. **可恢复性**：不可自行恢复（硬件损坏）> 可重启恢复 > 完全不影响运行
        4. **客户信号**：投诉升级/索赔/罚款 → P0；加急 → P1；客户明确不急 → 仅可在其他证据都指向 P3 级时作为确认信号，
          若综合证据指向 P2 级及以上，客户主观"不急"最多降一级，不得从 P0 直接降至 P3
        5. **重复性**：≥2次同故障未解决 → 至少 P1；≥3次 → 倾向 P0
        6. **信息歧义时保守取高**：信息不足或判断模糊时，宁可判高一级，绝不漏判紧急工单

        ## 边界规则（高频易错场景）
        - **客户说"不急"不能过度降级**：客户说不急只能从当前判定下调最多一级（如 P1→P2），
          若其他证据指向 P0 级（停产/批量不良），客户主观"不急"不得将 P0 降为 P3
        - **同一故障第3次复现应倾向 P0**：即使每次都能重启恢复，≥3次未解决的重复故障
          说明根因未闭环，存在生产风险，应从 P1 升至 P0（除非客户明确接受现状）
        - **新机验收期故障至少 P1**：刚验收设备无论故障轻重，均不低于 P1 级

        ## 边界示例
        示例1：故障现象「EQ-200 伺服报警 AL-03，这是本月第3次了，每次重启能恢复」
        → priority: P0，reason: 同一故障第3次复现，根因未闭环，存在停产风险，confidence: 0.82

        示例2：故障现象「涂胶量偏少，客户说这批货交期不急，下周处理也行」
        → priority: P3，reason: 客户明确不急，偶发且不影响当前生产，confidence: 0.78
        （注意：客户说不急是 P3 级的支撑，但若同时存在批量不良，则不得低于 P2）

        ## 输出格式
        严格以 JSON 输出，不要其他解释：
        {"priority": "<P0|P1|P2|P3>", "reason": "<40字以内理由>", "confidence": <保留两位小数的0.00~1.00>}""").strip()

    out = llm_chat(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": text}],
        temperature=0.1, max_tokens=200,
        function_name="suggest_priority_llm",
    )
    if out:
        data = _parse_json_loose(out)
        if data and "priority" in data:
            pri = str(data["priority"]).strip().upper()
            if pri in ("P0", "P1", "P2", "P3"):
                raw_conf = data.get("confidence")
                try:
                    confidence = float(raw_conf)
                    if not (0.0 <= confidence <= 1.0):
                        confidence = 0.7
                except (TypeError, ValueError):
                    confidence = 0.7
                confidence = min(confidence, 0.95)
                return {
                    "priority": pri,
                    "reason": str(data.get("reason", "LLM 已判定"))[:100],
                    "confidence": round(confidence, 2),
                    "source": "deepseek",
                }

    # LLM 失败 → 降级到规则引擎
    rule_result = suggest_priority(fault_phenomenon, customer_note)
    rule_result["source"] = "rules"
    return rule_result


# ── 相似历史案例推荐 ──────────────────────────────────
# 0715 P0-1 FTS5升级：内存bigram全量扫描 → FTS5 MATCH数据库索引检索
# 0728 增加 fault_category 过滤：同类优先，无结果再放宽
def find_similar_cases(fault_phenomenon: str, top_k: int = SIMILAR_CASES_TOP_K,
                        fault_category: str = "") -> list[dict]:
    """
    从知识库中查找与当前故障现象相似的案例。
    0730 改用 search_kb_by_phenomenon() — 仅匹配 fault_phenomenon 字段。
    优先在同类别内检索，同类无结果时放宽到全类别。
    0908 RAG 阶段 1：升级为混合召回（关键词 ⊕ 向量 → RRF 融合，无 LLM 精排的
    轻量路径），级联语义不变；向量通道缺席时退化为关键词通道（即原行为）。
    """
    if not fault_phenomenon or not fault_phenomenon.strip():
        return []
    results = _hybrid_retrieve(fault_phenomenon.strip(), fault_category=fault_category,
                               relax=False)
    return results[:top_k]



def suggest_checklist(category: str) -> list[str]:
    """根据故障类别返回标准排查清单"""
    checklists: dict[str, list[str]] = {
        "机械": [
            "检查设备是否存在异响/振动及发生位置",
            "测量关键运动部件精度（导轨、丝杆、轴承）",
            "检查紧固件是否松动（螺丝、联轴器、皮带）",
            "确认润滑状态（油位、润滑周期）",
            "检查机械限位和传感器安装位置",
            "对比同型号正常设备的运行参数",
        ],
        "电气": [
            "检查电源输入电压/电流是否正常",
            "查看设备报警日志和故障代码",
            "检查传感器信号是否正常（示波器测量）",
            "检查通讯线缆连接和屏蔽情况",
            "测试驱动器/电机单体运转状态",
            "检查控制板卡指示灯状态",
            "确认接地和EMC措施是否到位",
        ],
        "工艺": [
            "确认当前工艺参数与标准参数是否一致",
            "检查来料质量（批次、存储条件、有效期）",
            "确认环境温湿度是否在工艺窗口内",
            "检查胶水/辅料的固化时间和温度曲线",
            "对比良品与不良品的工艺参数差异",
            "检查工装夹具的磨损和清洁状态",
        ],
        "光学": [
            "检查相机镜头清洁度，擦拭后重新标定",
            "确认光源亮度和均匀性（灰度值）",
            "运行Mark识别测试，检查识别率",
            "检查相机焦距和对位精度",
            "确认照明角度和安装位置是否偏移",
            "对比新旧产品的Mark特征差异",
        ],
        "软件": [
            "确认软件版本是否为最新",
            "查看软件日志，定位报错模块",
            "重启软件/系统后是否复现",
            "检查参数配置文件是否被修改",
            "确认操作系统和驱动的兼容性",
            "尝试复现操作步骤，确认触发条件",
        ],
        "其他": [
            "详细记录故障现象和发生频率",
            "确认是否在保修/服务范围内",
            "联系相关负责人进行初步诊断",
            "检查历史工单是否有相似案例",
        ],
    }
    return checklists.get(category, checklists["其他"])


def extract_keywords(text: str) -> list[str]:
    """从文本中提取有意义的关键词（2字以上中文）"""
    return list(set(re.findall(r"[一-龥]{2,}", text)))


# ══════════════════════════════════════════════════════
#  LLM 层（DeepSeek，OpenAI 兼容接口）
#  规则引擎作为降级方案：key 未配置或网络异常时自动回退
# ══════════════════════════════════════════════════════

# 0715 P0-2：session_state错误追踪 + 模块级回退
_llm_last_error_module: str | None = None


def _set_llm_error(error_msg: str | None):
    """将LLM错误写入模块级变量。"""
    global _llm_last_error_module
    _llm_last_error_module = error_msg


def get_last_llm_error() -> str | None:
    """读取模块级LLM错误变量。"""
    return _llm_last_error_module


# 0715 P0-2：OpenAI客户端单例（避免重复创建连接）
_OPENAI_CLIENT_CACHE: tuple | None = None


# 0714 工厂函数：创建 OpenAI 客户端（消除 llm_chat / check_deepseek 中的重复）
def _get_openai_client(timeout: int = 30):
    """0715 单例模式：复用客户端实例（模块级缓存）。"""
    global _OPENAI_CLIENT_CACHE
    from openai import OpenAI
    from ai_engine.core.llm_config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
    if _OPENAI_CLIENT_CACHE is None or _OPENAI_CLIENT_CACHE[1] != DEEPSEEK_MODEL:
        _OPENAI_CLIENT_CACHE = (
            OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=timeout),
            DEEPSEEK_MODEL,
        )
    return _OPENAI_CLIENT_CACHE[0], _OPENAI_CLIENT_CACHE[1]


# 0714 验证/模糊匹配故障类别
def _validate_category(raw: str) -> str:
    """将 LLM 返回的类别字符串模糊匹配到 CATEGORY_KEYWORDS 中的有效类别。"""
    if not raw:
        return ""
    raw_l = raw.strip().lower()
    for ck in CATEGORY_KEYWORDS:
        if raw_l in ck.lower() or ck.lower() in raw_l:
            return ck
    return ""


# 0715 P0-2：3次指数退避重试 + DB日志记录
def llm_chat(messages: list, temperature: float = 0.3, max_tokens: int = 1024,
             function_name: str = "", triggered_by: str = "", complaint_id: int = 0) -> str | None:
    """
    底层 LLM 调用。失败（key 未配置/网络异常/限流）返回 None，
    并把错误信息写入 session_state 供 UI 展示。
    本函数**不**自动降级——是否降级由上层根据业务策略决定。

    triggered_by: 触发调用的用户名
    complaint_id: 关联的工单 ID（如有）
    """
    import time

    fn = function_name or "llm_chat"

    # ── 配置检查 ──
    try:
        from ai_engine.core.llm_config import is_configured, DEEPSEEK_MODEL
        if not is_configured():
            err = "DeepSeek API key 未配置（检查 core/llm_config.py 或环境变量 DEEPSEEK_API_KEY）"
            _set_llm_error(err)
            _record_llm_call_impl(fn, DEEPSEEK_MODEL, 0, 0, "error", err, triggered_by, complaint_id)
            return None
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        _set_llm_error(err)
        _record_llm_call_impl(fn, "unknown", 0, 0, "error", err, triggered_by, complaint_id)
        return None

    client, model = _get_openai_client(timeout=30)
    prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)

    # ── 3次指数退避重试（仅对瞬态错误）──
    RETRYABLE = ("RateLimitError", "ServiceUnavailableError",
                 "APITimeoutError", "APIConnectionError",
                 "ConnectionError", "Timeout", "ReadTimeout")
    last_error = None

    for attempt in range(LLM_MAX_RETRIES):
        try:
            t0 = time.time()
            resp = client.chat.completions.create(
                model=model, messages=messages,
                temperature=temperature, max_tokens=max_tokens,
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            _set_llm_error(None)
            result = resp.choices[0].message.content

            _record_llm_call_impl(fn, model, elapsed_ms, prompt_chars, "success", "", triggered_by, complaint_id)
            return result

        except Exception as e:
            err_type = type(e).__name__
            last_error = f"{err_type}: {e}"
            is_retryable = any(t in err_type for t in RETRYABLE)
            if not is_retryable or attempt == 2:
                break
            time.sleep(2 ** attempt)  # 1s, 2s, 4s

    # 全部失败
    _set_llm_error(last_error)
    _record_llm_call_impl(fn, model, 0, prompt_chars, "error", last_error or "", triggered_by, complaint_id)
    return None


def _record_llm_call_impl(fn: str, model: str, latency: int,
                          chars: int, status: str, err: str,
                          triggered_by: str = "", complaint_id: int = 0):
    """内部实现：调用 database.record_llm_call，忽略写入错误。"""
    try:
        from data.database import record_llm_call
        record_llm_call(fn, model, latency, chars, status, err, triggered_by, complaint_id)
    except Exception:
        pass


def check_deepseek_connection() -> dict:
    """
    轻量级 DeepSeek 连通性检测。发一个最小请求（max_tokens=1），
    返回 {connected, latency_ms, error, last_check}。
    不缓存——调用方决定缓存策略。
    """
    import time
    try:
        from ai_engine.core.llm_config import is_configured
    except Exception as e:
        return {
            "connected": False, "latency_ms": 0,
            "error": f"core/llm_config 加载失败：{e}",
            "last_check": time.time(),
        }
    if not is_configured():
        return {
            "connected": False, "latency_ms": 0,
            "error": "API key 未配置（检查 llm_config.py 或环境变量 DEEPSEEK_API_KEY）",
            "last_check": time.time(),
        }
    try:
        client, model = _get_openai_client(timeout=8)
        t0 = time.time()
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
        )
        return {
            "connected": True,
            "latency_ms": int((time.time() - t0) * 1000),
            "error": None,
            "last_check": time.time(),
        }
    except Exception as e:
        return {
            "connected": False, "latency_ms": 0,
            "error": f"{type(e).__name__}: {str(e)[:120]}",
            "last_check": time.time(),
        }


def _parse_json_loose(text: str) -> dict | None:
    """
    宽松地从 LLM 输出里提取 JSON 对象。
    DeepSeek 偶尔会在 JSON 外裹一层 ```json ``` 或多余解释，这里做兜底。
    """
    import json
    if not text:
        return None
    # 直接试
    try:
        return json.loads(text)
    except Exception:
        pass
    # 提取第一个 {...}
    m = re.search(r"\{[\s\S]*?\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def classify_complaint_llm(fault_phenomenon: str) -> dict | None:
    """
    用 LLM 对客诉故障现象进行分类。
    成功返回 {category, reason, source: "deepseek"}；
    失败返回 None（调用方降级到规则）。
    """
    if not fault_phenomenon or not fault_phenomenon.strip():
        return None
    # 0923 数据校准（60 单真实数据回溯）：system/user 分离 + 真实机型术语表 + 3 个真实错例负例 + thinking 推理
    system_msg = textwrap.dedent(f"""\
        你是自动化设备售后故障分类助手。自动化设备 主要由运动平台（机械）、电气控制柜（电气）、涂胶与固化模组（工艺）、视觉对位系统（光学）、上位机软件（软件）五大子系统组成。

        {DOMAIN_CONTEXT}
        ## 分类决策原则
        1. **按根因而非表象分类**：从现象推断最可能的根因所属子系统，而非停留在表面描述。
        2. **多因素时选最上游**：如"视觉对位失败导致涂胶偏移"，根因在光学（对位失败），选光学而非工艺。
        3. **需求按改动落点归类**：功能添加/界面优化/操作体验类诉求不是故障，但也按改动落在哪个子系统归类——
           软件/程式/界面/参数类需求一律选「软件」，不得因"不是故障"而选「其他」。
        4. **通信类报警优先怀疑硬件链路**：TCP 发送失败/掉线/掉灯光/通讯中断，现场根因多为网线松动、
           网口/交换机异常、线缆接触不良（电气）；仅当明确是协议 Bug 或界面逻辑错误才选「软件」。

        ## 类别定义与边界
        - **机械**：运动部件的物理故障——异响/振动/磨损/断裂/卡死/松动/变形/精度超标/部件干涉/装配无标准。
          ⚠️ 电机线圈烧坏→电气；电机轴卡死→机械。传感器本身故障→电气；传感器支架松动→机械。
        - **电气**：电路、信号、电源、驱动系统的电气属性异常——短路/断路/电压电流异常/信号通讯故障/报警急停/传感器失灵/驱动器报警/电机烧坏/跳闸漏电。
          ⚠️ 通讯线松动→电气；通讯协议 Bug→软件。
        - **工艺**：材料、配方、环境参数相关的加工质量缺陷——气泡/溢胶/涂胶量/固化不良/温度压力异常/脱模/翘曲/偏移/厚度/均匀性。
          ⚠️ 温度传感器读数异常→电气；温度设定值不合理→工艺。涂胶阀机械卡死→机械；涂胶量偏差→工艺。
        - **光学**：视觉系统的成像、识别、定位故障——对位失败/识别错误/相机黑屏/光源衰减/图像模糊/Mark 搜索失败/CCD 噪点/镜头失焦/灰度异常。
          ⚠️ 视觉系统电源故障→电气；视觉参数配置错误→软件。
        - **软件**：程序逻辑、参数配置、系统运行时的代码级异常——死机/闪退/报错弹窗/异常重启/参数丢失/版本不兼容/Bug/界面卡顿/日志报崩溃，以及软件功能与界面需求。
          ⚠️ 因电气干扰导致的软件报错→电气；因硬盘故障导致系统崩溃→电气。
        - **其他**：明确不属于以上五类的非技术问题——客户沟通投诉/物流损坏/商务合同/非设备本身的技术支持需求。
          ⚠️ 技术故障即使难以判断也应先尝试归入前五类，确实无法归类才选"其他"。

        ## 分类示例（后三条为真实纠错案例）
        故障：贴片平台移动时发出周期性尖锐异响，速度越快声音越大 → 机械（运动部件异响，速度关联→机械传动链）
        故障：固化工位实际温度比设定值低 15℃，产品出现大面积气泡 → 工艺（温度→固化→气泡，根因在工艺参数或加热组件，优先工艺）
        故障：Mark 识别超时报错，导致整片物料无法对位，设备停机 → 光学（Mark 识别→视觉系统根因，后续停机是连锁反应）
        故障：伺服驱动器频繁报 AL-03 过流，更换驱动器后仍复现 → 电气（驱动器过流→电气回路或电机绕组问题）
        故障：升级到 V3.2 后每运行约 2 小时软件就闪退，旧版本正常 → 软件（版本升级引入 Bug，2h 规律崩溃→典型的软件问题）
        需求：软件主界面添加方向盘四轴正负方向指引图标 → 软件（界面功能需求，改动落点在上位机软件；❌ 选「其他」是错的）
        故障：焊接头点光异常无法控制，调节时报警 TCP 发送失败 → 电气（通信报警优先怀疑网线/网口/交换机等硬件链路；❌ 选「软件」是错的）
        故障：切换程式进入吸头取片动作后，软件卡住不动，无法操作任何软件界面 → 软件（「吸头取片」只是触发场景，卡死的是软件；❌ 选「机械」是错的）

        ## 输出格式
        先在 thinking 里写出根因归属子系统的推理（≤40字），再给结论。
        严格以 JSON 输出（不要其他解释）：
        {{"thinking": "<≤40字推理>", "category": "<机械|电气|工艺|光学|软件|其他>", "reason": "<30字以内理由>", "confidence": <0.0~1.0>}}

        confidence 含义：你对本次分类的确定程度。明确典型案例（如"异响振动→机械"）给 0.85+；模糊案例（信息不足或跨类别边界）给 0.5~0.7；完全不确定给 0.3 以下。""").strip()

    user_msg = f"故障现象：{fault_phenomenon.strip()}"

    out = llm_chat(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": user_msg}],
        temperature=0.1, max_tokens=300,
        function_name="classify_complaint_llm",
    )
    if not out:
        return None
    data = _parse_json_loose(out)
    if not data or "category" not in data:
        return None
    cat = str(data["category"]).strip()
    # 校验类别合法性
    valid = list(CATEGORY_KEYWORDS.keys()) + ["其他"]
    if cat not in valid:
        # 尝试模糊匹配
        for v in valid:
            if v in cat or cat in v:
                cat = v
                break
        else:
            cat = "其他"
    # 0722 解析 LLM 输出的置信度：有效范围 0~1，异常值兜底 0.7
    raw_conf = data.get("confidence")
    try:
        confidence = float(raw_conf)
        if not (0.0 <= confidence <= 1.0):
            confidence = 0.7
    except (TypeError, ValueError):
        confidence = 0.7
    # 轻量校准：防止 LLM 过度自信
    confidence = min(confidence, 0.95)
    return {
        "category": cat,
        "reason": str(data.get("reason", "LLM 已分类"))[:100],
        "source": "deepseek",
        "confidence": round(confidence, 2),
    }


def extract_knowledge_llm(raw_text: str) -> dict | None:
    """
    用 LLM 从非结构化文本抽取知识库字段。
    成功返回带 source="deepseek" 的 dict；失败返回 None。
    """
    if not raw_text or not raw_text.strip():
        return None
    # [提示词优化 2026-08-03] system/user 分离，强化字段规范、优先级和负例约束
    system_msg = (
        "你是自动化设备售后知识库录入专家，"
        "负责从工程师提交的非结构化文本中提取结构化知识条目。\n\n"
        "## 字段说明与提取优先级\n"
        "优先级从高到低：title（必填）> root_cause > solution > 其余字段；"
        "未提及的字段留空字符串 \"\"，不得编造。\n\n"
        "字段规范：\n"
        "- title: 简洁标题，≤30字，概括故障类型和处理要点；"
        "不要把设备型号写进标题（型号在 equipment_model 字段）\n"
        "  ✅ 正例：「伺服驱动器过流报警 AL-03 的排查与更换」\n"
        "  ❌ 负例：「EQ-200 故障处理记录」（型号入侵标题，内容空洞）\n"
        "- fault_category: 机械 / 电气 / 工艺 / 光学 / 软件 / 其他 之一，按根因判断而非表面现象\n"
        "- equipment_model: 设备型号（如 EQ-200、EQ-300A、EQ-400；无则空）\n"
        "- fault_keywords: 3~8 个关键词，逗号分隔，覆盖故障部件+现象+处理方式\n"
        "  示例：「伺服驱动器,过流,AL-03,更换驱动器」\n"
        "- root_cause: 根因分析，说明故障发生的机理和原因，≤150字\n"
        "- solution: 具体操作步骤；不要重复 root_cause 的描述内容，直接写怎么处理\n"
        "- checklist: 检查清单，多步骤用换行符（\\n）分隔；无则空字符串\n"
        "- lesson_learned: 经验教训，说明如何避免同类问题复发，≤100字\n"
        "- contact_author: 姓名或联系方式（如：张三 138xxxxxxxx）；无则空\n\n"
        "## 短文本处理规则\n"
        "输入文本≤5句话时：从全文提炼 title，能提取几个字段就填几个，其余留空，不得编造细节。\n\n"
        "## 示例（工程师简短笔记）\n"
        "输入：EQ-200 今天贴片偏移，检查发现 XY 平台丝杆磨损，已更换。建议定期润滑。\n"
        "输出：{\"title\":\"XY平台丝杆磨损导致贴片偏移\","
        "\"fault_category\":\"机械\",\"equipment_model\":\"EQ-200\","
        "\"fault_keywords\":\"XY平台,丝杆,磨损,贴片偏移,更换\","
        "\"root_cause\":\"XY平台丝杆磨损，运动精度下降，贴片出现偏移\","
        "\"solution\":\"更换磨损丝杆，重新校准运动平台精度\","
        "\"checklist\":\"检查XY平台丝杆磨损程度\\n更换丝杆\\n重新校准并验证贴片精度\","
        "\"lesson_learned\":\"丝杆应定期润滑保养，建议每3个月检查一次\","
        "\"contact_author\":\"\"}\n\n"
        "严格以 JSON 输出，不要其他解释，不要 markdown 代码块。"
    )
    user_msg = f"请提取以下文本中的知识库字段：\n\n{raw_text.strip()}"
    out = llm_chat(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": user_msg}],
        temperature=0.2, max_tokens=1200,
        function_name="extract_knowledge_llm",
    )
    if not out:
        return None
    data = _parse_json_loose(out)
    if not data:
        return None
    result = {
        "title": str(data.get("title", "")).strip(),
        "fault_category": str(data.get("fault_category", "")).strip(),
        "equipment_model": str(data.get("equipment_model", "")).strip(),
        "fault_keywords": str(data.get("fault_keywords", "")).strip(),
        "root_cause": str(data.get("root_cause", "")).strip(),
        "solution": str(data.get("solution", "")).strip(),
        "checklist": str(data.get("checklist", "")).strip(),
        "lesson_learned": str(data.get("lesson_learned", "")).strip(),
        "contact_author": str(data.get("contact_author", "")).strip(),
        "source": "deepseek",
    }
    # 类别合法性校验
    valid = list(CATEGORY_KEYWORDS.keys()) + ["其他"]
    if result["fault_category"] and result["fault_category"] not in valid:
        result["fault_category"] = ""
    return result



# ── 知识库智能抽取（启发式，无 LLM 时降级使用）─────
def extract_knowledge_from_text(raw_text: str, allow_rule_fallback: bool = False) -> dict:
    """
    从非结构化文本抽取知识库字段。

    策略：**默认只走 DeepSeek LLM，失败不自动降级**（除非客户确认）。
    - allow_rule_fallback=False（默认）：LLM 失败时返回 source="failed"，
      所有字段空，附带 error 字段。
    - allow_rule_fallback=True：LLM 失败时降级到启发式规则：
       1) 设备型号：正则匹配 H\\d{3,4}；
        2) 段落锚点：识别「根因/方案/检查清单/教训」；
        3) 故障类别：用 CATEGORY_KEYWORDS 投票；
        4) 关键词：高频 2~4 字中文词 top-N；
        5) 标题：第一行或机型+类别合成。

    Returns: dict，含 source ∈ {deepseek, rules, failed}；failed 时附带 error。
    """
    # 优先走 LLM
    llm_result = extract_knowledge_llm(raw_text)
    if llm_result:
        return llm_result  # 已含 source="deepseek"

    # LLM 失败
    if not allow_rule_fallback:
        return {
            "title": "", "fault_category": "", "equipment_model": "",
            "fault_keywords": "", "root_cause": "", "solution": "",
            "checklist": "", "lesson_learned": "",
            "contact_author": "",
            "source": "failed",
            "error": get_last_llm_error() or "LLM 调用失败（未知原因）",
        }

    # 显式降级到启发式规则
    import re
    from collections import Counter

    empty = {
        "title": "",
        "fault_category": "",
        "equipment_model": "",
        "fault_keywords": "",
        "root_cause": "",
        "solution": "",
        "checklist": "",
        "lesson_learned": "",
        "contact_author": "",
    }
    if not raw_text or not raw_text.strip():
        return empty

    text = raw_text.strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    result = dict(empty)

    # 1) 设备型号
    model_patterns = [
        r"(?:设备型号|机型|设备)[:：\s]*([A-Z]?\d{3,4}[A-Z]?)",
        r"\b([A-Z]?\d{3,4}[A-Z]?)\b",
    ]
    for pat in model_patterns:
        m = re.search(pat, text)
        if m:
            result["equipment_model"] = m.group(1)
            break

    # 2) 段落锚点扫描
    anchors = [
        ("root_cause", r"(?:根因分析|根本原因|根因|故障原因|原因)[:：]?"),
        ("solution", r"(?:解决方案|处理方案|解决办法|处理措施|处理|方案|措施|对策)[:：]?"),
        ("checklist", r"(?:检查清单|排查清单|排查步骤|检查步骤|Checklist|检查项)[:：]?"),
        ("lesson_learned", r"(?:经验教训|经验|教训|启示|小结|Lesson)[:：]?"),
    ]
    sections = {}
    current_key = None
    current_buf = []
    for line in lines:
        matched = False
        for key, pat in anchors:
            m = re.match(r"\s*" + pat + r"(.*)", line, re.IGNORECASE)
            if m:
                if current_key and current_buf:
                    sections[current_key] = "\n".join(current_buf).strip()
                current_key = key
                rest = m.group(1).strip()
                current_buf = [rest] if rest else []
                matched = True
                break
        if not matched and current_key:
            current_buf.append(line)
    if current_key and current_buf:
        sections[current_key] = "\n".join(current_buf).strip()
    result.update(sections)

    # 3) 故障类别投票
    bucket = " ".join([text, sections.get("root_cause", ""), sections.get("solution", "")])
    cat_scores = {cat: sum(1 for kw in kws if kw in bucket) for cat, kws in CATEGORY_KEYWORDS.items()}
    if any(cat_scores.values()):
        result["fault_category"] = max(cat_scores, key=cat_scores.get)

    # 4) 关键词 top-8
    tokens = re.findall(r"[一-龥]{2,4}", text)
    common = [t for t, _ in Counter(tokens).most_common(8)]
    result["fault_keywords"] = ", ".join(common)

    # 5) 标题
    first_line = lines[0] if lines else ""
    title_m = re.match(r"(?:标题|题目|主题)[:：]?\s*(.*)", first_line)
    if title_m and title_m.group(1).strip():
        result["title"] = title_m.group(1).strip()
    elif len(first_line) <= 40:
        result["title"] = first_line
    else:
        parts = [p for p in [result["equipment_model"], (result["fault_category"] + "故障") if result["fault_category"] else ""] if p]
        result["title"] = " ".join(parts) if parts else "未命名知识"

    result["source"] = "rules"
    return result


# ══════════════════════════════════════════════════════
#  混合检索（0908 RAG 阶段 1：关键词通道 ⊕ 向量通道 → RRF 融合）
#  供 semantic_search_kb（LLM 精排前粗筛）与 find_similar_cases（轻量直出）共用；
#  向量通道缺席（provider 未配置 / pgvector 未启用 / API 失败）时退化为关键词通道
#  单通道排序，即升级前行为——降级显式（日志），不静默伪造结果。
# ══════════════════════════════════════════════════════

def _embed_query_once(query: str) -> list[float] | None:
    """查询向量（0908 RAG 阶段 1）：查询扩展 → embedding → 单条向量。
    级联各级复用同一次计算。不可用/失败返回 None（向量通道缺席）。"""
    try:
        from ai_engine import embedding
        if not embedding.is_available():
            return None
        vecs = embedding.embed_texts([_expand_query_for_vector(query)],
                                     triggered_by="hybrid_search")
        return vecs[0] if vecs else None
    except Exception as e:
        print(f"[hybrid] 查询向量生成异常，本轮跳过向量通道：{type(e).__name__}: {e}", flush=True)
        return None


def _rrf_fuse(channel_lists: list[tuple[str, list[dict]]], k: int = RRF_K) -> list[dict]:
    """RRF 融合去重（Reciprocal Rank Fusion）：score = Σ 1/(k + rank)。
    按名次融合，两通道天然可比，无需调分数权重（docs/05 §5.5）。
    每条候选附带 rrf_score 与 retrieval_channels（命中通道，供观测/后续分通道统计）。"""
def _rrf_fuse(channel_lists: list[tuple[str, list[dict]]], k: int = RRF_K) -> list[dict]:
    """RRF 融合去重（Reciprocal Rank Fusion）：score = Σ 1/(k + rank)。
    按名次融合，两通道天然可比，无需调分数权重（docs/05 §5.5）。
    每条候选附带 rrf_score 与 retrieval_channels（命中通道，供观测/后续分通道统计），
    并合并各通道的附加分值字段（keyword_score/vector_score）便于阈值校准。"""
    scores: dict = {}
    hits: dict = {}
    rows: dict = {}
    for name, lst in channel_lists:
        for rank, row in enumerate(lst, start=1):
            kid = row.get("id")
            if kid is None:
                continue
            scores[kid] = scores.get(kid, 0.0) + 1.0 / (k + rank)
            hits.setdefault(kid, []).append((name, row))
            if kid not in rows:
                rows[kid] = row
    fused = []
    for kid, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        row = dict(rows[kid])
        row["rrf_score"] = round(score, 6)
        row["retrieval_channels"] = sorted({name for name, _ in hits[kid]})
        for _, src in hits[kid]:
            for score_key in ("keyword_score", "vector_score"):
                if score_key in src and score_key not in row:
                    row[score_key] = src[score_key]
        fused.append(row)
    return fused


def _filter_solo_vector(rows: list[dict]) -> list[dict]:
    """0909 精度收尾：仅 vector 单通道命中且分数低于精筛线的条目剔除。

    依据种子回放：VECTOR_MIN_SIMILARITY=0.5 挡得住无关查询（噪声 ≤0.465），挡不住
    相关查询内混入的弱相关条目（0.509~0.592），且与期望命中分数（0.572 起）重叠、
    单调调全局阈值无解（Q9 误引 0.592 > Q3 期望 0.572）——改为按命中通道结构过滤：
    双通道（keyword+vector）或 keyword 命中不受影响，仅向量单通道须过 0.6 线
    （VECTOR_SOLO_MIN_SIMILARITY，Q1 同义召回 0.633 仍保留）。无 channels 字段的
    降级路径（向量缺席时的纯关键词结果）自动 no-op。"""
    out = []
    for r in rows:
        if (r.get("retrieval_channels") == ["vector"]
                and float(r.get("vector_score") or 0) < VECTOR_SOLO_MIN_SIMILARITY):
            continue
        out.append(r)
    return out


def _hybrid_retrieve(query: str, fault_category: str = "",
                     top_k: int = FTS5_COARSE_TOP_K, relax: bool = True) -> list[dict]:
    """混合召回 + 级联（0908 RAG 阶段 1）。relax=True（供 semantic_search_kb，LLM 精排
    会滤噪）时四级级联与原 Stage 1 完全同构：
        (类别, 默认阈值) → (无类别) → (类别, 阈值1) → (无类别, 阈值1)
    relax=False（供 find_similar_cases 直出展示，无 LLM 滤噪）只保留前两级——阈值 1
    的单词弱匹配不允许直接展示（0923 校准：'设备上电跳闸'须返回 0，防无关混入）。
    每级 = 关键词通道（jieba 加权，含 keyword_score）⊕ 向量通道（pgvector 余弦，
    自身同样类别优先、空结果放开类别）→ RRF 融合 → 单通道低分过滤（0909，过滤后为空
    则该级视为无结果、级联继续放宽）；查询向量全程只算一次。"""
    from data.database import search_kb_by_phenomenon, search_kb_by_vector
    query_vec = _embed_query_once(query)

    def _vector_stage(category: str) -> list[dict]:
        if query_vec is None:
            return []
        hits = search_kb_by_vector(query_vec, top_k=VECTOR_TOP_K, category_filter=category)
        if not hits and category:
            hits = search_kb_by_vector(query_vec, top_k=VECTOR_TOP_K)
        return hits

    def _stage(category: str, min_overlap) -> list[dict]:
        kw = search_kb_by_phenomenon(query, category_filter=category,
                                     min_overlap=min_overlap)[:top_k]
        vec = _vector_stage(category)[:top_k]
        if query_vec is None:
            return kw
        return _filter_solo_vector(_rrf_fuse([("keyword", kw), ("vector", vec)]))

    fused = _stage(fault_category, None)
    if not fused and fault_category:
        fused = _stage("", None)
    if relax:
        if not fused:
            fused = _stage(fault_category, 1)
        if not fused and fault_category:
            fused = _stage("", 1)
    return fused[:top_k]


def kb_embed_text(data: dict) -> str:
    """KB 条目嵌入文本（0908 RAG 阶段 1）：整条原文拼接、不分块（条目本身是
    结构化整条粒度，docs/05 §2.2）；标题/现象前置保证现象相似检索的语境权重。"""
    parts = [
        str(data.get("title", "") or ""),
        str(data.get("fault_phenomenon", "") or ""),
        str(data.get("fault_keywords", "") or ""),
        str(data.get("root_cause", "") or ""),
        str(data.get("solution", "") or ""),
    ]
    return " ".join(p for p in parts if p)


def embed_kb_entry(kb_id: int, data: dict, triggered_by: str = "") -> bool:
    """为 KB 条目生成并写入向量（0908 RAG 阶段 1）。
    不可用（provider 未配置 / pgvector 未启用）或任何失败：记日志 + llm_call_log，
    返回 False，不抛异常——不阻断归档/保存（docs/05 §5.3，回填脚本可后补）。"""
    try:
        from ai_engine import embedding
        from data.database import update_kb_embedding
        if not embedding.is_available():
            return False
        text = kb_embed_text(data)
        if not text.strip():
            return False
        vecs = embedding.embed_texts([text], triggered_by=triggered_by or "kb_write")
        if not vecs:
            return False
        return update_kb_embedding(kb_id, vecs[0], embedding.get_embed_model())
    except Exception as e:
        print(f"[embedding] KB#{kb_id} 向量生成失败（不阻断保存，可由回填脚本补）："
              f"{type(e).__name__}: {e}", flush=True)
        return False


# 0715 P0-1 FTS5升级：全量KB塞LLM → 两阶段检索（FTS5粗排Top-20 + LLM精排Top-5）
# 0728 增加 fault_category 过滤：同类优先，无结果再放宽
def semantic_search_kb(query: str, top_k: int = SEMANTIC_SEARCH_TOP_K,
                        fault_category: str = "") -> list[dict]:
    """
    使用 FTS5 + DeepSeek 两阶段语义检索。
    Stage 1: 混合粗筛 Top-20（0908 RAG 阶段 1：关键词 ⊕ 向量 → RRF 融合，级联同类优先）
    Stage 2: LLM 精排 Top-K（在候选集内语义重排序）
    LLM 不可用时自动降级返回粗筛结果；向量通道不可用时 Stage 1 = 纯关键词（原行为）。
    0909 判空收紧：LLM 有效判定（含空列表）完全信任，不再用粗筛候选补足 top_k。
    """
    if not query or not query.strip():
        return []

    # ── Stage 1: 混合粗筛 Top-20（0908 RAG 阶段 1；四级级联见 _hybrid_retrieve）──
    candidates = _hybrid_retrieve(query.strip(), fault_category=fault_category)
    if not candidates:
        return []
    candidates = candidates[:FTS5_COARSE_TOP_K]

    # ── Stage 2: LLM精排 ──
    lines = []
    for e in candidates:
        parts = [f"[ID:{e['id']}] {e['title']}"]
        if e.get("fault_keywords"):
            parts.append(f"关键词：{e['fault_keywords']}")
        if e.get("root_cause"):
            parts.append(f"根因：{e['root_cause'][:60]}")
        if e.get("solution"):
            parts.append(f"方案：{e['solution'][:60]}")
        if e.get("contact_author"):
            parts.append(f"作者：{e['contact_author']}")
        lines.append(" | ".join(parts))

    # prompt = (
    #     "你是自动化设备售后知识库的智能检索助手。\n"
    #     "用户输入了一条查询，请从以下知识库条目中，找出所有与查询**含义相近**的条目。\n"
    #     "所谓「含义相近」是指：描述的是相同或相似的故障场景、设备问题、根因、解决方案。\n"
    #     "**即使关键词不完全匹配**，只要意思相近就应该选中。\n\n"
    #     f"用户查询：{query.strip()}\n\n"
    #     "知识库条目：\n"
    #     f"{chr(10).join(lines)}\n\n"
    #     "请选出含义相近的条目 ID，按相关性从高到低排列。\n"
    #     "严格以 JSON 格式输出（不要其他解释）：\n"
    #     '{"matched_ids": [3, 7, 1]}'
    # )
    # [提示词优化 2026-08-03] system/user 分离，明确选中标准/排除规则/上限/零结果规范
    system_msg = (
        "你是自动化设备售后知识库的语义检索专家。\n"
        "你的任务是从候选条目中，判断哪些与用户查询的故障**含义相近**，而非仅字面匹配。\n\n"
        "## 选中标准（至少满足其中一条才可选中）\n"
        "1. 故障现象相同或高度相似（如都表现为异响/振动/停机/精度异常等同类症状）\n"
        "2. 涉及相同的设备部件或子系统（如传动系统、涂胶系统、视觉系统）\n"
        "3. 根因或解决方案可互相借鉴（排查思路/修复方法可复用，即使现象不完全相同）\n\n"
        "## 明确排除（满足以下任一条则不得选中）\n"
        "- 仅设备型号相同，但故障内容完全无关\n"
        "- 仅关键词字面匹配，但故障机理不同（如「振动」在「机身振动」和「振动盘卡料」中指向不同子系统）\n"
        "- 与查询完全无关的条目\n\n"
        "## 输出规则\n"
        "- 按相关性从高到低排列，最多返回 10 个 ID\n"
        "- 无相近条目时输出空列表，不得输出 null\n"
        "- 严格以 JSON 格式输出，不要其他解释：{\"matched_ids\": [3, 7, 1]} 或 {\"matched_ids\": []}"
    )
    user_msg = (
        f"用户查询：{query.strip()}\n\n"
        f"候选条目：\n{chr(10).join(lines)}"
    )

    out = llm_chat(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": user_msg}],
        temperature=0.1,
        max_tokens=500,
        function_name="semantic_search_kb",
    )
    if not out:
        # LLM不可用时降级：直接返回FTS5结果
        return candidates[:top_k]

    data = _parse_json_loose(out)
    if not data or "matched_ids" not in data:
        return candidates[:top_k]

    matched_ids = data["matched_ids"]
    if not isinstance(matched_ids, list):
        return candidates[:top_k]

    # 0909 判空收紧：LLM 有效给出判定（含空列表）即完全信任——按其排序返回候选集内
    # 有效 id，不再用粗筛候选补足 top_k。此前"判空后仍补足"会让无关查询带出弱候选
    # 并被 case_search_solution 误引（0908 已知边界；推翻 0803"保证有结果"取舍，
    # docs/05 §4.4"无引用不下结论"红线）。LLM 返回 id 均不在候选集（幻觉 id）视为判空。
    id_map = {e["id"]: e for e in candidates}
    results = []
    for eid in matched_ids:
        if eid in id_map:
            results.append(id_map[eid])
            if len(results) >= top_k:
                break
    return results


def extract_complaint_from_text(raw_text: str, allow_rule_fallback: bool = False) -> dict:
    """
    从非结构化文本（聊天记录、邮件、笔记等）提取客诉表单字段。
    优先走 DeepSeek LLM；失败时若 allow_rule_fallback=True 可降级到简单规则。
    返回 dict，含 source ∈ {deepseek, rules, failed}。
    """
    if not raw_text or not raw_text.strip():
        return {"source": "failed", "error": "输入文本为空"}

    # [提示词优化 2026-08-03] system/user 分离，补充多设备/多日期规则和 preliminary_category 负例
    # [0923 数据校准] 机型示例换真实谱系；新增 software_version 禁入型号规则（真实错例：版本字段被填入设备型号）
    system_msg = textwrap.dedent("""\
        你是自动化设备售后客诉录入助手。
        自动化设备 常见设备型号如 EQ-200/EQ-200A、EQ-220A/EQ-300A/EQ-380F、EQ-400SP/EQ-400/EQ-400A/EQ-500、EQ-600 等（字母系列+数字）；软件版本如 V1.2.6.6、v3.0、V3.0、1.3.0.0 等。
        从非结构化文本（微信/钉钉聊天记录、邮件、电话笔记等）中提取客诉表单字段。
        文本可能包含多人对话、无关寒暄、邮件签名等噪音——忽略噪音，仅提取关键信息。

        ## 提取规则
        - 未提及的字段留空字符串 ""，不要编造任何内容；文本明确写「无」「没有」的也视为未提及，留空 ""
        - 如多人对话，以「提出故障的人」为客户方
        - 客户名称优先法人全称，不得用个人姓名代替公司名（如"示例客户A"优于"客户工程师"）；客户为编号/代号时（如 HB-A-421）原样保留
        - 设备型号可能以简称出现（如"EQ-200"、"2200机型"）；文本提到多台设备时，以**最先报故障的设备**为准
        - software_version 只接受版本号格式（V/v+数字 或 纯数字点分，如 V3.0、1.2.6.6）；
          设备型号（如 EQ-500）不是软件版本，禁止填入 software_version；未提及留空 ""
        - 故障现象保留原文关键描述，去除"请问"、"帮忙看看"等礼貌用语
        - expected_complete_date：严格输出 YYYY-MM-DD 格式或空字符串，不得输出"明天""下周""本周内"等相对时间；
          文本中出现多个日期时，以**明确要求完成/交货的日期**为准；无年份则推断为当前年份
        - impact_level：保留原文对影响的描述，不得自行评级或添加主观判断
        - equipment_sn：从文本中提取设备序列号/SN/机身编号；未提及则留空 ""
        - device_part：从文本中提取设备具体故障部位（如"涂胶阀""伺服驱动器""上视相机""取放头""顶升销座""物料台""接料台"等 自动化设备 组件）；未提及则留空 ""
        - **preliminary_category 必须输出空字符串 ""**：故障分类由后续专用 AI 判定，此处绝对不填任何值

        ## 示例 1 — 聊天记录
        输入：
        客服人员：客户工程师你好，我们这边 EQ-200 今天下午突然报错了
        客户客户工程师：啥情况？机器直接停了，整条线等着呢
        客服人员：显示伺服驱动器报警 AL-03，已经重启过了没用
        客户客户工程师：赶紧找人来看吧，这批货后天要交的，急！
        输出：
        {"customer_name":"","equipment_model":"EQ-200","equipment_sn":"","software_version":"","fault_phenomenon":"伺服驱动器报警 AL-03，重启无效，设备停机","preliminary_category":"","expected_complete_date":"","impact_level":"整线停产，交期紧迫","device_part":"伺服驱动器","customer_note":"后天交期，紧急处理"}

        ## 示例 2 — 邮件
        输入：
        发件人：zhang@example.com
        主题：关于 EQ-300A 设备涂胶异常的问题
        客户工程师你好，我司上周新装的 EQ-300A 设备（软件 V3.0.5）在生产中发现涂胶量不稳定，导致约 3% 产品溢胶。目前还能生产但良率下降，希望本周内安排人来看一下。另请把维修报告抄送我司品质部品质经理。
        输出：
        {"customer_name":"示例客户A","equipment_model":"EQ-300A","equipment_sn":"","software_version":"V3.0.5","fault_phenomenon":"涂胶量不稳定，约3%产品溢胶，良率下降","preliminary_category":"","expected_complete_date":"","impact_level":"良率下降约3%，仍可生产","device_part":"涂胶阀","customer_note":"本周内安排；维修报告抄送品质部品质经理"}

        ## 示例 3 — 简单笔记
        输入：
        今天接到 示例客户B电话，说他们那台 EQ-500 视觉对位老是对不上，换了光源也不行，怀疑是相机问题。客户说下周要审计，希望在审计前搞定。
        输出：
        {"customer_name":"示例客户B","equipment_model":"EQ-500","equipment_sn":"","software_version":"","fault_phenomenon":"视觉对位失败，更换光源无效，疑似相机故障","preliminary_category":"","expected_complete_date":"","impact_level":"影响客户审计准备","device_part":"视觉模块","customer_note":"下周审计前需解决"}

        ## 示例 4 — 负例（preliminary_category 绝对不填）
        输入：
        客户反馈 EQ-200 伺服驱动器频繁报过流，怀疑是电机问题。
        ❌ 错误输出：{"preliminary_category":"电气",...}
        ✅ 正确输出：{"preliminary_category":"",...}

        严格以 JSON 输出，不要其他解释，不要 markdown 代码块：
        {"customer_name":"...","equipment_model":"...","equipment_sn":"...","software_version":"...","fault_phenomenon":"...","preliminary_category":"","expected_complete_date":"YYYY-MM-DD或空","impact_level":"...","device_part":"...","customer_note":"..."}""").strip()

    out = llm_chat(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": raw_text.strip()}],
        temperature=0.1, max_tokens=800,
        function_name="extract_complaint_from_text",
    )
    if not out:
        if not allow_rule_fallback:
            return {
                "source": "failed",
                "error": get_last_llm_error() or "LLM 调用失败",
            }
        return {
            "source": "rules",
            "customer_name": "",
            "equipment_model": "",
            "equipment_sn": "",
            "software_version": "",
            "fault_phenomenon": raw_text.strip()[:200],
            "preliminary_category": "",
            "expected_complete_date": "",
            "impact_level": "",
            "device_part": "",
            "customer_note": "",
        }

    data = _parse_json_loose(out)
    if not data:
        return {"source": "failed", "error": "LLM 返回格式无法解析"}

    return {
        "customer_name": str(data.get("customer_name", "")).strip(),
        "equipment_model": str(data.get("equipment_model", "")).strip(),
        "equipment_sn": str(data.get("equipment_sn", "")).strip(),
        "device_part": str(data.get("device_part", "")).strip(),
        "software_version": str(data.get("software_version", "")).strip(),
        "fault_phenomenon": str(data.get("fault_phenomenon", "")).strip(),
        "preliminary_category": str(data.get("preliminary_category", "")).strip(),
        "expected_complete_date": str(data.get("expected_complete_date", "")).strip(),
        "impact_level": str(data.get("impact_level", "")).strip(),
        "customer_note": str(data.get("customer_note", "")).strip(),
        "source": "deepseek",
    }


def diagnose_complaint(fault_phenomenon: str, equipment_model: str = "", customer_name: str = "") -> dict | None:
    """
    使用 DeepSeek 对客诉进行智能诊断，包括初步根因分析和分工建议。
    自动检索知识库相似案例作为参考，结合大模型自身经验输出诊断结果。

    Returns: dict with keys:
      - preliminary_diagnosis: 初步诊断
      - lead_engineer: 牵头工程师专业
      - participating_engineers: 参与工程师列表
      - collaboration_workflow: 协同方案
      - source: "deepseek"
    """
    if not fault_phenomenon or not fault_phenomenon.strip():
        return None

    # 0715 P0-1 FTS5升级：KB上下文检索从 search_kb(截断60字) 改为 semantic_search_kb（两阶段语义检索）
    kb_context = ""
    try:
        similar = semantic_search_kb(fault_phenomenon, top_k=5)
        if similar:
            lines = []
            for s in similar[:5]:
                rc = s.get("root_cause", "")[:80]
                sol = s.get("solution", "")[:80]
                entry = f"  - {s['title']}"
                if rc:
                    entry += f"\n    根因：{rc}"
                if sol:
                    entry += f"\n    方案：{sol}"
                lines.append(entry)
            kb_context = "\n\n📚 知识库相关历史案例：\n" + "\n".join(lines)
    except Exception:
        pass

    # [提示词优化 2026-08-03] system/user 分离，明确工程师字段为专业/部门方向，加证据推理约束
    # [提示词优化 2026-08-20] 多人协同：participating_engineers 覆盖全部所需专业方向，workflow 描述多工程师协作
    # [0923 数据校准] 人力配比与问题复杂度匹配（真实反馈：简单标准/公差类问题被强配多专业协同，准确率被评 1 分）；
    #                 排查步骤要求可执行（动作+工具+量化判据，对齐真实主管审核评估风格）
    system_msg = (
        "你是自动化设备售后智能诊断专家，"
        "具备机械、电气、工艺、光学、软件全专业背景。\n\n"
        f"{DOMAIN_CONTEXT}\n"
        "## 诊断原则\n"
        "1. **基于证据推理**：所有诊断结论必须来自故障现象或知识库案例，不得凭空臆造\n"
        "2. **优先引用知识库**：若有相似历史案例，preliminary_diagnosis 须说明「参考案例XX」或「与历史案例类似」\n"
        "3. **无案例时说明依据**：纯靠大模型知识时，须在 preliminary_diagnosis 中注明「根据故障现象判断」\n"
        "4. **工程师字段为专业/部门方向**：lead_engineer 和 participating_engineers "
        "填写专业或部门方向（如「机械工程师」「电气工程师」「工艺工程师」「光学工程师」「软件工程师」），"
        "不得填写真实人名，实际人员由审批人指派\n"
        "5. **人力配比与问题复杂度匹配**：participating_engineers 不得机械凑数——\n"
        "   简单问题（装配标准缺失/公差干涉/单部件更换/工艺文件更新/参数调整）只需牵头专业一个方向，"
        "participating_engineers 输出空列表 []；\n"
        "   仅当故障确需跨专业排查（如发热需电气测量+机械查负载、通信报警需软件查日志+电气查链路）才配 2~3 个方向；\n"
        "   不得为凑数而添加与排查无关的专业\n"
        "6. **排查步骤可执行**：workflow 中的步骤要具体到动作、工具与量化判据"
        "（如：红外测温枪定位最高温点；测三相直流电阻对比出厂值偏差<5%；示波器查三相电流波形是否对称），"
        "不写「联合分析」「共同确认」等空话\n\n"
        "## 示例 1 — 简单标准类（单专业，无需协同）\n"
        "故障：上视相机安装方向接头朝内朝外无标准，现场两种都存在\n"
        '输出：{"preliminary_diagnosis":"根据故障现象判断，属装配标准缺失而非部件损坏，'
        '按现行工艺文件统一安装方向即可；若该相机为特殊定制则按特殊装配处理",'
        '"lead_engineer":"机械工程师","participating_engineers":[],'
        '"collaboration_workflow":"机械工程师查现行工艺文件确认标准方向；无标准则提出工艺文件更新项，'
        '输出统一装配说明并交装配与售后执行。"}\n\n'
        "## 示例 2 — 复杂跨域类（需协同）\n"
        "故障：X轴工作台运行发热明显，已更换动力线缆、优化驱动参数均无好转，需确认是否直线电机动子损坏\n"
        '输出：{"preliminary_diagnosis":"根据故障现象判断，发热集中在X轴运动系统，'
        '线缆与驱动参数因素已排除，需用测温与电气测量区分电机本体故障与负载过大",'
        '"lead_engineer":"电气工程师","participating_engineers":["机械工程师"],'
        '"collaboration_workflow":"电气工程师红外测温定位最高温点，测电机三相直流电阻对比出厂值（偏差应<5%），'
        '示波器查三相电流波形对称性；机械工程师并行盘动X轴查阻力、检查导轨与光栅尺安装；'
        '空载与带载对比温升速率确认负载来源后给出对策。"}\n\n'
        "## 输出字段规范\n"
        "- preliminary_diagnosis：≤120字，须包含推断依据（引用案例或说明判断来源）\n"
        "- lead_engineer：主导排查的专业方向，单个字符串，如「机械工程师」\n"
        "- participating_engineers：确需协同的其他专业方向列表（简单问题输出 []，复杂问题 2~3 个）\n"
        "- collaboration_workflow：≤150字，按时序描述排查步骤，每步含具体动作/工具/判据\n\n"
        "严格以 JSON 输出，不要其他解释：\n"
        '{"preliminary_diagnosis":"...","lead_engineer":"...","participating_engineers":[...],"collaboration_workflow":"..."}'
    )
    user_msg = (
        f"📋 客诉信息\n"
        f"客户名称：{customer_name or '未知'}\n"
        f"设备型号：{equipment_model or '未知'}\n"
        f"故障现象：{fault_phenomenon}"
        f"{kb_context}"
    )
    out = llm_chat(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": user_msg}],
        temperature=0.2, max_tokens=800,
        function_name="diagnose_complaint",
    )
    if not out:
        return None
    data = _parse_json_loose(out)
    if not data:
        return None
    return {
        "preliminary_diagnosis": str(data.get("preliminary_diagnosis", "")).strip()[:120],
        "lead_engineer": str(data.get("lead_engineer", "")).strip(),
        "participating_engineers": data.get("participating_engineers", []),
        "collaboration_workflow": str(data.get("collaboration_workflow", "")).strip()[:150],
        "source": "deepseek",
    }


# ── LLM 接口（已接入 DeepSeek） ───────────────────
def llm_suggest(prompt: str) -> str | None:
    """
    通用 LLM 文本补全接口（已接入 DeepSeek）。
    供未来扩展的场景调用；当前三个具体场景使用上方的 classify_complaint_llm /
    extract_knowledge_llm。失败返回 None。
    """
    return llm_chat([{"role": "user", "content": prompt}], temperature=0.3, function_name="llm_suggest")


# 0728 客户邮件草稿生成 — DeepSeek 撰写正式客户沟通邮件
def generate_email_draft(
    fault_phenomenon: str,
    solution: str = "",
    customer_name: str = "",
    equipment_model: str = "",
    complaint_no: str = "",
) -> dict | None:
    """使用 DeepSeek 生成发送给客户的邮件草稿。

    成功返回 {"subject": str, "body": str, "source": "deepseek"}；
    失败返回 None（调用方处理降级 UI 提示）。
    """
    if not fault_phenomenon or not fault_phenomenon.strip():
        return None

    # [提示词优化 2026-08-03] system/user 分离，补充无solution示例，强化禁工单号规则，明确正文字数
    has_solution = bool(solution and solution.strip())
    system_msg = textwrap.dedent("""\
        你是自动化设备售后客服邮件撰写助手，负责起草发给客户的正式沟通邮件。

        ## 邮件格式规范
        - subject：≤30字，包含设备型号和故障类型；绝对不得出现工单编号（如 CP-XXXXX 格式）
          示例：「关于 EQ-200 设备贴片平台异响问题的处理进展」
        - body：300~500字为宜，段落分明，结构依次为：
          1. 称呼：尊敬的[客户名] 您好；客户名为编号/代号时（如 HB-A-421）写「尊敬的 HB-A-421 负责人 您好」，不得把编号当公司名直接称呼
          2. 感谢语
          3. 故障现象说明：用自己的话一句话概括（≤40字），不得整段照抄原始故障描述
          4. 处理结果或当前进展（见下方规则）
          5. 下一步建议或请客户确认
          6. 结尾固定为：如有任何疑问，请随时与我们联系。署名「售后服务中心」
        - 语气：正式、专业、礼貌；body 中不得出现任何工单编号

        ## 无解决方案时正文第4段的写法
        解决方案为空时，写：「目前我司工程师正在积极跟进处理，预计将于近期给出解决方案，届时将第一时间与您沟通。」
        禁止使用"处理中"、"待后续更新"、"暂无"等空洞占位语。

        ## 示例 1 — 有解决方案
        客户：示例客户A  设备：EQ-200  故障：贴片平台移动时发出周期性异响  解决方案：更换磨损导轨并重新校准精度
        输出：
        {"subject":"关于 EQ-200 设备贴片平台异响问题的处理进展","body":"尊敬的示例客户A 您好：\\n\\n感谢贵司一直以来的信任与支持。关于贵司反馈的 EQ-200 设备贴片平台异响问题，经我司工程师现场排查，确认故障原因为线性导轨磨损。工程师已更换磨损部件并重新校准运动平台精度，目前设备已恢复正常运行。\\n\\n请您安排操作人员试用确认，如有任何问题请随时与我们联系。\\n\\n祝商祺！\\n售后服务中心"}

        ## 示例 2 — 无解决方案（跟进中）
        客户：示例客户B  设备：EQ-300A  故障：视觉对位失败，更换光源无效  解决方案：（空）
        输出：
        {"subject":"关于 EQ-300A 设备视觉对位故障的处理进展","body":"尊敬的示例客户B 您好：\\n\\n感谢贵司一直以来的信任与支持。关于贵司反馈的 EQ-300A 设备视觉对位失败问题，我司已安排工程师进行排查，初步判断与相机系统相关。目前我司工程师正在积极跟进处理，预计将于近期给出解决方案，届时将第一时间与您沟通。\\n\\n如有任何疑问，请随时与我们联系。\\n\\n祝商祺！\\n售后服务中心"}

        严格以 JSON 输出，不要其他解释，不要 markdown 代码块：
        {"subject":"...","body":"..."}""").strip()

    user_msg = (
        f"客户名称：{customer_name or '客户'}\n"
        f"设备型号：{equipment_model or '未知'}\n"
        f"故障现象：{fault_phenomenon.strip()}\n"
        f"解决方案：{solution.strip() if has_solution else '（暂无）'}\n"
        f"注意：主题中不要出现工单编号（{complaint_no or '无'}）"
    )
    out = llm_chat(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": user_msg}],
        temperature=0.3, max_tokens=800,
        function_name="generate_email_draft",
    )
    if not out:
        return None

    data = _parse_json_loose(out)
    if not data or "subject" not in data or "body" not in data:
        return None

    return {
        "subject": str(data.get("subject", "")).strip(),
        "body": str(data.get("body", "")).strip(),
        "source": "deepseek",
    }


# 0716 案例搜索方案推荐——复用 semantic_search_kb 检索 + LLM 总结
def case_search_solution(fault_phenomenon: str, equipment_model: str = "",
                         fault_category: str = "") -> dict | None:
    """
    从知识库检索相似案例，结合 LLM 自身知识给出解决方案。
    返回 {"summary": str, "source_type": str, "source_cases": list, "cited_kb_ids": list}
    source_type: "kb_and_llm"（检索到案例）或 "llm_only"（无案例，纯 LLM 知识）
    cited_kb_ids: 生成内容中实际引用且通过候选集校验的 KB ID 列表（按出现顺序去重；
    0908 引用可溯源——docs/05 §4.4"无引用不下结论"红线最小落地：句末 [KB#n] 标注 +
    生成后校验，编造引用剔除并记日志）
    """
    if not fault_phenomenon or not fault_phenomenon.strip():
        return None

    # Stage 1: 知识库检索（同类优先）
    source_cases = []
    try:
        source_cases = semantic_search_kb(fault_phenomenon.strip(), top_k=5,
                                           fault_category=fault_category)
    except Exception:
        pass

    has_cases = bool(source_cases)

    # Stage 2: 构建 prompt
    case_lines = []
    if has_cases:
        for c in source_cases:
            parts = [f"[KB#{c.get('id')}] {c.get('title', '')}"]
            if c.get("fault_category"):
                parts.append(f"分类：{c['fault_category']}")
            if c.get("equipment_model"):
                parts.append(f"机型：{c['equipment_model']}")
            if c.get("root_cause"):
                parts.append(f"根因：{c['root_cause'][:120]}")
            if c.get("solution"):
                parts.append(f"方案：{c['solution'][:150]}")
            if c.get("lesson_learned"):
                parts.append(f"教训：{c['lesson_learned'][:100]}")
            case_lines.append(" | ".join(parts))

    source_label = "相似历史案例 + LLM 知识库" if has_cases else "仅基于 LLM 自身知识"
    cases_text = "\n\n".join(case_lines) if case_lines else "（未检索到相似历史案例）"

    # [提示词优化 2026-08-03] system/user 分离，明确案例引用规范、步骤字数、无案例标注
    # 0908 引用可溯源：候选行带真实 KB 编号，结论句末标注 [KB#n]，返回前校验防编造
    cite_rule = (
        "- 引用案例时必须说明相似点，并在对应结论/步骤句末标注来源编号，"
        "格式：「……（与本故障同属XX子系统/均表现为XX）[KB#3]」；"
        "多个来源连标 [KB#3][KB#5]；**只能引用候选列表中存在的编号，禁止编造**；"
        "无案例依据的通用经验不标注编号\n"
        if has_cases else
        "- 第一行标注后注明：「以下建议基于模型知识，无历史案例支持」\n"
    )
    system_msg = (
        "你是自动化设备售后技术支持专家，具备10年以上现场服务经验。\n"
        f"{DOMAIN_CONTEXT}\n"
        "根据故障信息和知识库案例，为现场工程师提供结构化的解决方案建议。\n\n"
        "## 输出规范\n"
        "1. 第一行必须是来源标注，格式固定为：> 📌 方案来源：**{source_label}**\n"
        f"{cite_rule}"
        "2. 排查步骤必须编号，由简到繁排列；每步≤30字且**可执行**——写清动作与工具"
        "（万用表/示波器/红外测温枪/钳形表/兆欧表等），能定量的给量化判据"
        "（如：测三相直流电阻，对比出厂值偏差应<5%），不写「检查是否正常」这类无动作的空话\n"
        "3. 纯文本输出，不要 Markdown 语法（不用 ** # ``` 等），用清晰标题和分段即可\n"
        "4. 四个章节必须完整输出，不得省略\n\n"
        "## 输出结构\n"
        "> 📌 方案来源：（来源标签）\n\n"
        "1. 常见根因\n"
        "列出2~5个最可能的根本原因，按概率从高到低排序\n\n"
        "2. 排查步骤\n"
        "编号列出由简到繁的排查流程，每步≤30字\n\n"
        "3. 解决方案建议\n"
        "针对每种可能根因给出具体处理方案\n\n"
        "4. 经验教训\n"
        "可复用的经验总结和需要避免的常见坑"
    ).replace("{source_label}", source_label)

    user_msg = (
        f"设备型号：{equipment_model or '未知'}\n"
        f"故障分类：{fault_category or '未知'}\n"
        f"故障现象：{fault_phenomenon.strip()}\n\n"
        f"相似历史案例（知识库检索，已编号）：\n{cases_text}"
    )

    # Stage 3: LLM 调用
    result = llm_chat(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": user_msg}],
        temperature=0.3,
        max_tokens=1200,
        function_name="case_search_solution",
    )
    if not result:
        return None

    # 0908 引用可溯源：校验 [KB#n] 只允许指向候选集内条目（AI 输出按不可信输入处理，
    # 编造引用剔除并记日志），同时收集实际引用的 KB ID 供前端/统计使用
    valid_ids = {c.get("id") for c in source_cases if c.get("id") is not None}
    cited_kb_ids: list = []

    def _validate_cite(m) -> str:
        kid = int(m.group(1))
        if kid in valid_ids:
            if kid not in cited_kb_ids:
                cited_kb_ids.append(kid)
            return m.group(0)
        print(f"[case_search_solution] 剔除编造引用 [KB#{kid}]（不在候选集内）", flush=True)
        return ""

    if has_cases:
        result = re.sub(r"\[KB#(\d+)\]", _validate_cite, result)

    return {
        "summary": result,
        "source_type": "kb_and_llm" if has_cases else "llm_only",
        "source_cases": source_cases,
        "cited_kb_ids": cited_kb_ids,
    }


# 0728 AI 自排查推荐 — 面向客户的简单安全排查建议（最多5条）
def suggest_customer_self_check(fault_phenomenon: str, equipment_model: str = "") -> dict | None:
    """生成面向产线操作工的客户自排查清单。

    检索相似历史案例作为参考，用 LLM 生成最多 5 条简单安全的排查建议。
    返回 {"suggestions": list[str], "summary": str} 或 None（LLM 失败时）。
    """
    if not fault_phenomenon or not fault_phenomenon.strip():
        return None

    # Stage 1: FTS5 检索相似案例作为参考
    kb_context = "（未检索到相似历史案例）"
    try:
        similar = find_similar_cases(fault_phenomenon.strip(), top_k=3)
        if similar:
            lines = []
            for i, c in enumerate(similar, 1):
                parts = [f"案例{i}：{c.get('title', '')}"]
                if c.get("root_cause"):
                    parts.append(f"根因：{c['root_cause'][:80]}")
                lines.append(" | ".join(parts))
            kb_context = "\n".join(lines)
    except Exception:
        pass

    # [提示词优化 2026-08-03] system/user 分离，安全规则移至system最前，强化字数约束和内部故障直接拒排
    system_msg = (
        "你是自动化设备售后客户自排查指导专家。\n"
        "目标用户是产线操作工（非技术人员），语言必须通俗易懂，禁止使用专业术语。\n\n"
        "【绝对禁止 — 任何理由均不得绕过】\n"
        "1. 禁止建议任何带电操作（测量电压、拆接线、触碰电气元件）\n"
        "2. 禁止建议拆卸防护罩、安全门、联锁装置\n"
        "3. 禁止建议接触高温部件（加热模块、热压头、固化灯等）\n"
        "4. 禁止建议操作高压气路或液压系统\n"
        "5. 只允许建议：目视检查、简单手动操作（拧螺丝、插拔接头、清洁表面、重启设备）\n\n"
        "## 内部故障处理规则\n"
        "若故障明显属于设备内部电气/结构问题（如驱动器报警、电机故障、电路板异常、内部机械损坏），\n"
        "suggestions 只输出一条：「建议立即联系售后工程师，此类故障客户无法自行排查，请勿自行拆机」\n"
        "summary 输出：「设备内部故障，需工程师处理」\n\n"
        "## 格式规范\n"
        "- suggestions：1~5条，从最简单（目视检查）到稍复杂排列，每条≤25字；"
        "用疑问句/检查项形式表述（如「吸头是否堵塞」「传感器表面是否有灰尘遮挡」），便于客户逐条对照回答\n"
        "- 优先列客户容易疏忽的问题：急停未复位、线缆松动、耗材用完、参数被误改等\n"
        "- summary：一句话，≤20字，说明最可能的排查方向\n"
        "- 严格 JSON 输出，不要 Markdown 代码块：{\"suggestions\": [...], \"summary\": \"...\"}"
    )
    user_msg = (
        f"设备型号：{equipment_model or '未知'}\n"
        f"故障现象：{fault_phenomenon.strip()}\n\n"
        f"历史相似案例（供参考）：\n{kb_context}"
    )

    # Stage 3: LLM 调用
    result_text = llm_chat(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": user_msg}],
        temperature=0.3,
        max_tokens=500,
        function_name="suggest_customer_self_check",
    )
    if not result_text:
        return None

    parsed = _parse_json_loose(result_text)
    if not parsed:
        return None

    suggestions = parsed.get("suggestions", [])
    if isinstance(suggestions, list):
        suggestions = [s for s in suggestions if isinstance(s, str) and s.strip()]
    else:
        suggestions = []

    return {
        "suggestions": suggestions[:5],
        "summary": parsed.get("summary", ""),
    }


# 0728 AI 排期建议 — 基于工程师历史+类别统计+负载（0820 支持多人协同 team_size）
def suggest_schedule(engineer_name: str, fault_category: str = "",
                     estimated_hours: float = 0,
                     engineer_avg: float = 0, engineer_closed: int = 0,
                     category_avg: float = 0, category_closed: int = 0,
                     active_count: int = 0, team_size: int = 0) -> dict | None:
    """生成排期工时建议。样本量不足时用规则公式兜底，不走 LLM。
    team_size >= 2 时提示词按团队总工时（并行提速 + 沟通协调开销）给出建议。

    返回 {"recommended_hours": float, "reasoning": str, "confidence": str, "source": str}
    """
    if not engineer_name or not engineer_name.strip():
        return None

    # 小样本兜底：工程师和类别历史数据都不够时，用规则公式
    MIN_SAMPLES = 3
    if engineer_closed < MIN_SAMPLES and category_closed < MIN_SAMPLES:
        # 规则公式：有主管预估用预估，否则默认 8h
        base = estimated_hours if estimated_hours > 0 else 8.0
        # 当前负载每个 +2h 缓冲
        buffer = active_count * 2
        return {
            "recommended_hours": round(base + buffer, 1),
            "reasoning": f"该工程师历史关闭工单仅 {engineer_closed} 个，同类别工单仅 {category_closed} 个，样本不足，"
                         f"基于{'主管预估' if estimated_hours > 0 else '默认值'} {base}h + 负载缓冲 {buffer}h 计算。",
            "confidence": "低",
            "source": "rules",
        }

    # [提示词优化 2026-08-03] system/user 分离，加 breakdown 求和约束，max_tokens 300→500
    system_msg = (
        "你是自动化设备售后服务的资深排程专家。\n"
        "你拥有 10 年以上 自动化设备 现场服务管理经验，深谙各故障类别的排查难度、典型工时范围，\n"
        "以及如何根据工程师历史表现、当前负载和故障特征做出合理的排期决策。\n\n"
        "=== 排期分析框架（决策方法论） ===\n\n"
        "按以下四个维度综合分析，给出排期工时建议：\n\n"
        "【维度一：故障类别复杂度基准（权重 40%）】（0923 按真实历史工时校准）\n"
        "  - 机械类：结构件返修/工装选型/装配标准类 1~10h；涉及设计变更或批量装配改造 8~24h\n"
        "  - 电气类：电路/伺服/驱动/IO 诊断 2~16h；需现场长期复现排查的取上限\n"
        "  - 光学类：视觉系统、光源/相机/镜头校准，典型工时 3~12h\n"
        "  - 工艺类：键合参数、温度曲线、压力调试、工艺文件更新，典型工时 1~10h\n"
        "  - 软件类：参数配置/小型开关/命名修正 1~8h；功能开发/逻辑优化类需求多为 8~120h"
        "（需求明确取下限，涉及底层逻辑或需长期复现测试取上限），不得按远程小问题一刀切\n"
        "  - 其他类：默认 4h，根据现象灵活调整\n\n"
        "【维度二：工程师历史绩效（权重 30%）】\n"
        "  - 个人均值 < 同类均值×0.8：效率高，可适当压低工时\n"
        "  - 个人均值在同类均值×0.8~1.3 之间：接近均值，使用基准线\n"
        "  - 个人均值 > 同类均值×1.3：效率偏低，需加缓冲并在 reasoning 中备注\n"
        "  - 工程师历史样本 < 5 个时，该维度权重降为 15%，更多依赖类别基准\n\n"
        "【维度三：当前负载缓冲（权重 20%）】\n"
        "  - 0 个处理中：无缓冲\n"
        "  - 1~2 个：每个 +1.5h\n"
        "  - 3~5 个：每个 +3h（reasoning 中说明排队风险）\n"
        "  - 6 个及以上：每个 +5h（reasoning 中明确标注严重积压风险）\n\n"
        "【维度四：主管预估锚点（权重 10%）】\n"
        "  - 主管预估在模型计算 ±30% 内：优先采纳主管预估\n"
        "  - 偏差 > 30% 或 > 2h：使用模型结果，reasoning 中说明原因\n"
        "  - 主管未填写：该维度权重并入维度一（维度一升至 50%）\n\n"
        "=== 硬性约束 ===\n"
        "  - recommended_hours：1.0~40.0h，保留一位小数，必须是单值不得给区间\n"
        "  - breakdown 求和约束：category_base + engineer_adjustment + load_buffer 必须等于 final，\n"
        "    engineer_adjustment 可以是负数（效率高时），load_buffer 可以为 0\n"
        "  - reasoning：3~5句，必须引用输入中的具体数字（如「该工程师历史均值X.Xh」）\n\n"
        "=== 多人协同场景（输入含「协同处理人数」时生效）===\n"
        "  - recommended_hours 为**团队总工时**：多人并行可缩短关键路径（乘以并行系数 0.7~0.85），\n"
        "    但须加上沟通协调与接口衔接开销（每人约 +0.5~1h）\n"
        "  - reasoning 中须明确说明并行提速与协调开销的取舍计算\n\n"
        "=== 置信度判定 ===\n"
        "  - 高：工程师>=10 且同类>=10，各维度数据一致\n"
        "  - 中：工程师5~9 或同类5~9，趋势可判断\n"
        "  - 低：工程师3~4 且同类3~4，或多维度数据矛盾\n\n"
        "严格 JSON 输出，不要 Markdown 代码块：\n"
        '{"recommended_hours": 数字, "reasoning": "3~5句分析", "confidence": "高/中/低", '
        '"breakdown": {"category_base": 数字, "engineer_adjustment": 数字, "load_buffer": 数字, "final": 数字}}'
    )
    user_msg = (
        f"目标工程师：{engineer_name}\n"
        f"故障类别：{fault_category or '未知'}\n"
        f"部门主管预估工时：{estimated_hours}h"
        f"{'（未填写，该维度权重并入故障类别基准）' if estimated_hours <= 0 else ''}\n"
        f"{f'协同处理人数：{team_size} 人（多人协同场景）\n' if team_size >= 2 else ''}\n"
        f"【工程师历史数据】\n"
        f"- 已关闭工单数：{engineer_closed} 个\n"
        f"- 历史平均全程耗时：{engineer_avg}h\n\n"
        f"【同类别历史数据】\n"
        f"- {fault_category or '该类别'}已关闭工单数：{category_closed} 个\n"
        f"- 同类平均全程耗时：{category_avg}h\n\n"
        f"【当前负载】\n"
        f"- 该工程师当前处理中工单数：{active_count} 个"
    )

    result_text = llm_chat(
        [{"role": "system", "content": system_msg},
         {"role": "user", "content": user_msg}],
        temperature=0.2,
        max_tokens=500,
        function_name="suggest_schedule",
    )
    if not result_text:
        return None

    parsed = _parse_json_loose(result_text)
    if not parsed:
        return None

    try:
        hours = float(parsed.get("recommended_hours", 8))
    except (ValueError, TypeError):
        hours = 8.0

    return {
        "recommended_hours": round(hours, 1),
        "reasoning": parsed.get("reasoning", ""),
        "confidence": parsed.get("confidence", "中"),
        "source": "deepseek",
    }
