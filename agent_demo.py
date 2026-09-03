# 模块全局变量
_KB_INITIALIZED = False
retriever = None

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
import os
import re
import json
from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
from langchain_tavily import TavilySearch
from langchain_chroma import Chroma
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HOME"] = r"D:\hf_cache"
load_dotenv()

llm = ChatDeepSeek(model="deepseek-chat", timeout=60)
embedding = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"}
)

# --------------------------
# 工具层
# --------------------------
@tool
def calculator_calculate(a: float, b: float, op: str) -> str:
    """
    通用计算器工具，支持 + - * /
    :param a: 数字1
    :param b: 数字2
    :param op: 运算符，可选:"+","-","*","/"
    :return: 计算结果文本
    """
    if op == "+":
        res = a + b
    elif op == "-":
        res = a - b
    elif op == "*":
        res = a * b
    elif op == "/":
        if b == 0:
            return """
==== 计算器计算结果 ====
输入：{a} / {b}
结果：除数不能为0
"""
        res = a / b
    else:
        return "不支持的运算符"
    return f"""
==== 计算器计算结果 ====
输入：{a} {op} {b}
结果：{res}
"""

# ============ 知识库配置（封装为函数，不在顶层自动执行） ============
KB_FILE = "kb.md"
persist_path = "./chroma_db"

def init_kb():
    """初始化本地知识库与向量库，需要手动调用；避免import自动执行删库重建
    注意：仅程序启动调用一次，运行期间禁止重复调用，否则会引发向量库异常
    """
    global retriever, _KB_INITIALIZED
    try:
        with open(KB_FILE, "r", encoding="utf-8") as f:
            md_content = f.read()
    except FileNotFoundError:
        raise RuntimeError(f"缺失知识库文件 {KB_FILE}，请确认文件存在于程序根目录")
    except UnicodeDecodeError:
        raise RuntimeError(f"{KB_FILE} 文件编码错误，请使用utf‑8保存")

    documents = [Document(page_content=md_content)]
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    split_docs = text_splitter.split_documents(documents)
    print(f"实际生成chunk数量： {len(split_docs)}")

    try:
        tmp_store = Chroma(
            persist_directory=persist_path,
            embedding_function=embedding
        )
        tmp_store.delete_collection()
        del tmp_store
        print("ℹ️已清除旧向量集合")
    except Exception:
        print("ℹ️无旧集合，直接新建")

    try:
        vector_store = Chroma.from_documents(
            documents=split_docs,
            embedding=embedding,
            persist_directory=persist_path
        )
    except Exception as e:
        raise RuntimeError(f"向量库初始化失败，请检查db目录是否损坏: {e}")

    print(f"向量库集合总条数： {vector_store._collection.count()}")
    print("✅kb.md知识库入库完成\n")
    retriever = vector_store.as_retriever(search_kwargs={"k": 2})
    _KB_INITIALIZED = True

def local_knowledge_search(query: str) -> str:
    global retriever
    if retriever is None:
        print("[local_knowledge_search] WARN retriever还未初始化")
        return ""
    docs = retriever.invoke(query)
    content = "\n".join([d.page_content for d in docs])
    if not content.strip():
        print("[local_knowledge_search] 检索返回为空")
    return content

tavily_tool = None
if os.environ.get("TAVILY_API_KEY"):
    tavily_tool = TavilySearch(max_results=3)
else:
    print("⚠️未配置TAVILY_API_KEY，联网搜索功能禁用")

def rule_based_check(text: str, is_from_web: bool = False):
    """
    本地零token规则校验
    :param text:待检测文本
    :param is_from_web: True=联网搜索来源，跳过数字幻觉检测
    :return: (is_block:bool, block_reasons:list)
    """
    import re
    block_reasons = []
    # --------1 违禁业务关键词拦截（无论数据源，全部生效）--------
    ban_keywords = [
        "面临挑战",
        "诸多挑战"
    ]
    for kw in ban_keywords:
        if kw in text:
            block_reasons.append(f"【违禁业务词】{kw}")
    # --------2 数字幻觉检测：联网来源直接跳过 --------
    if not is_from_web:
        num_pattern = re.compile(r"\d{4,}")
        num_matches = num_pattern.findall(text)
        if num_matches:
            block_reasons.append("【数字幻觉】")
    is_block = len(block_reasons) > 0
    return is_block, block_reasons

def judge_material_sufficient(user_query: str, local_material: str) -> bool:
    prompt = f"""
用户原始问题：{user_query}
已获取本地知识库素材：
{local_material}
任务：判断上面素材是否足够完整回答用户问题。
规则：
1.素材包含回答问题需要的关键信息，仅输出 SUFFICIENT
2.素材缺少核心信息，无法作答，仅输出 INSUFFICIENT
只允许输出这两个英文单词，不要多余文字，不要解释。
"""
    try:
        resp = llm.invoke(prompt, timeout=60)
        content_raw = resp.content or ""
        lines = content_raw.strip().splitlines()
        if not lines:
            return False
        first_line = lines[0]
        content = first_line.strip().strip("。.，, \n\r")
        return content == "SUFFICIENT"
    except Exception as e:
        print(f"[judge_material_sufficient llm调用异常]{e}")
        return False

def orchestrator_agent(user_query: str) -> dict:
    prompt = f"""
你是通用多智能体总控调度。
对用户问题分类，**只输出纯JSON，不要```json标记，不要解释文字，不要注释**。
question_type只能三选一：
simple：名词概念查询，只用本地知识库，不需要分析、校验、report
analysis：业务风险/逻辑推演，不需要完整markdown报告
report：输出完整Markdown正式报告
输出结构：
{{
  "question_type": "simple",
  "task_list": [{{"task_name":"xxx","task_desc":"xxx"}}]
}}
用户问题：{user_query}
"""
    try:
        resp = llm.invoke(prompt, timeout=60)
        raw = resp.content.strip() if resp.content else ""
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        data = json.loads(raw)
        if "task_list" not in data or not isinstance(data["task_list"], list) or len(data["task_list"]) == 0:
            data["task_list"] = [{"task_name": "default_task", "task_desc": "执行默认任务"}]
        if "question_type" not in data:
            data["question_type"] = "report"
        return data
    except Exception as e:
        print(f"[orchestrator json parse error] {e}，降级为report模式")
        return {
            "question_type": "report",
            "task_list": [{"task_name": "full_workflow", "task_desc": "执行完整流水线"}]
        }

def simple_qa(user_q: str, refs: str) -> str:
    prompt = f"""
你是问答助手，严格依据提供的参考资料回答用户问题。
参考资料：
{refs}
硬性规则：
1.只允许使用上面参考资料里面存在的信息作答；
2.资料没有覆盖的内容，直接如实回复：【现有知识库缺少该部分信息】，**禁止调用你本身的内部知识进行编造补充**；
3.回答简洁精炼，不要多余扩展，不要输出不在资料内的观点。
用户问题：{user_q}
"""
    try:
        resp = llm.invoke(prompt, timeout=60)
        print("====传入simple_qa的refs====\n", refs)
        return resp.content if resp.content is not None else ""
    except Exception as e:
        print(f"[simple_qa llm异常]{e}")
        return "【系统异常：问答调用失败】"

def analyst_agent(task_desc: str, raw_material: str) -> str:
    prompt = f"""
【分析智能体‑领域专家】
任务：{task_desc}
原始资料素材：
{raw_material}
硬性规则：
1. **允许摘抄、拼接、同义精简多条分散事实；禁止主动生成大标题、总结段落；禁止自行编造原始素材不存在的章节标题、业务分类；尽量复用原文句式，只删减无效冗余内容；严禁做因果归因、严禁推导未来结论、严禁生成操作建议、严禁自创素材不存在的名词概念、营收、用户规模、策略总结。**
2. 素材不存在的内容，不要自行编造，不要调用内置外部知识；
3. 信息不足时，**仅输出固定文本：【现有知识库缺少该部分信息，无法完整分析】，禁止列举任何具体缺失的指标、字段、名词；**
4. 只做素材的整理合并，不允许推理延伸，不允许自己提炼业务维度。
5. 禁止凭空生成“面临挑战、发展难题、行业难题、业务风险、应对对策、应对方案、发展策略、行业策略”这类业务归纳；原始素材没有对应原文，就不要产出该类段落与标题。
"""
    try:
        resp = llm.invoke(prompt, timeout=60)
        return resp.content if resp.content is not None else ""
    except Exception as e:
        print(f"[analyst_agent llm异常]{e}")
        return "【现有知识库缺少该部分信息，无法完整分析】"

def validator_agent(analyst_content: str, original_material: str) -> dict:
    prompt = f"""
【校验智能体】
原始全部素材：
{original_material}
待校验文本：
{analyst_content}
判定规则：
✅允许：
1.对原文同义转述、精简摘要、重组语序；
2.对多条分散的已有事实做聚合概括，概括内容100%来自素材，不引入外部信息。
3.基于已有素材归纳标题、章节、原则分类，底层事实全部来源于素材，没有新增事实、因果推导、预测，则允许。
❌判定invalid触发条件（满足任意一条直接invalid）：
1. 新增素材不存在的事实、数据、金额、营收、占比、用户规模、名词；
2. 做因果归因、推导未来预测（单纯事实聚合概括不算）；
3. 将第三方行业现象改写为“我方应该做XX”操作建议；
4. 编造素材完全没有的观点、业务总结；
5. 出现数字、金额、用户量、营收类表述，在原始素材找不到原文出处；
6. 凭空生成素材不存在的业务归纳：面临挑战、发展难题、行业难题、业务风险、应对对策、应对方案、发展策略、行业策略，出现即invalid。
输出严格JSON，不要```，不要多余文字：
{{
  "status": "valid"|"invalid",
  "reason": "简短说明判定原因，如果valid写：内容全部来源于原始素材；如果invalid，写明哪一句话违反哪一条规则"
}}
"""
    try:
        resp = llm.invoke(prompt, timeout=60)
        raw = resp.content.strip() if resp.content else ""
        j = json.loads(raw)
        # 增加JSON字段完整性校验
        if "status" not in j or "reason" not in j:
            return {"status": "invalid", "reason": "校验JSON字段缺失，保守拦截"}
        return j
    except Exception as e:
        print(f"[validator json parse error] {e}")
        return {"status": "invalid", "reason": "校验输出解析失败，保守拦截"}

def report_agent(validated_content: str, user_query: str) -> str:
    prompt = f"""
【报告生成智能体】
已校验完成内容素材：
{validated_content}
用户原始提问：{user_query}
硬性规则：
1. **只对已有内容做Markdown章节排版，不新增、不引申、不归因、不补充任何素材以外信息；禁止自己生成结语、总结、额外说明段落；**
2. 如果传入内容中存在【现有知识库缺少该部分信息，无法完整分析】标记，原样保留该标记即可，**不允许扩展、不允许列举具体缺失的数据/指标名词；**
3. 不得修改原文语义，不能自创指标、策略、操作建议；
4. 不要自己追加“结语”“总结”板块。
"""
    try:
        resp = llm.invoke(prompt, timeout=60)
        return resp.content if resp.content is not None else ""
    except Exception as e:
        print(f"[report_agent llm异常]{e}")
        return "【报告生成异常】"

def run_workflow(user_input: str):
    global _KB_INITIALIZED, retriever
    # 惰性初始化：第一次调用自动加载知识库
    if not _KB_INITIALIZED:
        print("====触发惰性初始化init_kb====")
        init_kb()
        print(f"====初始化完成 _KB_INITIALIZED={_KB_INITIALIZED}, retriever is None? {retriever is None}====")
    if not isinstance(user_input, str) or len(user_input.strip()) == 0:
        return "错误：输入不能为空字符串"
    print(f"[调度Agent]收到用户输入：{user_input}\n")
    schedule = orchestrator_agent(user_input)
    q_type = schedule.get("question_type", "report")
    task_list = schedule.get("task_list", [])
    # 防御：task_list为空时兜底
    if not isinstance(task_list, list) or len(task_list) == 0:
        task_list = [{"task_name": "default_task", "task_desc": "执行默认任务"}]

    local_material = local_knowledge_search(user_input)
    full_material = local_material
    has_web_source = False
    is_sufficient = judge_material_sufficient(user_input, local_material)
    is_sufficient_after_web = False

    if not is_sufficient:
        if tavily_tool is not None:
            print("[充足度判断]本地素材不足，执行联网搜索补充\n")
            try:
                web_result = tavily_tool.invoke({"query": user_input})
                web_text_parts = []
                # 健壮兼容：部分版本返回直接是list
                if isinstance(web_result, list):
                    res_list = web_result
                else:
                    res_list = web_result.get("results") or []
                for item in res_list:
                    cnt = item.get("content", "").strip()
                    if cnt:
                        web_text_parts.append(f"【网页片段】\n{cnt}")
                if len(web_text_parts) == 0:
                    print("[Tavily] 搜索返回0条有效结果")
                web_content = "\n\n".join(web_text_parts)
                full_material = f"====本地知识库素材====\n{local_material}\n\n====联网搜索素材====\n{web_content}"
                has_web_source = True
                # ✅联网拿到素材后，二次判断素材充足度
                is_sufficient_after_web = judge_material_sufficient(user_input, full_material)
                print(f"[充足度判断]补充联网素材后充足度：{is_sufficient_after_web}")
            except Exception as e:
                print(f"[Tavily调用异常] {e}")
                full_material = f"====本地知识库素材====\n{local_material}\n\n====联网搜索素材====\n【联网调用失败】"
                has_web_source = True  # 异常分支同样标记经过联网流程
        else:
            print("[充足度判断]本地素材不足，但联网搜索未启用\n")
            full_material = f"====本地知识库素材====\n{local_material}\n\n====联网搜索素材====\n无（未配置TAVILY_API_KEY）"
    else:
        print("[充足度判断]本地素材充足，跳过联网\n")

    # 联网后素材充足，强制切simple问答分支
    if is_sufficient_after_web:
        q_type = "simple"

    final_result = ""
    if q_type == "simple":
        qa_out = simple_qa(user_input, full_material)
        # ✅传递has_web_source
        is_block, block_reasons = rule_based_check(qa_out, is_from_web=has_web_source)
        if is_block:
            print(f"⚠️simple模式规则层拦截，reason:{block_reasons}")
            final_result = f"【检测到LLM生成幻觉，已拦截】\n校验原因：{block_reasons}"
        else:
            final_result = qa_out
    elif q_type == "analysis":
        output_segments = []
        for task in task_list:
            task_desc = task.get("task_desc", "执行默认任务")
            analysis_result = analyst_agent(task_desc, full_material)
            print("[分析Agent]完成业务分析\n")
            print("[DEBUG analyst输出]\n", analysis_result)
            is_block, block_reasons = rule_based_check(analysis_result, is_from_web=has_web_source)
            if is_block:
                print(f"⚠️规则层拦截，reason:{block_reasons}")
                final_result = f"【检测到LLM生成幻觉，已拦截】\n校验原因：{block_reasons}"
                output_segments.clear()
                break
            validate_ret = validator_agent(analysis_result, full_material)
            if not isinstance(validate_ret, dict):
                validate_ret = {"status": "invalid", "reason": "校验返回格式异常，保守拦截"}
            print("[DEBUG validator返回]", validate_ret)
            print("[校验Agent]完成业务校验\n")
            if validate_ret.get("status") == "invalid":
                print(f"⚠️LLM校验拦截，原因：{validate_ret.get('reason', '')}")
                final_result = f"【检测到LLM生成幻觉，已拦截】\n校验原因：{validate_ret.get('reason', '')}"
                output_segments.clear()
                break
            output_segments.append(analysis_result)
        if output_segments:
            final_result = "\n\n=====任务分割=====\n\n".join(output_segments)
        else:
            final_result = "【输出为空，未获取有效回答】"
    else:
        # report模式串行执行全部task_list任务
        output_segments = []
        for task in task_list:
            task_desc = task.get("task_desc", "执行默认任务")
            analysis_result = analyst_agent(task_desc, full_material)
            print("[分析Agent]完成业务分析\n")
            print("[DEBUG analyst输出]\n", analysis_result)
            is_block, block_reasons = rule_based_check(analysis_result, is_from_web=has_web_source)
            if is_block:
                print(f"⚠️规则层拦截，reason:{block_reasons}")
                final_result = f"【检测到LLM生成幻觉，已拦截】\n校验原因：{block_reasons}"
                output_segments.clear()
                break
            validate_ret = validator_agent(analysis_result, full_material)
            if not isinstance(validate_ret, dict):
                validate_ret = {"status": "invalid", "reason": "校验返回格式异常，保守拦截"}
            print("[DEBUG validator返回]", validate_ret)
            print("[校验Agent]完成业务校验\n")
            if validate_ret.get("status") == "invalid":
                print(f"⚠️LLM校验拦截，原因：{validate_ret.get('reason', '')}")
                final_result = f"【检测到LLM生成幻觉，已拦截】\n校验原因：{validate_ret.get('reason', '')}"
                output_segments.clear()
                break
            final_report = report_agent(analysis_result, user_input)
            print("[报告后兜底校验，校验report_agent输出内容]")
            is_block_final, block_reasons_final = rule_based_check(final_report, is_from_web=has_web_source)
            if is_block_final:
                print(f"⚠️报告层‑规则拦截:{block_reasons_final}")
                final_result = f"【检测到LLM生成幻觉，已拦截】\n校验原因：{block_reasons_final}"
                output_segments.clear()
                break
            output_segments.append(final_report)
        if output_segments:
            final_result = "\n\n=====任务分割=====\n\n".join(output_segments)
        else:
            final_result = "【输出为空，未获取有效回答】"
    # 兜底：防止返回空字符串
    if not final_result or not final_result.strip():
        final_result = "【输出为空，未获取有效回答】"
    return final_result

if __name__ == "__main__":
    test_cases = [
        "MES系统紧急插单会带来哪些业务冲突？",
        "请分析MES与ERP成品入库交互的核心风险点，输出3条分析结论",
        "写一份MES可信报工方案完整markdown报告，包含员工画像、报工流程、防虚报校验规则",
        "MES OEE指标怎么计算，请给出公式",
        "MES系统面临挑战有哪些",
        "MES‑ERP对接，成品入库接口需要哪些核心字段",
        "如果本地知识库没有内容，介绍一下IATF16949质量体系要求",
    ]
    for query in test_cases:
        output = run_workflow(query)
        print(f"输出:\n{output}\n")
