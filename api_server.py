"""
MES 业务分析 Agent - FastAPI 后端服务（v5.0 带 JWT 认证）
启动：uvicorn api_server:api --host 0.0.0.0 --port 8000
"""
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["AUTO_APPROVE_SEARCH"] = "true"

import time
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from graph_agent_skeleton import (
    app as agent_app,
    AgentState,
    quick_answer,
    quick_answer_stream,
    get_cache_stats,
)
import session_store
import auth


api = FastAPI(
    title="MES 业务分析 Agent API",
    description="制造业 MES 领域智能助手（JWT 认证 + 多会话隔离）",
    version="5.0.0",
)


# ==================== 数据模型 ====================
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    name: str


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
    # 注意：不再接收 user_role，从 JWT token 解析


class ChatResponse(BaseModel):
    answer: str
    elapsed: float
    mode: str
    session_id: str


# ==================== 上下文拼接 ====================
def needs_context(query: str) -> bool:
    pronouns = ["它", "他", "她", "这个", "那个", "这些", "那些", "该", "此", "上述", "刚才", "之前"]
    followup = ["详细说说", "展开", "继续", "还有呢", "然后呢", "举个例子", "再说说"]
    if len(query) < 20 and any(p in query for p in pronouns):
        return True
    if len(query) < 15 and any(f in query for f in followup):
        return True
    return False


def build_query_with_context(query: str, history: list[dict]) -> str:
    if not history:
        return query
    recent = history[-4:]
    if not recent:
        return query
    if not needs_context(query):
        return query
    history_text = "\n".join([
        f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:150]}"
        for m in recent
    ])
    return f"【上文】\n{history_text[:300]}\n\n【当前】\n{query}"


# ==================== 基础端点 ====================
@api.get("/")
def root():
    return {
        "service": "MES Agent",
        "status": "running",
        "version": "5.0.0",
    }


@api.get("/health")
def health():
    return {"status": "ok", "ready": True}


# ==================== 认证端点 ====================
@api.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    """登录：返回 JWT token"""
    if not auth.verify_password(req.username, req.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = auth.create_access_token(req.username)
    info = auth.get_user_info(req.username)
    return LoginResponse(
        access_token=token,
        username=info["username"],
        role=info["role"],
        name=info["name"],
    )


@api.get("/auth/me")
def me(user: dict = Depends(auth.get_current_user)):
    """获取当前用户信息（用于验证 token）"""
    return user


# ==================== 会话管理（需登录） ====================
@api.post("/session/new", response_model=NewSessionResponse)
def new_session(user: dict = Depends(auth.get_current_user)):
    sid = session_store.create_session(user["username"])
    return NewSessionResponse(session_id=sid)


@api.get("/session/{sid}/messages", response_model=HistoryResponse)
def get_history(
    sid: str,
    limit: int = 20,
    user: dict = Depends(auth.get_current_user),
):
    if not session_store.session_belongs_to(sid, user["username"]):
        raise HTTPException(status_code=403, detail="无权访问该会话")
    msgs = session_store.get_messages(sid, limit=limit)
    return HistoryResponse(
        session_id=sid,
        messages=[MessageItem(**m) for m in msgs],
    )


@api.post("/session/{sid}/clear")
def clear_history(
    sid: str,
    user: dict = Depends(auth.get_current_user),
):
    if not session_store.session_belongs_to(sid, user["username"]):
        raise HTTPException(status_code=403, detail="无权访问该会话")
    session_store.clear_session(sid)
    return {"ok": True, "session_id": sid}


# ==================== 快速模式 ====================
@api.post("/quick", response_model=ChatResponse)
def quick_chat(
    req: ChatRequest,
    user: dict = Depends(auth.get_current_user),
):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    if not session_store.session_belongs_to(req.session_id, user["username"]):
        raise HTTPException(status_code=403, detail="无权访问该会话")

    user_role = user["role"]   # ← 从 token 解析

    history = session_store.get_messages(req.session_id, limit=10)
    full_query = build_query_with_context(req.query, history)

    start = time.time()
    try:
        answer = quick_answer(full_query, user_role=user_role)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行失败：{str(e)}")

    session_store.append_message(req.session_id, "user", req.query)
    session_store.append_message(req.session_id, "assistant", answer)

    return ChatResponse(
        answer=answer,
        elapsed=round(time.time() - start, 2),
        mode="快速",
        session_id=req.session_id,
    )


@api.post("/quick/stream")
async def quick_stream(
    req: ChatRequest,
    user: dict = Depends(auth.get_current_user),
):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    if not session_store.session_belongs_to(req.session_id, user["username"]):
        raise HTTPException(status_code=403, detail="无权访问该会话")

    user_role = user["role"]
    history = session_store.get_messages(req.session_id, limit=10)
    full_query = build_query_with_context(req.query, history)
    session_store.append_message(req.session_id, "user", req.query)

    def event_gen():
        full_answer = ""
        try:
            for chunk in quick_answer_stream(full_query, user_role=user_role):
                full_answer += chunk
                safe = chunk.replace("\n", "\\n")
                yield f"data: {safe}\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
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
def deep_chat(
    req: ChatRequest,
    user: dict = Depends(auth.get_current_user),
):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    if not session_store.session_belongs_to(req.session_id, user["username"]):
        raise HTTPException(status_code=403, detail="无权访问该会话")

    user_role = user["role"]
    history = session_store.get_messages(req.session_id, limit=10)
    full_query = build_query_with_context(req.query, history)

    start = time.time()
    init_state: AgentState = {
        "case_id": f"api_{req.session_id}",
        "user_query": full_query,
        "user_id": user["username"],
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


# ==================== 缓存统计 ====================
@api.get("/stats/cache")
def cache_stats(user: dict = Depends(auth.get_current_user)):
    return get_cache_stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=8000)