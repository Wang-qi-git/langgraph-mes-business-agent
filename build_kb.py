from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHROMA_PERSIST_DIR = "./chroma_db"

model_name = "BAAI/bge-small-zh-v1.5"
model_kwargs = {"device": "cpu"}
encode_kwargs = {"normalize_embeddings": True}

embedding = HuggingFaceEmbeddings(
    model_name=model_name,
    model_kwargs=model_kwargs,
    encode_kwargs=encode_kwargs
)

def build_vector_db(pdf_file: str):
    loader = PyPDFLoader(pdf_file)
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(docs)

    # ！！！关键：embedding直接作为第二个位置参数，不加embedding_function=
    Chroma.from_documents(
        chunks,
        embedding,
        persist_directory=CHROMA_PERSIST_DIR
    )
    print(f"✅向量库构建完成，目录：{CHROMA_PERSIST_DIR}")

if __name__ == "__main__":
    build_vector_db("./mes.pdf")
