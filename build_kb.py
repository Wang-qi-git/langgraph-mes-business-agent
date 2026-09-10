import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import time
import shutil
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHROMA_PERSIST_DIR = "./chroma_db"
PDF_DIR = "./pdf_docs"
MD_DIR = "./md_docs"

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
BATCH_SIZE = 100

print("🔧 加载 BGE 模型（首次约需 5-10 秒）...")
t0 = time.time()
embedding = HuggingFaceEmbeddings(
    model_name="BAAI/bge-small-zh-v1.5",
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True}
)
print(f"✅ 模型加载完成，耗时 {time.time() - t0:.1f}s")


def load_pdf_dir(pdf_dir):
    """加载 pdf_dir 下所有 PDF"""
    chunks_all = []
    if not os.path.exists(pdf_dir):
        print(f"⚠️ 目录不存在: {pdf_dir}")
        return chunks_all

    pdf_files = sorted([f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")])
    if not pdf_files:
        print(f"⚠️ {pdf_dir} 下没有 PDF 文件")
        return chunks_all

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )

    for i, pdf_file in enumerate(pdf_files, 1):
        pdf_path = os.path.join(pdf_dir, pdf_file)
        print(f"\n📄 [{i}/{len(pdf_files)}] 加载 PDF: {pdf_file}")
        t1 = time.time()
        try:
            loader = PyPDFLoader(pdf_path)
            docs = loader.load()
            chunks = splitter.split_documents(docs)
            for chunk in chunks:
                chunk.metadata["source_file"] = pdf_file
                chunk.metadata["doc_type"] = "pdf"
            chunks_all.extend(chunks)
            print(f"   → 切分 {len(chunks)} 个 chunk，耗时 {time.time() - t1:.1f}s")
        except Exception as e:
            print(f"   ❌ 加载失败: {e}")

    return chunks_all


def load_md_dir(md_dir):
    """加载 md_dir 下所有 Markdown"""
    chunks_all = []
    if not os.path.exists(md_dir):
        print(f"⚠️ 目录不存在: {md_dir}")
        return chunks_all

    md_files = sorted([f for f in os.listdir(md_dir) if f.lower().endswith(".md")])
    if not md_files:
        print(f"⚠️ {md_dir} 下没有 MD 文件")
        return chunks_all

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )

    for i, md_file in enumerate(md_files, 1):
        md_path = os.path.join(md_dir, md_file)
        print(f"\n📝 [{i}/{len(md_files)}] 加载 MD: {md_file}")
        t1 = time.time()
        try:
            loader = TextLoader(md_path, encoding="utf-8")
            docs = loader.load()
            chunks = splitter.split_documents(docs)
            for chunk in chunks:
                chunk.metadata["source_file"] = md_file
                chunk.metadata["doc_type"] = "markdown"
            chunks_all.extend(chunks)
            print(f"   → 切分 {len(chunks)} 个 chunk，耗时 {time.time() - t1:.1f}s")
        except Exception as e:
            print(f"   ❌ 加载失败: {e}")

    return chunks_all


def build_vector_db():
    all_chunks = []

    print("\n" + "=" * 50)
    print("📚 加载 PDF 文档")
    print("=" * 50)
    all_chunks.extend(load_pdf_dir(PDF_DIR))

    print("\n" + "=" * 50)
    print("📚 加载 Markdown 文档")
    print("=" * 50)
    all_chunks.extend(load_md_dir(MD_DIR))

    if not all_chunks:
        print("\n❌ 没有加载到任何文档，退出")
        return

    print(f"\n" + "=" * 50)
    print(f"📦 共 {len(all_chunks)} 个 chunk，开始计算 embedding 并写入 Chroma...")
    print("=" * 50)

    t2 = time.time()
    vector_db = None

    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i:i + BATCH_SIZE]
        batch_no = i // BATCH_SIZE + 1
        total_batches = (len(all_chunks) + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"   写入第 {batch_no}/{total_batches} 批 ({len(batch)} 个 chunk)...")
        if vector_db is None:
            vector_db = Chroma.from_documents(
                batch,
                embedding,
                persist_directory=CHROMA_PERSIST_DIR
            )
        else:
            vector_db.add_documents(batch)

    print(f"\n✅ 向量库构建完成，目录：{CHROMA_PERSIST_DIR}")
    print(f"   总耗时 {time.time() - t2:.1f}s")
    print(f"   总 chunk 数：{len(all_chunks)}")


if __name__ == "__main__":
    if os.path.exists(CHROMA_PERSIST_DIR):
        try:
            shutil.rmtree(CHROMA_PERSIST_DIR)
            print(f"🗑️ 已删除旧向量库: {CHROMA_PERSIST_DIR}")
        except Exception as e:
            print(f"⚠️ 删除旧向量库失败: {e}")
            print(f"   请手动执行: rmdir /s /q {CHROMA_PERSIST_DIR}")

    build_vector_db()