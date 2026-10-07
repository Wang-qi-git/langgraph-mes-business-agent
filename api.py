"""
MES 业务分析 Agent - FastAPI 服务
启动：uvicorn api:api --host 0.0.0.0 --port 8000
"""
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["AUTO_APPROVE_SEARCH"] = "true"  # API 模式自动批准联网

import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from graph_agent_skeleton import app as agent_app, AgentState


api = FastAPI(
    title="MES 业务分析 Agent API",
    description="基于 LangGraph 的制造业 MES 领域智能助手",
    version="1.0.0",
)


class ChatRequest(BaseModel):
    query: str
    case_id: str = "api_call"


class ChatResponse(BaseModel):
    answer: str
    ref_docs: list
    elapsed: float
    case_id: str


@api.get("/")
def root():
    return {
        "service": "MES 业务分析 Agent",
        "status": "running",
        "docs": "/docs",
    }


@api.get("/health")
def health():
    return {"status": "ok"}


@api.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """单次问答接口"""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    start = time.time()
    init_state: AgentState = {
        "case_id": req.case_id,
        "user_query": req.query,
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
        "ref_docs": [],
    }

    try:
        result = agent_app.invoke(
            init_state,
            config={"recursion_limit": 80},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 执行失败：{str(e)}")

    return ChatResponse(
        answer=result.get("final_answer", ""),
        ref_docs=result.get("ref_docs", []),
        elapsed=round(time.time() - start, 2),
        case_id=req.case_id,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=8000)