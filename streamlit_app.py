"""
MES 业务分析 Agent - Streamlit 前端（v5.0 带 JWT 登录）
"""
import streamlit as st
import requests
import time
from datetime import datetime

import os
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="MES 业务分析 Agent",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-title { font-size: 2.2em; font-weight: bold; color: #2c3e50; }
    .sub-title { font-size: 1em; color: #7f8c8d; margin-bottom: 1.5em; }
    .session-tag {
        display: inline-block; background: #e3f2fd; color: #1565c0;
        padding: 2px 8px; border-radius: 4px; font-family: monospace; font-size: 0.85em;
    }
    .user-card {
        background: #f8f9fa; padding: 10px 12px; border-radius: 8px;
        border-left: 4px solid #4caf50; margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)


# ==================== URL 参数工具 ====================
def get_query_param(key: str, default=None):
    try:
        val = st.query_params.get(key)
        return val if val else default
    except Exception:
        params = st.experimental_get_query_params()
        return params.get(key, [default])[0]


def set_query_param(key: str, value: str):
    try:
        st.query_params[key] = value
    except Exception:
        params = st.experimental_get_query_params()
        params[key] = value
        st.experimental_set_query_params(**params)


# ==================== API 调用 ====================
def _headers() -> dict:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def check_backend() -> bool:
    try:
        return requests.get(f"{API_BASE}/health", timeout=2).status_code == 200
    except Exception:
        return False


def do_login(username: str, password: str):
    try:
        r = requests.post(
            f"{API_BASE}/auth/login",
            json={"username": username, "password": password},
            timeout=5,
        )
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def create_new_session() -> str:
    r = requests.post(f"{API_BASE}/session/new", headers=_headers(), timeout=5)
    if r.status_code == 401:
        st.session_state.token = None
        st.rerun()
    r.raise_for_status()
    return r.json()["session_id"]


def load_history(sid: str) -> list[dict]:
    try:
        r = requests.get(f"{API_BASE}/session/{sid}/messages", headers=_headers(), timeout=5)
        if r.status_code == 200:
            return r.json()["messages"]
    except Exception:
        pass
    return []


def clear_history(sid: str):
    try:
        requests.post(f"{API_BASE}/session/{sid}/clear", headers=_headers(), timeout=5)
    except Exception:
        pass


def stream_from_api(query: str, sid: str):
    """SSE 流式读取"""
    with requests.post(
        f"{API_BASE}/quick/stream",
        json={"query": query, "session_id": sid},
        headers=_headers(),
        stream=True,
        timeout=120,
    ) as r:
        if r.status_code == 401:
            st.session_state.token = None
            st.rerun()
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if not line.startswith("data: "):
                continue
            content = line[6:]
            if content == "[DONE]":
                break
            if content.startswith("[ERROR]"):
                raise RuntimeError(content[7:].strip())
            yield content.replace("\\n", "\n")


# ==================== 会话状态初始化 ====================
if "token" not in st.session_state:
    st.session_state.token = None
if "user_info" not in st.session_state:
    st.session_state.user_info = None
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None


# ==================== 登录页 ====================
if st.session_state.token is None:
    st.markdown("<h1 style='text-align:center;'>🏭 MES 业务分析 Agent</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#7f8c8d;'>请登录后使用</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if not check_backend():
            st.error("❌ 后端服务未启动，请先运行：\n`uvicorn api_server:api --port 8000`")
            st.stop()

        with st.form("login_form"):
            st.markdown("### 登录")
            username = st.text_input("用户名")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录", use_container_width=True)

            if submitted:
                if not username or not password:
                    st.warning("请输入用户名和密码")
                else:
                    info = do_login(username, password)
                    if info:
                        st.session_state.token = info["access_token"]
                        st.session_state.user_info = {
                            "username": info["username"],
                            "role": info["role"],
                            "name": info["name"],
                        }
                        st.rerun()
                    else:
                        st.error("用户名或密码错误")

        st.caption("**演示账号**：operator / op123　　supervisor / sup123　　admin / admin123")
    st.stop()


# ==================== 已登录：主界面 ====================
user_info = st.session_state.user_info
backend_ok = check_backend()


# ==================== 侧边栏 ====================
with st.sidebar:
    st.markdown("### 🏭 MES 业务分析 Agent")
    st.markdown("基于 LangGraph 的制造业 MES 领域智能助手")
    st.divider()

    # 用户信息卡
    st.markdown(
        f'<div class="user-card">'
        f'👤 <b>{user_info["name"]}</b><br>'
        f'<span style="color:#666;font-size:0.9em;">角色：{user_info["role"]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if st.button("🚪 退出登录", use_container_width=True):
        st.session_state.token = None
        st.session_state.user_info = None
        st.session_state.session_id = None
        st.session_state.messages = []
        st.rerun()

    st.divider()

    if backend_ok:
        st.success("✅ 后端服务在线")
        if st.session_state.session_id is None:
            st.session_state.session_id = create_new_session()
            set_query_param("sid", st.session_state.session_id)
            st.session_state.messages = []
            st.rerun()
    else:
        st.error("❌ 后端服务离线")

    if st.session_state.session_id:
        st.markdown(
            f'当前会话：<span class="session-tag">{st.session_state.session_id}</span>',
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🆕 新会话", use_container_width=True):
                new_sid = create_new_session()
                st.session_state.session_id = new_sid
                set_query_param("sid", new_sid)
                st.session_state.messages = []
                st.rerun()
        with col2:
            if st.button("🗑️ 清空", use_container_width=True):
                clear_history(st.session_state.session_id)
                st.session_state.messages = []
                st.rerun()

    st.divider()

    st.markdown("#### ⚡ 回答模式")
    mode = st.radio(
        "选择模式",
        ["⚡ 快速模式（1~3s）", "🔍 深度模式（40~60s）"],
        index=0,
        label_visibility="collapsed",
    )
    is_quick = mode.startswith("⚡")

    st.divider()

    st.markdown("#### 💡 示例问题")
    examples = [
        "什么是MES系统中的工单管理？",
        "简述8D报告D4根本原因分析有哪些要求？",
        "工单 WO-20261007-001 现在什么状态？",
        "哪些物料低于安全库存？",
        "现在有哪些设备报警？",
    ]
    for ex in examples:
        if st.button(ex, key=f"ex_{ex}", use_container_width=True):
            st.session_state.pending_query = ex


# ==================== 首次加载历史 ====================
if (
    st.session_state.session_id
    and not st.session_state.messages
    and backend_ok
):
    history = load_history(st.session_state.session_id)
    if history:
        st.session_state.messages = [
            {"role": m["role"], "content": m["content"]}
            for m in history
        ]


# ==================== 主区域 ====================
st.markdown('<div class="main-title">🏭 MES 业务分析 Agent</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">JWT 认证 · 多会话隔离 · 快速 1s / 深度 60s</div>',
    unsafe_allow_html=True,
)

for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])

user_input = st.chat_input("请输入 MES 相关问题...")

if st.session_state.pending_query:
    user_input = st.session_state.pending_query
    st.session_state.pending_query = None


# ==================== 处理输入 ====================
if user_input:
    if not backend_ok:
        st.error("❌ 后端服务未启动")
        st.stop()

    if not st.session_state.session_id:
        st.error("❌ 会话未初始化，请刷新页面")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_input)

    with st.chat_message("assistant", avatar="🤖"):
        mode_label = "快速" if is_quick else "深度"

        if is_quick:
            status_ph = st.empty()
            ans_ph = st.empty()
            status_ph.info("⏳ 正在检索并生成...")

            start = time.time()
            full_answer = ""
            first_ts = None

            try:
                for chunk in stream_from_api(user_input, st.session_state.session_id):
                    if first_ts is None:
                        first_ts = time.time()
                        status_ph.success(f"⏳ 首字 {first_ts - start:.2f}s...")
                    full_answer += chunk
                    ans_ph.markdown(full_answer)

                elapsed = time.time() - start
                first_lat = (first_ts - start) if first_ts else elapsed
                status_ph.success(f"✅ 完成（首字 {first_lat:.2f}s / 总 {elapsed:.2f}s）")

                st.download_button(
                    label="📥 下载答案 (Markdown)",
                    data=full_answer,
                    file_name=f"mes_answer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                    key=f"dl_{int(time.time()*1000)}",
                )

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_answer,
                })

            except Exception as e:
                status_ph.error(f"❌ 失败：{str(e)}")

        else:
            with st.spinner("⏳ 深度分析中（六节点工作流，约 40~60s）..."):
                try:
                    start = time.time()
                    r = requests.post(
                        f"{API_BASE}/deep",
                        json={"query": user_input, "session_id": st.session_state.session_id},
                        headers=_headers(),
                        timeout=180,
                    )
                    if r.status_code == 401:
                        st.session_state.token = None
                        st.rerun()
                    elapsed = time.time() - start

                    if r.status_code == 200:
                        data = r.json()
                        full_answer = data["answer"]
                        st.markdown(full_answer)
                        st.success(f"✅ 深度模式完成（耗时 {elapsed:.1f}s）")

                        st.download_button(
                            label="📥 下载答案 (Markdown)",
                            data=full_answer,
                            file_name=f"mes_answer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                            mime="text/markdown",
                            key=f"dl_{int(time.time()*1000)}",
                        )

                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": full_answer,
                        })
                    else:
                        st.error(f"❌ 后端错误 {r.status_code}: {r.text}")
                except Exception as e:
                    st.error(f"❌ 请求异常：{str(e)}")


st.divider()
st.caption("🔐 JWT 认证 · ⚡ Powered by LangGraph + DeepSeek + BGE + Chroma")