import streamlit as st
import os
from dotenv import load_dotenv
from pathlib import Path

# 直接导入编译完成的LangGraph graph对象
from graph_agent_skeleton import graph

# 加载.env环境变量
load_dotenv(".env")

st.set_page_config(
    page_title="AI‑Agent 作品集演示Demo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 深色主题CSS
css = """
<style>
*{box-sizing:border-box;}
.stApp {background-color:#17171a;color:#eee;}
header[data-testid="stHeader"]{display:none !important;}
[data-testid="stSidebar"]{background-color:#212127;}
div[data-testid="stChatMessage-user"]{
    background-color:#2550ea;
    border-radius:16px 16px 4px 16px;
    padding:12px 16px;
    margin:8px 0;
}
div[data-testid="stChatMessage-assistant"]{
    background-color:#2a2a33;
    border-radius:16px 16px 16px 4px;
    padding:12px 16px;
    margin:8px 0;
}
</style>
"""
st.markdown(css, unsafe_allow_html=True)

# 侧边栏
with st.sidebar:
    st.title("🤖 AI Agent Demo")
    st.markdown("**作品集演示：LangGraph + RAG + Tavily搜索 + 报告生成**")
    st.divider()

    uploaded_pdf = st.file_uploader("上传PDF知识库", type=["pdf"])
    pdf_save_dir = Path("./pdf_docs")
    pdf_save_dir.mkdir(exist_ok=True)

    if uploaded_pdf is not None:
        save_path = pdf_save_dir / uploaded_pdf.name
        with open(save_path, "wb") as f:
            f.write(uploaded_pdf.getbuffer())
        st.success(f"已保存:{uploaded_pdf.name}，重启程序载入向量库")

    st.divider()
    if st.button("🔄 清空对话会话"):
        st.session_state.chat_history = []
        st.rerun()

# 初始化会话记忆
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# 渲染历史对话
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            if msg.get("thinking_log"):
                with st.status("🔍 Agent思考&执行过程", expanded=False):
                    st.write(msg["thinking_log"])
        st.markdown(msg["content"])
        if msg.get("report_md"):
            st.download_button(
                label="📥 下载生成报告(Markdown)",
                data=msg["report_md"],
                file_name="agent_generated_report.md",
                mime="text/markdown"
            )

# 聊天输入框
user_query = st.chat_input(placeholder="输入问题，Agent联网搜索+PDF私有知识库，输出分析报告...")

if user_query:
    st.session_state.chat_history.append({"role":"user","content":user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.status("🤖 Agent运行中：检索/搜索/推理...", expanded=True) as status:
            # 调用LangGraph
            inputs = {"question": user_query}
            result = graph.invoke(inputs)

            thinking_text = result.get("thinking_log", "无执行日志")
            answer_text = result.get("final_answer", "")
            report_content = result.get("report_content", "")

            status.update(label="✅ 执行完成", state="complete", expanded=False)

        st.markdown(answer_text)
        if report_content:
            st.download_button(
                label="📥 下载生成报告(Markdown)",
                data=report_content,
                file_name="agent_generated_report.md",
                mime="text/markdown"
            )

    st.session_state.chat_history.append({
        "role":"assistant",
        "content": answer_text,
        "thinking_log": thinking_text,
        "report_md": report_content
    })
    st.rerun()
