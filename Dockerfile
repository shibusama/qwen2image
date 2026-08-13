# 千问知识海报 · Qwen2Image — Docker 镜像
# 构建: docker build -t qwen-infographic .
# 运行: docker run -p 5000:5000 --env-file .env qwen-infographic

FROM python:3.12-slim

# 运行参数：外部可通过 -e DEPLOY_RUN_PORT=xxxx 覆盖监听端口（默认 5000）
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEPLOY_RUN_PORT=5000

WORKDIR /app

# 先拷贝依赖清单并安装，利用 Docker 层缓存加速后续构建
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝项目源码（.dockerignore 已排除 .env / .git 等）
COPY . .

# 以非 root 用户运行，提升安全性
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${DEPLOY_RUN_PORT}"]
