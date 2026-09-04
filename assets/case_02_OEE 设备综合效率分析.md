case\_02：OEE 设备综合效率分析

(venv) D:\\langgraph‑mes‑business‑agent>python graph\_agent\_skeleton.py

D:\\langgraph‑mes‑business‑agent\\graph\_agent\_skeleton.py:1: DeprecationWarning: `langchain-community` is being sunset and is no longer actively maintained. See https://github.com/langchain-ai/langchain-community/issues/674 for details and migration guidance toward standalone integration packages.

&#x20; from langchain\_community.vectorstores import Chroma

D:\\langgraph‑mes‑business‑agent\\graph\_agent\_skeleton.py:40: LangChainDeprecationWarning: The class `HuggingFaceBgeEmbeddings` was deprecated in LangChain 0.2.2 and will be removed in 1.0. An updated version of the class exists in the `langchain-huggingface package and should be used instead. To use it run `pip install -U `langchain-huggingface` and import as `from `langchain\_huggingface import HuggingFaceEmbeddings``.

&#x20; embedding = HuggingFaceBgeEmbeddings(

Loading weights: 100%|███████████████████████████████████████████████████████████████████████████████████████████████████| 71/71 \[00:00<00:00, 4543.58it/s]

D:\\langgraph‑mes‑business‑agent\\graph\_agent\_skeleton.py:45: LangChainDeprecationWarning: The class `Chroma` was deprecated in LangChain 0.2.9 and will be removed in 1.0. An updated version of the class exists in the `langchain-chroma package and should be used instead. To use it run `pip install -U `langchain-chroma` and import as `from `langchain\_chroma import Chroma``.

&#x20; vector\_db = Chroma(



==== Graph Mermaid ====

\---

config:

&#x20; flowchart:

&#x20;   curve: linear

\---

graph TD;

&#x20;       \_\_start\_\_(\[<p>\_\_start\_\_</p>]):::first

&#x20;       planner\_node(planner\_node)

&#x20;       tool\_decide\_node(tool\_decide\_node)

&#x20;       tool\_exec\_node(tool\_exec\_node)

&#x20;       task\_execute\_node(task\_execute\_node)

&#x20;       reflect\_node(reflect\_node)

&#x20;       summary\_node(summary\_node)

&#x20;       \_\_end\_\_(\[<p>\_\_end\_\_</p>]):::last

&#x20;       \_\_start\_\_ --> planner\_node;

&#x20;       planner\_node --> tool\_decide\_node;

&#x20;       reflect\_node -.-> summary\_node;

&#x20;       reflect\_node -.-> tool\_decide\_node;

&#x20;       task\_execute\_node --> reflect\_node;

&#x20;       tool\_decide\_node --> tool\_exec\_node;

&#x20;       tool\_exec\_node --> task\_execute\_node;

&#x20;       summary\_node --> \_\_end\_\_;

&#x20;       classDef default fill:#f2f0ff,line-height:1.2

&#x20;       classDef first fill-opacity:0

&#x20;       classDef last fill:#bfb6fc





==== Running Agent ====



【planner\_node】初始任务拆解

【tool\_decide\_node】工具决策

【tool\_exec\_node】执行工具

【task\_execute\_node】执行业务任务与校验

【reflect\_node】反思+动态重规划（含输出质量校验）

【tool\_decide\_node】工具决策

【tool\_exec\_node】执行工具

【task\_execute\_node】执行业务任务与校验

【reflect\_node】反思+动态重规划（含输出质量校验）

【tool\_decide\_node】工具决策

【tool\_exec\_node】执行工具

【task\_execute\_node】执行业务任务与校验

【reflect\_node】反思+动态重规划（含输出质量校验）

【tool\_decide\_node】工具决策

【tool\_exec\_node】执行工具

【task\_execute\_node】执行业务任务与校验

【reflect\_node】反思+动态重规划（含输出质量校验）

【summary\_node】生成最终完整报告

summary\_node：复用reflect草稿，仅做润色



====完整最终报告====



\# OEE设备综合效率分析方案（正式报告）





\## 一、概述



本方案围绕OEE（设备综合效率）分析展开，目前已形成完整的工作方案，涵盖指标体系定义、计算模型与损失分析框架、可视化看板与异常预警机制，以及改进建议与报告模板等核心模块。方案以MES系统实时数据为基础，旨在实现设备效率的量化评估、损失识别与持续改进。





\## 二、指标体系与计算模型



\### 2.1 OEE计算公式



方案明确采用国际通用的OEE计算模型，具体公式如下：



\*\*OEE = 可用率 × 性能率 × 良品率\*\*



其中：



\- \*\*可用率\*\*反映设备时间利用效率，考量故障停机、换产调试等时间损失；

\- \*\*性能率\*\*反映设备运行速度效率，考量小停机、空转及速度降低等损失；

\- \*\*良品率\*\*反映设备质量输出水平，考量生产不良与启动不良等质量损失。



\### 2.2 六大损失分解



围绕OEE三大构成要素，方案将设备效率损失系统分解为六大类：



| 损失类别 | 归属维度 |

|----------|----------|

| 故障停机 | 可用率 |

| 换产调试 | 可用率 |

| 小停机/空转 | 性能率 |

| 速度降低 | 性能率 |

| 生产不良 | 良品率 |

| 启动不良 | 良品率 |



该分解框架为后续损失定位与根因分析提供了统一口径和结构化基础。





\## 三、数据采集与系统支撑



方案数据采集依托MES系统，覆盖以下关键数据项：



\- \*\*计划生产时间\*\*：用于计算设备理论可用时间；

\- \*\*停机时间\*\*：含故障停机、换产调试等，用于计算可用率；

\- \*\*产出数量\*\*：用于计算性能率；

\- \*\*合格品数量\*\*：用于计算良品率。



上述数据为OEE的实时计算、趋势分析及异常追溯提供了可靠的数据基础。





\## 四、可视化看板与异常预警机制



方案设计了OEE可视化看板，用于集中展示设备综合效率、三大指标变化趋势及六大损失分布情况，支撑管理层与现场人员实时掌握设备运行状态。



同时，方案建立了异常预警机制，针对OEE指标异常波动及关键损失项超限情况及时触发预警，推动快速响应与闭环处理。





\## 五、改进建议与报告模板



方案提供了标准化的改进建议框架，结合损失分析结果，指导制定针对性改善措施。同时，配套设计了OEE分析报告模板，便于定期输出分析结论、改善进展及后续行动计划，形成“数据采集→效率分析→改善执行→效果验证”的持续改进闭环。





\## 六、总结



本方案以MES系统数据为支撑，构建了从指标定义、数据采集、损失分析到监控预警和改进闭环的完整OEE分析体系，能够有效支撑设备效率的持续提升。后续可按计划推进方案落地实施，并在运行过程中持续优化指标口径与分析维度。



