"""
MES 业务分析 Agent - Streamlit 前端
支持多会话隔离（URL 带 session_id，刷新不丢）
运行：streamlit run streamlit_app.py
"""
import streamlit as st
import requests
import time
import uuid
from datetime import datetime

API_BASE = "http://127.0.0.1:8000"

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
        display: inline-block;
        background: #e3f2fd;
        color: #1565c0;
        padding: 2px 8px;
        border-radius: 4px;
        font-family: monospace;
        font-size: 0.85em;
    }
</style>
""", unsafe_allow_html=True)


# ==================== URL 参数工具（兼容新旧 Streamlit） ====================
def get_query_param(key: str, default=None):
    """读取 URL query 参数（兼容新旧 API）"""
    try:
        # Streamlit >= 1.30
        val = st.query_params.get(key)
        return val if val else default
    except Exception:
        # 老版本
        params = st.experimental_get_query_params()
        return params.get(key, [default])[0]


def set_query_param(key: str, value: str):
    """写入 URL query 参数"""
    try:
        st.query_params[key] = value
    except Exception:
        params = st.experimental_get_query_params()
        params[key] = value
        st.experimental_set_query_params(**params)


# ==================== 后端调用 ====================
def check_backend() -> bool:
    try:
        return requests.get(f"{API_BASE}/health", timeout=2).status_code == 200
    except Exception:
        return False


def create_new_session() -> str:
    r = requests.post(f"{API_BASE}/session/new", timeout=5)
    r.raise_for_status()
    return r.json()["session_id"]


def load_history(sid: str) -> list[dict]:
    try:
        r = requests.get(f"{API_BASE}/session/{sid}/messages", timeout=5)
        if r.status_code == 200:
            return r.json()["messages"]
    except Exception:
        pass
    return []


def clear_history(sid: str):
    try:
        requests.post(f"{API_BASE}/session/{sid}/clear", timeout=5)
    except Exception:
        pass


def stream_from_api(query: str, sid: str, user_role: str):
    """SSE 流式读取"""
    with requests.post(
        f"{API_BASE}/quick/stream",
        json={"query": query, "session_id": sid, "user_role": user_role},
        stream=True,
        timeout=120,
    ) as r:
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


# ==================== 会话初始化 ====================
# 从 URL 读 sid，没有就创建
if "session_id" not in st.session_state:
    existing_sid = get_query_param("sid")
    if existing_sid:
        st.session_state.session_id = existing_sid
    else:
        # 等后端就绪后再创建（第一次可能是离线）
        st.session_state.session_id = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_query" not in st.session_state:
    st.session_state.pending_query = None


# ==================== 侧边栏 ====================
with st.sidebar:
    st.markdown("### 🏭 MES 业务分析 Agent")
    st.markdown("基于 LangGraph 的制造业 MES 领域智能助手")
    st.divider()

    backend_ok = check_backend()

    if backend_ok:
        st.success("✅ 后端服务在线")
        # 确保有 session_id
        if st.session_state.session_id is None:
            st.session_state.session_id = create_new_session()
            set_query_param("sid", st.session_state.session_id)
            st.session_state.messages = []
            st.rerun()
    else:
        st.error("❌ 后端服务离线\n\n请先启动：\n`uvicorn api_server:api --port 8000`")

    # 显示当前会话 ID
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
        "SPC统计过程控制的基本原理是什么？",
        "设备故障排查的一般步骤？",
        "如何降低生产过程中的不良率？",
    ]
    for ex in examples:
        if st.button(ex, key=f"ex_{ex}", use_container_width=True):
            st.session_state.pending_query = ex

    st.divider()

    st.markdown("#### 👤 用户角色")
    user_role = st.selectbox("选择角色", ["operator", "supervisor", "admin"], index=2)


# ==================== 首次加载历史 ====================
# 如果本地 messages 为空但 session_id 存在，从后端加载（刷新恢复）
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
    '<div class="sub-title">多会话隔离 · 刷新不丢 · 快速 1s / 深度 60s</div>',
    unsafe_allow_html=True,
)


# ==================== 渲染历史 ====================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])


# ==================== 输入框 ====================
user_input = st.chat_input("请输入 MES 相关问题...")

if st.session_state.pending_query:
    user_input = st.session_state.pending_query
    st.session_state.pending_query = None


# ==================== 处理输入 ====================
if user_input:
    if not backend_ok:
        st.error("❌ 后端服务未启动，请先运行：`uvicorn api_server:api --port 8000`")
        st.stop()

    if not st.session_state.session_id:
        st.error("❌ 会话未初始化，请刷新页面")
        st.stop()

    # 显示用户消息
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_input)

    with st.chat_message("assistant", avatar="🤖"):
        mode_label = "快速" if is_quick else "深度"

        if is_quick:
            # 快速模式 SSE
            status_ph = st.empty()
            ans_ph = st.empty()
            status_ph.info("⏳ 正在检索并生成...")

            start = time.time()
            full_answer = ""
            first_ts = None

            try:
                for chunk in stream_from_api(
                    user_input,
                    st.session_state.session_id,
                    user_role,
                ):
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
            # 深度模式
            with st.spinner("⏳ 深度分析中（六节点工作流，约 40~60s）..."):
                try:
                    start = time.time()
                    r = requests.post(
                        f"{API_BASE}/deep",
                        json={
                            "query": user_input,
                            "session_id": st.session_state.session_id,
                            "user_role": user_role,
                        },
                        timeout=180,
                    )
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
st.caption("⚡ Powered by LangGraph + DeepSeek + BGE + Chroma · 会话隔离已启用")