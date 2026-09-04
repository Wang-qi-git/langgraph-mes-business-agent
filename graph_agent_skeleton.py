from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
import json
import re
from tavily import TavilyClient
# ==========新增本地向量库导入==========
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceBgeEmbeddings

load_dotenv()
# ====================== 全局可调常量 ======================
MAX_LOOP = 4
CONTEXT_MAX_LEN = 6000
REFLECT_TASK_OUTPUT_TRUNC = 500
SUMMARY_TASK_OUTPUT_TRUNC = 1200
SUMMARY_DRAFT_MIN_LEN = 100
TRACE_MAX_ITEMS = 50
GRAPH_RECURSION_LIMIT = 20
CHROMA_PERSIST_DIR = "./chroma_db"
CHROMA_TOP_K = 3

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1",
    temperature=0
)
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# ==========本地BGE Embedding + Chroma初始化==========
model_name = "BAAI/bge-small-zh-v1.5"
model_kwargs = {"device": "cpu"}
encode_kwargs = {"normalize_embeddings": True}
embedding = HuggingFaceBgeEmbeddings(
    model_name=model_name,
    model_kwargs=model_kwargs,
    encode_kwargs=encode_kwargs
)
vector_db = Chroma(
    persist_directory=CHROMA_PERSIST_DIR,
    embedding_function=embedding
)



def chroma_search(query: str) -> str:
    """本地向量库检索"""
    docs = vector_db.similarity_search(query, k=CHROMA_TOP_K)
    if not docs:
        return ""
    chunks = [doc.page_content for doc in docs]
    return "\n\n".join(chunks)

def tavily_search(query: str, cache: dict) -> tuple[str, dict]:
    """
    返回(搜索结果,更新后的cache)，缓存不使用全局变量
    """
    cache_key = query.strip()
    if cache_key in cache:
        return cache[cache_key], cache
    resp = tavily.search(query=query, max_results=2)
    contents = []
    for item in resp["results"]:
        contents.append(f"标题:{item['title']}\n摘要:{item['content'][:600]}")
    result = "\n---\n".join(contents)
    new_cache = cache.copy()
    new_cache[cache_key] = result
    return result, new_cache

# ====================================================
class AgentState(TypedDict):
    user_query: str
    task_list: list[dict]
    current_task: dict | None
    context_local_kb: str    # 本地知识库结果
    context_from_web: str
    think_trace: Annotated[list[str], operator.add]
    raw_tool_obs: Annotated[list[str], operator.add]
    intermediate_answer: str
    final_answer: str
    need_more_info: bool
    block_flag: bool
    loop_count: int
    tavily_cache: dict

PLANNER_PROMPT = """
拆分为2‑4个粗粒度任务，禁止细碎任务。输出纯JSON。
{{"tasks":[{{"task_id":int,"desc":"任务描述","status":"pending"}}]}}
用户问题：{user_query}
"""

TOOL_DECIDE_PROMPT = """
任务：{task_desc}
已有本地知识库KB：{kb_ctx}
已有Web：{web_ctx}
工具三选一：chroma_search / tavily_search / no_tool。
优先使用chroma_search查询本地知识库；本地无有效信息再选择tavily_search联网；已有信息足够就选no_tool，避免多余搜索。
输出JSON：{{"tool":"xxx","tool_query":"xxx"}}
"""

TASK_EXECUTE_PROMPT = """
基于素材完成该子任务输出，不要回答整体问题。
任务：{task_desc}
本地KB：{kb_ctx}
Web：{web_ctx}
"""

REFLECT_REPLAN_PROMPT = """
反思重规划。用户问题：{user_query}
任务列表：{task_list_payload}
KB片段：{kb_snippet}
Web片段：{web_snippet}
规则：
1.任务保持粗粒度，status仅pending/completed。
2.质量校验：completed任务输出幻觉/信息不足则改为pending重跑；合格保留completed。
3.返回JSON禁止携带大段task_output。
4.有pending任务：need_more_info=true，final_answer=""。
5.全部completed且校验通过：need_more_info=false，输出final_answer草稿。
仅输出JSON：
{{
  "task_list": [{{"task_id":int,"desc":"str","status":"pending|completed"}}],
  "need_more_info": true|false,
  "final_answer": ""
}}
"""

SUMMARY_PROMPT = """
原始问题：{user_query}
子任务片段：{task_output_blocks}
基于上面内容输出完整通顺报告。
如果已有草稿可以直接复用、润色，不要完全重写。
"""

def extract_json(text: str):
    """带兜底降级，解析失败返回None，上层做容错"""
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
    prompt = PLANNER_PROMPT.format(user_query=state["user_query"])
    resp = llm.invoke(prompt)
    data = extract_json(resp.content)
    if data is None or "tasks" not in data:
        task_list = [{"task_id":1, "desc":f"回答用户问题：{state['user_query']}", "status":"pending"}]
    else:
        task_list = data.get("tasks", [])
    trace = f"planner：生成{len(task_list)}个粗粒度任务"
    think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [trace]
    return {
        "task_list": task_list,
        "think_trace": think_trace,
        "loop_count": 0
    }

def tool_decide_node(state: AgentState):
    print("【tool_decide_node】工具决策")
    pending = [t for t in state["task_list"] if t["status"] == "pending"]
    if not pending:
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + ["tool_decide：无pending任务"]
        return {"current_task": None, "think_trace": think_trace}
    curr_task = pending[0].copy()
    prompt = TOOL_DECIDE_PROMPT.format(
        task_desc=curr_task["desc"],
        kb_ctx=state["context_local_kb"],
        web_ctx=state["context_from_web"]
    )
    resp = llm.invoke(prompt)
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
    return {
        "current_task": curr_task,
        "think_trace": think_trace
    }

def tool_exec_node(state: AgentState):
    print("【tool_exec_node】执行工具")
    curr = state["current_task"]
    if not curr or curr["tool_name"] == "no_tool":
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + ["tool_exec：no_tool，跳过工具调用"]
        return {"think_trace": think_trace}
    new_local_kb = state["context_local_kb"]
    new_web = state["context_from_web"]
    obs_list = []
    tavily_cache = state["tavily_cache"].copy()

    if curr["tool_name"] == "chroma_search":
        res = chroma_search(curr["tool_query"])
        if res:
            new_local_kb += "\n" + res
            if len(new_local_kb) > CONTEXT_MAX_LEN:
                new_local_kb = new_local_kb[-CONTEXT_MAX_LEN:]
        obs_list.append(f"chroma_search 返回:{res[:200]}...")
    elif curr["tool_name"] == "tavily_search":
        res, tavily_cache = tavily_search(curr["tool_query"], tavily_cache)
        if res:
            new_web += "\n" + res
            if len(new_web) > CONTEXT_MAX_LEN:
                new_web = new_web[-CONTEXT_MAX_LEN:]
        obs_list.append(f"tavily_search 返回:{res[:200]}...")

    think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + obs_list
    raw_tool_obs = state["raw_tool_obs"][-TRACE_MAX_ITEMS:] + obs_list
    return {
        "context_local_kb": new_local_kb,
        "context_from_web": new_web,
        "tavily_cache": tavily_cache,
        "raw_tool_obs": raw_tool_obs,
        "think_trace": think_trace
    }

def task_execute_node(state: AgentState):
    print("【task_execute_node】执行业务任务与校验")
    curr = state["current_task"]
    task_list = [t.copy() for t in state["task_list"]]
    if not curr:
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + ["task_execute：无当前任务"]
        return {"think_trace": think_trace}
    prompt = TASK_EXECUTE_PROMPT.format(
        task_desc=curr["desc"],
        kb_ctx=state["context_local_kb"],
        web_ctx=state["context_from_web"]
    )
    resp = llm.invoke(prompt)
    output_text = resp.content.strip()
    for idx, t in enumerate(task_list):
        if t["task_id"] == curr["task_id"]:
            task_list[idx]["status"] = "completed"
            task_list[idx]["task_output"] = output_text
            break
    trace = f"task_execute task{curr['task_id']} 生成子任务输出"
    think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [trace]
    return {
        "task_list": task_list,
        "intermediate_answer": output_text,
        "current_task": None,
        "think_trace": think_trace
    }

def reflect_node(state: AgentState):
    print("【reflect_node】反思+动态重规划（含输出质量校验）")
    loop_cnt = state["loop_count"]
    task_list = [t.copy() for t in state["task_list"]]
    pending = [t for t in task_list if t["status"] == "pending"]
    if loop_cnt >= MAX_LOOP and len(pending) == 0:
        msg = f"reflect：达到最大迭代{MAX_LOOP}次，全部任务完成"
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [msg]
        return {
            "need_more_info": False,
            "final_answer": "",
            "think_trace": think_trace,
            "loop_count": loop_cnt + 1
        }
    elif loop_cnt >= MAX_LOOP and len(pending) > 0:
        warn_msg = f"reflect警告：达到最大迭代{MAX_LOOP}次，仍存在{len(pending)}个pending任务，强制结束迭代"
        print(warn_msg)
        for idx, t in enumerate(task_list):
            if t["status"] == "pending":
                task_list[idx]["status"] = "completed"
                task_list[idx]["task_output"] = "【达到最大迭代次数，该任务未充分执行】"
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [warn_msg]
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
    prompt = REFLECT_REPLAN_PROMPT.format(
        user_query=state["user_query"],
        task_list_payload=json.dumps(llm_payload, ensure_ascii=False),
        kb_snippet=kb_snippet,
        web_snippet=web_snippet
    )
    resp = llm.invoke(prompt)
    re_data = extract_json(resp.content)
    if re_data is None:
        trace_msg = "reflect：JSON解析失败，停止迭代"
        think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [trace_msg]
        return {
            "task_list": task_list,
            "need_more_info": False,
            "final_answer": "",
            "think_trace": think_trace,
            "loop_count": loop_cnt + 1
        }
    updated_tasks = re_data.get("task_list", [])
    need_more = re_data.get("need_more_info", True)
    draft_final = re_data.get("final_answer", "")
    id2orig = {t["task_id"]: t for t in task_list}
    merged = []
    seen_ids = set()
    for st in updated_tasks:
        tid = st["task_id"]
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        if tid in id2orig:
            orig = id2orig[tid].copy()
            orig["desc"] = st["desc"]
            orig["status"] = st["status"]
            merged.append(orig)
        else:
            merged.append(st)
    trace_msg = f"reflect：need_more_info={need_more},返回任务数{len(merged)}"
    think_trace = state["think_trace"][-TRACE_MAX_ITEMS:] + [trace_msg]
    return {
        "task_list": merged,
        "need_more_info": need_more,
        "final_answer": draft_final,
        "think_trace": think_trace,
        "loop_count": loop_cnt + 1
    }

def summary_node(state: AgentState):
    print("【summary_node】生成最终完整报告")
    if state.get("final_answer") and len(state["final_answer"]) > SUMMARY_DRAFT_MIN_LEN:
        print("summary_node：复用reflect草稿，仅做润色")
        prompt = f"""已有草稿，润色整理成正式报告，不要大段重写。
草稿：{state['final_answer']}
原始问题：{state['user_query']}
"""
        resp = llm.invoke(prompt)
        return {"final_answer": resp.content.strip()}
    blocks = []
    for t in state["task_list"]:
        out = t.get("task_output")
        if out:
            blocks.append(f"### 任务{t['task_id']}：{t['desc']}\n{out[:SUMMARY_TASK_OUTPUT_TRUNC]}")
    all_blocks = "\n\n".join(blocks)
    prompt = SUMMARY_PROMPT.format(user_query=state["user_query"], task_output_blocks=all_blocks)
    resp = llm.invoke(prompt)
    return {"final_answer": resp.content.strip()}

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
builder.add_conditional_edges("reflect_node", route_reflect, {
    "tool_decide_node": "tool_decide_node",
    "summary_node": "summary_node"
})
builder.add_edge("summary_node", END)
app = builder.compile()

if __name__ == "__main__":
    print("\n==== Graph Mermaid ====")
    print(app.get_graph().draw_mermaid())
    print("\n==== Running Agent ====\n")
    init_state: AgentState = {
        "user_query": "帮我分析MES系统紧急插单会带来哪些风险",
        "task_list": [],
        "current_task": None,
        "context_local_kb": "",
        "context_from_web": "",
        "think_trace": [],
        "raw_tool_obs": [],
        "intermediate_answer": "",
        "final_answer": "",
        "need_more_info": False,
        "block_flag": False,
        "loop_count": 0,
        "tavily_cache": {}
    }
    result = app.invoke(init_state, config={"recursion_limit": GRAPH_RECURSION_LIMIT})
    print("\n====完整最终报告====\n")
    print(result["final_answer"])
