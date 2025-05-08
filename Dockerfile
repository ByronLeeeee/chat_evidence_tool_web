# 使用一个包含 Python 的官方镜像，slim 版本比较小
FROM python:3.11-slim

# 设置环境变量，避免 Python 写入 .pyc 文件和缓冲 stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

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

# 复制 Python 依赖文件并安装
COPY ./backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 复制后端和前端代码到镜像中
COPY ./backend /app/backend
COPY ./frontend /app/frontend

# （可选）预下载 PaddleOCR 模型
# 这会使镜像变大，但可以避免首次运行时下载模型，加快启动速度
ENV PADDLEOCR_HOME=/app/paddleocr_models
# 使用 os.getenv 读取环境变量 PADDLEOCR_HOME
RUN mkdir -p $PADDLEOCR_HOME && \
    python -c "import os; from paddleocr import PaddleOCR; \
    paddleocr_home = os.getenv('PADDLEOCR_HOME', '/app/paddleocr_models'); \
    print(f'>>> Pre-downloading PaddleOCR models to: {paddleocr_home}'); \
    try: \
        PaddleOCR(use_angle_cls=True, lang='ch', ocr_version='PP-OCRv4', \
                  det_model_dir=f'{paddleocr_home}/det_v4', \
                  rec_model_dir=f'{paddleocr_home}/rec_v4', \
                  cls_model_dir=f'{paddleocr_home}/cls_v2', \
                  show_log=True); \
        print('>>> PaddleOCR models pre-download attempt finished.'); \
    except Exception as e: \
        print(f'>>> Error during PaddleOCR pre-download: {e}'); \
        # Decide if you want the build to fail on error, or just warn
        # exit(1) # Uncomment to make the build fail if download fails
    "
# 注意：模型路径 (det_v4, rec_v4, cls_v2) 可能需要根据你实际使用的 PaddleOCR 版本调整。

# 暴露 FastAPI 应用运行的端口
EXPOSE 18765

# 设置容器启动时运行的命令
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "18765"]
