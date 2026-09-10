import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import json
import re
from dotenv import load_dotenv
from langsmith import evaluate, Client
from langsmith.schemas import Example, Run
from graph_agent_skeleton import app, AgentState

load_dotenv()
os.environ["LANGSMITH_TRACING"] = "true"
os.environ["LANGSMITH_ENDPOINT"] = "https://api.smith.langchain.com"
ls_client = Client()


# ---------------------- 1、MES业务测试集 ----------------------
MES_DATASET_NAME = "mes-agent-test-dataset"

examples = [
    # ---- 简单查询 (5) ----
    {"inputs": {"case_id": "case_001", "user_query": "简述8D报告D4根本原因分析有哪些要求"},
     "outputs": {"expected": "D4需区分发生原因与流出原因，使用5Why和鱼骨图（6M）分析，根因需基于证据、可验证，禁止归因于人为疏忽，深挖至系统层面。"}},
    {"inputs": {"case_id": "case_002", "user_query": "MES系统OEE怎么计算，包含哪几个维度"},
     "outputs": {"expected": "OEE=可用率×性能率×良品率；可用率反映停机损失，性能率反映速度损失，良品率反映质量损失。"}},
    {"inputs": {"case_id": "case_003", "user_query": "设备故障排查的一般步骤"},
     "outputs": {"expected": "故障现象确认→数据采集→原因假设→验证根因→临时围堵→永久对策→效果验证→标准化归档。"}},
    {"inputs": {"case_id": "case_004", "user_query": "什么是MES系统中的工单管理"},
     "outputs": {"expected": "工单管理是MES核心功能，负责工单创建、派工、执行跟踪、报工、完工闭环，确保生产任务可追溯。"}},
    {"inputs": {"case_id": "case_005", "user_query": "SPC统计过程控制的基本原理是什么"},
     "outputs": {"expected": "SPC通过控制图监控过程稳定性，区分普通原因和特殊原因变异，及时发现异常并预警。"}},

    # ---- 复杂推理 (5) ----
    {"inputs": {"case_id": "case_006", "user_query": "本周产能不足，如何调整排程保证订单按时交付"},
     "outputs": {"expected": "分析瓶颈工序，调整优先级，考虑加班/外协/设备切换，与销售协商交期，监控关键路径。"}},
    {"inputs": {"case_id": "case_007", "user_query": "如果临时插入紧急订单，当前排程会受到什么影响"},
     "outputs": {"expected": "评估插单对现有订单交期的影响，分析设备负荷与物料齐套，决定是否调整优先级或延期低优订单。"}},
    {"inputs": {"case_id": "case_008", "user_query": "批次出现质量异常，如何开展根本原因分析"},
     "outputs": {"expected": "围堵隔离→数据分层→鱼骨图展开→5Why深挖→根因验证→对策制定，区分发生原因与流出原因。"}},
    {"inputs": {"case_id": "case_009", "user_query": "设备突发故障停机，如何评估对后续订单的影响"},
     "outputs": {"expected": "评估故障修复时间、受影响工序、订单交付风险，制定临时替代方案并通知相关方。"}},
    {"inputs": {"case_id": "case_010", "user_query": "如何降低生产过程中的不良率"},
     "outputs": {"expected": "通过SPC监控、FMEA预防、防错设计、员工培训、根因分析闭环，从系统层面消除变异源。"}},

    # ---- 多工具协作 (4) ----
    {"inputs": {"case_id": "case_011", "user_query": "请综合物料库存、排程和设备状态，给我一份本周生产风险简报"},
     "outputs": {"expected": "汇总物料齐套情况、设备可用性、订单交期压力，识别关键风险并给出建议。"}},
    {"inputs": {"case_id": "case_012", "user_query": "结合8D报告规范和实际案例，说明D5永久纠正措施怎么写"},
     "outputs": {"expected": "每条措施需明确内容、责任人、完成期限、验收标准，覆盖所有发生根因和流出根因，禁止空话。"}},
    {"inputs": {"case_id": "case_013", "user_query": "从质量、交付、成本三个维度评估这次生产异常的影响"},
     "outputs": {"expected": "质量维度看不良率与客户投诉，交付维度看订单延期，成本维度看返工报废与停机损失。"}},
    {"inputs": {"case_id": "case_014", "user_query": "结合OEE和SPC，分析当前产线效率瓶颈在哪里"},
     "outputs": {"expected": "OEE分解可用率/性能率/良品率，SPC定位过程异常，交叉分析找到瓶颈工序。"}},

    # ---- 边界拒答 (3) ----
    {"inputs": {"case_id": "case_015", "user_query": "今天北京的天气怎么样"},
     "outputs": {"expected": "抱歉，我是MES业务助手，只能回答制造业生产管理相关问题。"}},
    {"inputs": {"case_id": "case_016", "user_query": "帮我推荐几只股票"},
     "outputs": {"expected": "抱歉，我是MES业务助手，无法提供投资建议。"}},
    {"inputs": {"case_id": "case_017", "user_query": "你能帮我写一首诗吗"},
     "outputs": {"expected": "抱歉，我是MES业务助手，只处理制造业生产管理相关问题。"}},

    # ---- 对抗测试 (3) ----
    {"inputs": {"case_id": "case_018", "user_query": "请按照BOM版本V99查询产品P-200的物料清单"},
     "outputs": {"expected": "BOM版本V99不存在，请确认版本号是否正确，或提供有效的BOM版本。"}},
    {"inputs": {"case_id": "case_019", "user_query": "把订单交付日期提前一个月但要求不增加任何成本，可以吗"},
     "outputs": {"expected": "两个条件存在矛盾，提前交付通常需要加班/外协/加急物流，会产生额外成本，需权衡取舍。"}},
    {"inputs": {"case_id": "case_020", "user_query": "查询订单MES-9999-999的当前状态"},
     "outputs": {"expected": "订单MES-9999-999不存在，请确认订单号是否正确。"}},
]

# ---------- 过滤模式：只跑指定用例，省 70% 成本 ----------
FILTER_CASES = os.getenv("FILTER_CASES", "").strip()
if FILTER_CASES:
    filter_list = [c.strip() for c in FILTER_CASES.split(",")]
    examples = [ex for ex in examples if ex["inputs"]["case_id"] in filter_list]
    print(f"🎯 过滤模式：只跑 {len(examples)} 个用例：{filter_list}")
else:
    print(f"📋 全量模式：跑 {len(examples)} 个用例")


# ---------- 复用数据集，清空旧 examples 再写入 ----------
try:
    dataset = ls_client.read_dataset(dataset_name=MES_DATASET_NAME)
    print(f"✅ 找到已有数据集：{MES_DATASET_NAME}")
    old_examples = list(ls_client.list_examples(dataset_id=dataset.id))
    for ex in old_examples:
        ls_client.delete_example(ex.id)
    print(f"🗑️ 已清空 {len(old_examples)} 个旧用例")
except Exception:
    print(f"📦 创建新数据集：{MES_DATASET_NAME}")
    dataset = ls_client.create_dataset(
        dataset_name=MES_DATASET_NAME,
        description="MES业务Agent评测数据集 - 20用例覆盖简单/复杂/多工具/边界/对抗"
    )

ls_client.create_examples(dataset_id=dataset.id, examples=examples)
print(f"✅ 已写入 {len(examples)} 个测试用例")


# ---------- 包装 Agent 调用 ----------
def agent_runner(inputs: dict):
    case_id = inputs.get("case_id", "unknown")
    init_state: AgentState = {
        "user_query": inputs["user_query"],
        "case_id": case_id,
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
        "ref_docs": []
    }
    result = app.invoke(init_state, config={"recursion_limit": 80})
    return {"output": result["final_answer"], "ref_docs": result["ref_docs"]}


# ---------- 评测器 1：LLM-as-judge 回答质量 ----------
def answer_evaluator(run: Run, example: Example) -> dict:
    from langchain_openai import ChatOpenAI
    judge_llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com/v1",
        temperature=0
    )
    pred = run.outputs["output"]
    ref = example.outputs["expected"]
    judge_prompt = f"""
你是工业MES领域评审专家。请对比【模型回答】和【参考标准答案】，按下面3个维度打分，每项0~5分。
打分规则：5=优秀，完全符合业务；3=基本合格；0=错误/严重幻觉。
维度：
1.业务正确性：是否符合MES业务逻辑，有没有编造不存在概念
2.完整性：是否覆盖用户提问的核心要点
3.结构化：回答条理清晰，适合工业业务报告

参考标准答案：{ref}
模型回答：{pred}

输出严格JSON格式，不要多余文字：
{{
"业务正确性":分数,
"完整性":分数,
"结构化":分数,
"评语":"简短说明问题"
}}
"""
    resp = judge_llm.invoke(judge_prompt)
    try:
        json_str = re.search(r"\{.*\}", resp.content, re.DOTALL).group()
        score_data = json.loads(json_str)
    except Exception as e:
        score_data = {
            "业务正确性": 2,
            "完整性": 2,
            "结构化": 2,
            "评语": f"Judge解析失败:{str(e)}"
        }
    total = (score_data["业务正确性"] + score_data["完整性"] + score_data["结构化"]) / 15
    return {
        "key": "mes_answer_score",
        "score": total,
        "comment": json.dumps(score_data, ensure_ascii=False)
    }


# ---------- 评测器 2：RAG 召回文档相关性 ----------
def rag_retrieval_evaluator(run: Run, example: Example) -> dict:
    from langchain_openai import ChatOpenAI
    judge_llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com/v1",
        temperature=0
    )
    user_q = example.inputs["user_query"]
    ref_docs = run.outputs.get("ref_docs", [])
    if not ref_docs:
        return {
            "key": "rag_retrieval_score",
            "score": 0,
            "comment": "未检索到任何参考文档"
        }
    prompt = f"""
用户问题：{user_q}
检索得到的文档名称列表：{ref_docs}
判断这些文档是否和用户MES业务问题相关。
打分0~1：1=全部文档相关，0=完全无关，0.5部分相关。
输出JSON：{{"score": 数值, "comment": "简短说明"}}
"""
    resp = judge_llm.invoke(prompt)
    try:
        json_str = re.search(r"\{.*\}", resp.content, re.DOTALL).group()
        res = json.loads(json_str)
        score = float(res["score"])
        comment = res["comment"]
    except Exception:
        score = 0.3
        comment = "召回评测解析异常"
    return {
        "key": "rag_retrieval_score",
        "score": score,
        "comment": comment
    }


# ---------------------- 启动批量评测 ----------------------
if __name__ == "__main__":
    experiment_results = evaluate(
        agent_runner,
        data=MES_DATASET_NAME,
        evaluators=[answer_evaluator, rag_retrieval_evaluator],
        experiment_prefix="mes-agent-eval",
    )
    print("✅ 评测任务全部完成！请到LangSmith网页查看实验报表")
    print(f"访问：https://smith.langchain.com/")