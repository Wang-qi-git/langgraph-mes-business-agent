"""
MES 业务分析 Agent - FastAPI 后端服务
启动：uvicorn api_server:api --host 0.0.0.0 --port 8000

端点：
  GET  /health                       健康检查
  POST /session/new                  创建新会话，返回 sid
  GET  /session/{sid}/messages       获取会话历史
  POST /session/{sid}/clear          清空会话
  POST /quick                        快速模式（非流式）
  POST /quick/stream                 快速模式（SSE 流式）
  POST /deep                         深度模式
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
import session_store


api = FastAPI(
    title="MES 业务分析 Agent API",
    description="制造业 MES 领域智能助手（支持多会话隔离）",
    version="3.0.0",
)


# ==================== 数据模型 ====================
class NewSessionResponse(BaseModel):
    session_id: str


class MessageItem(BaseModel):
    role: str
    content: str
    created_at: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[MessageItem]


class ChatRequest(BaseModel):
    query: str
    session_id: str
    user_role: str = "admin"


class ChatResponse(BaseModel):
    answer: str
    elapsed: float
    mode: str
    session_id: str


# ==================== 上下文拼接 ====================
def needs_context(query: str) -> bool:
    """判断问题是否需要拼接历史上下文"""
    pronouns = ["它", "他", "她", "这个", "那个", "这些", "那些", "该", "此", "上述", "刚才", "之前"]
    followup = ["详细说说", "展开", "继续", "还有呢", "然后呢", "举个例子", "再说说"]
    if len(query) < 20 and any(p in query for p in pronouns):
        return True
    if len(query) < 15 and any(f in query for f in followup):
        return True
    return False


def build_query_with_context(query: str, history: list[dict]) -> str:
    """按需拼接历史上下文"""
    if not history:
        return query

    # 取最近 2 轮（4 条消息），不含当前问题
    recent = history[-4:]
    if not recent:
        return query

    if not needs_context(query):
        return query

    history_text = "\n".join([
        f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:150]}"
        for m in recent
    ])
    history_text = history_text[:300]
    return f"【上文】\n{history_text}\n\n【当前】\n{query}"


# ==================== 基础端点 ====================
@api.get("/")
def root():
    return {
        "service": "MES Agent",
        "status": "running",
        "version": "3.0.0",
        "endpoints": [
            "/health",
            "/session/new",
            "/session/{sid}/messages",
            "/session/{sid}/clear",
            "/quick",
            "/quick/stream",
            "/deep",
        ],
    }


@api.get("/health")
def health():
    return {"status": "ok", "ready": True}


# ==================== 会话管理 ====================
@api.post("/session/new", response_model=NewSessionResponse)
def new_session():
    """创建新会话，返回 session_id"""
    sid = session_store.create_session()
    return NewSessionResponse(session_id=sid)


@api.get("/session/{sid}/messages", response_model=HistoryResponse)
def get_history(sid: str, limit: int = 20):
    """获取会话历史"""
    msgs = session_store.get_messages(sid, limit=limit)
    return HistoryResponse(
        session_id=sid,
        messages=[MessageItem(**m) for m in msgs],
    )


@api.post("/session/{sid}/clear")
def clear_history(sid: str):
    """清空会话历史"""
    session_store.clear_session(sid)
    return {"ok": True, "session_id": sid}


@api.get("/sessions")
def list_sessions(limit: int = 20):
    """列出最近活跃的会话（调试用）"""
    return {"sessions": session_store.list_sessions(limit=limit)}


# ==================== 快速模式 ====================
@api.post("/quick", response_model=ChatResponse)
def quick_chat(req: ChatRequest):
    """快速模式（非流式）"""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id 不能为空")

    # 拼接上下文
    history = session_store.get_messages(req.session_id, limit=10)
    full_query = build_query_with_context(req.query, history)

    start = time.time()
    try:
        answer = quick_answer(full_query, user_role=req.user_role)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行失败：{str(e)}")

    # 存储对话（存原始 query，不存拼接过上下文的）
    session_store.append_message(req.session_id, "user", req.query)
    session_store.append_message(req.session_id, "assistant", answer)

    return ChatResponse(
        answer=answer,
        elapsed=round(time.time() - start, 2),
        mode="快速",
        session_id=req.session_id,
    )


@api.post("/quick/stream")
async def quick_stream(req: ChatRequest):
    """快速模式 SSE 流式"""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id 不能为空")

    # 拼接上下文
    history = session_store.get_messages(req.session_id, limit=10)
    full_query = build_query_with_context(req.query, history)

    # 先存用户消息（这样即使流式中断也能留下记录）
    session_store.append_message(req.session_id, "user", req.query)

    def event_gen():
        full_answer = ""
        try:
            for chunk in quick_answer_stream(full_query, user_role=req.user_role):
                full_answer += chunk
                safe = chunk.replace("\n", "\\n")
                yield f"data: {safe}\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            # 流式结束后存完整回答
            if full_answer:
                session_store.append_message(req.session_id, "assistant", full_answer)
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ==================== 深度模式 ====================
@api.post("/deep", response_model=ChatResponse)
def deep_chat(req: ChatRequest):
    """深度模式：六节点 Reflection Loop"""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    if not req.session_id:
        raise HTTPException(status_code=400, detail="session_id 不能为空")

    history = session_store.get_messages(req.session_id, limit=10)
    full_query = build_query_with_context(req.query, history)

    start = time.time()
    init_state: AgentState = {
        "case_id": f"api_{req.session_id}",
        "user_query": full_query,
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

    answer = result.get("final_answer", "")
    session_store.append_message(req.session_id, "user", req.query)
    session_store.append_message(req.session_id, "assistant", answer)

    return ChatResponse(
        answer=answer,
        elapsed=round(time.time() - start, 2),
        mode="深度",
        session_id=req.session_id,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=8000)