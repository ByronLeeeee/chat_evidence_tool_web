# 易存讯 - 聊天记录取证助手 (Web版)

[![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ByronLeeeee/chat_evidence_tool_web/docker-publish-ghcr.yml?branch=main&style=flat-square)](https://github.com/ByronLeeeee/chat_evidence_tool_web/actions/workflows/docker-publish-ghcr.yml)
[![Docker Image Version (latest by date)](https://img.shields.io/github/v/release/ByronLeeeee/chat_evidence_tool_web?display_name=release&sort=date&style=flat-square)](https://github.com/ByronLeeeee/chat_evidence_tool_web/pkgs/container/chat-evidence-tool-web) 
[![GitHub Container Registry](https://img.shields.io/badge/ghcr.io-ByronLeeeee/chat_evidence_tool_web-blue?style=flat-square)](https://github.com/ByronLeeeee/chat_evidence_tool_web/pkgs/container/chat-evidence-tool-web)

**易存讯** 是一款基于 Web 的工具，旨在帮助用户（特别是法律从业者）从屏幕录制的视频文件中，高效地提取聊天记录截图，利用 AI 模型进行 OCR 识别和智能筛选（排除无关信息、处理滚动重叠），最终生成格式规范、适合作为证据提交的 PDF 文件。

## ✨ 功能特性

*   **视频上传:** 支持上传常见的视频格式文件 (MP4, MOV, AVI, MKV 等)。
*   **智能帧提取:** 根据设定的时间间隔从视频中提取图像帧。
*   **OCR 识别:** 使用 PaddleOCR 对提取的图像帧进行高精度中文文字识别。
*   **内容筛选与去重:**
    *   可配置“内容排除白名单”，自动过滤截图中的特定干扰信息（如“对方正在输入…”、系统状态栏文字等）。
    *   智能检测相邻截图之间的内容重叠，自动筛选掉冗余截图，保留内容变化的关键帧。
*   **OCR 区域选择 (可选):** 提供可视化界面，允许用户在参考帧上框选仅需要进行 OCR 分析的特定区域（例如去除顶部状态栏和底部输入框）。
*   **截图预览与排序:** 展示筛选后的关键截图，并允许用户通过拖拽调整截图在最终 PDF 中的顺序。
*   **PDF 生成:** 将筛选并排序后的截图按照指定的行列布局，生成清晰、规范的 A4 格式 PDF 文件。
    *   可自定义 PDF 标题。
    *   可自定义每页排列的截图数量（行数 x 列数）。
*   **主题切换:** 支持明亮和暗黑两种界面主题，适应不同用户的偏好。
*   **Docker 支持:** 提供 Dockerfile，方便快速部署和运行。
*   **跨平台:** 基于 Web 技术，可在任何现代浏览器中访问。

## 🚀 技术栈

*   **后端:**
    *   **框架:** FastAPI
    *   **OCR 引擎:** PaddleOCR
    *   **视频处理:** FFmpeg (通过 `subprocess` 调用)
    *   **PDF 生成:** ReportLab
    *   **异步处理:** Asyncio, `run_in_executor`
    *   **实时通信:** WebSockets
*   **前端:**
    *   **核心:** HTML, CSS, JavaScript (ES6+)
    *   **UI 库:** Bootstrap 5
    *   **图像裁剪:** Cropper.js
    *   **拖拽排序:** SortableJS
*   **部署:** Docker, GitHub Actions (用于 CI/CD)

## 快速开始

### 方式一：使用 Docker (推荐)

这是最简单且推荐的运行方式，避免了本地环境配置的复杂性。

1.  **安装 Docker:** 确保你的系统已安装 Docker 和 Docker Compose (可选)。
2.  **拉取镜像:**
    ```bash
    # 将 '你的用户名/你的仓库名' 替换为实际的 GHCR 路径
    docker pull ghcr.io/你的用户名/你的仓库名:latest
    ```
    *注意：如果镜像是私有的，你可能需要先 `docker login ghcr.io`。*
3.  **创建本地数据目录 (用于持久化):**
    在你的工作目录下创建两个文件夹：
    ```bash
    mkdir temp_sessions_host
    mkdir output_host
    ```
4.  **运行容器:**
    ```bash
    docker run -d -p 8000:8000 \
        -v ./temp_sessions_host:/app/temp_sessions \
        -v ./output_host:/app/output \
        --name chat-evidence-tool \
        ghcr.io/你的用户名/你的仓库名:latest
    ```
    *   `-d`: 后台运行
    *   `-p 8000:8000`: 将主机的 8000 端口映射到容器的 8000 端口
    *   `-v ./temp_sessions_host:/app/temp_sessions`: 挂载临时文件目录
    *   `-v ./output_host:/app/output`: 挂载 PDF 输出目录
    *   `--name chat-evidence-tool`: 为容器命名
5.  **访问应用:** 打开浏览器，访问 `http://localhost:8000`。

### 方式二：本地运行 (需要手动配置环境)

1.  **克隆仓库:**
    ```bash
    git clone https://github.com/你的用户名/你的仓库名.git
    cd 你的仓库名
    ```
2.  **安装 FFmpeg:**
    确保你的系统安装了 FFmpeg，并且 `ffmpeg` 命令在系统的 PATH 环境变量中。
    *   **Ubuntu/Debian:** `sudo apt update && sudo apt install ffmpeg`
    *   **macOS (使用 Homebrew):** `brew install ffmpeg`
    *   **Windows:** 从 [FFmpeg 官网](https://ffmpeg.org/download.html) 下载预编译版本，并将其 `bin` 目录添加到系统 PATH。
3.  **创建并激活 Python 虚拟环境 (推荐):**
    ```bash
    python -m venv .venv
    # Windows
    .\.venv\Scripts\activate
    # macOS/Linux
    source .venv/bin/activate
    ```
4.  **安装 Python 依赖:**
    ```bash
    pip install -r backend/requirements.txt
    ```
    *注意：安装 `paddlepaddle` 和 `paddleocr` 可能需要一些时间，并会自动下载所需的模型文件（首次运行时）。*
5.  **运行 FastAPI 服务器:**
    ```bash
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
    ```
    *   `--reload` 参数用于开发模式，当代码更改时会自动重启服务器。生产环境部署时请移除。
6.  **访问应用:** 打开浏览器，访问 `http://localhost:8000`。

## 📝 使用说明

1.  **上传视频:** 点击 "选择视频文件" 按钮选择你的屏幕录制视频，然后点击 "上传视频"。
2.  **配置参数 (可选):**
    *   调整 **帧提取间隔** (秒) 来控制截图密度。
    *   在 **内容排除白名单** 中输入希望 OCR 忽略的常见短语（每行一个）。
    *   点击 **加载参考帧**，在图片上框选出聊天记录主要区域，以提高 OCR 精度和速度。使用 **清除选区** 取消框选。
    *   设置 **PDF 每页行数/列数** 和 **PDF 标题**。
3.  **开始处理:** 点击 "开始处理并生成PDF" 按钮。
4.  **监控进度:** 在右侧面板查看实时日志和进度条。
5.  **预览与排序:** 处理完成后，筛选出的关键帧会显示在预览区域。你可以通过拖拽调整它们的顺序。
6.  **下载 PDF:** 点击 "下载PDF" 按钮获取最终生成的证据文件。
7.  **清理会话 (可选):** 处理完成后，点击 "清理会话" 可以删除服务器上的临时文件（视频、帧截图）。
8.  **主题切换:** 点击右下角的图标切换明亮/暗黑主题。

## 🤝 贡献

欢迎各种形式的贡献！

*   **报告 Bug:** 如果你发现了问题，请在 [Issues](https://github.com/你的用户名/你的仓库名/issues) 中提交详细的 Bug 报告。
*   **功能建议:** 有好的想法？也请在 [Issues](https://github.com/你的用户名/你的仓库名/issues) 中提出。
*   **代码贡献:**
    1.  Fork 本仓库。
    2.  创建你的特性分支 (`git checkout -b feature/AmazingFeature`)。
    3.  提交你的更改 (`git commit -m 'Add some AmazingFeature'`)。
    4.  将你的分支推送到你的 Fork (`git push origin feature/AmazingFeature`)。
    5.  创建一个 Pull Request。

## 📜 开源许可

本项目采用 [MIT License](LICENSE) 开源许可。 <!-- 你需要添加一个 LICENSE 文件 -->

## 致谢

*   感谢 [PaddlePaddle](https://github.com/PaddlePaddle/Paddle) 和 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) 团队提供的强大 OCR 能力。
*   感谢 [FastAPI](https://fastapi.tiangolo.com/) 框架的开发者。
*   感谢 [ReportLab](https://www.reportlab.com/)。
*   感谢 [Bootstrap](https://getbootstrap.com/), [Cropper.js](https://github.com/fengyuanchen/cropperjs), [SortableJS](https://github.com/SortableJS/Sortable)。

---

*如果在使用中遇到问题或有任何建议，欢迎联系作者：李伯阳 (liboyang@lslby.com / 微信号: legal-lby)*