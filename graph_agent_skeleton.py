# 环境变量设置
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# 导入依赖
from langchain_core.callbacks import BaseCallbackHandler
import time
import uuid
import json
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from tavily import TavilyClient
import mes_tools

# 加载 .env 环境变量
load_dotenv()
os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# ====================== 全局可调常量 ======================
MAX_LOOP = 3
CONTEXT_MAX_LEN = 4000
REFLECT_TASK_OUTPUT_TRUNC = 500
SUMMARY_TASK_OUTPUT_TRUNC = 1200
SUMMARY_DRAFT_MIN_LEN = 100
TRACE_MAX_ITEMS = 50
GRAPH_RECURSION_LIMIT = 80
CHROMA_PERSIST_DIR = "./chroma_db"
CHROMA_TOP_K = 3
PRICE_IN = 0.0014
PRICE_OUT = 0.0028
AUTO_APPROVE_SEARCH = os.getenv("AUTO_APPROVE_SEARCH", "false").lower() == "true"

# LLM 与工具初始化
llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1",
    temperature=0
)
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


# ====================== 自定义Callback 链路追踪 ======================
class AgentTraceHandler(BaseCallbackHandler):
    def __init__(self, trace_id):
        self.trace_id = trace_id
        self.start_time = {}
        self.run_id_to_name = {}

    def _get_name(self, serialized, kwargs):
        if serialized and isinstance(serialized, dict):
            name = serialized.get("name")
            if name:
                return name
        if "name" in kwargs and kwargs["name"]:
            return kwargs["name"]
        return "unknown_node"

    def on_chain_start(self, serialized, inputs, *, run_id=None, **kwargs):
        node_name = self._get_name(serialized, kwargs)
        self.run_id_to_name[run_id] = node_name
        self.start_time[node_name] = time.time()
        print(f"\n[TRACE:{self.trace_id}] 【进入节点】：{node_name}")

    def on_chain_end(self, outputs, *, run_id=None, **kwargs):
        node_name = self.run_id_to_name.get(run_id, "unknown_node")
        cost = round(time.time() - self.start_time.get(node_name, time.time()), 3)
        print(f"[TRACE:{self.trace_id}] 【退出节点】：{node_name}, 节点耗时={cost}s")

    def on_tool_start(self, serialized, input_str, *, run_id=None, **kwargs):
        tool_name = self._get_name(serialized, kwargs)
        print(f"[TRACE:{self.trace_id}] 【启动工具】：{tool_name}, 查询={input_str}")

    def on_tool_end(self, output, *, run_id=None, **kwargs):
        print(f"[TRACE:{self.trace_id}] 【工具调用完成】")

    def on_llm_start(self, serialized, prompts, *, run_id=None, **kwargs):
        print(f"[TRACE:{self.trace_id}] 【发起LLM调用】")


# ========== Token统计辅助函数 ==========
def print_token_usage(resp):
    if hasattr(resp, "usage_metadata") and resp.usage_metadata:
        usage = resp.usage_metadata
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        total_tok = usage.get("total_tokens", 0)
        cost = (in_tok / 1000) * PRICE_IN + (out_tok / 1000) * PRICE_OUT
        print(f"【Token统计】输入:{in_tok}, 输出:{out_tok}, 合计:{total_tok}, 预估本轮费用:{cost:.6f} 元")
        write_trace_log({
            "level": "info",
            "func": "token_stat",
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": total_tok,
            "cost_yuan": round(cost, 6)
        })
        return in_tok, out_tok, total_tok
    else:
        print("【Token统计】接口未返回usage信息")
        return 0, 0, 0


# ========== 模型缓存（模块级全局） ==========
_GLOBAL_VECTOR_DB = None
_GLOBAL_RERANKER = None


def _get_vector_db():
    global _GLOBAL_VECTOR_DB
    if _GLOBAL_VECTOR_DB is None:
        print("【懒加载】首次调用，加载BGE Embedding和Chroma向量库...")
        embedding = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-zh-v1.5",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True}
        )
        _GLOBAL_VECTOR_DB = Chroma(
            persist_directory=CHROMA_PERSIST_DIR,
            embedding_function=embedding
        )
    return _GLOBAL_VECTOR_DB


def get_reranker():
    global _GLOBAL_RERANKER
    if _GLOBAL_RERANKER is None:
        print("【懒加载】加载 Reranker 模型 bge-reranker-v2-m3...")
        from FlagEmbedding import FlagReranker
        _GLOBAL_RERANKER = FlagReranker(
            './models/bge-reranker-v2-m3',
            use_fp16=False
        )
        print("【懒加载】Reranker 加载完成")
    return _GLOBAL_RERANKER


# RAG 检索（粗召回 + Rerank 精排）
def chroma_search(query: str) -> tuple[str, list]:
    vector_db = _get_vector_db()

    try:
        docs = vector_db.similarity_search(query, k=10)
    except Exception as e:
        err_msg = f"Chroma检索异常:{str(e)}"
        print(err_msg)
        write_trace_log({"level": "error", "func": "chroma_search", "msg": err_msg})
        return "", []

    if not docs:
        return "", []

    try:
        reranker = get_reranker()
        pairs = [[query, doc.page_content] for doc in docs]
        scores = reranker.compute_score(pairs)
        ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
        top_docs = [doc for _, doc in ranked[:CHROMA_TOP_K]]
        write_trace_log({
            "func": "rerank",
            "query": query,
            "before": len(docs),
            "after": len(top_docs),
            "top_scores": [round(float(s), 3) for s, _ in ranked[:3]]
        })
    except Exception as e:
        print(f"【Rerank 降级】{str(e)}，使用原始 Top {CHROMA_TOP_K}")
        write_trace_log({
            "level": "error",
            "func": "rerank",
            "msg": f"Rerank失败，降级到原始Top{CHROMA_TOP_K}",
            "error": str(e)
        })
        top_docs = docs[:CHROMA_TOP_K]

    chunks = [doc.page_content for doc in top_docs]
    source_list = list({
        doc.metadata.get("source_file", "未知文档")
        for doc in top_docs
    })
    return "\n\n".join(chunks), source_list


def write_trace_log(entry: dict):
    entry["timestamp"] = datetime.now().isoformat()
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open("./trace.jsonl", "a", encoding="utf-8") as f:
        f.write(line)


# ====================== BOM 版本前置守卫 ======================
_available_versions_cache = None

def get_available_versions() -> set:
    global _available_versions_cache
    if _available_versions_cache is not None:
        return _available_versions_cache

    versions = set()
    pattern = re.compile(r'(?:BOM\s*)?版本\s*[:：]?\s*[vV]?(\d+(?:\.\d+)?)')
    docs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "md_docs")

    if os.path.isdir(docs_dir):
        for fn in os.listdir(docs_dir):
            if fn.endswith(".md"):
                try:
                    with open(os.path.join(docs_dir, fn), "r", encoding="utf-8") as f:
                        content = f.read()
                    for m in pattern.findall(content):
                        versions.add(f"V{m}")
                except Exception as e:
                    print(f"【版本索引】读取 {fn} 失败: {e}")

    _available_versions_cache = versions
    print(f"【版本索引】已加载可用版本：{sorted(versions)}")
    return versions


def _normalize_version(v: str) -> str:
    v = v.upper().lstrip("V")
    if "." not in v:
        v = v + ".0"
    return v


def check_bom_version_guard(tool_query: str, user_query: str = "") -> str | None:
    available = get_available_versions()
    if not available:
        return None

    available_norm = {_normalize_version(v) for v in available}
    bom_pattern = re.compile(
        r'BOM\s*(?:版本|version)?\s*[:：]?\s*[vV]?(\d+(?:\.\d+)?)',
        re.IGNORECASE
    )

    for q in (tool_query, user_query):
        if not q:
            continue
        for m in bom_pattern.finditer(q):
            target = f"V{m.group(1)}"
            if _normalize_version(target) not in available_norm:
                available_display = "、".join(sorted(available))
                return (
                    f"【系统前置拦截】查询中提及的 BOM 版本 {target} 不存在。"
                    f"当前知识库中可用的 BOM 版本为：{available_display}。"
                    f"请确认版本号是否正确，不要基于其他版本信息推测该版本内容。"
                )
    return None


def tavily_search(query: str, cache: dict) -> tuple[str | None, dict]:
    cache_key = query.strip()
    if cache_key in cache:
        return cache[cache_key], cache
    try:
        resp = tavily.search(query=query, max_results=2)
    except Exception as e:
        err_msg = f"Tavily联网搜索异常:{str(e)}"
        print(err_msg)
        write_trace_log({"level": "error", "func": "tavily_search", "query": query, "msg": err_msg})
        return None, cache
    contents = []
    for item in resp["results"]:
        contents.append(f"标题:{item['title']}\n摘要:{item['content'][:600]}")
    result = "\n---\n".join(contents)
    new_cache = cache.copy()
    new_cache[cache_key] = result
    return result, new_cache


# ============AgentState 定义================
class AgentState(TypedDict):
    user_query: str
    case_id: str
    user_id: str
    user_role: str
    task_list: list[dict]
    current_task: dict | None
    context_local_kb: str
    context_from_web: str
    think_trace: list[str]
    raw_tool_obs: list[str]
    intermediate_answer: str
    final_answer: str
    need_more_info: bool
    loop_count: int
    tavily_cache: dict
    ref_docs: list


# ====================== 权限矩阵 ======================
ROLE_PERMISSIONS = {
    "operator": [
        "chroma_search",
        "mes_work_order", "mes_inventory", "mes_equipment",
        "mes_low_stock", "mes_alarm_equipment", "mes_quality_issues",
    ],
    "supervisor": [
        "chroma_search", "tavily_search",
        "mes_work_order", "mes_inventory", "mes_equipment",
        "mes_low_stock", "mes_alarm_equipment", "mes_quality_issues",
    ],
    "admin": [
        "chroma_search", "tavily_search",
        "mes_work_order", "mes_inventory", "mes_equipment",
        "mes_low_stock", "mes_alarm_equipment", "mes_quality_issues",
    ],
}

AUDIT_LOG_FILE = "./audit.log"


def write_audit_log(entry: dict):
    entry["timestamp"] = datetime.now().isoformat()
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def check_permission(user_role: str, tool_name: str) -> bool:
    allowed = ROLE_PERMISSIONS.get(user_role, [])
    return tool_name in allowed


# ========== 5 个 Prompt 模板 ==========
PLANNER_PROMPT = """
拆分为2‑4个粗粒度任务，禁止细碎任务。输出纯JSON。

【拒答规则（最高优先级）】
如果用户问题与MES、制造业生产管理、质量体系（8D/SPC/FMEA）、生产排程、设备管理、物料管理等无关，
例如：闲聊、股票、天气、娱乐、编程、投资建议等，直接输出：
{"tasks":[{"task_id":1,"desc":"REJECT:该问题不属于MES业务范围","status":"pending"}]}

【正常拆解】
{"tasks":[{"task_id":int,"desc":"任务描述","status":"pending"}]}

用户问题：{user_query}
"""

TOOL_DECIDE_PROMPT = """
任务：{task_desc}
已有本地知识库KB：{kb_ctx}
已有Web：{web_ctx}

【工具列表】
- chroma_search：查本地知识库（规范、规则、SOP）
- tavily_search：联网搜索（最新资讯、外部信息）
- mes_work_order：查实时工单状态。tool_query 填工单号，如 WO-20261007-001
- mes_inventory：查实时物料库存。tool_query 填 SKU 编码，如 SKU-A100-01
- mes_equipment：查设备实时状态。tool_query 填设备编号，如 M-001
- mes_low_stock：查所有低库存物料（无参数，tool_query 填空）
- mes_alarm_equipment：查所有报警/维护中的设备（无参数，tool_query 填空）
- mes_quality_issues：查处理中的质量问题（无参数，tool_query 填空）
- no_tool：无需工具

【决策原则】
1. 问"工单现在什么状态/进度" → mes_work_order
2. 问"库存还有多少/齐套情况" → mes_inventory；问"哪些物料要补货/低于安全库存" → mes_low_stock
3. 问"设备是否正常/报警" → mes_equipment 或 mes_alarm_equipment
4. 问"质量问题/异常批次" → mes_quality_issues
5. 问"规范是什么/8D要求/SPC原理" → chroma_search
6. 需要最新资讯 → tavily_search
7. 已有信息足够回答 → no_tool

输出 JSON：{"tool":"xxx","tool_query":"xxx"}
"""

TASK_EXECUTE_PROMPT = """
基于素材完成该子任务输出，不要回答整体问题。
任务：{task_desc}
本地KB：{kb_ctx}
Web：{web_ctx}

【数据源措辞要求】
- 如果素材来自【工单实时状态】【设备实时状态】【物料库存实时数据】等标记 → 这是 MES 系统实时数据，请说"根据 MES 实时数据"，不要说"根据本地知识库"
- 如果素材来自文档片段（规范、SOP）→ 才说"根据知识库"
- 不要混淆两个数据源
"""

REFLECT_REPLAN_PROMPT = """
反思重规划。用户问题：{user_query}
任务列表：{task_list_payload}
KB片段：{kb_snippet}
Web片段：{web_snippet}

【收敛优先原则（最高优先级）】
只要所有任务的输出能基本回答用户问题，立即收敛，need_more_info=false。
以下情况不算"信息不足"，禁止继续循环：
- "可以更详细"
- "可以更结构化"
- "可以补充更多细节"
- "可以引用更多文档"
- "理论上可以更完美"

只有以下情况才允许把任务改回 pending：
- 输出明显答非所问（比如问 OEE 答成 SPC）
- 输出大量编造内容，与知识库冲突
- 任务状态是 completed 但 task_output 为空

【规则】
1. 任务保持粗粒度，status 仅 pending / completed。
2. 所有任务已 completed 且有非空输出，默认 need_more_info=false。
3. 返回 JSON 禁止携带大段 task_output。
4. 有明确 pending 任务：need_more_info=true，final_answer=""。
5. 全部 completed 且校验通过：need_more_info=false，输出 final_answer 草稿。

仅输出 JSON：
{
  "task_list": [{"task_id":int,"desc":"str","status":"pending|completed"}],
  "need_more_info": true|false,
  "final_answer": ""
}
"""

SUMMARY_PROMPT = """
原始问题：{user_query}
子任务片段：{task_output_blocks}
基于上面内容输出完整通顺报告。

【去重原则】
- 如果多个子任务引用了同一份数据源（比如同一张工单、同一批库存），合并展示，不要重复罗列字段
- 不要出现两个章节讲同一个数据
- 报告结构：先给结论，再给支撑数据

【数据源措辞】
- 来自 MES 实时系统的数据，标注"实时数据"
- 来自文档的规范/SOP，标注"知识库"
- 不要混淆

如果已有草稿可以直接复用、润色，不要完全重写。
"""


def extract_json(text: str):
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        raw = match.group(1)
    else:
        raw = text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raw_fixed = re.sub(r'\n(?!(\s*[\}\],]))', " ", raw)
        try:
            return json.loads(raw_fixed)
        except json.JSONDecodeError:
            return None


def planner_node(state: AgentState):
    print("【planner_node】初始任务拆解")
    write_trace_log({
        "case_id": state["case_id"],
        "node": "planner_node",
        "user_query": state["user_query"]
    })
    prompt = PLANNER_PROMPT.replace("{user_query}", state["user_query"])
    try:
        resp = llm.invoke(prompt)
        print_token_usage(resp)
    except Exception as e:
        err_msg = f"planner_node LLM调用异常:{str(e)}"
        print(err_msg)
        write_trace_log({"level": "error", "node": "planner_node", "msg": err_msg})
        task_list = [{"task_id": 1, "desc": f"回答用户问题：{state['user_query']}", "status": "pending"}]
        return {
            "task_list": task_list,
            "think_trace": state["think_trace"][-TRACE_MAX_ITEMS:] + [err_msg],
            "loop_count": 0
        }
    data = extract_json(resp.content)
    if data is None or "tasks" not in data:
        task_list = [{"task_id": 1, "desc": f"回答用户问题：{state['user_query']}", "status": "pending"}]
    else:
        task_list = data.get("tasks", [])
    trace = f"planner：生成{len(task_list)}个粗粒度任务"
    think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [trace]
    write_trace_log({"node": "planner_node", "trace_info": trace})
    return {
        "task_list": task_list,
        "think_trace": think_trace,
        "loop_count": 0
    }


def tool_decide_node(state: AgentState):
    print("【tool_decide_node】工具决策")
    write_trace_log({
        "case_id": state["case_id"],
        "node": "tool_decide_node"
    })
    pending = [t for t in state["task_list"] if t["status"] == "pending"]
    if not pending:
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + ["tool_decide：无pending任务"]
        return {"current_task": None, "think_trace": think_trace}
    curr_task = pending[0].copy()
    prompt = TOOL_DECIDE_PROMPT.replace("{task_desc}", curr_task["desc"])
    prompt = prompt.replace("{kb_ctx}", state["context_local_kb"])
    prompt = prompt.replace("{web_ctx}", state["context_from_web"])
    try:
        resp = llm.invoke(prompt)
        print_token_usage(resp)
    except Exception as e:
        err_msg = f"tool_decide_node LLM调用异常:{str(e)}"
        print(err_msg)
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [err_msg]
        return {"current_task": None, "think_trace": think_trace}
    dec = extract_json(resp.content)
    if dec is None:
        tool_name = "no_tool"
        tool_q = ""
    else:
        tool_name = dec.get("tool", "no_tool")
        tool_q = dec.get("tool_query", "")
    curr_task["tool_name"] = tool_name
    curr_task["tool_query"] = tool_q
    trace = f"tool_decide：task{curr_task['task_id']} → {tool_name}, query:{tool_q}"
    think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [trace]
    write_trace_log({"node": "tool_decide_node", "trace": trace})
    return {
        "current_task": curr_task,
        "think_trace": think_trace
    }


def tool_exec_node(state: AgentState):
    print("【tool_exec_node】执行工具")
    write_trace_log({
        "case_id": state["case_id"],
        "node": "tool_exec_node"
    })
    curr = state["current_task"]
    if not curr or curr["tool_name"] == "no_tool":
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + ["tool_exec：no_tool，跳过工具调用"]
        write_trace_log({"node": "tool_exec_node", "trace_info": "no_tool跳过调用"})
        return {"think_trace": think_trace}

    user_role = state.get("user_role", "operator")
    user_id = state.get("user_id", "anonymous")
    tool_name = curr["tool_name"]

    if not check_permission(user_role, tool_name):
        denied_msg = f"【权限拒绝】用户 {user_id}（角色：{user_role}）无权调用工具 {tool_name}"
        print(denied_msg)
        write_trace_log({"node": "tool_exec_node", "action": "permission_denied", "tool": tool_name, "role": user_role})
        write_audit_log({
            "user_id": user_id,
            "user_role": user_role,
            "action": "permission_denied",
            "tool": tool_name,
            "query": state["user_query"],
        })
        task_list = [t.copy() for t in state["task_list"]]
        for idx, t in enumerate(task_list):
            if t["task_id"] == curr["task_id"]:
                task_list[idx]["status"] = "completed"
                task_list[idx]["task_output"] = denied_msg
                break
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [denied_msg]
        return {
            "task_list": task_list,
            "think_trace": think_trace,
            "current_task": None,
        }

    tool_q = curr.get("tool_query", "").strip()
    new_local_kb = state["context_local_kb"]
    new_web = state["context_from_web"]
    obs_list = []
    tavily_cache = state["tavily_cache"].copy()
    new_ref = state.get("ref_docs", []).copy()

    # ========== chroma_search ==========
    if curr["tool_name"] == "chroma_search":
        if not tool_q:
            skip_msg = f"tool_exec：task{curr['task_id']} tool_query为空，跳过工具调用"
            print(skip_msg)
            think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [skip_msg]
            write_trace_log({"node": "tool_exec_node", "trace_info": skip_msg})
            return {"think_trace": think_trace}

        block_message = check_bom_version_guard(tool_q, state.get("user_query", ""))
        if block_message:
            print(f"【前置拦截】{block_message}")
            write_trace_log({
                "node": "tool_exec_node",
                "action": "bom_version_blocked",
                "tool_query": tool_q,
                "msg": block_message
            })
            new_local_kb += "\n" + block_message
            new_local_kb = new_local_kb[-CONTEXT_MAX_LEN:]
            obs_list.append(f"chroma_search 被前置拦截:{block_message}")
        else:
            res, sources = chroma_search(tool_q)
            if res:
                new_local_kb += "\n" + res
                new_local_kb = new_local_kb[-CONTEXT_MAX_LEN:]
                new_ref = list(set(new_ref + sources))
            obs_list.append(f"chroma_search 返回:{res[:200]}... 来源:{sources}")

    # ========== MES 实时工具 ==========
    elif curr["tool_name"] in mes_tools.MES_TOOLS:
        try:
            mes_func = mes_tools.MES_TOOLS[curr["tool_name"]]
            if curr["tool_name"] in ("mes_low_stock", "mes_alarm_equipment", "mes_quality_issues"):
                mes_result = mes_func()
            else:
                if not tool_q:
                    skip_msg = f"tool_exec：task{curr['task_id']} MES工具缺参数，跳过"
                    print(skip_msg)
                    think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [skip_msg]
                    write_trace_log({"node": "tool_exec_node", "trace_info": skip_msg})
                    return {"think_trace": think_trace}
                mes_result = mes_func(tool_q)

            print(f"【MES 工具】{curr['tool_name']} 返回：{mes_result[:200]}...")
            new_local_kb += "\n" + mes_result
            new_local_kb = new_local_kb[-CONTEXT_MAX_LEN:]
            obs_list.append(f"{curr['tool_name']} 返回:{mes_result[:200]}...")
            write_trace_log({
                "node": "tool_exec_node",
                "action": "mes_tool_call",
                "tool": curr["tool_name"],
                "query": tool_q,
            })
        except Exception as e:
            err_msg = f"【MES 工具异常】{curr['tool_name']}: {str(e)}"
            print(err_msg)
            obs_list.append(err_msg)
            write_trace_log({"level": "error", "node": "tool_exec_node", "msg": err_msg})

    # ========== tavily_search ==========
    elif curr["tool_name"] == "tavily_search":
        if not tool_q:
            skip_msg = f"tool_exec：task{curr['task_id']} tool_query为空，跳过工具调用"
            print(skip_msg)
            think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [skip_msg]
            write_trace_log({"node": "tool_exec_node", "trace_info": skip_msg})
            return {"think_trace": think_trace}

        if AUTO_APPROVE_SEARCH:
            user_input = "y"
        else:
            print(f"\n===== HITL人工确认：准备联网搜索，query【{tool_q}】 =====")
            user_input = input("是否执行联网搜索 y/n：").strip().lower()
        if user_input == "y":
            res, tavily_cache = tavily_search(tool_q, tavily_cache)
            if res is not None:
                new_web += "\n" + res
                new_web = new_web[-CONTEXT_MAX_LEN:]
                obs_list.append(f"tavily_search 返回:{res[:200]}...")
            else:
                obs_list.append(f"tavily_search 查询失败，跳过")
        else:
            skip_msg = f"HITL拒绝联网搜索，跳过query:{tool_q}"
            print(skip_msg)
            obs_list.append(skip_msg)
            write_trace_log({"node": "tool_exec_node", "trace_info": skip_msg})

    think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + obs_list
    raw_tool_obs = state["raw_tool_obs"][-TRACE_MAX_ITEMS:] + obs_list
    for obs in obs_list:
        write_trace_log({"node": "tool_exec_node", "obs": obs})
    return {
        "context_local_kb": new_local_kb,
        "context_from_web": new_web,
        "tavily_cache": tavily_cache,
        "raw_tool_obs": raw_tool_obs,
        "think_trace": think_trace,
        "ref_docs": new_ref
    }


def task_execute_node(state: AgentState):
    print("【task_execute_node】执行业务任务与校验")
    write_trace_log({
        "case_id": state["case_id"],
        "node": "task_execute_node"
    })
    curr = state["current_task"]
    task_list = [t.copy() for t in state["task_list"]]
    if not curr:
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + ["task_execute：无当前任务"]
        write_trace_log({"node": "task_execute_node", "trace_info": "无当前任务"})
        return {"think_trace": think_trace}

    if curr["desc"].startswith("REJECT:"):
        reject_msg = (
            "抱歉，我是MES业务助手，专注于制造业生产管理相关问题"
            "（如8D报告、SPC、OEE、排程、质量异常、设备管理等）。"
            "您的问题不在我的业务范围内，无法回答。"
        )
        print(f"【拒答】{reject_msg}")
        write_trace_log({
            "node": "task_execute_node",
            "action": "reject",
            "reason": curr["desc"]
        })
        for idx, t in enumerate(task_list):
            if t["task_id"] == curr["task_id"]:
                task_list[idx]["status"] = "completed"
                task_list[idx]["task_output"] = reject_msg
                break
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + ["task_execute：触发拒答"]
        return {
            "task_list": task_list,
            "intermediate_answer": reject_msg,
            "current_task": None,
            "think_trace": think_trace
        }

    prompt = TASK_EXECUTE_PROMPT.replace("{task_desc}", curr["desc"])
    prompt = prompt.replace("{kb_ctx}", state["context_local_kb"])
    prompt = prompt.replace("{web_ctx}", state["context_from_web"])
    try:
        resp = llm.invoke(prompt)
        print_token_usage(resp)
    except Exception as e:
        err_msg = f"task_execute_node LLM调用异常:{str(e)}"
        print(err_msg)
        write_trace_log({"level": "error", "node": "task_execute_node", "msg": err_msg})
        output_text = f"【子任务执行异常】{str(e)}"
    else:
        output_text = resp.content.strip()
    for idx, t in enumerate(task_list):
        if t["task_id"] == curr["task_id"]:
            task_list[idx]["status"] = "completed"
            task_list[idx]["task_output"] = output_text
            break
    trace = f"task_execute task{curr['task_id']} 生成子任务输出"
    think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [trace]
    write_trace_log({"node": "task_execute_node", "trace_info": trace})
    return {
        "task_list": task_list,
        "intermediate_answer": output_text,
        "current_task": None,
        "think_trace": think_trace
    }


def reflect_node(state: AgentState):
    write_trace_log({
        "case_id": state["case_id"],
        "node": "reflect_node",
        "msg": "反思校验节点，评估当前信息是否足够回答MES业务问题"
    })
    print("【reflect_node】反思+动态重规划（含输出质量校验）")
    loop_cnt = state["loop_count"]
    task_list = [t.copy() for t in state["task_list"]]
    pending = [t for t in task_list if t["status"] == "pending"]

    if loop_cnt >= MAX_LOOP and len(pending) == 0:
        msg = f"reflect：达到最大循环{MAX_LOOP}次，全部任务完成"
        print(msg)
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [msg]
        write_trace_log({"node": "reflect_node", "trace_info": msg})
        return {
            "need_more_info": False,
            "final_answer": "",
            "think_trace": think_trace,
            "loop_count": loop_cnt + 1
        }

    if loop_cnt >= MAX_LOOP and len(pending) > 0:
        warn_msg = f"reflect警告：达到最大循环{MAX_LOOP}次，仍存在未完成任务，强制结束"
        print(warn_msg)
        for idx, t in enumerate(task_list):
            if t["status"] == "pending":
                task_list[idx]["status"] = "completed"
                task_list[idx]["task_output"] = "【达到最大迭代次数，任务未充分执行】"
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [warn_msg]
        write_trace_log({"node": "reflect_node", "trace_info": warn_msg})
        return {
            "task_list": task_list,
            "need_more_info": False,
            "final_answer": "",
            "think_trace": think_trace,
            "loop_count": loop_cnt + 1
        }

    # 分支 C：快速收敛保护
    if loop_cnt >= 0:
        all_done = all(
            t["status"] == "completed" and t.get("task_output", "").strip()
            for t in task_list
        )
        if all_done:
            msg = f"reflect：快速收敛保护触发（loop={loop_cnt}，全部任务已完成且有输出）"
            print(msg)
            write_trace_log({"node": "reflect_node", "trace_info": msg})
            think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [msg]
            return {
                "task_list": task_list,
                "need_more_info": False,
                "final_answer": "",
                "think_trace": think_trace,
                "loop_count": loop_cnt + 1
            }

    llm_payload = []
    for t in task_list:
        item = {"task_id": t["task_id"], "desc": t["desc"], "status": t["status"]}
        if "task_output" in t:
            item["task_output"] = t["task_output"][:REFLECT_TASK_OUTPUT_TRUNC]
        llm_payload.append(item)
    kb_snippet = state["context_local_kb"][:2000]
    web_snippet = state["context_from_web"][:2000]
    prompt = REFLECT_REPLAN_PROMPT.replace("{user_query}", state["user_query"])
    prompt = prompt.replace("{task_list_payload}", json.dumps(llm_payload, ensure_ascii=False))
    prompt = prompt.replace("{kb_snippet}", kb_snippet)
    prompt = prompt.replace("{web_snippet}", web_snippet)
    try:
        resp = llm.invoke(prompt)
        print_token_usage(resp)
    except Exception as e:
        err_msg = f"reflect_node LLM调用异常，沿用原有任务继续执行:{str(e)}"
        print(err_msg)
        write_trace_log({"level": "error", "node": "reflect_node", "msg": err_msg})
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [err_msg]
        return {
            "task_list": task_list,
            "need_more_info": False,
            "final_answer": "",
            "think_trace": think_trace,
            "loop_count": loop_cnt + 1
        }
    re_data = extract_json(resp.content)
    if re_data is None:
        trace_msg = "reflect：JSON解析失败，沿用现有任务"
        print(trace_msg)
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [trace_msg]
        write_trace_log({"node": "reflect_node", "trace_info": trace_msg})
        return {
            "task_list": task_list,
            "need_more_info": False,
            "final_answer": "",
            "think_trace": think_trace,
            "loop_count": loop_cnt + 1
        }
    updated_tasks = re_data.get("task_list", task_list)
    need_more = re_data.get("need_more_info", True)
    draft_ans = re_data.get("final_answer", "")
    id_map = {t["task_id"]: t for t in task_list}
    for new_t in updated_tasks:
        tid = new_t["task_id"]
        old = id_map.get(tid, {})
        merged_t = old.copy()
        merged_t.update(new_t)
        id_map[tid] = merged_t
    merged_tasks = list(id_map.values())
    trace_msg = f"reflect：need_more={need_more},任务数量{len(merged_tasks)}"
    think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [trace_msg]
    write_trace_log({"node": "reflect_node", "trace_info": trace_msg})
    return {
        "task_list": merged_tasks,
        "need_more_info": need_more,
        "final_answer": draft_ans,
        "think_trace": think_trace,
        "loop_count": loop_cnt + 1
    }


def summary_node(state: AgentState):
    write_trace_log({
        "case_id": state["case_id"],
        "node": "summary_node"
    })
    ref_list = state.get("ref_docs", [])
    ref_text = ""
    if ref_list:
        ref_text = "\n\n## 参考文档来源\n" + "\n".join([f"- {name}" for name in ref_list])

    if state.get("final_answer") and len(state["final_answer"]) > SUMMARY_DRAFT_MIN_LEN:
        print("summary_node：复用reflect草稿，仅做润色")
        prompt = f"""已有草稿，润色整理成正式报告，不要完全重写。
草稿：{state['final_answer']}
原始用户问题：{state['user_query']}
报告末尾追加参考文档来源：
{ref_text}
"""
        try:
            resp = llm.invoke(prompt)
            print_token_usage(resp)
        except Exception as e:
            err_msg = f"summary_node LLM润色异常:{str(e)}"
            print(err_msg)
            write_trace_log({"level": "error", "node": "summary_node", "msg": err_msg})
            full_report = state["final_answer"] + ref_text + f"\n【润色异常:{str(e)}】"
            write_audit_log({
                "user_id": state.get("user_id", "anonymous"),
                "user_role": state.get("user_role", "operator"),
                "action": "query_completed",
                "status": "summary_llm_error",
                "query": state["user_query"],
                "ref_docs": state.get("ref_docs", []),
            })
            return {"final_answer": full_report}

        full_report = resp.content.strip()
        write_audit_log({
            "user_id": state.get("user_id", "anonymous"),
            "user_role": state.get("user_role", "operator"),
            "action": "query_completed",
            "status": "success",
            "query": state["user_query"],
            "ref_docs": state.get("ref_docs", []),
        })
        return {"final_answer": full_report}

    blocks = []
    for t in state["task_list"]:
        out = t.get("task_output")
        if out:
            blocks.append(f"### 任务{t['task_id']}：{t['desc']}\n{out[:SUMMARY_TASK_OUTPUT_TRUNC]}")
    all_blocks = "\n\n".join(blocks)
    prompt = SUMMARY_PROMPT.replace("{user_query}", state["user_query"])
    prompt = prompt.replace("{task_output_blocks}", all_blocks)
    try:
        resp = llm.invoke(prompt)
        print_token_usage(resp)
    except Exception as e:
        err_msg = f"summary_node LLM生成报告异常:{str(e)}"
        print(err_msg)
        write_trace_log({"level": "error", "node": "summary_node", "msg": err_msg})
        full_report = f"【生成报告失败】{str(e)}" + ref_text
        write_audit_log({
            "user_id": state.get("user_id", "anonymous"),
            "user_role": state.get("user_role", "operator"),
            "action": "query_completed",
            "status": "summary_llm_error",
            "query": state["user_query"],
            "ref_docs": state.get("ref_docs", []),
        })
        return {"final_answer": full_report}

    final_report = resp.content.strip()
    write_audit_log({
        "user_id": state.get("user_id", "anonymous"),
        "user_role": state.get("user_role", "operator"),
        "action": "query_completed",
        "status": "success",
        "query": state["user_query"],
        "ref_docs": state.get("ref_docs", []),
    })
    return {"final_answer": final_report}


def route_reflect(state: AgentState):
    if state["need_more_info"] is True:
        return "tool_decide_node"
    else:
        return "summary_node"


# 构建图
builder = StateGraph(AgentState)
builder.add_node("planner_node", planner_node)
builder.add_node("tool_decide_node", tool_decide_node)
builder.add_node("tool_exec_node", tool_exec_node)
builder.add_node("task_execute_node", task_execute_node)
builder.add_node("reflect_node", reflect_node)
builder.add_node("summary_node", summary_node)
builder.set_entry_point("planner_node")
builder.add_edge("planner_node", "tool_decide_node")
builder.add_edge("tool_decide_node", "tool_exec_node")
builder.add_edge("tool_exec_node", "task_execute_node")
builder.add_edge("task_execute_node", "reflect_node")
builder.add_conditional_edges("reflect_node", route_reflect)
builder.add_edge("summary_node", END)
app = builder.compile()


# ========== 模块级模型预热 ==========
_global_warmup_done = False

def _warmup_models():
    """加载模型 + 真跑一次检索，消除所有首次调用开销"""
    global _global_warmup_done
    if _global_warmup_done:
        return
    try:
        import time as _time
        print("【模块预热】开始加载 Embedding + Reranker 模型...")
        _t0 = _time.time()

        _ = _get_vector_db()
        _ = get_reranker()

        print("【模块预热】执行一次真实检索（消除首次调用开销）...")
        _ = chroma_search("预热查询")
        print("【模块预热】真实检索完成")

        _global_warmup_done = True
        print(f"【模块预热】完成，耗时 {_time.time() - _t0:.2f}s")
    except Exception as e:
        print(f"【模块预热】失败（不影响主流程）：{e}")

_warmup_models()
# ========== 模块预热结束 ==========


# ========== 流式输出辅助函数 ==========
NODE_LABELS = {
    "planner_node":       "正在拆解问题...",
    "tool_decide_node":   "正在选择工具...",
    "tool_exec_node":     "正在检索知识库...",
    "task_execute_node":  "正在生成子答案...",
    "reflect_node":       "正在反思校验...",
    "summary_node":       "正在整理最终答案...",
}

PROGRESS_PREFIX = "[PROGRESS]"


# ---------- 深度模式（六节点工作流，异步流式） ----------
async def stream_agent(user_query: str, case_id: str = "stream", user_role: str = "admin"):
    """深度模式：六节点 Reflection Loop，带进度反馈 + 正文流式"""
    init_state: AgentState = {
        "user_query": user_query,
        "case_id": case_id,
        "user_id": "stream_user",
        "user_role": user_role,
        "task_list": [],
        "current_task": None,
        "context_local_kb": "",
        "context_from_web": "",
        "think_trace": [],
        "raw_tool_obs": [],
        "intermediate_answer": "",
        "final_answer": "",
        "need_more_info": False,
        "loop_count": 0,
        "tavily_cache": {},
        "ref_docs": []
    }

    last_node = None
    async for event in app.astream_events(
        init_state,
        config={"recursion_limit": GRAPH_RECURSION_LIMIT},
        version="v2"
    ):
        kind = event["event"]
        node = event.get("metadata", {}).get("langgraph_node", "")

        if kind == "on_chain_start" and node in NODE_LABELS and node != last_node:
            last_node = node
            yield f"{PROGRESS_PREFIX}{NODE_LABELS[node]}"

        if kind == "on_chat_model_stream" and node == "summary_node":
            chunk = event["data"]["chunk"]
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content


# ---------- 快速模式（RAG + 单次 LLM） ----------
QUICK_PROMPT = """你是制造业MES业务专家。基于下面的参考资料回答用户问题。

【硬性要求】
- 回答控制在 150~250 字，不要超过 300 字
- 直接给结论和要点，不要铺垫、不要"综上所述"
- 用 2~4 个小节或 3~5 个要点，Markdown 格式
- 不要重复问题，不要写"根据参考资料"

参考资料：
{kb_ctx}

用户问题：{user_query}

回答："""


def quick_answer(user_query: str, user_role: str = "admin") -> str:
    """快速模式（非流式）：RAG + 单次 LLM，同步返回完整答案。"""
    try:
        kb_ctx, _ = chroma_search(user_query)
    except Exception as e:
        print(f"【快速模式】检索异常：{e}")
        kb_ctx = ""

    if not kb_ctx:
        kb_ctx = "（无参考资料，基于你的领域知识回答）"

    prompt = QUICK_PROMPT.replace("{kb_ctx}", kb_ctx[:800]).replace("{user_query}", user_query)
    resp = llm.invoke(prompt)
    return resp.content


def quick_answer_stream(user_query: str, user_role: str = "admin"):
    """快速模式（流式）：RAG + 单次 LLM，同步流式 yield token。"""
    try:
        kb_ctx, _ = chroma_search(user_query)
    except Exception as e:
        print(f"【快速流式】检索异常：{e}")
        kb_ctx = ""

    if not kb_ctx:
        kb_ctx = "（无参考资料，基于你的领域知识回答）"

    prompt = QUICK_PROMPT.replace("{kb_ctx}", kb_ctx[:800]).replace("{user_query}", user_query)
    for chunk in llm.stream(prompt):
        if hasattr(chunk, "content") and chunk.content:
            yield chunk.content
# ========== 流式输出辅助函数结束 ==========


# 主入口
if __name__ == "__main__":
    print("\n==== Graph Mermaid ====")
    print(app.get_graph().draw_mermaid())
    print("\n==== Running Agent ====\n")
    init_state: AgentState = {
        "case_id": "local_debug",
        "user_query": "工单 WO-20261007-001 现在什么状态？",
        "user_id": "local_user",
        "user_role": "admin",
        "task_list": [],
        "current_task": None,
        "context_local_kb": "",
        "context_from_web": "",
        "think_trace": [],
        "raw_tool_obs": [],
        "intermediate_answer": "",
        "final_answer": "",
        "need_more_info": False,
        "loop_count": 0,
        "tavily_cache": {},
        "ref_docs": []
    }
    trace_id = str(uuid.uuid4())
    trace_handler = AgentTraceHandler(trace_id)

    result = app.invoke(
        init_state,
        config={
            "recursion_limit": GRAPH_RECURSION_LIMIT,
            "callbacks": [trace_handler]
        }
    )
    final_report = result["final_answer"]
    print("\n====完整最终报告====\n")
    print(final_report)