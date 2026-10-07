"""
MES 工具封装 - 把 Mock MES API 包装成 Agent 可调用的函数
"""
import requests
from typing import Optional

MES_BASE = "http://127.0.0.1:8001"
TIMEOUT = 5


def _get(path: str) -> Optional[dict]:
    """安全 GET，异常返回 None"""
    try:
        r = requests.get(f"{MES_BASE}{path}", timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return {"_not_found": True, "_detail": r.json().get("detail", "")}
        return None
    except Exception as e:
        print(f"【MES 工具】请求 {path} 失败: {e}")
        return None


def query_work_order(order_id: str) -> str:
    """查询单个工单的实时状态"""
    order_id = order_id.strip().upper()
    data = _get(f"/mes/work-orders/{order_id}")
    if data is None:
        return f"【MES 查询失败】无法连接到 MES 系统，请稍后重试。"
    if data.get("_not_found"):
        return f"【MES 查询结果】工单 {order_id} 不存在，请确认单号是否正确。"

    return (
        f"【工单实时状态】\n"
        f"- 工单号：{data['order_id']}\n"
        f"- 产品：{data['product']}\n"
        f"- 数量：{data['quantity']}\n"
        f"- 状态：{data['status']}\n"
        f"- 当前工序：{data['current_process']}\n"
        f"- 进度：{data['progress']}%\n"
        f"- 良率：{data['yield_rate']}%\n"
        f"- 计划完工：{data['planned_end']}\n"
        f"- 优先级：{data['priority']}"
    )


def query_inventory(sku: str) -> str:
    """查询物料库存"""
    sku = sku.strip().upper()
    data = _get(f"/mes/inventory/{sku}")
    if data is None:
        return f"【MES 查询失败】无法连接到 MES 系统，请稍后重试。"
    if data.get("_not_found"):
        return f"【MES 查询结果】物料 {sku} 不存在，请确认编码是否正确。"

    flag = "⚠️ 低于安全库存" if data.get("below_safety") else "✅ 库存充足"
    return (
        f"【物料库存实时数据】\n"
        f"- SKU：{data['sku']}\n"
        f"- 名称：{data['name']}\n"
        f"- 当前库存：{data['quantity']} {data['unit']}\n"
        f"- 安全库存：{data['safety_stock']} {data['unit']}\n"
        f"- 库位：{data['location']}\n"
        f"- 状态：{flag}"
    )


def query_equipment(machine_id: str) -> str:
    """查询设备实时状态"""
    machine_id = machine_id.strip().upper()
    data = _get(f"/mes/equipment/{machine_id}")
    if data is None:
        return f"【MES 查询失败】无法连接到 MES 系统，请稍后重试。"
    if data.get("_not_found"):
        return f"【MES 查询结果】设备 {machine_id} 不存在，请确认设备编号。"

    alarm = f"\n- 报警信息：{data['alarm']}" if data.get("alarm") else ""
    order = f"\n- 当前工单：{data['current_order']}" if data.get("current_order") else ""
    return (
        f"【设备实时状态】\n"
        f"- 设备编号：{data['machine_id']}\n"
        f"- 名称：{data['name']}\n"
        f"- 状态：{data['status']}{order}\n"
        f"- OEE：{data['oee']}%{alarm}"
    )


def query_low_stock() -> str:
    """列出所有低库存物料"""
    data = _get("/mes/inventory?low_stock=true")
    if data is None:
        return f"【MES 查询失败】无法连接到 MES 系统，请稍后重试。"
    if not data:
        return "【物料库存】当前没有低于安全库存的物料。"

    lines = ["【低库存物料清单】"]
    for item in data:
        lines.append(
            f"- {item['sku']} {item['name']}：库存 {item['quantity']}/{item['safety_stock']} {item['unit']}"
        )
    return "\n".join(lines)


def query_alarm_equipment() -> str:
    """列出所有报警/维护中的设备"""
    data = _get("/mes/equipment")
    if data is None:
        return f"【MES 查询失败】无法连接到 MES 系统，请稍后重试。"

    abnormal = [e for e in data if e["status"] in ("报警", "维护")]
    if not abnormal:
        return "【设备状态】当前所有设备运行正常。"

    lines = ["【异常设备清单】"]
    for e in abnormal:
        alarm = f"（{e['alarm']}）" if e.get("alarm") else ""
        lines.append(f"- {e['machine_id']} {e['name']}：{e['status']}{alarm}")
    return "\n".join(lines)


def query_quality_issues(status: str = "处理中") -> str:
    """查询质量问题"""
    data = _get(f"/mes/quality-issues?status={status}")
    if data is None:
        return f"【MES 查询失败】无法连接到 MES 系统，请稍后重试。"
    if not data:
        return f"【质量问题】当前没有状态为「{status}」的质量问题。"

    lines = [f"【{status}的质量问题】"]
    for q in data:
        lines.append(
            f"- {q['issue_id']} 批次{q['batch']} [{q['severity']}]：{q['description']}"
        )
    return "\n".join(lines)


# 工具注册表（供 Agent 调用）
MES_TOOLS = {
    "mes_work_order": query_work_order,
    "mes_inventory": query_inventory,
    "mes_equipment": query_equipment,
    "mes_low_stock": query_low_stock,
    "mes_alarm_equipment": query_alarm_equipment,
    "mes_quality_issues": query_quality_issues,
}