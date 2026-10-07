"""
MES 业务分析 Agent - Streamlit 前端（调 FastAPI 后端）
运行：streamlit run streamlit_app.py
"""
import streamlit as st
import requests
import time
from datetime import datetime

# ⚠️ 必须用 127.0.0.1，不要用 localhost（Windows 上会走 IPv6 超时）
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
</style>
""", unsafe_allow_html=True)


# ==================== 工具函数 ====================
def check_backend() -> bool:
    try:
        r = requests.get(f"{API_BASE}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def needs_context(query: str) -> bool:
    pronouns = ["它", "他", "她", "这个", "那个", "这些", "那些", "该", "此", "上述", "刚才", "之前"]
    followup = ["详细说说", "展开", "继续", "还有呢", "然后呢", "举个例子", "再说说"]
    if len(query) < 20 and any(p in query for p in pronouns):
        return True
    if len(query) < 15 and any(f in query for f in followup):
        return True
    return False


def stream_from_api(query: str, user_role: str):
    """从 FastAPI SSE 端点流式读取 token"""
    with requests.post(
        f"{API_BASE}/quick/stream",
        json={"query": query, "user_role": user_role},
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
            # 还原被转义的换行
            content = content.replace("\\n", "\n")
            yield content


# ==================== 侧边栏 ====================
with st.sidebar:
    st.markdown("### 🏭 MES 业务分析 Agent")
    st.markdown("基于 LangGraph 的制造业 MES 领域智能助手")
    st.divider()

    if check_backend():
        st.success("✅ 后端服务在线")
    else:
        st.error("❌ 后端服务离线\n\n请先启动：\n`uvicorn api_server:api --port 8000`")

    st.divider()

    st.markdown("#### ⚡ 回答模式")
    mode = st.radio(
        "选择模式",
        ["⚡ 快速模式（流式，首字 2~3s）", "🔍 深度模式（40~60s）"],
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

    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()

    st.markdown("#### 👤 用户角色")
    user_role = st.selectbox("选择角色", ["operator", "supervisor", "admin"], index=2)


# ==================== 主区域 ====================
st.markdown('<div class="main-title">🏭 MES 业务分析 Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">快速模式流式输出，深度模式输出结构化长报告</div>', unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_query" not in st.session_state:
    st.session_state.pending_query = None


# ==================== 渲染历史 ====================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])
        if msg.get("meta"):
            with st.expander("📊 执行详情", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("耗时", f"{msg['meta'].get('elapsed', 0):.1f}s")
                with col2:
                    st.metric("模式", msg['meta'].get('mode', '-'))


# ==================== 输入 ====================
user_input = st.chat_input("请输入 MES 相关问题...")

if st.session_state.pending_query:
    user_input = st.session_state.pending_query
    st.session_state.pending_query = None


# ==================== 处理输入 ====================
if user_input:
    if not check_backend():
        st.error("❌ 后端服务未启动，请先运行：`uvicorn api_server:api --port 8000`")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_input)

    # 上下文拼接
    if needs_context(user_input) and len(st.session_state.messages) > 1:
        recent = st.session_state.messages[-4:-1]
        history_text = "\n".join([
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:150]}"
            for m in recent
        ])
        full_query = f"【上文】\n{history_text[:300]}\n\n【当前】\n{user_input}"
    else:
        full_query = user_input

    with st.chat_message("assistant", avatar="🤖"):
        mode_label = "快速" if is_quick else "深度"

        if is_quick:
            # ============ 快速模式：SSE 流式 ============
            status_placeholder = st.empty()
            answer_placeholder = st.empty()
            status_placeholder.info("⏳ 正在检索并生成...")

            start = time.time()
            full_answer = ""
            first_token_ts = None

            try:
                for chunk in stream_from_api(full_query, user_role):
                    if first_token_ts is None:
                        first_token_ts = time.time()
                        status_placeholder.success(
                            f"⏳ 首字延迟 {first_token_ts - start:.2f}s（正在生成...）"
                        )
                    full_answer += chunk
                    answer_placeholder.markdown(full_answer)

                elapsed = time.time() - start
                first_lat = (first_token_ts - start) if first_token_ts else elapsed
                status_placeholder.success(
                    f"✅ 完成（首字 {first_lat:.2f}s / 总 {elapsed:.2f}s）"
                )

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
                    "meta": {"elapsed": elapsed, "mode": mode_label},
                })

            except Exception as e:
                status_placeholder.error(f"❌ 失败：{str(e)}")

        else:
            # ============ 深度模式：非流式 ============
            with st.spinner("⏳ 深度分析中（六节点工作流，约 40~60s）..."):
                try:
                    start = time.time()
                    resp = requests.post(
                        f"{API_BASE}/deep",
                        json={"query": full_query, "user_role": user_role},
                        timeout=180,
                    )
                    elapsed = time.time() - start

                    if resp.status_code == 200:
                        data = resp.json()
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
                            "meta": {"elapsed": elapsed, "mode": mode_label},
                        })
                    else:
                        st.error(f"❌ 后端错误 {resp.status_code}: {resp.text}")
                except Exception as e:
                    st.error(f"❌ 请求异常：{str(e)}")


st.divider()
st.caption("⚡ Powered by LangGraph + DeepSeek + BGE + Chroma")