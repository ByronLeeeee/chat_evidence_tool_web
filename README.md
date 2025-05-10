# 易存讯 - 聊天记录取证助手 (Web版)

[![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ByronLeeeee/chat_evidence_tool_web/docker-publish-ghcr.yml?branch=main&style=flat-square)](https://github.com/ByronLeeeee/chat_evidence_tool_web/actions/workflows/docker-publish-ghcr.yml)
[![GitHub Container Registry](https://img.shields.io/badge/ghcr.io-ByronLeeeee/chat_evidence_tool_web-blue?style=flat-square)](https://github.com/ByronLeeeee/chat_evidence_tool_web/pkgs/container/chat-evidence-tool-web)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)

**易存讯** 是一款基于 Web 的多功能工具，旨在帮助用户（特别是法律从业者）高效处理聊天记录证据。它不仅能从屏幕录制的**视频文件**中提取聊天截图、利用 AI 模型进行 OCR 识别和智能筛选，还能对**长截图图片**进行智能分割和优化，最终生成格式规范、适合作为证据提交的 PDF 文件。

## ✨ 功能特性

### 通用功能
*   **PDF 生成:** 将处理后的截图按照指定的行列布局，生成清晰、规范的 A4 格式 PDF 文件。
    *   可自定义 PDF 标题。
    *   可自定义每页排列的截图数量（行数 x 列数）。
    *   可选择 PDF 排列方式（行优先或列优先）。
*   **截图预览与排序:** 展示处理后的截图，并允许用户通过拖拽调整它们在最终 PDF 中的顺序。
*   **主题切换:** 支持明亮和暗黑两种界面主题，适应不同用户的偏好。
*   **Docker 支持:** 提供 Dockerfile，方便快速部署和运行。
*   **跨平台:** 基于 Web 技术，可在任何现代浏览器中访问。

### 针对视频处理
*   **视频上传:** 支持上传常见的视频格式文件 (MP4, MOV, AVI, MKV 等)。
*   **智能帧提取:** 根据设定的时间间隔从视频中提取图像帧。
*   **OCR 识别:** 使用 PaddleOCR 对提取的图像帧进行高精度中文文字识别。
*   **内容筛选与去重:**
    *   可配置“内容排除白名单”，自动过滤截图中的特定干扰信息（如“对方正在输入…”、系统状态栏文字等）。
    *   智能检测相邻截图之间的内容重叠，自动筛选掉冗余截图，保留内容变化的关键帧。
*   **OCR 区域选择 (可选):** 提供可视化界面，允许用户在参考帧上框选仅需要进行 OCR 分析的特定区域。

### 针对长截图处理
*   **长截图上传:** 支持上传常见的图片格式 (PNG, JPG/JPEG, WEBP)。
*   **智能分割:** 根据用户设定的“每张截图高度”和“重叠区域高度”，将一张长截图智能分割成多张适合分页展示的独立截图。
*   **保持连续性:** 通过重叠区域的设置，确保分割后的截图内容自然衔接，不丢失信息。

## 🚀 技术栈

*   **后端:**
    *   **框架:** FastAPI
    *   **OCR 引擎:** PaddleOCR (用于视频处理)
    *   **图像处理:** Pillow (用于长截图分割)
    *   **视频处理:** FFmpeg
    *   **PDF 生成:** ReportLab
*   **前端:**
    *   **UI 库:** Bootstrap 5
    *   **图像裁剪:** Cropper.js (用于视频OCR区域选择)
    *   **拖拽排序:** SortableJS
*   **部署:** Docker, GitHub Actions (CI/CD)

## 快速开始

### 方式一：使用 Docker (推荐)

这是最简单且推荐的运行方式，避免了本地环境配置的复杂性。

1.  **安装 Docker:** 确保你的系统已安装 Docker。
2.  **拉取镜像:**
    ```bash
    docker pull ghcr.io/byronleeeee/chat_evidence_tool_web:latest
    ```
    *注意: 如果镜像是私有的，或者你遇到认证错误，可能需要先使用 `docker login ghcr.io -u YOUR_GITHUB_USERNAME -p YOUR_PAT` 登录。(YOUR_PAT 是具有 `read:packages` 权限的个人访问令牌)*
3.  **创建本地数据目录 (用于持久化):**
    在你的工作目录下创建两个文件夹：
    ```bash
    mkdir temp_sessions_host
    mkdir output_host
    ```
4.  **运行容器:**
    ```bash
    docker run -d -p 18765:18765 \
        -v ./temp_sessions_host:/app/temp_sessions \
        -v ./output_host:/app/output \
        --name chat-evidence-tool \
        ghcr.io/byronleeeee/chat_evidence_tool_web:latest
    ```
    *   `-d`: 后台运行
    *   `-p 18765:18765`: 将主机的 18765 端口映射到容器的 18765 端口
    *   `-v ./temp_sessions_host:/app/temp_sessions`: 挂载临时文件目录
    *   `-v ./output_host:/app/output`: 挂载 PDF 输出目录
    *   `--name chat-evidence-tool`: 为容器命名
5.  **访问应用:** 打开浏览器，访问 `http://localhost:18765`。

### 方式二：本地运行 (需要手动配置环境)

1.  **克隆仓库:**
    ```bash
    git clone https://github.com/byronleeeee/chat_evidence_tool_web.git
    cd chat_evidence_tool_web
    ```
2.  **安装 FFmpeg:** (视频处理功能需要)
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
    *注意：安装 Python 依赖可能需要一些时间，特别是 PaddleOCR 会在首次初始化时自动下载所需模型文件，请确保网络连接畅通。*
5.  **运行 FastAPI 服务器:**
    ```bash
    # 运行在 18765 端口，与 Docker 配置保持一致
    uvicorn backend.main:app --host 0.0.0.0 --port 18765 --reload
    ```
    *   `--reload` 参数用于开发模式。生产环境部署时请移除。
6.  **访问应用:** 打开浏览器，访问 `http://localhost:18765`。

## 📝 使用说明

应用界面包含两个主要功能标签页：**视频处理** 和 **长截图处理**。

### 通用操作
*   **预览与排序:** 在各自的处理流程完成后，生成的截图会显示在预览区域，你可以通过拖拽调整顺序。
*   **下载 PDF:** 点击对应功能区的 "下载PDF" 按钮获取最终文件。
*   **清理:** 点击 "清理会话" 或 "清理临时文件" 可以删除服务器上该次操作产生的临时文件。
*   **主题切换:** 点击右下角的图标切换明亮/暗黑主题。

### 视频处理标签页

1.  **上传视频:** 点击 "选择视频文件" 选择屏幕录制视频，然后点击 "上传视频"。
2.  **配置参数 (可选，通过手风琴展开各项设置):**
    *   **参数设置:**
        *   调整 **帧提取间隔** (秒)。
        *   配置 **内容排除白名单**。
    *   **OCR 分析区域:**
        *   点击 **加载参考帧**，在图片上框选聊天记录主要区域。
        *   使用 **清除选区** 取消框选。
    *   **PDF 输出设置:**
        *   设置 **每页行数/列数**，选择 **PDF排列方式** 和编辑 **PDF 标题**。
3.  **开始处理:** 点击 "处理视频并生成PDF" 按钮。
4.  **监控与获取结果:** 在右侧面板查看日志、进度，并在完成后下载 PDF。

### 长截图处理标签页

1.  **上传长截图:** 点击 "选择长截图文件" 选择你的长截图图片。
2.  **配置参数 (可选，通过手风琴展开各项设置):**
    *   **裁剪参数:**
        *   设定 **每张截图高度** (像素)。
        *   设定 **重叠区域高度** (像素)，以保证截图内容的连续性。
    *   **PDF 输出设置:**
        *   设置 **每页行数/列数**，选择 **PDF排列方式** 和编辑 **PDF 标题**。
3.  **开始处理:** 点击 "裁剪并生成PDF" 按钮。
4.  **监控与获取结果:** 在右侧面板查看日志、进度，并在完成后下载 PDF。

## 🤝 贡献

欢迎各种形式的贡献！

*   **报告 Bug:** 如果你发现了问题，请在 [Issues](https://github.com/byronleeeee/chat_evidence_tool_web/issues) 中提交详细的 Bug 报告。
*   **功能建议:** 有好的想法？也请在 [Issues](https://github.com/byronleeeee/chat_evidence_tool_web/issues) 中提出。
*   **代码贡献:**
    1.  Fork 本仓库。
    2.  创建你的特性分支 (`git checkout -b feature/AmazingFeature`)。
    3.  提交你的更改 (`git commit -m 'Add some AmazingFeature'`)。
    4.  将你的分支推送到你的 Fork (`git push origin feature/AmazingFeature`)。
    5.  创建一个 Pull Request。

## 📜 开源许可

本项目采用 [MIT License](LICENSE) 开源许可。

## 致谢

*   感谢 [PaddlePaddle](https://github.com/PaddlePaddle/Paddle) 和 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) 团队提供的强大 OCR 能力。
*   感谢 [FastAPI](https://fastapi.tiangolo.com/) 框架的开发者。
*   感谢 [ReportLab](https://www.reportlab.com/) 和 [Pillow](https://python-pillow.org/)。
*   感谢 [Bootstrap](https://getbootstrap.com/), [Cropper.js](https://github.com/fengyuanchen/cropperjs), [SortableJS](https://github.com/SortableJS/Sortable)。

---

*如果在使用中遇到问题或有任何建议，欢迎联系作者：李伯阳 (liboyang@lslby.com / 微信号: legal-lby)*