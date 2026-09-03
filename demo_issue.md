\# MES智能制造多智能体Agent Demo 缺陷与调优日志

> 项目版本：agent\_demo.py + streamlit app.py

> 记录目的：用于面试展示工程能力：缺陷发现、风险治理、prompt调优、边界case处理

> 等级：P0阻断 / P1功能错误 / P2体验问题 / P3优化建议



\## 缺陷列表



\### Issue‑001：LLM输出脏JSON，task\_list返回字符串而非dict对象

\- 等级：P1

\- 复现步骤：

&#x20; 1. 输入复杂业务问题，触发orchestrator\_agent调度

&#x20; 2. LLM偶尔输出 `{"question\_type":"analysis","task\_list":\["任务1","任务2"]}`，task\_list内部是字符串，不是`{"task\_desc":"xxx"}`字典

\- 现象：循环执行task时，`task.get("task\_desc")` 抛出异常

\- 根因：大模型生成JSON不可控，prompt约束不足；缺少解析后清洗逻辑

\- 风险：子任务执行链路崩溃，业务中断

\- 修复方案：

&#x20; 1. Prompt增加强约束：`task\_list数组内部每一项必须是{"task\_desc":"描述"}对象，禁止放入字符串`

&#x20; 2. orchestrator\_agent解析后增加清洗逻辑：遍历task\_list，只保留`isinstance(item, dict)`的任务；为空则填充兜底任务

&#x20; 3. run\_workflow运行时二次防护：`if not isinstance(task, dict): continue`，漏网脏任务直接跳过

\- 调优后效果：脏JSON不会崩溃，自动降级兜底任务



\### Issue‑002：网页复制代码带入不可见Unicode特殊字符，触发SyntaxError

\- 等级：P0

\- 复现步骤：从网页复制代码，切片符号 `\[:‑3]` 得到U+2011非标准减号

\- 现象：Python启动直接报语法错误，肉眼看不出字符差异

\- 根因：网页复制引入隐形特殊Unicode字符

\- 修复方案：全部替换为英文半角符号；交付时校验源码字符；禁止网页直接复制大段代码，优先使用代码块导出

\- 风险提示：工程交付注意，网页复制是高频坑



\### Issue‑003：run\_workflow返回类型不稳定，app未做类型判断，触发 `TypeError: string indices must be integers`

\- 等级：P0

\- 复现步骤：工作流极端异常场景返回字符串而非标准dict

\- 现象：`resp\["final\_answer"]`直接崩溃

\- 根因：前端没有做返回值类型兼容判断，直接假设resp一定是字典

\- 修复方案：app.py增加 `isinstance(resp,str)`分支，构造模拟trace对象，保证页面不崩



\### Issue‑004：Streamlit会话状态为浏览器内存，刷新页面/重启服务对话历史全部丢失

\- 等级：P2

\- 复现步骤：多轮提问后，刷新浏览器页面

\- 现象：全部历史对话清空

\- 根因：st.session\_state生命周期绑定浏览器会话，无持久化存储

\- 风险：用户使用体验差，无法回看历史

\- 临时缓解：当前功能可用；

\- 优化方案(P3)：增加json本地持久化，每次问答写入本地`chat\_log.json`，页面加载读取恢复历史



\### Issue‑005：orchestrator\_agent llm=None时没有保护，直接调用llm.invoke()抛出异常

\- 等级：P0

\- 复现步骤：没有初始化llm全局实例直接启动服务

\- 现象：程序启动访问页面直接报错

\- 根因：缺少判空保护

\- 修复：orchestrator\_agent开头增加`if llm is None: return fallback\_data`直接返回兜底任务



\### Issue‑006：tavily\_tool为None（没有配置TAVILY\_API\_KEY）依然进入联网逻辑

\- 等级：P1

\- 复现：.env不配置TAVILY\_API\_KEY，tavily\_tool=None

\- 现象：调用`.invoke()`抛出异常

\- 修复：联网条件增加 `tavily\_tool is not None` 判断



\### Issue‑007：validator\_agent LLM输出JSON格式错乱，json.loads解析失败

\- 等级：P1

\- 复现：校验任务，大模型输出带多余说明文字，包裹markdown代码块

\- 现象：json.loads抛异常，直接进入except保守拦截

\- 根因：validator\_agent的prompt约束不足，没有剥离markdown代码块标记

\- 调优Prompt方案：

> 强制只输出JSON，禁止任何解释文字；输出允许```json ```包裹，代码会自动剥离标记；只输出：{"status":"valid/invalid","reason":"xxx"}

\- 代码增强：增加字符串切片，提取`{...}`子串再loads



\### Issue‑008：rule\_based\_check规则简陋，幻觉拦截能力有限，仅少量黑名单关键词

\- 等级：P1

\- 现象：部分编造内容无法被规则拦截，只能依赖validator\_agent LLM校验

\- 根因：规则校验只是简单字符串匹配，能力弱

\- 调优方向：

1\. 扩充黑名单；

2\. 增加时间、数字、专有名词正则校验；

3\. rule‑check作为第一层快速过滤，validator LLM校验作为第二层，双层防护。



\### Issue‑009：PDF上传功能依赖embedding、persist\_path全局变量，如果换成占位agent\_demo会直接导入报错

\- 等级：P2

\- 复现：使用占位壳版本agent\_demo，app.py继续导入embedding等变量

\- 现象：ImportError

\- 治理：app.py做降级处理；检测依赖缺失，UI禁用PDF上传按钮，给出提示文案。



\### Issue‑010：trace信息中retrieve\_docs没有区分来源，本地知识库片段、联网片段混在一起展示

\- 等级：P2

\- 现状：虽然联网片段标记【联网检索片段】，但是没有单独字段统计联网命中条数

\- 优化(P3)：trace增加`local\_docs`、`web\_docs`两个字段，前端分开渲染，更直观看到哪些来自本地知识库，哪些来自互联网。



\## Prompt调优记录

\### 1. orchestrator\_agent调度Prompt优化点

原始缺陷：大模型容易输出task\_list为字符串数组，question\_type输出不在枚举集合。

优化增加约束：

1\. question\_type严格只能 simple / analysis / report，不允许输出其他值；

2\. task\_list数组每个元素必须是 `{"task\_desc":"描述"}` 对象，禁止字符串；

3\. 禁止输出解释、前言，只输出JSON；

4\. 允许```json```包裹，代码自动剥离标记。



\### 2. simple\_qa问答Prompt优化

> 严格依据参考资料回答，资料没有的内容绝对禁止编造。资料不足直接回复【现有知识库缺少该部分信息】，禁止脑补MES业务知识。



\### 3. analyst\_agent分析Prompt优化

> 只允许整理合并现有素材，严禁编造、严禁无依据推理、严禁自行总结风险对策。无资料固定输出【现有知识库缺少该部分信息，无法完整分析】。



\### 4. validator\_agent校验Prompt优化

> 校验内容必须100%来源于原始素材，不允许推理扩展。只输出JSON，不要多余文字。



\## 风险治理总结

1\. \*\*大模型输出不可信是核心风险\*\*：

&#x20;  - 第一层：Prompt强约束

&#x20;  - 第二层：代码层面做格式清洗、类型校验

&#x20;  - 第三层：规则校验rule\_based\_check

&#x20;  - 第四层：LLM二次校验validator\_agent

&#x20;  四层防御，不能只依赖prompt。

2\. 所有外部调用（llm.invoke、tavily.invoke、向量库）全部包裹try‑except，设置fallback降级策略，拒绝直接崩溃。

3\. 前端永远不要假设后端返回一定是理想格式，必须做类型与字段容错。



\## 待优化TODO(P3产品迭代)

1\. 对话历史本地持久化json存储

2\. trace页面区分本地素材/联网素材，统计条数

3\. 增加日志输出，把orchestrator原始LLM输出记录日志，方便调试

4\. 增加导出PDF功能

5\. 增加知识库清空按钮

6\. 增加输入长度限制，防止超长文本拖慢大模型



