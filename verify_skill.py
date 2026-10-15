# verify_skill.py
"""
SKILL.md 验证脚本
检查 SKILL.md 格式、内容与项目实际是否一致
"""
import os
import re
import sys


def check(name, condition, detail=""):
    status = "[OK]" if condition else "[FAIL]"
    line = f"{status} {name}"
    if detail:
        line += f" {detail}"
    print(line)
    return condition


def main():
    print("=" * 60)
    print("SKILL.md 验证")
    print("=" * 60)
    print()

    results = []

    # 1. SKILL.md 文件存在
    if not os.path.exists("SKILL.md"):
        check("SKILL.md 存在", False)
        print()
        print("!!! SKILL.md 不存在，请先创建 !!!")
        sys.exit(1)
    results.append(check("SKILL.md 存在", True))

    # 2. 读取内容
    content = open("SKILL.md", "r", encoding="utf-8").read()

    # 3. YAML 头部
    yaml_match = re.match(r'^---\n(.*?)\n---', content, re.S)
    has_yaml = yaml_match is not None
    results.append(check("YAML 头部完整", has_yaml))

    if yaml_match:
        yaml_head = yaml_match.group(1)
        results.append(check("有 name 字段", "name:" in yaml_head))
        results.append(check("有 description 字段", "description:" in yaml_head))

        # 提取 name 和 description
        name_match = re.search(r'name:\s*(.+)', yaml_head)
        if name_match:
            print(f"     Skill 名称: {name_match.group(1).strip()}")

    # 4. 必需文件核对
    print()
    print("--- 项目文件核对 ---")
    required_files = [
        "graph_agent_skeleton.py",
        "api_server.py",
        "streamlit_app.py",
        "auth.py",
        "session_store.py",
        "mes_tools.py",
        "build_kb.py",
        "eval_agent.py",
        "docker-compose.yml",
        "Dockerfile",
        "prometheus.yml",
        "requirements.txt",
    ]
    for f in required_files:
        exists = os.path.exists(f)
        results.append(check(f"文件存在: {f}", exists))

    # 5. MES 工具核对
    print()
    print("--- MES 工具核对 ---")
    if os.path.exists("mes_tools.py"):
        tools_content = open("mes_tools.py", "r", encoding="utf-8").read()
        query_funcs = re.findall(r'^def (query_\w+)', tools_content, re.M)
        print(f"     找到 {len(query_funcs)} 个查询函数:")
        for fn in query_funcs:
            print(f"       - {fn}")
        results.append(check(f"工具数量 >= 5", len(query_funcs) >= 5))

    # 6. BOM 守卫函数
    print()
    print("--- 关键机制核对 ---")
    bom_found = False
    for root, dirs, files in os.walk("."):
        if "venv" in root or "__pycache__" in root or ".git" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                try:
                    c = open(os.path.join(root, f), "r", encoding="utf-8").read()
                    if "check_bom_version_guard" in c or "bom_version" in c.lower():
                        bom_found = True
                        print(f"     BOM 守卫在: {os.path.join(root, f)}")
                        break
                except Exception:
                    pass
        if bom_found:
            break
    results.append(check("BOM 守卫机制存在", bom_found))

    # 7. 检查 docs 目录
    print()
    print("--- 文档目录核对 ---")
    results.append(check("docs/ 目录存在", os.path.isdir("docs")))
    results.append(check("tests/ 目录存在", os.path.isdir("tests")))
    results.append(check("md_docs/ 目录存在", os.path.isdir("md_docs")))

    # 8. 检查 AGENTS.md
    print()
    print("--- AI 上下文文件 ---")
    results.append(check("AGENTS.md 存在", os.path.exists("AGENTS.md")))
    if os.path.exists("AGENTS.md"):
        agents_content = open("AGENTS.md", "r", encoding="utf-8").read()
        results.append(check("AGENTS.md 有内容", len(agents_content) > 1000))

    # 9. 检查 README
    results.append(check("README.md 存在", os.path.exists("README.md")))

    # 10. 检查 trace 文件（说明项目跑过）
    print()
    print("--- 运行痕迹核对 ---")
    results.append(check("trace.jsonl 存在（跑过 Eval）", os.path.exists("trace.jsonl")))
    results.append(check("sessions.db 存在（跑过会话）", os.path.exists("sessions.db")))

    # 总结
    print()
    print("=" * 60)
    total = len(results)
    passed = sum(results)
    print(f"结果: {passed}/{total} 通过")
    if passed == total:
        print("!!! SKILL 验证全部通过 !!!")
    else:
        print(f"有 {total - passed} 项未通过，请根据上面 [FAIL] 项排查")
    print("=" * 60)


if __name__ == "__main__":
    main()