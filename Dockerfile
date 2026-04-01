# ============================================================
# TVC Director Agent — Backend Dockerfile
# ============================================================
# 生产级 LangGraph API Server

FROM python:3.12-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir \
      "langgraph-api>=0.1.0" \
      "langgraph-checkpoint-postgres>=2.0.0" \
      "uvicorn>=0.30.0"

# 项目文件
COPY langgraph.json .
COPY src/ ./src/
COPY prompts/ ./prompts/

# LangGraph API Server 端口
EXPOSE 8000

# 启动生产 API Server
# langgraph-api 提供与 langgraph dev 兼容的 REST API
CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "8000"]
