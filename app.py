"""
MES 业务分析 Agent - Streamlit Web 界面
运行：streamlit run app.py
"""
import os

# ========== 关键：必须在 import graph_agent_skeleton 之前设置 ==========
# Streamlit 环境没有终端 input，必须自动批准联网搜索
os.environ["AUTO_APPROVE_SEARCH"] = "true"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import streamlit as st
import time
from datetime import datetime

# 导入 Agent
from graph_agent_skeleton import app as agent_app, AgentState


# ==================== 页面配置 ====================
st.set_page_config(
    page_title="MES 业务分析 Agent",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==================== 自定义样式 ====================
st.markdown("""
<style>
    .main-title {
        font-size: 2.2em;
        font-weight: bold;
        color: #2c3e50;
        margin-bottom: 0.2em;
    }
    .sub-title {
        font-size: 1em;
        color: #7f8c8d;
        margin-bottom: 1.5em;
    }
    .metric-box {
        background-color: #f8f9fa;
        padding: 10px 15px;
        border-radius: 8px;
        border-left: 4px solid #3498db;
        margin-bottom: 10px;
    }
    .stChatMessage {
        padding: 10px;
    }
</style>
""", unsafe_allow_html=True)


# ==================== 辅助函数：判断是否需要上下文 ====================
def needs_context(query: str) -> bool:
    """判断问题是否需要上下文（指代词/追问词）"""
    pronouns = ["它", "他", "她", "这个", "那个", "这些", "那些", "该", "此", "上述", "刚才", "之前"]
    followup = ["详细说说", "展开", "继续", "还有呢", "然后呢", "举个例子", "再说说"]

    if len(query) < 20 and any(p in query for p in pronouns):
        return True
    if len(query) < 15 and any(f in query for f in followup):
        return True
    return False


# ==================== 侧边栏 ====================
with st.sidebar:
    st.markdown("### 🏭 MES 业务分析 Agent")
    st.markdown("基于 LangGraph 的制造业 MES 领域智能助手")
    st.divider()

    # 项目信息
    st.markdown("#### 📌 核心能力")
    st.markdown("""
    - 六节点工作流编排
    - RAG 知识库检索
    - 双层拒答机制
    - 多轮对话支持
    - Eval 评估体系
    - 多层安全兜底
    """)

    st.divider()

    # 技术栈
    st.markdown("#### 🛠️ 技术栈")
    st.markdown("""
    `LangGraph` `LangChain` `DeepSeek`
    `BGE` `Chroma` `Tavily` `LangSmith`
    """)

    st.divider()

    # 示例问题
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

    # 清空对话
    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()

    # 用户角色选择
    st.markdown("#### 👤 用户角色")
    user_role = st.selectbox(
        "选择角色",
        ["operator", "supervisor", "admin"],
        index=1,
        help="operator：只能查本地知识库；supervisor/admin：可以联网"
    )

    st.caption("GitHub: [Wang-qi-git/langgraph-mes-business-agent](https://github.com/Wang-qi-git/langgraph-mes-business-agent)")


# ==================== 主区域 ====================
st.markdown('<div class="main-title">🏭 MES 业务分析 Agent</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">输入制造业 MES 相关问题，Agent 自动检索知识库并输出结构化分析报告（支持多轮追问）</div>', unsafe_allow_html=True)


# ==================== 初始化会话状态 ====================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_query" not in st.session_state:
    st.session_state.pending_query = None


# ==================== 渲染历史对话 ====================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑" if msg["role"] == "user" else "🤖"):
        st.markdown(msg["content"])

        # 如果有元数据（耗时、参考文档），展示
        if msg.get("meta"):
            with st.expander("📊 查看执行详情", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("耗时", f"{msg['meta'].get('elapsed', 0):.1f}s")
                with col2:
                    st.metric("参考文档", len(msg["meta"].get("ref_docs", [])))

                if msg["meta"].get("ref_docs"):
                    st.markdown("**参考文档来源：**")
                    for doc in msg["meta"]["ref_docs"]:
                        st.markdown(f"- {doc}")

        # 下载按钮
        if msg["role"] == "assistant" and msg.get("downloadable"):
            st.download_button(
                label="📥 下载报告 (Markdown)",
                data=msg["content"],
                file_name=f"mes_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                key=f"dl_{id(msg)}",
            )


# ==================== 输入框 ====================
user_input = st.chat_input("请输入 MES 相关问题...")

# 处理侧边栏示例按钮点击
if st.session_state.pending_query:
    user_input = st.session_state.pending_query
    st.session_state.pending_query = None


# ==================== 处理用户输入 ====================
if user_input:
    # 1. 显示用户消息
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(user_input)

    # 2. 判断是否需要拼接历史
    if needs_context(user_input) and len(st.session_state.messages) > 1:
        # 只取最近 2 轮对话（不含当前问题）
        recent = st.session_state.messages[-4:-1]
        history_text = "\n".join([
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:150]}"
            for m in recent
        ])
        history_text = history_text[:300]  # 硬上限 300 字
        full_query = f"【上文】\n{history_text}\n\n【当前】\n{user_input}"
    else:
        full_query = user_input

    # 3. 调用 Agent
    with st.chat_message("assistant", avatar="🤖"):
        with st.status("🤖 Agent 运行中...", expanded=True) as status:
            if full_query != user_input:
                st.write("💡 检测到追问，已携带上下文")
            st.write("📋 Planner 正在拆解任务...")

            start_time = time.time()

            # 构建初始状态
            init_state: AgentState = {
                "case_id": f"web_{int(time.time())}",
                "user_query": full_query,
                "user_id": "web_user",
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
                result = agent_app.invoke(
                    init_state,
                    config={"recursion_limit": 80},
                )
                final_answer = result.get("final_answer", "【无输出】")
                ref_docs = result.get("ref_docs", [])
                elapsed = time.time() - start_time

                status.update(
                    label=f"✅ 分析完成（耗时 {elapsed:.1f}s）",
                    state="complete",
                    expanded=False,
                )

                # 显示结果
                st.markdown(final_answer)

                # 执行详情
                with st.expander("📊 查看执行详情", expanded=False):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("耗时", f"{elapsed:.1f}s")
                    with col2:
                        st.metric("参考文档", len(ref_docs))

                    if ref_docs:
                        st.markdown("**参考文档来源：**")
                        for doc in ref_docs:
                            st.markdown(f"- {doc}")

                # 下载按钮
                st.download_button(
                    label="📥 下载报告 (Markdown)",
                    data=final_answer,
                    file_name=f"mes_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                )

                # 保存到历史
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": final_answer,
                    "meta": {"elapsed": elapsed, "ref_docs": ref_docs},
                    "downloadable": True,
                })

            except Exception as e:
                status.update(label="❌ 执行失败", state="error", expanded=True)
                error_msg = f"【执行异常】{str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg,
                    "meta": {"elapsed": time.time() - start_time, "ref_docs": []},
                })


# ==================== 页脚 ====================
st.divider()
st.caption(
    "⚡ Powered by LangGraph + DeepSeek + BGE + Chroma  |  "
    "📦 [GitHub 开源项目](https://github.com/Wang-qi-git/langgraph-mes-business-agent)"
)