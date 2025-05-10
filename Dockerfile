# 使用一个包含 Python 的官方镜像，slim 版本比较小
FROM python:3.11-slim

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PADDLEOCR_HOME=/app/paddleocr_models

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制 Python 依赖文件
COPY ./backend/requirements.txt /app/requirements.txt

# 安装 Python 依赖
RUN pip install --no-cache-dir -r /app/requirements.txt

# 复制后端和前端代码
COPY ./backend /app/backend
COPY ./frontend /app/frontend

# 复制并执行模型下载脚本
COPY ./backend/download_models.py /app/download_models.py
RUN python /app/download_models.py

# 暴露 FastAPI 应用运行的端口
EXPOSE 18765

# 设置容器启动命令
# 确保 uvicorn 能找到 backend 目录下的 main.py 中的 app 实例
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "18765"]