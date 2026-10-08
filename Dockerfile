# ================================================
# 多阶段构建：backend / frontend / mock-mes 共用基础镜像
# ================================================

# ---------- 基础层：公共依赖 ----------
FROM python:3.11-slim AS base

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 用国内 pip 源加速
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ \
    && pip config set global.trusted-host mirrors.aliyun.com

# 先装依赖（利用 Docker 缓存）
COPY requirements.txt .

# ⚠️ 关键：先装 CPU 版 torch，避免下载几个 GB 的 CUDA 包
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# 复制项目代码（.dockerignore 会排除 models/、chroma_db/ 等大文件）
COPY . .

# 环境变量
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
ENV PYTHONUNBUFFERED=1


# ---------- backend：FastAPI ----------
FROM base AS backend

EXPOSE 8000

CMD ["uvicorn", "api_server:api", "--host", "0.0.0.0", "--port", "8000"]


# ---------- frontend：Streamlit ----------
FROM base AS frontend

EXPOSE 8501

# 前端连后端的地址通过环境变量传入
ENV API_BASE=http://backend:8000

CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]


# ---------- mock-mes：模拟 MES 系统 ----------
FROM base AS mock-mes

EXPOSE 8001

CMD ["uvicorn", "mock_mes_api:mes_api", "--host", "0.0.0.0", "--port", "8001"]