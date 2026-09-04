```markdown
# langgraph‑mes‑business‑agent
>基于 LangGraph 搭建的制造业MES业务多智能体，可完成生产场景问题拆解、工具调用、任务执行、反思重规划，输出结构化业务分析报告。

## ✨项目特性
1. **多节点工作流**：任务规划 planner →工具决策 tool_decide →工具执行 tool_exec →业务任务执行 task_execute →反思重规划 reflect →报告汇总 summary
2. RAG向量知识库：使用BGE‑small‑zh‑v1.5中文向量模型，读取本地PDF业务文档做检索增强
3. 业务场景：MES紧急插单、排程优化、OEE、报工、物料齐套、质量合规等制造业售前分析
4. 输出：自动生成结构化Markdown正式业务报告，适合简历/作品集展示

## 🛠环境依赖
Python >=3.11
```bash
# 创建虚拟环境
"C:\Users\Honor\AppData\Local\Programs\Python\Python311\python.exe" -m venv venv

# 激活虚拟环境
venv\Scripts\activate.bat

# 安装依赖
pip install -r requirements.txt
```

## 🚀运行方式
### Windows环境（必须设置HuggingFace国内镜像，避免10060网络超时）
```cmd
venv\Scripts\activate.bat
set HF_ENDPOINT=https://hf-mirror.com
python graph_agent_skeleton.py
```

>⚠️Windows注意事项
1. 首次启动会自动下载BGE‑small‑zh‑v1.5向量模型，约400MB，需要等待下载完成；
2. 如果镜像依旧下载失败：把模型手动下载至`./models/bge‑small‑zh‑v1.5`本地目录，修改embedding代码读取本地路径，完全不访问外网；
3. 运行会出现LangChain版本弃用警告，属于库迭代，**不影响业务功能运行**。

### ✅推荐验证环境
WSL2‑Ubuntu Linux，网络与huggingface下载稳定性优于原生Windows。

## ⚠️版本迁移提示
当前代码基于旧版LangChain开发，存在两处废弃API警告，升级执行：
```bash
pip install -U langchain‑huggingface
```
导入替换为：
```python
from langchain_huggingface import HuggingFaceBgeEmbeddings
```
`langchain‑community`包已经停止维护，向量存储Chroma后续建议迁移独立包`langchain‑chroma`。

## 📂目录结构
```
├── graph_agent_skeleton.py   # LangGraph主智能体工作流
├── build_kb.py               # 知识库构建脚本
├── requirements.txt         # 依赖清单
├── .env                      # API密钥配置
├── pdf_docs/                 # 业务PDF知识库文档
├── chroma_db/                # Chroma向量数据库持久化存储
├── models/                   # 可选：本地离线embedding模型存放目录
└── assets / docs             # 作品集文档、流程图
```

> 📌 版本废弃警告说明
运行时会出现DeprecationWarning警告：
1. `HuggingFaceBgeEmbeddings`：BGE专用封装类，新版本`langchain‑huggingface`不再提供该类；
2. `langchain‑community`：该包逐步停止维护。

现状：为保留BGE模型专用检索指令，保证RAG检索质量，项目暂时沿用该实现。
后续升级方案：
- 使用通用`HuggingFaceEmbeddings`，手动配置`query_instruction`兼容BGE提示词；
- Chroma向量库迁移至独立包`langchain‑chroma`。
