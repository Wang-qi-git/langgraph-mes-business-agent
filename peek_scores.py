import os
from dotenv import load_dotenv
from langsmith import Client

load_dotenv()
client = Client()

# 列出最近的实验项目（去掉 project_type 参数）
print("=== 最近 5 个 project ===")
experiments = list(client.list_projects(limit=10))
for i, p in enumerate(experiments):
    print(f"  [{i}] {p.name}  (id={p.id})")

if not experiments:
    print("❌ 没找到任何 project，可能 API Key 有问题")
    exit()

# 找名字里带 mes-agent-eval 的那个
target = None
for p in experiments:
    if "mes-agent-eval" in p.name:
        target = p
        break
if target is None:
    target = experiments[0]

print(f"\n=== 详细分数：{target.name} ===")

runs = list(client.list_runs(project_name=target.name, is_root=True))
print(f"共 {len(runs)} 条 run\n")

for r in runs:
    q = str(r.inputs.get("user_query", ""))[:60]
    print(f"Q: {q}")
    if r.end_time and r.start_time:
        latency = (r.end_time - r.start_time).total_seconds()
        print(f"  Latency: {latency:.2f}s")
    feedbacks = list(client.list_feedback(run_ids=[r.id]))
    if feedbacks:
        for fb in feedbacks:
            print(f"  [{fb.key}] score={fb.score}")
    else:
        print("  （无反馈分数）")
    print()