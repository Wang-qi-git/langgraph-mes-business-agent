---

name: mes-business-agent

description: MES 业务分析 Agent。支持工单、库存、设备、报警、质量查询，以及 BOM 版本守卫、双层拒答、六节点 Reflection 工作流。

version: 5.4

---



# MES Business Agent



面向制造业 MES 领域的 AI 业务分析助手，从"规范文档问答"升级为"对接实时 MES 系统的业务智能体"。



## 能力边界



| 能力 | 说明 |

|------|------|

| 工单查询 | 按工单号查状态、进度、数量 |

| 库存查询 | 按产品/物料编码查库存 |

| 设备状态 | 按设备编号查运行状态、开动率 |

| 报警查询 | 按设备/全厂查报警明细 |

| 质量数据 | 按工单查合格率、不合格数 |

| 知识检索 | RAG 混合检索 MES 术语、SOP |

| BOM 版本守卫 | 代码级前置校验，防幻觉 |

| 双层拒答 | Prompt + 代码短路，省 Token |



## 工作流



### 快速模式（1-3 秒）

意图识别 → 向量 Top-2 → 单次 LLM → 返回



### 深度模式（40-60 秒）

六节点 Reflection：

Planner → Tool Decide → Tool Exec → Task Execute

↑ ↓

└────────── Reflect ←────────────────┘

↓

Summary





## 工具集（`mes\_tools.py`）



1\. `query\_workorder(workorder\_no)` — 工单查询

2\. `query\_inventory(code)` — 库存查询

3\. `query\_equipment(equipment\_id)` — 设备状态

4\. `query\_alarm(equipment\_id)` — 报警查询

5\. `query\_quality(workorder\_no)` — 质量数据

6\. `query\_low\_inventory()` — 低库存清单



## 资源



\- 知识库源文件：`md\_docs/`、`pdf\_docs/`

\- 构建脚本：`build\_kb.py`

\- 向量库：`chroma\_db/`

\- Reranker：`models/bge-reranker-v2-m3`



## 关键设计机制



### 双层拒答（省 Token 95%）

\- Layer 1（Prompt）：Planner 输出 `REJECT:`

\- Layer 2（代码）：命中 `REJECT:` 直接短路，\*\*不调 LLM\*\*



### BOM 版本前置守卫（防幻觉）

\- `check\_bom\_version\_guard()` 正则 + 知识库比对

\- 命中不存在版本 → \*\*直接拦截，跳过向量检索\*\*

\- 案例：case\_018 从 0.67 → 1.0



### Reranker 三级降级

1\. 正常 → 精排 Top-3

2\. 推理异常 → 退回向量 Top-K

3\. 加载失败 → 永久标记不可用



### 会话隔离

\- `session\_store.py` 基于 SQLite

\- 前端 URL 带 `?sid=xxx`，刷新不丢



### JWT + 三角色权限



| 角色 | 权限 |

|------|------|

| operator | chroma\_search + MES 工具 |

| supervisor | + tavily\_search |

| admin | 全部 |



## 技术栈



LangGraph / DeepSeek / Chroma / BGE / Tavily / FastAPI / Streamlit / JWT / SQLite / Prometheus / Grafana / Docker Compose / pytest / GitHub Actions



## 环境入口



| 服务 | 地址 |

|------|------|

| 前端 | http://localhost:8501 |

| 后端 API | http://localhost:8000/docs |

| Mock MES | http://localhost:8001 |

| Prometheus | http://localhost:9090 |

| Grafana | http://localhost:3000 |



## 版本演进



V1 → V5.4：answer AVG 0.80→0.96，rag AVG 0.38→0.67，快速模式 55s→1.06s



## 开发约定（踩坑记录）



1\. 不要在 `planner\_node` 里加硬规则

2\. 确定性问题用代码拦截，概率性问题用 LLM

3\. 改动后必跑全量 20 用例

4\. 不要在 Streamlit 里加载模型

5\. 修改 `.gitignore` 时注意换行

6\. 不要用 `localhost`，用 `127.0.0.1`

7\. Docker 容器内 `127.0.0.1` 不是宿主机

8\. 模型缓存要挂载到容器

9\. 容器内强制离线

10\. Docker 数据放 D 盘

11\. `pip install xxx>=版本` 要加引号

12\. 跑测试用 `python -m pytest`

13\. CI 要装全依赖





