\# AGENTS.md — AI 助手上下文入口



> 任何 AI 助手（Claude / GPT / Cursor / Copilot）接手本项目前，\*\*必读本文\*\*。

> 人类读者可从 README.md 开始。



\---



\## 1. 项目是什么



\*\*langgraph-mes-business-agent\*\* — 面向制造业 MES 领域的业务分析 Agent。



把 8D 报告规范、SPC 控制、工艺手册、报工规范、BOM 管理规则等文档查询，

从"人工翻阅"升级为"智能问答"。



\- 定位：作品集项目，兼有生产级设计思路

\- 语言：中文

\- 领域：制造业 MES

\- 当前版本：\*\*v4.1\*\*（多会话隔离）



\---



\## 2. 核心架构



\### 双进程架构

┌─────────────────────┐ HTTP ┌─────────────────────┐

│ Streamlit (前端) │ ──────────────────> │ FastAPI (后端) │

│ - 纯 UI，秒开 │ │ - 启动时预热模型 │

│ - URL 带 session\_id │ <────────────────── │ - 常驻进程 │

│ - 通过 HTTP 调用 │ JSON + 历史 │ - SQLite 存会话 │

└─────────────────────┘ └─────────────────────┘





\### 六节点工作流（深度模式）

Planner → Tool Decide → Tool Exec → Task Execute → Reflect ↺ → Summary

↑\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_\_|

(need\_more\_info=true 时回退)



\### 双模式设计



| 模式 | 检索策略 | 输出 | 首字 | 总耗时 |

|------|---------|------|------|--------|

| ⚡ 快速 | 向量 Top-2（跳过 Reranker） | 100\~150 字要点 | 0.74s | \*\*1.06s\*\* |

| 🔍 深度 | 粗召回 10 + Reranker 精排 3 | 结构化长报告 | 40s | \*\*44s\*\* |



\---



\## 3. 代码结构

langgraph-mes-business-agent/

├── AGENTS.md # ⭐ AI 上下文入口（本文件）

├── README.md # 对外门面

├── .env / .env.example

├── .gitignore

│

├── graph\_agent\_skeleton.py # ⭐ Agent 核心（六节点 + 双模式 + 预热）

├── api\_server.py # ⭐ FastAPI 后端（常驻进程）

├── streamlit\_app.py # ⭐ Streamlit 前端（纯 UI）

├── session\_store.py # ⭐ 会话存储（SQLite）

│

├── eval\_agent.py # LangSmith 批量评测

├── peek\_scores.py # 快速拉评测分数

├── build\_kb.py # 知识库构建（PDF/MD → Chroma）

├── download\_reranker.py # Reranker 模型下载（一次性）

├── requirements.txt

│

├── md\_docs/ # Markdown 规范文档（知识库源）

├── pdf\_docs/ # PDF 规范文档

├── chroma\_db/ # 向量库（gitignore）

├── models/ # 本地模型（gitignore）

├── screenshots/ # 项目截图

└── docs/

├── CHANGELOG.md # V1→V4.1 版本演进

└── ...





\---



\## 4. 技术栈



| 层 | 选型 | 说明 |

|----|------|------|

| 编排 | \*\*LangGraph\*\* | StateGraph + TypedDict State |

| LLM | \*\*DeepSeek\*\* (`deepseek-chat`) | OpenAI 兼容接口 |

| 向量库 | \*\*Chroma\*\* | 本地持久化 |

| Embedding | `BAAI/bge-small-zh-v1.5` | 本地加载 |

| Reranker | `bge-reranker-v2-m3` | 本地加载，仅深度模式用 |

| 联网搜索 | \*\*Tavily\*\* | 需 HITL 人工确认 |

| 会话存储 | \*\*SQLite\*\* | 轻量、零依赖 |

| 评测 | \*\*LangSmith\*\* | `evaluate` API + LLM-as-Judge |

| 后端 | \*\*FastAPI\*\* + uvicorn | 常驻服务 |

| 前端 | \*\*Streamlit\*\* | 纯 UI |



\---



\## 5. 关键设计机制



\### 5.1 双层拒答

\- \*\*Layer 1（Prompt）\*\*：Planner 判断是否属 MES 领域，否则输出 `REJECT:`

\- \*\*Layer 2（代码）\*\*：Task Execute 检测 `REJECT:` 后\*\*直接返回固定话术，不调 LLM\*\*

\- 效果：拒答用例 Token ↓95%（15000 → 780），耗时 ↓90%（30s → 3s）



\### 5.2 BOM 版本前置守卫

\- `check\_bom\_version\_guard()` 用正则提取 query 里的版本号

\- 与 `md\_docs/` 扫描出的真实版本对比，不存在则直接拦截

\- 效果：case\_018 从 0.67/0.33 → \*\*1.0/1.0\*\*，延迟 53.81s → \*\*9.27s\*\*

\- \*\*核心教训\*\*：确定性问题用代码拦截，概率性问题用 LLM



\### 5.3 模型预热

\- `\_warmup\_models()` 在模块加载时执行

\- 加载 Embedding + Chroma + Reranker，并\*\*真跑一次检索\*\*

\- 效果：用户请求全部享受稳态性能



\### 5.4 快速模式跳过 Reranker

\- 快速模式用向量 Top-2，\*\*不调用 Reranker\*\*

\- 效果：单次调用 36s → \*\*1.06s\*\*

\- 权衡：召回质量略降，但覆盖 90%+ 场景



\### 5.5 多会话隔离

\- `session\_store.py` 基于 SQLite

\- 前端 URL 带 `?sid=xxx`，刷新不丢

\- 后端按需拼接历史上下文（`needs\_context()` 判断）

\- 多标签独立、一键清空、新会话



\### 5.6 权限矩阵



| 角色 | 权限 |

|------|------|

| operator | `chroma\_search` |

| supervisor | `chroma\_search`, `tavily\_search` |

| admin | 全部 |



权限不足时\*\*拒绝执行并把任务标记为 completed\*\*（防死循环），审计写入 `audit.log`。



\### 5.7 Reflection 收敛

\- 分支 A：达到最大循环 + 全完成 → 直接出报告

\- 分支 B：达到最大循环 + 有 pending → 强制收尾

\- \*\*分支 C\*\*：所有任务已完成且有输出 → \*\*快速收敛\*\*（V4 新增）

\- 分支 D：正常情况 → 调 LLM 反思



\---



\## 6. 当前版本状态（V4.1）



| 版本 | 关键优化 | answer AVG | rag AVG | 稳态延迟 |

|------|----------|-----------|---------|---------|

| V1 | 初始版本 | 0.80 | 0.38 | 55s |

| V2 | 双层拒答机制 | 0.93 | 0.38 | 55s |

| V3 | metadata 修复 + 知识库扩充 | 0.92 | 0.61 | 55s |

| \*\*V4.0\*\* | \*\*BOM 守卫 + 模型预热 + 双模式架构\*\* | \*\*0.96\*\* | \*\*0.67\*\* | \*\*1.06s（快速）\*\* |

| \*\*V4.1\*\* | \*\*多会话隔离（SQLite）\*\* | — | — | — |



\---



\## 7. 已知问题 / 待办



\- \[ ] \*\*首次启动需 50s 预热\*\*（本地模型加载成本，一次性）

\- \[ ] \*\*深度模式仍耗时 40\~60s\*\*（Reflection 循环 + Reranker 精排的必然代价）

\- \[ ] \*\*无 Prometheus 监控指标暴露\*\*

\- \[ ] \*\*无多用户认证\*\*（当前 API 无鉴权）

\- \[ ] \*\*单机部署\*\*：不支持多副本水平扩展



\---



\## 8. 开发约定（踩过的坑）



1\. \*\*不要在 `planner\_node` 里加硬规则\*\*——曾因"对象不存在直接拒答"规则过度泛化，全量 20 用例平均分从 0.90 掉到 0.70

2\. \*\*确定性问题用代码拦截，概率性问题用 LLM\*\*——BOM V99 案例的核心教训

3\. \*\*改动后必须跑全量 20 用例\*\*——只看 5 个会漏掉回归

4\. \*\*不要在 Streamlit 里加载模型\*\*——每次 rerun 都会重加载，必须放 FastAPI 后端

5\. \*\*修改 `.gitignore` 时注意换行\*\*——`sessions.db` 和 `models/` 曾粘成一行，导致规则失效

6\. \*\*不要用 `localhost`，用 `127.0.0.1`\*\*——Windows 上 `localhost` 优先解析 IPv6，会超时



\---



\## 9. 常用命令



```bash

\# 启动后端（终端 A，等 50s 预热）

uvicorn api\_server:api --host 0.0.0.0 --port 8000



\# 启动前端（终端 B，秒开）

streamlit run streamlit\_app.py



\# 本地调试

python graph\_agent\_skeleton.py



\# 全量评测（约 20 分钟）

python eval\_agent.py



\# 只跑指定用例

set FILTER\_CASES=case\_018

python eval\_agent.py



\# 拉最近评测分数（不开浏览器）

python peek\_scores.py



\# 查看活跃会话

python -c "import session\_store; print(session\_store.list\_sessions())"



10\. 环境变量（.env）

DEEPSEEK\_API\_KEY=sk-xxx

TAVILY\_API\_KEY=tvly-xxx

LANGCHAIN\_API\_KEY=lsv2\_pt\_xxx

LANGCHAIN\_ENDPOINT=https://api.smith.langchain.com

LANGCHAIN\_TRACING\_V2=true



11\. 进一步阅读

架构细节：README.md



版本演进：docs/CHANGELOG.md



效果演示：screenshots/



评测数据：LangSmith 平台



12\. 给 AI 助手的特别提示

修改 graph\_agent\_skeleton.py 前，先看第 8 节"开发约定"



涉及 Prompt 改动，务必提醒用户跑全量评测



BOM 拦截逻辑在 check\_bom\_version\_guard()，不要误删



快速模式的 quick\_answer 故意跳过 Reranker，不要"好心"加回去



本地模型路径：./models/bge-reranker-v2-m3



会话数据在 sessions.db（SQLite），已被 gitignore





\---



