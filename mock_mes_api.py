"""
Mock MES API - 模拟真实制造业执行系统
启动：uvicorn mock_mes_api:mes_api --host 0.0.0.0 --port 8001

模拟真实 MES 系统的核心接口：
- 工单管理（含客户、批次、车间、产线）
- 物料库存 + BOM
- 设备状态 + OEE
- 质量问题
- 工单齐套分析（跨表联动）
"""
import sqlite3
import os
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_mes.db")

mes_api = FastAPI(
    title="Mock MES System",
    description="模拟制造业 MES 系统（用于 Agent 演示）",
    version="1.1.0",
)


# ==================== 数据库初始化 ====================
def init_db():
    # 如果表结构变了，删掉旧库重建
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            # 检查是否有 BOM 表（新表）
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bom'")
            if not c.fetchone():
                conn.close()
                os.remove(DB_PATH)
                print("【Mock MES】检测到旧库，已删除，将重建")
            else:
                conn.close()
        except Exception:
            pass

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 工单表（扩充字段）
    c.execute("""
        CREATE TABLE IF NOT EXISTS work_orders (
            order_id TEXT PRIMARY KEY,
            product TEXT,
            quantity INTEGER,
            status TEXT,
            current_process TEXT,
            progress INTEGER,
            yield_rate REAL,
            planned_start TEXT,
            planned_end TEXT,
            priority TEXT,
            customer TEXT,
            batch_no TEXT,
            workshop TEXT,
            line TEXT,
            operator TEXT
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
            unit TEXT,
            supplier TEXT
        )
    """)

    # BOM 表（新增：产品 → 物料清单）
    c.execute("""
        CREATE TABLE IF NOT EXISTS bom (
            product TEXT,
            sku TEXT,
            qty_per_unit REAL,
            PRIMARY KEY (product, sku)
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
            alarm TEXT,
            workshop TEXT
        )
    """)

    # 质量问题表
    c.execute("""
        CREATE TABLE IF NOT EXISTS quality_issues (
            issue_id TEXT PRIMARY KEY,
            batch TEXT,
            order_id TEXT,
            severity TEXT,
            status TEXT,
            description TEXT,
            reported_at TEXT
        )
    """)

    # ============ 插入数据 ============
    now = datetime.now()

    # 工单：15 条真实感数据
    orders = [
        ("WO-20261007-001", "伺服电机-A100", 500, "生产中", "装配", 65, 98.2,
         (now - timedelta(days=1)).strftime("%Y-%m-%d"),
         (now + timedelta(days=1)).strftime("%Y-%m-%d"), "高",
         "某汽车厂", "B2026100601", "装配车间", "A线", "张三"),
        ("WO-20261007-002", "减速器-B200", 300, "待开工", "备料", 0, 0.0,
         (now + timedelta(days=1)).strftime("%Y-%m-%d"),
         (now + timedelta(days=3)).strftime("%Y-%m-%d"), "中",
         "某机械厂", "B2026100702", "机加车间", "B线", "未派工"),
        ("WO-20261007-003", "控制器-C300", 200, "生产中", "老化测试", 85, 96.5,
         (now - timedelta(days=2)).strftime("%Y-%m-%d"),
         (now + timedelta(hours=8)).strftime("%Y-%m-%d"), "高",
         "某电子厂", "B2026100503", "测试车间", "C线", "李四"),
        ("WO-20261007-004", "齿轮箱-D400", 150, "暂停", "机加工", 30, 92.0,
         (now - timedelta(days=3)).strftime("%Y-%m-%d"),
         (now + timedelta(days=5)).strftime("%Y-%m-%d"), "低",
         "某机械厂", "B2026100404", "机加车间", "B线", "王五"),
        ("WO-20261007-005", "伺服电机-A100", 800, "生产中", "装配", 45, 97.8,
         (now - timedelta(days=1)).strftime("%Y-%m-%d"),
         (now + timedelta(days=2)).strftime("%Y-%m-%d"), "高",
         "某汽车厂", "B2026100705", "装配车间", "A线", "张三"),
    ]
    # 批量追加 10 条（生成感）
    for i in range(6, 16):
        orders.append((
            f"WO-20261007-{i:03d}",
            ["伺服电机-A100", "减速器-B200", "控制器-C300", "齿轮箱-D400"][i % 4],
            100 + i * 10,
            ["待开工", "生产中", "已完工"][i % 3],
            ["备料", "机加工", "装配", "测试", "入库"][i % 5],
            (i * 7) % 100,
            95.0 + (i % 4),
            (now - timedelta(days=i % 5)).strftime("%Y-%m-%d"),
            (now + timedelta(days=i % 7 + 1)).strftime("%Y-%m-%d"),
            ["高", "中", "低"][i % 3],
            "某客户-" + str(i),
            f"B202610{i:02d}",
            ["装配车间", "机加车间", "测试车间"][i % 3],
            ["A线", "B线", "C线"][i % 3],
            ["张三", "李四", "王五", "未派工"][i % 4],
        ))

    c.executemany(
        "INSERT OR IGNORE INTO work_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        orders,
    )

    # 库存：10 条
    c.executemany(
        "INSERT OR IGNORE INTO inventory VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("SKU-A100-01", "伺服电机定子", 1250, 500, "A-01-03", "个", "供应商A"),
            ("SKU-A100-02", "转子总成", 180, 300, "A-02-01", "个", "供应商B"),   # 低库存
            ("SKU-B200-01", "行星齿轮", 2400, 1000, "B-01-05", "套", "供应商A"),
            ("SKU-C300-01", "PCB 主板", 85, 200, "C-03-02", "块", "供应商C"),     # 低库存
            ("SKU-C300-02", "电容组件", 5600, 2000, "C-04-01", "套", "供应商D"),
            ("SKU-D400-01", "齿轮箱壳体", 320, 150, "D-01-02", "件", "供应商E"),
            ("SKU-D400-02", "润滑油", 50, 100, "D-02-03", "L", "供应商F"),        # 低库存
            ("SKU-A100-03", "轴承", 3200, 800, "A-03-01", "个", "供应商B"),
            ("SKU-B200-02", "密封圈", 800, 400, "B-02-04", "个", "供应商G"),
            ("SKU-C300-03", "连接器", 1500, 500, "C-05-06", "个", "供应商D"),
        ],
    )

    # BOM：产品 → 物料清单
    c.executemany(
        "INSERT OR IGNORE INTO bom VALUES (?, ?, ?)",
        [
            ("伺服电机-A100", "SKU-A100-01", 1.0),
            ("伺服电机-A100", "SKU-A100-02", 1.0),
            ("伺服电机-A100", "SKU-A100-03", 4.0),
            ("减速器-B200", "SKU-B200-01", 2.0),
            ("减速器-B200", "SKU-B200-02", 8.0),
            ("控制器-C300", "SKU-C300-01", 1.0),
            ("控制器-C300", "SKU-C300-02", 5.0),
            ("控制器-C300", "SKU-C300-03", 2.0),
            ("齿轮箱-D400", "SKU-D400-01", 1.0),
            ("齿轮箱-D400", "SKU-D400-02", 0.5),
        ],
    )

    # 设备：8 台
    c.executemany(
        "INSERT OR IGNORE INTO equipment VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("M-001", "数控车床-1号", "运行中", "WO-20261007-001", 85.2, None, "机加车间"),
            ("M-002", "数控车床-2号", "运行中", "WO-20261007-003", 78.5, None, "机加车间"),
            ("M-003", "三坐标测量仪", "空闲", None, 0.0, None, "测试车间"),
            ("M-004", "自动化装配线", "报警", "WO-20261007-001", 42.1,
             "刀具磨损超限，请更换", "装配车间"),
            ("M-005", "老化测试台", "维护", None, 0.0,
             "计划性保养，预计 2 小时", "测试车间"),
            ("M-006", "注塑机-1号", "运行中", "WO-20261007-005", 88.0, None, "注塑车间"),
            ("M-007", "注塑机-2号", "空闲", None, 0.0, None, "注塑车间"),
            ("M-008", "包装线", "运行中", "WO-20261007-005", 92.3, None, "包装车间"),
        ],
    )

    # 质量问题：5 条
    c.executemany(
        "INSERT OR IGNORE INTO quality_issues VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("QI-20261007-001", "B2026100601", "WO-20261007-001", "严重", "处理中",
             "齿轮箱异响，初步判定为齿轮装配间隙超标", "2026-10-07 08:30"),
            ("QI-20261007-002", "B2026100601", "WO-20261007-001", "一般", "已关闭",
             "外观划痕，已按返工流程处理", "2026-10-07 06:15"),
            ("QI-20261006-018", "B2026100503", "WO-20261007-003", "致命", "已关闭",
             "电机温升超标，8D 已结案", "2026-10-06 14:20"),
            ("QI-20261007-003", "B2026100705", "WO-20261007-005", "一般", "处理中",
             "PCB 虚焊，正在返修", "2026-10-07 10:00"),
            ("QI-20261007-004", "B2026100404", "WO-20261007-004", "严重", "处理中",
             "齿轮箱漏油，需检查密封圈", "2026-10-07 11:30"),
        ],
    )

    conn.commit()
    conn.close()
    print("【Mock MES】数据库初始化完成")


init_db()


# ==================== 工具函数 ====================
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
        "version": "1.1.0",
        "status": "running",
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


@mes_api.get("/mes/bom/{product}")
def get_bom(product: str):
    """查询产品的物料清单"""
    rows = query("SELECT * FROM bom WHERE product = ?", (product,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"产品 {product} 的 BOM 不存在")
    return rows


@mes_api.get("/mes/work-orders/{order_id}/readiness")
def check_readiness(order_id: str):
    """工单齐套分析（跨表联动）
    1. 查工单 → 产品 + 数量
    2. 查 BOM → 每个物料单位用量
    3. 查库存 → 现有数量
    4. 计算齐套率 + 缺料清单
    """
    orders = query("SELECT * FROM work_orders WHERE order_id = ?", (order_id,))
    if not orders:
        raise HTTPException(status_code=404, detail=f"工单 {order_id} 不存在")
    order = orders[0]

    boms = query("SELECT * FROM bom WHERE product = ?", (order["product"],))
    if not boms:
        return {
            "order_id": order_id,
            "product": order["product"],
            "readiness": None,
            "message": f"产品 {order['product']} 无 BOM 记录，无法齐套分析",
            "shortage": [],
        }

    shortage = []
    total_items = len(boms)
    ok_items = 0

    for b in boms:
        required = int(b["qty_per_unit"] * order["quantity"])
        inv = query("SELECT * FROM inventory WHERE sku = ?", (b["sku"],))
        available = inv[0]["quantity"] if inv else 0
        name = inv[0]["name"] if inv else "未知物料"

        if available >= required:
            ok_items += 1
        else:
            shortage.append({
                "sku": b["sku"],
                "name": name,
                "required": required,
                "available": available,
                "gap": required - available,
            })

    readiness_rate = round(ok_items / total_items * 100, 1)

    return {
        "order_id": order_id,
        "product": order["product"],
        "quantity": order["quantity"],
        "readiness_rate": readiness_rate,
        "total_items": total_items,
        "ok_items": ok_items,
        "shortage": shortage,
        "status": "齐套" if not shortage else "缺料",
    }


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