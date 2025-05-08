# 使用一个包含 Python 的官方镜像，slim 版本比较小
FROM python:3.11-slim

# 设置环境变量，避免 Python 写入 .pyc 文件和缓冲 stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装系统依赖
# libgl1-mesa-glx 和 libglib2.0-0 是 OpenCV (PaddleOCR的依赖) 可能需要的图形库
# 如果你的 PaddleOCR 使用的是 headless opencv，可能不需要这么多
# curl 和 unzip 用于后面下载 PaddleOCR 模型（可选）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    # 如果 Pillow 编译需要，可能还要 libjpeg-dev zlib1g-dev 等，但通常 slim 镜像的 Python 自带
    # 可选: 用于下载 PaddleOCR 模型
    # curl \
    # unzip \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制 Python 依赖文件并安装
# 这样做可以利用 Docker 的层缓存，只有当 requirements.txt 改变时才会重新安装
COPY ./backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 复制后端和前端代码到镜像中
COPY ./backend /app/backend
COPY ./frontend /app/frontend

# （可选）预下载 PaddleOCR 模型
# 这会使镜像变大，但可以避免首次运行时下载模型，加快启动速度
# 如果选择这样做，请确保你有足够的磁盘空间和网络带宽在构建时下载
ENV PADDLEOCR_HOME=/app/paddleocr_models
RUN mkdir -p $PADDLEOCR_HOME && \
    python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='ch', ocr_version='PP-OCRv4', det_model_dir=f'{PADDLEOCR_HOME}/det_v4', rec_model_dir=f'{PADDLEOCR_HOME}/rec_v4', cls_model_dir=f'{PADDLEOCR_HOME}/cls_v2', show_log=True)"
# 注意：上面的模型路径 (det_v4, rec_v4, cls_v2) 可能需要根据你实际使用的 PaddleOCR 版本调整。
# 或者，你也可以在第一次运行容器时，通过挂载一个包含已下载模型的卷来提供模型。

# 暴露 FastAPI 应用运行的端口
EXPOSE 18765

# 设置容器启动时运行的命令
# 使用 uvicorn 运行 FastAPI 应用
# backend.main:app 指向 backend 目录下的 main.py 文件中的 app FastAPI 实例
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "18675"]