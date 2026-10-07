"""
Mock MES API - 模拟真实的制造业执行系统
启动：uvicorn mock_mes_api:mes_api --host 0.0.0.0 --port 8001

模拟真实的 MES 系统接口，提供：
- 工单查询
- 库存查询
- 设备状态查询
- 排产查询
- 质量问题查询
"""
import sqlite3
import os
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_mes.db")

mes_api = FastAPI(
    title="Mock MES System",
    description="模拟制造业 MES 系统（用于 Agent 演示）",
    version="1.0.0",
)


# ==================== 数据库初始化 ====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 工单表
    c.execute("""
        CREATE TABLE IF NOT EXISTS work_orders (
            order_id TEXT PRIMARY KEY,
            product TEXT,
            quantity INTEGER,
            status TEXT,
            current_process TEXT,
            progress INTEGER,
            yield_rate REAL,
            planned_end TEXT,
            priority TEXT
        )
    """)

    # 库存表
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            sku TEXT PRIMARY KEY,
            name TEXT,
            quantity INTEGER,
            safety_stock INTEGER,
            location TEXT,
            unit TEXT
        )
    """)

    # 设备表
    c.execute("""
        CREATE TABLE IF NOT EXISTS equipment (
            machine_id TEXT PRIMARY KEY,
            name TEXT,
            status TEXT,
            current_order TEXT,
            oee REAL,
            alarm TEXT
        )
    """)

    # 质量问题表
    c.execute("""
        CREATE TABLE IF NOT EXISTS quality_issues (
            issue_id TEXT PRIMARY KEY,
            batch TEXT,
            severity TEXT,
            status TEXT,
            description TEXT,
            reported_at TEXT
        )
    """)

    # 若为空则插入模拟数据
    if c.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0] == 0:
        now = datetime.now()
        c.executemany(
            "INSERT INTO work_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("WO-20261007-001", "伺服电机-A100", 500, "生产中", "装配", 65, 98.2,
                 (now + timedelta(days=1)).strftime("%Y-%m-%d"), "高"),
                ("WO-20261007-002", "减速器-B200", 300, "待开工", "备料", 0, 0.0,
                 (now + timedelta(days=3)).strftime("%Y-%m-%d"), "中"),
                ("WO-20261007-003", "控制器-C300", 200, "生产中", "老化测试", 85, 96.5,
                 (now + timedelta(hours=8)).strftime("%Y-%m-%d"), "高"),
                ("WO-20261006-018", "伺服电机-A100", 800, "已完工", "入库", 100, 99.1,
                 (now - timedelta(days=1)).strftime("%Y-%m-%d"), "中"),
                ("WO-20261007-004", "齿轮箱-D400", 150, "暂停", "机加工", 30, 92.0,
                 (now + timedelta(days=5)).strftime("%Y-%m-%d"), "低"),
            ],
        )

        c.executemany(
            "INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("SKU-A100-01", "伺服电机定子", 1250, 500, "A-01-03", "个"),
                ("SKU-A100-02", "转子总成", 180, 300, "A-02-01", "个"),   # 低于安全库存
                ("SKU-B200-01", "行星齿轮", 2400, 1000, "B-01-05", "套"),
                ("SKU-C300-01", "PCB 主板", 85, 200, "C-03-02", "块"),     # 低库存
                ("SKU-C300-02", "电容组件", 5600, 2000, "C-04-01", "套"),
            ],
        )

        c.executemany(
            "INSERT INTO equipment VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("M-001", "数控车床-1号", "运行中", "WO-20261007-001", 85.2, None),
                ("M-002", "数控车床-2号", "运行中", "WO-20261007-003", 78.5, None),
                ("M-003", "三坐标测量仪", "空闲", None, 0.0, None),
                ("M-004", "自动化装配线", "报警", "WO-20261007-001", 42.1, "刀具磨损超限，请更换"),
                ("M-005", "老化测试台", "维护", None, 0.0, "计划性保养，预计 2 小时"),
            ],
        )

        c.executemany(
            "INSERT INTO quality_issues VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("QI-20261007-001", "B20261006", "严重", "处理中",
                 "齿轮箱异响，初步判定为齿轮装配间隙超标", "2026-10-07 08:30"),
                ("QI-20261007-002", "B20261006", "一般", "已关闭",
                 "外观划痕，已按返工流程处理", "2026-10-07 06:15"),
                ("QI-20261006-018", "B20261005", "致命", "已关闭",
                 "电机温升超标，8D 已结案", "2026-10-06 14:20"),
            ],
        )

        conn.commit()
    conn.close()


init_db()


# ==================== 工具函数 ====================
def row_to_dict(row, cursor):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(sql, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ==================== 端点 ====================
@mes_api.get("/")
def root():
    return {
        "service": "Mock MES System",
        "version": "1.0.0",
        "status": "running",
        "endpoints": [
            "/mes/work-orders/{order_id}",
            "/mes/work-orders",
            "/mes/inventory/{sku}",
            "/mes/inventory",
            "/mes/equipment/{machine_id}",
            "/mes/equipment",
            "/mes/quality-issues",
        ],
    }


@mes_api.get("/mes/work-orders/{order_id}")
def get_work_order(order_id: str):
    rows = query("SELECT * FROM work_orders WHERE order_id = ?", (order_id,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"工单 {order_id} 不存在")
    return rows[0]


@mes_api.get("/mes/work-orders")
def list_work_orders(status: str = None):
    if status:
        return query("SELECT * FROM work_orders WHERE status = ?", (status,))
    return query("SELECT * FROM work_orders")


@mes_api.get("/mes/inventory/{sku}")
def get_inventory(sku: str):
    rows = query("SELECT * FROM inventory WHERE sku = ?", (sku,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"物料 {sku} 不存在")
    item = rows[0]
    item["below_safety"] = item["quantity"] < item["safety_stock"]
    return item


@mes_api.get("/mes/inventory")
def list_inventory(low_stock: bool = False):
    if low_stock:
        return query("SELECT * FROM inventory WHERE quantity < safety_stock")
    return query("SELECT * FROM inventory")


@mes_api.get("/mes/equipment/{machine_id}")
def get_equipment(machine_id: str):
    rows = query("SELECT * FROM equipment WHERE machine_id = ?", (machine_id,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"设备 {machine_id} 不存在")
    return rows[0]


@mes_api.get("/mes/equipment")
def list_equipment(status: str = None):
    if status:
        return query("SELECT * FROM equipment WHERE status = ?", (status,))
    return query("SELECT * FROM equipment")


@mes_api.get("/mes/quality-issues")
def list_quality_issues(status: str = None):
    if status:
        return query("SELECT * FROM quality_issues WHERE status = ?", (status,))
    return query("SELECT * FROM quality_issues")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(mes_api, host="0.0.0.0", port=8001)