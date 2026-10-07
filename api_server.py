"""
MES 业务分析 Agent - FastAPI 后端服务
启动：uvicorn api_server:api --host 0.0.0.0 --port 8000

端点：
  POST /quick         快速模式（非流式，3~15s）
  POST /quick/stream  快速模式（SSE 流式，首字 2~3s）
  POST /deep          深度模式（40~60s）
"""
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["AUTO_APPROVE_SEARCH"] = "true"

import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from graph_agent_skeleton import (
    app as agent_app,
    AgentState,
    quick_answer,
    quick_answer_stream,
)


api = FastAPI(
    title="MES 业务分析 Agent API",
    description="制造业 MES 领域智能助手",
    version="2.1.0",
)


class ChatRequest(BaseModel):
    query: str
    user_role: str = "admin"


class ChatResponse(BaseModel):
    answer: str
    elapsed: float
    mode: str


@api.get("/")
def root():
    return {
        "service": "MES Agent",
        "status": "running",
        "endpoints": ["/health", "/quick", "/quick/stream", "/deep"],
    }


@api.get("/health")
def health():
    return {"status": "ok", "ready": True}


@api.post("/quick", response_model=ChatResponse)
def quick_chat(req: ChatRequest):
    """快速模式（非流式）"""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    start = time.time()
    try:
        answer = quick_answer(req.query, user_role=req.user_role)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行失败：{str(e)}")

    return ChatResponse(
        answer=answer,
        elapsed=round(time.time() - start, 2),
        mode="快速",
    )


@api.post("/quick/stream")
async def quick_stream(req: ChatRequest):
    """快速模式 SSE 流式端点。
    帧格式：
      data: <正文片段>\\n\\n
      data: [DONE]\\n\\n
      data: [ERROR] <msg>\\n\\n
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    def event_gen():
        try:
            for chunk in quick_answer_stream(req.query, user_role=req.user_role):
                # SSE 里的换行必须转义
                safe = chunk.replace("\n", "\\n")
                yield f"data: {safe}\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@api.post("/deep", response_model=ChatResponse)
def deep_chat(req: ChatRequest):
    """深度模式：六节点 Reflection Loop"""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    start = time.time()
    init_state: AgentState = {
        "case_id": f"api_{int(time.time())}",
        "user_query": req.query,
        "user_id": "api_user",
        "user_role": req.user_role,
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
        result = agent_app.invoke(init_state, config={"recursion_limit": 80})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行失败：{str(e)}")

    return ChatResponse(
        answer=result.get("final_answer", ""),
        elapsed=round(time.time() - start, 2),
        mode="深度",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=8000)