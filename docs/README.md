\# 基于LangGraph+RAG的制造业MES业务分析Agent

> 作品集项目完整文档

> 版本：V1.0

> 编制日期：2026‑09‑04



\---



\# 第一部分：PRD 产品需求文档



\## 1 产品概述

\### 1.1 产品背景

制造业MES售前、方案设计场景，需要基于行业PDF知识库，针对生产痛点（紧急插单、OEE损失、报工风险、物料齐套等）输出结构化业务分析报告。

传统方式：人工翻阅PDF资料，手动整理风险点、分级、应对方案，耗时长，输出质量依赖人员经验。

本Agent目标：输入制造业业务问题，自动完成任务拆解‑知识库检索‑草稿生成‑反思校验‑多轮迭代‑输出完整Markdown业务报告。



\### 1.2 产品目标

1\. 基于本地PDF制造业知识库，完成RAG知识检索；

2\. 通过LangGraph实现多节点工作流，支持反思、多轮迭代优化输出质量；

3\. 输出标准化Markdown报告，包含风险分级、表格化建议，可直接用于售前方案、内部分析；

4\. 向量库、Embedding模型本地运行，仅文本生成调用大模型API；

5\. 可扩展：后续可增加联网搜索、网页前端界面、导出文件功能。



\### 1.3 非目标（本次版本不做）

1\. 不实现本地大模型推理，文本生成依赖DeepSeek远程API；

2\. 不做WebUI界面，当前为命令行程序；

3\. 不支持多文件动态上传，PDF需要提前构建向量库；

4\. 不做用户账号、权限管理。



\### 1.4 术语定义

|术语|说明|

|---|---|

|Agent智能体|LangGraph编排的多节点工作流，具备规划‑工具调用‑反思迭代能力|

|RAG|检索增强生成，从本地Chroma向量库检索PDF片段作为参考上下文|

|Embedding|BGE‑small‑zh‑v1.5，本地CPU完成文本向量化|

|Chroma|本地向量数据库，持久化存储向量化后的文档片段|

|planner\_node|任务拆解节点，把用户问题拆解成执行计划|

|tool\_decide\_node|工具决策节点，判断是否调用知识库检索工具|

|tool\_exec\_node|工具执行节点，执行RAG向量检索|

|task\_execute\_node|业务任务执行节点，基于上下文输出分析草稿|

|reflect\_node|反思校验节点，校验草稿完整性，支持触发重新检索迭代|

|summary\_node|报告汇总节点，润色生成最终正式Markdown报告|



\## 2 需求清单

\### 2.1 功能需求

\#### FR‑001 向量库构建能力

\- 输入本地PDF制造业文档；

\- 使用BGE‑small‑zh‑v1.5做文本向量化；

\- 文本递归分割，chunk\_size=800，overlap=120；

\- 向量持久化保存至本地文件夹`./chroma\_db`；

\- 控制台输出构建完成提示。



\#### FR‑002 Agent工作流执行

1\. 接收用户业务查询（示例：MES系统紧急插单风险分析）；

2\. planner\_node：LLM生成任务拆解执行计划；

3\. tool\_decide\_node：决策调用RAG检索工具；

4\. tool\_exec\_node：从Chroma向量库检索top4相关文档片段；

5\. task\_execute\_node：结合计划+检索上下文，输出业务分析草稿；

6\. reflect\_node：LLM校验草稿完整性、业务覆盖度、风险点完备性；

7\. 支持闭环迭代：反思发现不足，回到tool\_decide\_node重新检索迭代；

8\. 校验合格进入summary\_node，输出完整格式化Markdown报告；

9\. 控制台打印每个节点执行日志，便于调试观察流程。



\#### FR‑003 报告输出规范

\- 输出Markdown格式完整报告；

\- 结构：概述、直接风险、连锁影响、专项问题、风险分级表格、缓解措施、总结；

\- 高/中/低风险使用表格输出风险点与对应缓解措施；

\- 语言贴合制造业MES售前业务，输出内容可直接用于方案材料。



\#### FR‑004 链路可视化

\- 程序启动输出Mermaid流程图，展示Agent节点流转拓扑。



\### 2.2 非功能需求

|类别|要求|

|---|---|

|性能|RAG检索毫秒级；完整Agent一轮迭代完成时间10‑30s，取决于API响应速度；Embedding本地CPU执行|

|兼容性|Windows Python venv环境；Chroma向量库版本兼容，无需联网即可做检索|

|可观测性|每个节点控制台打印节点名称，便于调试；输出Mermaid流程图|

|可扩展性|节点可新增；可接入联网搜索工具；可后续封装Streamlit网页；可新增报告导出本地文件功能|

|数据安全|PDF、向量库全部存储本地；知识库不上传云端；仅查询prompt发送给DeepSeek API|



\## 3 系统架构设计

\### 3.1 系统架构图

```mermaid

flowchart LR

&#x20;   subgraph "本地Venv运行环境 D:\\agent\_work"

&#x20;       User\[用户业务查询]

&#x20;       subgraph LangGraph\_Agent\["LangGraph Agent编排层"]

&#x20;           N1\[planner\_node<br/>任务拆解规划]

&#x20;           N2\[tool\_decide\_node<br/>工具决策]

&#x20;           N3\[tool\_exec\_node<br/>RAG检索执行]

&#x20;           N4\[task\_execute\_node<br/>生成业务草稿]

&#x20;           N5\[reflect\_node<br/>反思校验\&重规划]

&#x20;           N6\[summary\_node<br/>报告润色汇总]

&#x20;       end



&#x20;       subgraph LocalRAG\["本地RAG模块（离线）"]

&#x20;           Emb\[BGE‑small‑zh‑v1.5<br/>Embedding本地模型 CPU推理]

&#x20;           ChromaDB\[(Chroma向量库<br/>./chroma\_db 本地磁盘)]

&#x20;           PDFDoc\[本地PDF知识库<br/>MES制造业务文档]

&#x20;       end

&#x20;   end



&#x20;   RemoteLLM\[DeepSeek LLM API<br/>远程文本生成服务]



&#x20;   User --> N1

&#x20;   N1 --> N2

&#x20;   N2 --> N3

&#x20;   N3 -.-> Emb

&#x20;   Emb -.-> ChromaDB

&#x20;   ChromaDB -.-> N3



&#x20;   N1 -.调用.-> RemoteLLM

&#x20;   N4 -.调用.-> RemoteLLM

&#x20;   N5 -.调用.-> RemoteLLM

&#x20;   N6 -.调用.-> RemoteLLM



&#x20;   N3 --> N4

&#x20;   N4 --> N5

&#x20;   N5 -.迭代闭环.-> N2

&#x20;   N5 --> N6



&#x20;   PDFDoc -.构建向量库阶段.-> Emb

&#x20;   Emb -.构建向量库阶段.-> ChromaDB



&#x20;   N6 --> Output\[输出Markdown业务分析报告]



