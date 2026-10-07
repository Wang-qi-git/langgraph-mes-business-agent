from modelscope import snapshot_download

print("开始下载 bge-reranker-v2-m3...")
model_dir = snapshot_download(
    'BAAI/bge-reranker-v2-m3',
    local_dir='./models/bge-reranker-v2-m3'
)
print(f"✅ 下载完成，模型路径：{model_dir}")