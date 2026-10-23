# 客诉工单管理系统

> 设备售后客诉工单全流程管理平台：AI 从任意文本提取工单字段，包含优先级判定、故障分类、知识库混合检索与数据分析。FastAPI + Vue 3 + PostgreSQL。

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14%2B-4169E1?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

覆盖 **客诉受理 → AI 结构化 → 派工与进度跟踪 → 解决方案登记 → 客户确认 → 知识沉淀 → 数据分析** 的完整闭环。

> 本仓库为脱敏示例版：人员、客户、设备型号、密钥与业务数据均为虚构或占位内容，可直接替换后使用。

## 功能特性

### 受理与流转

- **AI 辅助受理**：粘贴邮件 / 聊天记录 / 工程师笔记等任意格式文本，自动提取客户、设备、故障现象、影响等级等结构化工单字段
- **工单流转**：看板 + 列表双视图，支持优先级、状态、进度更新、解决方案登记与客户确认
- **批量导入**：Excel 批量导入历史工单，带字段校验与去重
- **工单交接**：换人跟进时保留责任链与历史留痕

### AI 辅助（9 类角色提示词）

| 场景 | 作用 |
|---|---|
| 客诉录入 | 从自由文本抽取结构化工单字段并预填 |
| 优先级判定 | 结合产线瓶颈属性给出优先级与影响评估 |
| 故障分类 | 按子系统归类，便于统计与派工 |
| 知识库录入 | 把处理记录整理成可检索的 KB 条目 |
| 语义检索 | 自然语言查询历史案例 |
| 智能诊断 | 结合相似案例给出排查方向 |
| 邮件起草 | 生成发给客户的正式沟通邮件 |
| 客户自排查 | 生成客户侧可自行执行的自排查指引 |
| 服务排程 | 多工单上门排期建议 |

### 知识库混合检索

这是本项目最核心的工程部分：

- **关键词通道**：PostgreSQL `tsvector` 生成列 + `tsquery` 匹配，按相关度排序
- **向量通道**：pgvector 存储 embedding，余弦召回语义相近条目
- **RRF 融合**：两路结果用 Reciprocal Rank Fusion 合并（`score = Σ 1/(k + rank)`），向量通道缺席时自动退化为纯关键词
- **降级容错**：未配置 embedding 服务时退回关键词模式；`tsquery` 语法异常时降级 `LIKE` 并转义通配符，避免误命中全表
- **可回放的回归种子集**：把"检索效果"做成可度量的回归指标，改检索逻辑后跑一遍 seed 就能看出有没有退化

### 分析与通知

- **数据分析**：KPI、趋势、分类分布、SUS 满意度问卷、系统评估
- **通知**：站内通知（WebSocket 实时推送）+ 钉钉工作通知 + 邮件
- **导出**：按条件导出 Excel
- **权限**：角色体系（管理员 / 主管 / 工程师等）+ JWT 鉴权 + 部门数据范围

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.10+ / FastAPI / Uvicorn |
| 数据访问 | `psycopg` + `psycopg_pool`（原生 SQL + 连接池，无 ORM） |
| 数据库 | PostgreSQL（`tsvector` 全文检索 + pgvector 向量检索） |
| 前端 | Vue 3 / TypeScript / Vite / Pinia / Tailwind CSS |
| AI | DeepSeek（工单理解、分类、判定、草稿）+ embedding 服务（硅基流动等 OpenAI 兼容接口） |

## 快速开始

跑起来需要三步：**准备 PostgreSQL → 装后端依赖 → 构建前端**。

### 1. 准备数据库

```sql
CREATE ROLE demoapp WITH LOGIN PASSWORD '改成你的密码';
CREATE DATABASE complaint_demo OWNER demoapp ENCODING 'UTF8';
```

首次启动会自动建表。若要用向量检索，目标库还需启用 `pgvector` 扩展（未启用时自动降级为纯关键词检索）。

### 2. 后端

```bash
cd backend
cp .env.example .env      # 填写密钥与数据库连接
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8506
```

### 3. 前端

```bash
cd frontend
npm install
npm run build             # 产物输出 frontend/dist，由后端直接托管
```

> 也可以用 `npm run dev` 起 Vite 开发服务器。
> **后端不依赖 `dist` 也能启动**（`main.py` 有目录判断），只是没有页面。

### 一键方式

Windows 下双击项目根目录的 `start.bat`：自动创建持久化 Python 环境、安装依赖、`npm install` + 构建，然后启动服务。**但它不会替你装 PostgreSQL**，第 1 步仍需手工完成。

```
系统访问: http://localhost:8506
API 文档: http://localhost:8506/docs
```

首次启动仅创建 `admin` 账号（初始密码 `admin123`），登录后请立即修改。

## 配置

复制 `backend/.env.example` 为 `backend/.env` 并填写：

| 变量 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API Key，**必填**（AI 能力依赖） |
| `DATABASE_URL` | PostgreSQL 连接串 |
| `JWT_SECRET_KEY` | 会话签名密钥，**务必改为随机值** |
| `EMBEDDING_PROVIDER` / `EMBEDDING_API_BASE` / `EMBEDDING_API_KEY` / `EMBEDDING_API_MODEL` | 向量检索配置；不填则检索以纯关键词模式运行 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` | 邮件通知（选填，不填则降级为仅生成草稿） |
| `DINGTALK_APP_KEY` / `DINGTALK_APP_SECRET` / `DINGTALK_AGENT_ID` | 钉钉工作通知（选填） |

> `backend/.env` 已被 `.gitignore` 忽略，仓库里只提供 `.env.example`。

## 目录结构

```
backend/
  api/             REST 接口（complaints / ai / knowledge / analytics / export / auth ...）
  services/        业务服务层（工单 / 知识库 / 导出 / 通知 / 交接 ...）
  ai_engine/       LLM 调用、角色提示词、故障分类、混合检索与 RRF 融合
  schemas/         Pydantic 模型
  data/            建表与初始化、领域词库、检索种子集
  scripts/         迁移与运维脚本（含 SQLite → PostgreSQL）
  eval/            评测与回归
frontend/
  src/
    views/         页面（受理 / 看板 / 详情 / 知识库 / 分析 / 导出 / 用户管理 ...）
    components/    组件
    stores/        Pinia 状态
    api/           接口封装
    utils/         工具函数
start.bat          一键启动脚本
```

## 定制说明

- `backend/data/domain_dict.txt` 是 jieba 自定义词库（`词语 词频 词性`），按实际业务术语增删即可，**改完无需重建索引**——检索时对查询与库内字段现场分词，两侧一致
- `backend/data/retrieval_seed.jsonl` 是检索回归种子集，一行一个查询；改完可用 `python backend/scripts/replay_retrieval_seed.py` 回放验证
- 数据库迁移脚本在 `backend/scripts/`，包含 SQLite → PostgreSQL 迁移工具
- 工单编号格式、领域词库、机型枚举都集中在代码常量里，替换业务时优先改这些位置

## License

[MIT](LICENSE)
