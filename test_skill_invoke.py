# test_skill_invoke.py
"""
Skill 调用验证 - 模拟外部 Agent 调用 MES Skill
验证 mes_tools.py 作为 Skill 能否被独立调用
"""
import time
import inspect

print("=" * 60)
print("MES Skill 调用验证")
print("=" * 60)
print()

# ==================== 第一步：导入 Skill ====================
print("[1/4] 导入 Skill 模块...")
try:
    import mes_tools
    print(f"     ✅ mes_tools 导入成功")
    print(f"     模块路径: {mes_tools.__file__}")
except Exception as e:
    print(f"     ❌ 导入失败: {e}")
    exit(1)

# ==================== 第二步：扫描 Skill 暴露的工具 ====================
print()
print("[2/4] 扫描 Skill 暴露的工具函数...")

# 自动发现所有 query_ 开头的函数
skill_functions = []
for name, obj in inspect.getmembers(mes_tools, inspect.isfunction):
    if name.startswith("query_"):
        sig = inspect.signature(obj)
        skill_functions.append({
            "name": name,
            "signature": str(sig),
            "func": obj,
        })

print(f"     发现 {len(skill_functions)} 个工具:")
for f in skill_functions:
    print(f"       - {f['name']}{f['signature']}")

if len(skill_functions) == 0:
    print("     ❌ 没有发现工具函数")
    exit(1)

# ==================== 第三步：模拟 Agent 调用 ====================
print()
print("[3/4] 模拟 Agent 调用 Skill...")

# 定义测试用例（模拟 Agent 传参）
test_cases = [
    {"tool": "query_work_order", "args": {"order_id": "WO20241013-001"}},
    {"tool": "query_inventory", "args": {"sku": "CP4567890"}},
    {"tool": "query_equipment", "args": {"machine_id": "EQ001"}},
    {"tool": "query_alarm_equipment", "args": {}},
    {"tool": "query_quality_issues", "args": {"status": "处理中"}},
    {"tool": "query_order_readiness", "args": {"order_id": "WO20241013-001"}},
    {"tool": "query_low_stock", "args": {}},
]

success_count = 0
for tc in test_cases:
    tool_name = tc["tool"]
    args = tc["args"]
    
    # 找到对应函数
    func = None
    for f in skill_functions:
        if f["name"] == tool_name:
            func = f["func"]
            break
    
    if func is None:
        print(f"     ⚠️  {tool_name} 不存在，跳过")
        continue
    
    # 调用
    try:
        t0 = time.time()
        result = func(**args)
        cost = time.time() - t0
        print(f"     ✅ {tool_name}{args} → {cost*1000:.0f}ms")
        success_count += 1
    except Exception as e:
        print(f"     ❌ {tool_name} 调用失败: {e}")

# ==================== 第四步：验证结果 ====================
print()
print("[4/4] 验证结果...")
if success_count == len(test_cases):
    print(f"     ✅ 全部 {success_count} 个工具调用成功")
    print()
    print("=" * 60)
    print("🎉 Skill 验证通过！可被外部 Agent 调用")
    print("=" * 60)
else:
    print(f"     ⚠️ {success_count}/{len(test_cases)} 个工具调用成功")
    print("=" * 60)