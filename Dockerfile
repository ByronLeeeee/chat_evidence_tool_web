# 多阶段构建: 第一阶段用于安装依赖和下载模型
FROM python:3.11-slim AS builder

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PADDLEOCR_HOME=/app/paddleocr_models

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 创建一个非root用户
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 设置工作目录
WORKDIR /app

# 复制 Python 依赖文件
COPY ./backend/requirements.txt /app/requirements.txt

# 安装依赖 - 先安装关键依赖，利用缓存机制
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -r /app/requirements.txt

# 复制并执行模型下载脚本
COPY ./backend/download_models.py /app/download_models.py
RUN python /app/download_models.py && \
    # 确保目录结构符合预期
    mkdir -p /app/backend /app/frontend && \
    # 预先创建日志目录和设置权限
    mkdir -p /app/logs && \
    chown -R appuser:appuser /app

# 第二阶段: 最终镜像
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLEOCR_HOME=/app/paddleocr_models

# 必要的运行时依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    # 创建非root用户
    groupadd -r appuser && useradd -r -g appuser appuser

# 从上一阶段复制已安装的依赖和模型
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app/paddleocr_models /app/paddleocr_models
COPY --from=builder /app/logs /app/logs

# 设置工作目录
WORKDIR /app

# 复制代码
COPY --chown=appuser:appuser ./backend /app/backend
COPY --chown=appuser:appuser ./frontend /app/frontend

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:18765/health || exit 1

# 暴露 FastAPI 应用运行的端口
EXPOSE 18765

# 切换到非root用户
USER appuser

# 设置容器启动命令
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "18765"]