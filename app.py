import streamlit as st
import os
from agent_demo import (
    run_workflow,
    init_kb,
    embedding,
    KB_FILE,
    persist_path,
    _KB_INITIALIZED
)

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

st.set_page_config(page_title="MES智能制造知识库智能Agent｜作品集演示Demo", layout="wide")
st.title("MES智能制造知识库智能Agent｜作品集演示Demo")

# ==========会话状态初始化==========
if "kb_ready" not in st.session_state:
    with st.spinner("正在加载私有知识库..."):
        init_kb()
        st.session_state.kb_ready = True

# 对话历史存储
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# =========侧边栏知识库管理=========
with st.sidebar:
    st.header("知识库管理")
    st.markdown("方式1：本地kb.md私有业务知识库")
    if st.button("重新加载私有知识库"):
        init_kb()
        st.success("✅知识库重新加载完成")
    st.divider()
    st.markdown("方式2：上传PDF临时业务文档")
    uploaded_pdf = st.file_uploader("上传PDF文档", type=["pdf"])
    if uploaded_pdf is not None:
        if st.button("解析PDF并加载"):
            temp_path = "./temp_upload.pdf"
            with open(temp_path, "wb") as f:
                f.write(uploaded_pdf.getbuffer())
            loader = PyPDFLoader(temp_path)
            pages = loader.load()
            splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
            chunks = splitter.split_documents(pages)
            from langchain_chroma import Chroma
            vs = Chroma(persist_directory=persist_path, embedding_function=embedding)
            vs.add_documents(chunks)
            st.success(f"✅PDF解析完成，生成 {len(chunks)} 个切片")
    st.divider()
    if st.button("清空对话历史"):
        st.session_state.chat_history.clear()
        st.rerun()

# =========渲染历史对话==========
st.subheader("📜历史对话记录")
for idx, (q, a, trace_data) in enumerate(st.session_state.chat_history):
    st.markdown(f"**👤提问：** {q}")
    st.markdown(f"**📋输出结果：**\n{a}")
    with st.expander("🔍查看Agent内部工作过程"):
        st.markdown(f"**调度Agent分类：** {trace_data['route_type']}")
        st.markdown("**检索素材片段：**")
        for doc_text in trace_data["retrieve_docs"]:
            st.code(doc_text, language="text")
        st.markdown(f"**事实校验结果：** {trace_data['fact_check']}")
        st.markdown(f"**是否使用联网搜索：** {trace_data['has_web_source']}")
    st.divider()

# =========业务提问区==========
st.subheader("业务提问输入")
user_query = st.text_area(
    "请输入你的问题，支持问答、分析、生成Markdown报告",
    placeholder="示例：解释OEE指标；写一份MES可信报工风险评估报告",
    height=140
)
submit_btn = st.button("🚀执行Agent工作流", type="primary")

if submit_btn and user_query.strip():
    with st.spinner("Agent流水线执行：检索→调度路由→事实校验→生成报告，稍等..."):
        resp = run_workflow(user_query.strip())

    # 关键修复：判断返回是字符串还是字典，防止 TypeError string indices must be integers
    if isinstance(resp, str):
        result = resp
        trace_info = {
            "route_type": "直接返回字符串",
            "retrieve_docs": [],
            "fact_check": "无",
            "has_web_source": False
        }
    else:
        result = resp["final_answer"]
        trace_info = resp["trace"]

    # 存入会话：问题、答案、trace完整过程
    st.session_state.chat_history.append((user_query.strip(), result, trace_info))

    st.markdown("---")
    st.subheader("📋Agent输出结果")
    st.markdown(result)

    # 下载Markdown报告按钮
    st.download_button(
        label="📥下载Markdown报告",
        data=result,
        file_name="mes_agent_report.md",
        mime="text/markdown"
    )

    # 当前这一轮的工作过程展开面板
    with st.expander("🔍查看Agent内部工作过程"):
        st.markdown(f"**调度Agent分类：** {trace_info['route_type']}")
        st.markdown("**检索素材片段：**")
        for doc_text in trace_info["retrieve_docs"]:
            st.code(doc_text, language="text")
        st.markdown(f"**事实校验结果：** {trace_info['fact_check']}")
        st.markdown(f"**是否使用联网搜索：** {trace_info['has_web_source']}")

else:
    st.info("输入业务问题，点击按钮运行Agent")
