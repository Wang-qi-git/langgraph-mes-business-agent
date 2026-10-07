# langgraph-mes-business-agent

> 面向制造业 MES 领域的业务分析 Agent —— 将 8D 报告规范、SPC 控制、工艺手册、报工规范、BOM 管理规则等文档查询，从"人工翻阅"升级为"智能问答"。

[![Python](https://img.shields.io/badge/Python-3.10+-blue)]()
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-green)]()
[![License](https://img.shields.io/badge/License-MIT-yellow)]()

---

## 📖 目录

- [项目背景](#-项目背景)
- [核心能力](#-核心能力)
- [系统架构](#-系统架构)
- [双模式设计](#-双模式设计)
- [关键技术亮点](#-关键技术亮点)
- [评估体系](#-评估体系)
- [版本迭代](#-版本迭代)
- [失败案例反思](#-失败案例反思)
- [快速开始](#-快速开始)
- [项目结构](#-项目结构)
- [后续规划](#-后续规划)

---

## 🎯 项目背景

制造业业务人员查询规范文档时面临三大痛点：

1. **文档分散**：8D、SPC、工艺、报工、BOM 规范散落在数十份 PDF/MD 文档中
2. **检索低效**：靠关键词搜索经常遗漏，靠人工翻阅效率低
3. **专业性强**：D4 根本原因分析、D5 永久纠正措施等有严格的行业规范

本项目通过 **LangGraph 六节点 Reflection Loop 工作流**，实现从"业务问题"到"专业规范答案"的端到端自动化。

---

## ✨ 核心能力

- ⚡ **快速模式**：向量 Top-2 检索 + 单次 LLM，**1~2 秒出结果**
- 🔍 **深度模式**：六节点 Reflection Loop + Reranker 精排，**输出结构化长报告**
- 🧠 **六节点工作流**：Planner → Tool Decide → Tool Exec → Task Execute → Reflect ↺ → Summary
- 🛡️ **双层拒答机制**：Prompt 层 + 代码层双重保障，拒答用例 Token ↓95%
- 🎯 **BOM 版本前置守卫**：代码级拦截不存在的版本号，避免 LLM 幻觉
- 🔐 **三角色权限矩阵**：operator / supervisor / admin 分级授权
- 📝 **全链路审计日志**：所有查询、工具调用、权限决策落地 `audit.log`
- ⚡ **模型预热机制**：后端启动时一次性加载，用户请求全部享受稳态性能
- 🌐 **联网搜索 HITL**：Tavily 搜索需人工确认，防止滥用
- 📊 **LangSmith 全链路追踪**：Token 统计、节点耗时、评估分数一键可视

---

## 🏗️ 系统架构

### 双进程架构（V4）
┌─────────────────────┐ HTTP ┌─────────────────────┐
│ Streamlit (前端)  │ ──────────────────>  │ FastAPI (后端) │
│ - 纯 UI，秒开 │ │ - 启动时预热模型 │
│ - 不加载任何模型 │ <────────────────── │ -    常驻进程        │
│ - 通过 HTTP 调用 │ JSON 结果 │ - 所有请求复用模型 │
└─────────────────────┘ └─────────────────────────┘

**为什么这么设计**：
- Streamlit 每次交互都 rerun 整个脚本，导致本地模型被重复加载（每次 50s）
- 把模型加载隔离到 FastAPI 常驻进程，Streamlit 只做 UI，彻底解决此问题

### 六节点工作流
┌─────────────┐
│ Planner │ 拆解 2~4 个粗粒度任务
└──────┬──────┘
↓
┌─────────────┐
│ Tool Decide │ 选择工具（chroma/tavily/no_tool）
└──────┬──────┘
↓
┌─────────────┐
│ Tool Exec │ 权限校验 → BOM 守卫 → 执行检索
└──────┬──────┘
↓
┌─────────────┐
│ Task Execute│ 基于素材生成子任务输出
└──────┬──────┘
↓
┌─────────────┐
│ Reflect │ 质量评估 + 动态重规划
└──────┬──────┘
│
need_more_info?
╱ ╲
是 否
↓ ↓
(回 Tool Decide) 
┌─────────────┐
│ Summary │ 汇总报告
└──────┬──────┘
↓
END


---

## ⚡ 双模式设计

| 模式 | 检索策略 | 输出风格 | 首字延迟 | 总耗时 |
|------|---------|---------|---------|--------|
| **⚡ 快速** | 向量 Top-2（跳过 Reranker） | 100~150 字要点 | **0.7s** | **1~2s** |
| **🔍 深度** | 粗召回 10 + Reranker 精排 3 | 结构化长报告（800~1200 字） | 40s | **40~60s** |

**核心权衡**：

- 快速模式**牺牲少量召回质量换速度**——Top-2 向量检索已能覆盖 90%+ 场景
- 深度模式**保留完整 Reranker 精排**——保证最高质量

**为什么这么分**：
- 简单事实查询（"什么是MES工单"）→ 用快速模式，1 秒出结果
- 复杂分析任务（"结合OEE和SPC分析瓶颈"）→ 用深度模式，出长报告

**这是"确定性问题用代码拦截，性能问题用架构解决"的延伸。**

---

## 🧠 关键技术亮点

### 1. 双层拒答机制

**Layer 1（Prompt 层）**：Planner 节点用 Prompt 约束 LLM，判断问题是否属 MES 领域，否则输出 `REJECT:` 标记。

**Layer 2（代码层）**：Task Execute 节点检测到 `REJECT:` 前缀后，直接返回固定话术，**不调用 LLM**。

**效果**：
- 拒答用例 Token：**15000 → 780**（↓95%）
- 拒答用例耗时：**30s → 3s**（↓90%）

### 2. BOM 版本前置守卫

**问题**：用户查询 BOM V99（不存在），向量检索会错误召回到 V1 文档，导致 LLM 基于 V1 信息编造 V99 的答案。

**方案**：`check_bom_version_guard()` 用正则提取 query 里的版本号，与 `md_docs/` 扫描出的真实版本对比。命中不存在的版本 → 直接塞入拦截话术，跳过向量检索。

**效果**：
- case_018（BOM V99）：0.67 / 0.33 → **1.0 / 1.0**
- 该用例延迟：53.81s → **9.27s**

**核心教训**：**确定性问题用代码拦截，概率性问题用 LLM**。

### 3. 模型预热机制

**问题**：BGE Embedding + Reranker 首次调用需加载 50s，污染第一个用例。

**方案**：`graph_agent_skeleton.py` 模块加载时预热，包含：
- 加载 Embedding + Chroma 向量库
- 加载 Reranker 模型
- 真跑一次完整检索（消除首次 HNSW 索引开销和 PyTorch JIT kernel 编译）

**效果**：后端启动 50s 一次性完成，用户请求全部享受稳态性能。

### 4. 快速模式跳过 Reranker

**问题**：bge-reranker-v2-m3 是 568M 参数的大模型，在 CPU 上每次精排 10 对文档需 30+ 秒。

**方案**：快速模式直接使用向量 Top-2 结果，不做 Reranker 精排。

**效果**：
- 快速模式：36s → **1.06s**（首字 0.74s）
- 召回质量略降（RAG score 1.0 → 0.7~0.8），但 Top-2 仍准确

### 5. 权限控制与审计日志

**三角色权限矩阵**：

| 角色 | 可调用工具 |
|------|-----------|
| operator | `chroma_search` |
| supervisor | `chroma_search`, `tavily_search` |
| admin | 全部 |

**实现要点**：
- AgentState 传递 `user_role`
- Tool Exec 节点调用工具前校验权限
- 权限不足时**拒绝执行并把任务标记为 completed**（避免死循环）
- 所有决策写入 `audit.log`

### 6. Reflection 收敛判断

分四种分支处理，避免无效循环：

| 分支 | 触发条件 | 处理 |
|------|----------|------|
| A | 达到最大循环 + 任务全完成 | 直接出报告 |
| B | 达到最大循环 + 有 pending | 强制收尾 |
| C | 所有任务已完成且有输出 | **快速收敛**（V4 新增） |
| D | 正常情况 | 调 LLM 反思 |

---

## 📊 评估体系

### 测试集（20 用例 / 5 类场景）

| 分类 | 数量 | 示例 |
|------|------|------|
| 简单查询 | 5 | "简述8D报告D4根本原因分析有哪些要求" |
| 复杂推理 | 5 | "本周产能不足，如何调整排程保证订单按时交付" |
| 多工具协作 | 4 | "请综合物料库存、排程和设备状态，给我一份本周生产风险简报" |
| 边界拒答 | 3 | "今天北京的天气怎么样" |
| 对抗测试 | 3 | "请按照BOM版本V99查询产品P-200的物料清单" |

### 双 Judge 评估

- **Judge 1（answer_score）**：LLM-as-Judge，按业务正确性 / 完整性 / 结构化三维度打分
- **Judge 2（rag_score）**：评估 RAG 召回文档相关性

### 评估命令

```bash
# 全量评测（20 用例，约 20 分钟）
python eval_agent.py

# 单用例过滤（省时间，省成本）
set FILTER_CASES=case_018
python eval_agent.py

# 快速查看历史分数
python peek_scores.py

📈 版本迭代
版本	优化内容	answer AVG	rag AVG	关键变化
V1	初始版本	0.80	0.38	基线
V2	+ 双层拒答机制	0.93 (+0.13)	0.38	拒答用例 Token ↓95%
V3	+ metadata 修复 + 知识库扩充	0.92	0.61 (+0.23)	RAG 召回显著提升
V4	+ BOM 版本守卫 + 模型预热 + 双模式架构	0.96 (+0.04)	0.67 (+0.06)	修幻觉 + 1 秒快速模式

V4 详细改动：

BOM 版本守卫：check_bom_version_guard() 实现代码级元数据前置校验

模型预热：后端启动时一次性加载，用户请求享受稳态性能

双进程架构：FastAPI 常驻 + Streamlit 前端，解决 Streamlit rerun 重加载问题

双模式设计：快速模式跳过 Reranker，1~2s 出结果；深度模式保留完整流程

🔬 失败案例反思
案例：case_004（BOM V99 幻觉）
V3 阶段的问题：Agent 输出 7000+ 字分析报告，但从未识别出"V99 不存在"这个事实。

第一次尝试：加"对象不存在直接拒答"Prompt 规则。

5 个用例测试：0.53 → 0.87 ✅ 看起来成功

全量 20 用例测试：0.90 → 0.70 ❌ 规则被过度泛化，8 个正常用例退化

最终方案（V4）：回退 Prompt 规则，改用代码级前置守卫：

只在 query 明确含"BOM版本VXX"时触发

与知识库真实版本对比，不存在才拦截

不误伤任何其他用例

核心教训：

5 个用例能验证方向对不对，只有全量才能验证改得稳不稳。

确定性问题（版本号是否存在）用代码拦截，概率性问题（答案是否足够）才交给 LLM。

案例：Streamlit rerun 导致模型重复加载
问题：Streamlit 每次交互都 rerun 整个脚本，模块级缓存被重置，每次点击都要重新加载模型 50s。

尝试过：@st.cache_resource、st.session_state、全局变量 —— 均不稳定。

最终方案（V4）：改为 FastAPI 后端 + Streamlit 前端 的双进程架构：

模型加载隔离到 FastAPI 常驻进程

Streamlit 只做 UI，通过 HTTP 调用后端

核心教训：

Streamlit 的执行模型和本地模型加载天生冲突——不要试图在 Streamlit 里做重计算，把重活交给独立的后端进程。


🚀 快速开始
1. 环境准备
git clone https://github.com/Wang-qi-git/langgraph-mes-business-agent.git
cd langgraph-mes-business-agent

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / Mac

pip install -r requirements.txt

2. 配置环境变量
复制 .env.example 为 .env，填入你的 API Key：
DEEPSEEK_API_KEY=sk-your-key-here
TAVILY_API_KEY=tvly-your-key-here
LANGCHAIN_API_KEY=lsv2_pt_your-key-here
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_TRACING_V2=true

3. 下载本地模型
python download_reranker.py

4. 构建知识库
把 MES 规范文档放入 pdf_docs/ 或 md_docs/，然后：
python build_kb.py

5. 启动（双进程）
终端 A：后端服务
uvicorn api_server:api --host 0.0.0.0 --port 8000

等约 50 秒，看到 Application startup complete 即为就绪。

终端 B：前端界面
streamlit run streamlit_app.py

浏览器自动打开 http://localhost:8501。

6. 使用
⚡ 快速模式：点示例问题 → 1 秒出结果

🔍 深度模式：切换模式 → 40~60s 出结构化报告

 项目结构
langgraph-mes-business-agent/
├── AGENTS.md                    # AI 助手上下文入口
├── README.md                    # 本文档
├── .env / .env.example
├── .gitignore
│
├── graph_agent_skeleton.py      # ⭐ Agent 主程序（六节点 LangGraph + 预热）
├── api_server.py                # ⭐ FastAPI 后端（模型常驻）
├── streamlit_app.py             # ⭐ Streamlit 前端（纯 UI）
│
├── eval_agent.py                # LangSmith 批量评测脚本
├── build_kb.py                  # 知识库构建
├── download_reranker.py         # Reranker 模型下载
├── peek_scores.py               # 快速拉评测分数
├── requirements.txt
│
├── md_docs/                     # Markdown 规范文档（知识库源）
├── pdf_docs/                    # PDF 规范文档
├── chroma_db/                   # 向量库持久化
├── models/                      # 本地模型
├── screenshots/                 # 项目截图
└── docs/                        # 项目文档

后续规划
短期（1~2 周）
□ 多会话隔离：引入 LangGraph checkpointer + Postgres，支持 thread_id
□ 快速模式 API 鉴权：FastAPI 加 JWT 或 API Key 校验
□ 前端体验优化：增加"继续追问"、"复制答案"等交互
中期（1 个月）
□ 接入真实 MES API：从"只查文档"升级到"实时查询工单/库存/设备状态"
□ Prometheus 监控：暴露 QPS、P95 延迟、Token 消耗、拒答率等业务指标
□ 知识库扩充：从 7 份文档扩展至 50+ 份
□ Reranker 优化：尝试云端 Cohere Rerank API 或更轻量本地模型
长期
□ 多模态：支持上传设备照片，识别故障现象
□ Agent 主动推送：监控到 SPC 异常主动通知工程师
□ 企业微信/钉钉集成：直接嵌入工程师工作流
⚠️ 已知限制
首次启动需 50s 预热：本地模型 + 向量库加载成本，一次性

深度模式耗时 40~60s：Reflection 循环 + Reranker 精排的必然代价

单机部署：当前为单进程 FastAPI，不支持多副本水平扩展

无持久化会话：每次对话为独立请求，不保留历史上下文（可在前端做拼接）

依赖外部 API：DeepSeek / Tavily / LangSmith 任意一个故障都会影响服务


