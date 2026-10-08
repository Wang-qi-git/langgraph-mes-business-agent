# AGENTS.md — AI 助手上下文入口

> 任何 AI 助手（Claude / GPT / Cursor / Copilot）接手本项目前，**必读本文**。
> 人类读者可从 README.md 开始。

---

## 1. 项目是什么

**langgraph-mes-business-agent** — 面向制造业 MES 领域的业务分析 Agent。

从"规范文档问答"升级为"能对接实时 MES 系统的业务智能体"。

- 定位：作品集项目，具备生产级工程完整度
- 语言：中文
- 领域：制造业 MES
- **当前版本：v5.4**（CI/CD + 完整监控 + 容器化 + 单元测试）

---

## 2. 核心架构

### 容器化部署（V5.2+）
┌─────────────────────────────────────────────────────────────────┐
│ Docker Compose Network │
│ │
│ ┌──────────────┐ HTTP ┌──────────────┐ HTTP ┌────────┐ │
│ │ Streamlit │ ───────> │ FastAPI │ ──────> │ Mock │ │
│ │ (前端:8501) │ │ (后端:8000) │ │MES:8001│ │
│ └──────────────┘ └──────┬───────┘ └────────┘ │
│ │ /metrics │
│ ↓ │
│ ┌─────────────────┐ │
│ │ Prometheus │ │
│ │ (:9090) │ │
│ └────────┬────────┘ │
│ ↓ │
│ ┌─────────────────┐ │
│ │ Grafana │ │
│ │ (:3000) │ │
│ └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

### 六节点工作流（深度模式）
Planner → Tool Decide → Tool Exec → Task Execute → Reflect ↺ → Summary
↑______________________________________|
(need_more_info=true 时回退)


### 双模式设计

| 模式 | 检索策略 | 输出 | 首字 | 总耗时 |
|------|---------|------|------|--------|
| ⚡ 快速 | 向量 Top-2（跳过 Reranker）+ MES 意图识别 | 100~250 字 | 0.05s（缓存）| **1~3s** |
| 🔍 深度 | 粗召回 10 + Reranker 精排 3 | 结构化长报告 | 40s | **40~60s** |

---

## 3. 代码结构
langgraph-mes-business-agent/
├── AGENTS.md # ⭐ 本文件（AI 上下文）
├── README.md # 对外门面
├── Dockerfile # 多阶段构建（backend/frontend/mock-mes）
├── docker-compose.yml # 5 容器编排
├── prometheus.yml # Prometheus 抓取配置
├── .dockerignore / .coveragerc / pytest.ini
├── .env / .env.example
├── .gitignore
│
├── graph_agent_skeleton.py # ⭐ Agent 核心（748 行）
├── api_server.py # ⭐ FastAPI 后端
├── streamlit_app.py # ⭐ Streamlit 前端
├── auth.py # JWT 认证
├── session_store.py # 会话存储（SQLite）
├── mes_tools.py # MES 工具封装（6 个查询）
├── mock_mes_api.py # Mock MES 系统（端口 8001）
│
├── eval_agent.py # LangSmith 评测
├── peek_scores.py # 快速拉评测分数
├── build_kb.py # 知识库构建
├── download_reranker.py # Reranker 模型下载
├── requirements.txt
│
├── tests/ # ⭐ 单元测试（15 tests）
│ ├── conftest.py
│ ├── test_auth.py
│ ├── test_session_store.py
│ └── test_mes_tools.py
│
├── .github/workflows/test.yml # ⭐ CI/CD
├── md_docs/ / pdf_docs/ # 知识库源
├── chroma_db/ / models/ # gitignore
├── screenshots/
└── docs/CHANGELOG.md # V1→V5.4 演进

---

## 4. 技术栈

| 层 | 选型 |
|----|------|
| 编排 | LangGraph |
| LLM | DeepSeek (`deepseek-chat`) |
| 向量库 | Chroma |
| Embedding | `BAAI/bge-small-zh-v1.5` |
| Reranker | `bge-reranker-v2-m3` |
| 联网 | Tavily |
| 会话存储 | SQLite |
| 认证 | JWT (pyjwt) |
| 缓存 | cachetools.LRUCache |
| 监控 | Prometheus + Grafana |
| 评测 | LangSmith |
| 后端 | FastAPI + uvicorn |
| 前端 | Streamlit |
| 容器化 | Docker Compose |
| 测试 | pytest + pytest-cov + pytest-asyncio |
| CI | GitHub Actions |

---

## 5. 关键设计机制

### 5.1 双层拒答
- Layer 1（Prompt）：Planner 判断领域，输出 `REJECT:`
- Layer 2（代码）：检测到 `REJECT:` 直接返回固定话术，**不调 LLM**
- 效果：拒答用例 Token ↓95%、耗时 ↓90%

### 5.2 BOM 版本前置守卫
- `check_bom_version_guard()` 用正则 + `md_docs/` 扫描出的版本索引
- 命中不存在的版本 → 直接塞拦截话术，跳过向量检索
- 效果：case_018 从 0.67/0.33 → **1.0/1.0**
- **核心教训**：确定性问题用代码，概率性问题用 LLM

### 5.3 模型预热 + 双进程架构
- FastAPI 启动时 `_warmup_models()` 加载 Embedding + Reranker + 真跑一次检索
- Streamlit 只做 UI，通过 HTTP 调用后端
- 解决 Streamlit rerun 重加载问题

### 5.4 快速模式跳过 Reranker
- bge-reranker-v2-m3 是 568M 参数大模型，CPU 上精排 10 对需 30s
- 快速模式直接向量 Top-2 → **36s → 1s**
- **不要"好心"把 Reranker 加回快速模式**

### 5.5 多会话隔离
- `session_store.py` 基于 SQLite
- 前端 URL 带 `?sid=xxx`，刷新不丢
- 后端 `needs_context()` 判断是否拼接历史

### 5.6 JWT 认证 + 权限矩阵

| 角色 | 权限 |
|------|------|
| operator | chroma_search + MES 工具 |
| supervisor | + tavily_search |
| admin | 全部 |

**登录**：`POST /auth/login` 返回 Token；后续请求带 `Authorization: Bearer xxx`
**角色**：从 JWT 解析，**不再从前端传 `user_role`**

### 5.7 MES 实时工具集成
- `mes_tools.py` 封装 6 个工具：工单、库存、设备、低库存清单、报警设备、质量问题
- `mock_mes_api.py` 模拟真实 MES（端口 8001）
- **快速模式**：正则识别意图（零延迟）
- **深度模式**：LLM 决策工具

### 5.8 检索缓存
- `cachetools.LRUCache`（maxsize=500）
- Key：`md5(user_role::query)`
- **不同角色不共享缓存**（权限不同）

### 5.9 日志轮转
- `_rotate_if_needed()`：超过 10MB 自动轮转，保留 3 份
- 作用于 `trace.jsonl` 和 `audit.log`

### 5.10 Reranker 三级降级

| 级别 | 触发条件 | 行为 |
|------|---------|------|
| 一级 | 正常 | 精排 Top-3 |
| 二级 | 推理异常 | 向量 Top-K |
| 三级 | 加载失败 | 永久标记 `_RERANKER_FAILED=True` |

### 5.11 Reflection 收敛
- 分支 A：达到最大循环 + 全完成 → 直接出报告
- 分支 B：达到最大循环 + 有 pending → 强制收尾
- **分支 C**：所有任务已完成且有输出 → 快速收敛
- 分支 D：正常 → 调 LLM 反思

### 5.12 Prometheus 业务指标

| 指标 | 说明 |
|------|------|
| `mes_cache_hits_total` / `mes_cache_misses_total` | 缓存命中/未命中 |
| `mes_quick_mode_requests_total{cached}` | 快速模式请求（区分命中）|
| `mes_tool_calls_total{tool,role,status}` | 工具调用分布 |
| `mes_tool_calls_external_total{tool,status}` | MES 工具调用成功/失败 |
| `mes_llm_tokens_total{kind}` | LLM Token 消耗 |

---

## 6. 当前版本状态（V5.4）

| 版本 | 关键优化 | answer AVG | rag AVG | 快速模式 |
|------|---------|-----------|---------|---------|
| V1 | 初始版本 | 0.80 | 0.38 | 55s |
| V2 | 双层拒答 | 0.93 | 0.38 | 55s |
| V3 | metadata + 知识库扩充 | 0.92 | 0.61 | 55s |
| V4.0 | 双模式 + BOM 守卫 + 预热 | **0.96** | **0.67** | **1.06s** |
| V4.1 | 多会话隔离 | — | — | — |
| V4.2 | MES 实时集成 | — | — | — |
| V4.3 | 缓存 + 日志轮转 + 降级 | — | — | — |
| V5.0 | JWT + 会话绑定 + MES 意图识别 | — | — | — |
| V5.1 | Prometheus + Grafana | — | — | — |
| V5.2 | 全栈容器化 | — | — | 3.09s |
| V5.3 | 单元测试（15 tests） | — | — | — |
| **V5.4** | **CI/CD** | — | — | — |

**详细改动见 `docs/CHANGELOG.md`**

---

## 7. 已知问题 / 待办

- [ ] `mes_tools.py` 测试覆盖率 46% → 目标 75%
- [ ] Grafana 仪表盘在容器重建后丢失（需重新导入）
- [ ] CI 中未加 Docker 构建验证
- [ ] 无多副本水平扩展（单机 Docker Compose）
- [ ] 真实 MES 对接（当前为 Mock）

---

## 8. 开发约定（重要！踩过的坑）

1. **不要在 `planner_node` 里加硬规则**——曾因"对象不存在直接拒答"规则过度泛化，全量 20 用例从 0.90 掉到 0.70
2. **确定性问题用代码拦截，概率性问题用 LLM**——BOM V99 案例
3. **改动后必须跑全量 20 用例**——只看 5 个会漏掉回归
4. **不要在 Streamlit 里加载模型**——每次 rerun 都重加载，必须放 FastAPI 后端
5. **修改 `.gitignore` 时注意换行**——`sessions.db` 和 `models/` 曾粘成一行导致规则失效
6. **不要用 `localhost`，用 `127.0.0.1`**——Windows 上 localhost 优先解析 IPv6 会超时
7. **Docker 容器里 `127.0.0.1` 不是宿主机**——要用容器服务名（如 `mock-mes`）
8. **模型缓存要挂载到容器**——`C:\Users\<用户名>\.cache\huggingface` → `/root/.cache/huggingface`
9. **容器内强制离线**——环境变量 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`
10. **Docker 数据放 D 盘**——C 盘空间不足会导致 containerd 崩溃
11. **`pip install xxx>=版本` 要加引号**——否则 Windows 会把 `>` 当重定向符号
12. **跑测试用 `python -m pytest`**——避免 PATH 里系统 pytest 抢执行
13. **CI 要装全依赖**——`auth.py` 依赖 `fastapi`，漏了会导致 CI 失败但本地能过

---

## 9. 常用命令

### 方式 1: Docker 一键启动（推荐）

```bash
# 启动 5 个容器
docker-compose up -d

# 查看状态
docker-compose ps

# 看日志
docker-compose logs backend --tail 50

# 重建单个服务（改了代码后）
docker-compose up -d --build backend

# 停止所有容器
docker-compose down

# 完全清理（含数据卷）
docker-compose down -v

方式 2: 本地开发启动
# 终端 A: 后端
uvicorn api_server:api --host 0.0.0.0 --port 8000

# 终端 B: 前端
streamlit run streamlit_app.py

# 终端 C: Mock MES
uvicorn mock_mes_api:mes_api --host 0.0.0.0 --port 8001

方式 3: 测试 + 评测
# 单元测试（必须加 python -m）
python -m pytest -v

# 带覆盖率报告
python -m pytest --cov=. --cov-report=html

# 全量评测（LangSmith，约 20 分钟）
python eval_agent.py

# 只跑指定用例
set FILTER_CASES=case_018
python eval_agent.py

# 快速拉评测分数（不开浏览器）
python peek_scores.py

方式 4: 本地调试
# 直接跑 Agent（改 user_query 后测）
python graph_agent_skeleton.py

# 查看活跃会话
python -c "import session_store; print(session_store.list_sessions())"

10. 环境变量（.env）

DEEPSEEK_API_KEY=sk-xxx
TAVILY_API_KEY=tvly-xxx
LANGCHAIN_API_KEY=lsv2_pt_xxx
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_TRACING_V2=true
JWT_SECRET=your-secret-here

Docker 额外环境变量（在 docker-compose.yml 里）：
AUTO_APPROVE_SEARCH=true
MES_BASE=http://mock-mes:8001
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1

11. 访问入口
服务	地址	账号
🏭 前端	http://localhost:8501	admin / admin123
📡 后端 API	http://localhost:8000/docs	—
🏭 Mock MES	http://localhost:8001	—
📊 Prometheus	http://localhost:9090	—
📈 Grafana	http://localhost:3000	admin / admin123

测试账号：

operator / op123（车间操作员，无联网权限）
supervisor / sup123（班组长，可联网）
admin / admin123（管理员，全权限）

2. 进一步阅读
项目介绍：README.md
版本演进：docs/CHANGELOG.md
效果截图：screenshots/
评测数据：LangSmith 平台

13. 给 AI 助手的特别提示
修改 graph_agent_skeleton.py 前，先看第 8 节"开发约定"
涉及 Prompt 改动，务必提醒用户跑全量评测
BOM 拦截逻辑在 check_bom_version_guard()，不要误删
快速模式的 quick_answer 故意跳过 Reranker，不要"好心"加回去
本地模型路径：./models/bge-reranker-v2-m3
会话数据：sessions.db（SQLite，已 gitignore）
容器构建修改：改完 Dockerfile 或 docker-compose.yml 后，要 docker-compose up -d --build <service> 重建
CI 失败排查：本地过 CI 挂，通常是依赖遗漏（本地装了 CI 没装）
不要 commit：.env、*.db、models/、chroma_db/、venv/、htmlcov/、.pytest_cache/

---

## 🚦 保存后

```cmd
git add AGENTS.md
git commit -m "docs: update AGENTS.md to V5.4 with all new capabilities"
git push

