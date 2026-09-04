from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv
import os
import json
import re

load_dotenv()

# --------------------------配置区--------------------------
PERSIST_DIR = "./chroma_db"
LLM_MODEL = "deepseek-chat"
EMBED_MODEL = "text-embedding-ada-002"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

llm = ChatOpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=DEEPSEEK_BASE_URL,
    model=LLM_MODEL,
    temperature=0
)

embedding = OpenAIEmbeddings(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=DEEPSEEK_BASE_URL,
    model=EMBED_MODEL
)

vector_store = Chroma(persist_directory=PERSIST_DIR, embedding_function=embedding)
retriever = vector_store.as_retriever(search_kwargs={"k":3})

# --------------------------状态定义--------------------------
class AgentState(TypedDict):
    user_query: str
    kb_context: Annotated[list, operator.add]
    llm_output: str

# --------------------------节点1：planner 任务拆解--------------------------
def planner_node(state:AgentState):
    query = state["user_query"]
    prompt = f"""
你是任务拆解器，把用户问题判断是否需要查询本地知识库。
用户问题：{query}
只输出JSON：{{"need_kb":true/false}}
"""
    resp = llm.invoke(prompt)
    raw = re.search(r"\{.*\}", resp.content, re.DOTALL)
    need_kb = True
    if raw:
        j = json.loads(raw.group())
        need_kb = j.get("need_kb", True)

    kb_context = []
    if need_kb:
        docs = retriever.invoke(query)
        kb_context = [d.page_content for d in docs]
    return {"kb_context": kb_context}

# --------------------------节点2：answer生成回答--------------------------
def answer_node(state:AgentState):
    query = state["user_query"]
    context = "\n---\n".join(state["kb_context"])
    prompt = f"""
参考下面知识库内容回答用户问题，知识库为空就凭模型知识回答。
【知识库】
{context}
【用户问题】
{query}
直接输出答案。
"""
    res = llm.invoke(prompt)
    return {"llm_output": res.content}

# --------------------------构建LangGraph--------------------------
builder = StateGraph(AgentState)
builder.add_node("planner", planner_node)
builder.add_node("answer", answer_node)

builder.set_entry_point("planner")
builder.add_edge("planner", "answer")
builder.add_edge("answer", END)

graph = builder.compile()

# --------------------------运行入口--------------------------
if __name__ == "__main__":
    user_input = "帮我分析MES系统紧急插单会带来哪些风险"
    result = graph.invoke({"user_query": user_input})
    print("\n====输出结果====\n")
    print(result["llm_output"])
