document.addEventListener('DOMContentLoaded', () => {
    const videoFileInput = document.getElementById('videoFile');
    const uploadButton = document.getElementById('uploadButton');
    const frameIntervalInput = document.getElementById('frameInterval');
    const exclusionListInput = document.getElementById('exclusionList');
    const loadRefFrameButton = document.getElementById('loadRefFrameButton');
    const clearOcrRegionButton = document.getElementById('clearOcrRegionButton');
    const ocrCropContainer = document.getElementById('ocrCropContainer');
    const refImageElement = document.getElementById('refImage');
    const ocrCoordsP = document.getElementById('ocrCoords');
    const pdfRowsInput = document.getElementById('pdfRows');
    const pdfColsInput = document.getElementById('pdfCols');
    const pdfTitleInput = document.getElementById('pdfTitle');
    const processButton = document.getElementById('processButton');
    const progressBarContainer = document.getElementById('progressBarContainer');
    const progressBar = document.getElementById('progressBar');
    const progressStatus = document.getElementById('progressStatus');
    const logOutput = document.getElementById('logOutput');
    const previewArea = document.getElementById('previewArea');
    const downloadPdfButton = document.getElementById('downloadPdfButton');
    const cleanupButton = document.getElementById('cleanupButton');

    let currentSessionId = null;
    let websocket = null;
    let cropper = null;
    let ocrSelection = null; // { x, y, width, height }
    let sortable = null;

    // --- Helper Functions ---
    function addLog(message, type = 'info') {
        const time = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.innerHTML = `[${time}] ${message.replace(/\n/g, '<br>')}`; // Preserve newlines
        if (type === 'error') {
            logEntry.style.color = 'red';
        } else if (type === 'success') {
            logEntry.style.color = 'green';
        }
        logOutput.appendChild(logEntry);
        logOutput.scrollTop = logOutput.scrollHeight;
    }

    function updateProgress(percentage, statusText = '') {
        progressBarContainer.style.display = 'block';
        progressBar.style.width = `${percentage}%`;
        progressBar.setAttribute('aria-valuenow', percentage);
        progressBar.textContent = `${percentage}%`;
        progressStatus.textContent = statusText;
    }

    function resetUIForNewSession(resetFileInput = true) {
        currentSessionId = null;
        if (websocket) websocket.close();
        websocket = null;
    
        // 只在需要时重置文件输入
        if (resetFileInput) {
            videoFileInput.value = '';
            uploadButton.disabled = true;
        }
        
        loadRefFrameButton.disabled = true;
        clearOcrRegionButton.disabled = true;
        processButton.disabled = true;
        downloadPdfButton.classList.add('disabled');
        downloadPdfButton.href = '#';
        cleanupButton.disabled = true;
    
        logOutput.innerHTML = '';
        previewArea.innerHTML = '';
        ocrCropContainer.style.display = 'none';
        if (cropper) cropper.destroy();
        cropper = null;
        refImageElement.src = '#';
        ocrCoordsP.textContent = '';
        ocrSelection = null;
    
        progressBarContainer.style.display = 'none';
        updateProgress(0, '');
        if (resetFileInput) {
            addLog("请选择一个新的视频文件开始。");
        }
    }

    function setupSortable() {
        if (sortable) sortable.destroy();
        sortable = new Sortable(previewArea, {
            animation: 150,
            ghostClass: 'bg-light', // Class for the drop placeholder
            // onEnd: function (evt) { /* Can update server if needed, or just use order at PDF gen time */ }
        });
    }

    // --- Event Listeners ---
    if (videoFileInput) { // 确保元素存在
        videoFileInput.addEventListener('change', () => {
            uploadButton.disabled = !videoFileInput.files.length; // 根据是否有文件启用/禁用上传按钮
            if (videoFileInput.files && videoFileInput.files.length > 0) {
                console.log("File selected in 'change' event:", videoFileInput.files[0]);
                addLog(`已选择文件: ${videoFileInput.files[0].name}`);
            } else {
                console.log("File selection cleared in 'change' event.");
                addLog("文件选择已清除。");
            }
        });
    }

    uploadButton.addEventListener('click', async () => {
        console.log("Upload button clicked. Checking file input now.");
        
        // 1. 首先保存文件引用，这很重要
        const fileToUpload = videoFileInput.files[0];
        console.log("Captured file for upload:", fileToUpload);
        
        if (!fileToUpload) {
            addLog("错误：未检测到有效文件。请重新选择文件。", "error");
            uploadButton.disabled = false;
            return;
        }
        
        // 2. 禁用上传按钮防止重复点击
        uploadButton.disabled = true;
        addLog("开始上传视频...");
        
        // 注意：不要在这里调用resetUIForNewSession，而是只重置必要的UI元素
        // 清除之前的会话状态，但保留文件选择
        if (websocket) websocket.close();
        websocket = null;
        currentSessionId = null;
        
        logOutput.innerHTML = '';
        previewArea.innerHTML = '';
        ocrCropContainer.style.display = 'none';
        if (cropper) cropper.destroy();
        cropper = null;
        refImageElement.src = '#';
        ocrCoordsP.textContent = '';
        ocrSelection = null;
        progressBarContainer.style.display = 'none';
        updateProgress(0, '');
        
        // 3. 创建FormData对象
        const formData = new FormData();
        formData.append('video_file', fileToUpload); // 使用保存的引用
        
        // 4. 记录FormData内容
        console.log("FormData entries after append:");
        for (let pair of formData.entries()) {
            console.log(pair[0] + ': ', pair[1]);
        }
        
        // 5. 发送请求
        try {
            console.log("About to send fetch request with this body:", formData);
            const response = await fetch('/upload_video/', {
                method: 'POST',
                body: formData,
            });
            const data = await response.json();
    
            if (response.ok) {
                currentSessionId = data.session_id;
                addLog(`视频上传成功。会话ID: ${currentSessionId}`, "success");
                addLog(`文件名: ${data.filename}`);
                
                // 成功获取会话ID后，建立WebSocket连接
                connectWebSocket();
                
                // 然后启用相关按钮
                loadRefFrameButton.disabled = false;
                processButton.disabled = false;
                cleanupButton.disabled = false;
            } else {
                addLog(`上传失败: ${data.message || response.statusText}`, "error");
                uploadButton.disabled = false;
            }
        } catch (error) {
            addLog(`上传出错: ${error}`, "error");
            uploadButton.disabled = false;
        }
    });

    loadRefFrameButton.addEventListener('click', async () => {
        if (!currentSessionId) {
            addLog("没有活动的会话ID。请先上传视频。", "error");
            return;
        }
        addLog("正在加载参考帧...");
        loadRefFrameButton.disabled = true;

        try {
            const response = await fetch(`/get_reference_frame/${currentSessionId}`);
            if (response.ok) {
                const imageBlob = await response.blob();
                const imageUrl = URL.createObjectURL(imageBlob);
                refImageElement.src = imageUrl;
                ocrCropContainer.style.display = 'block';

                if (cropper) cropper.destroy();
                cropper = new Cropper(refImageElement, {
                    aspectRatio: NaN, // Free crop
                    viewMode: 1, // restrict the crop box not to exceed the size of the canvas.
                    autoCropArea: 0.8,
                    crop(event) {
                        ocrSelection = {
                            x: Math.round(event.detail.x),
                            y: Math.round(event.detail.y),
                            width: Math.round(event.detail.width),
                            height: Math.round(event.detail.height),
                        };
                        ocrCoordsP.textContent = `选区: X=${ocrSelection.x}, Y=${ocrSelection.y}, W=${ocrSelection.width}, H=${ocrSelection.height}`;
                    },
                });
                clearOcrRegionButton.disabled = false;
                addLog("参考帧已加载。请在图片上框选OCR区域。", "success");
            } else {
                const errorData = await response.json();
                addLog(`加载参考帧失败: ${errorData.detail || response.statusText}`, "error");
            }
        } catch (error) {
            addLog(`加载参考帧出错: ${error}`, "error");
        } finally {
            loadRefFrameButton.disabled = false;
        }
    });

    clearOcrRegionButton.addEventListener('click', () => {
        if (cropper) {
            cropper.clear(); // Clears the crop box
        }
        ocrSelection = null;
        ocrCoordsP.textContent = "选区已清除。";
        addLog("OCR选区已清除。");
    });

    processButton.addEventListener('click', async () => {
        if (!currentSessionId) {
            addLog("没有活动的会话ID。", "error");
            return;
        }
        addLog("开始处理流程...");
        processButton.disabled = true;
        downloadPdfButton.classList.add('disabled');
        downloadPdfButton.href = '#';
        previewArea.innerHTML = ''; // Clear previous previews
        updateProgress(0, "准备处理...");

        const settings = {
            frame_interval_seconds: parseFloat(frameIntervalInput.value),
            exclusion_list: exclusionListInput.value.split('\n').map(s => s.trim()).filter(s => s),
            ocr_analysis_rect: ocrSelection ? [ocrSelection.x, ocrSelection.y, ocrSelection.width, ocrSelection.height] : null,
            pdf_rows: parseInt(pdfRowsInput.value),
            pdf_cols: parseInt(pdfColsInput.value),
            pdf_title: pdfTitleInput.value,
            image_order: getPreviewImageOrder() // Get order before starting new process
        };

        try {
            const response = await fetch(`/process_video/${currentSessionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings),
            });
            const data = await response.json();
            if (response.ok) {
                addLog(data.message || "处理已启动，请关注WebSocket日志。", "success");
            } else {
                addLog(`启动处理失败: ${data.detail || data.message || response.statusText}`, "error");
                processButton.disabled = false;
            }
        } catch (error) {
            addLog(`启动处理出错: ${error}`, "error");
            processButton.disabled = false;
        }
    });

    function getPreviewImageOrder() {
        const items = previewArea.querySelectorAll('.preview-item img');
        const order = [];
        items.forEach(item => {
            const url = new URL(item.src);
            order.push(decodeURIComponent(url.pathname.split('/').pop())); // Get filename from URL
        });
        return order;
    }

    cleanupButton.addEventListener('click', async () => {
        if (!currentSessionId) {
            addLog("没有活动的会话ID可清理。", "warning");
            return;
        }
        if (!confirm(`确定要清理会话 ${currentSessionId} 的所有临时文件吗？`)) {
            return;
        }
        addLog(`正在清理会话 ${currentSessionId}...`);
        try {
            const response = await fetch(`/cleanup_session/${currentSessionId}`, { method: 'POST' });
            const data = await response.json();
            if (response.ok) {
                addLog(data.message, "success");
            } else {
                addLog(`清理失败: ${data.detail || data.message}`, "error");
            }
        } catch (error) {
            addLog(`清理出错: ${error}`, "error");
        } finally {
            resetUIForNewSession(); // Reset UI after cleanup attempt
        }
    });


    // --- WebSocket Handling ---
    function connectWebSocket() {
        if (!currentSessionId) {
            addLog("无法连接WebSocket：无会话ID。", "error");
            return;
        }
        
        if (websocket) {
            if (websocket.readyState === WebSocket.OPEN) {
                addLog("WebSocket 已连接。");
                return;
            }
            // 如果连接不是打开状态，关闭旧连接
            websocket.close();
            websocket = null;
        }
    
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/${currentSessionId}`;
        addLog(`正在连接WebSocket: ${wsUrl}`);
        
        websocket = new WebSocket(wsUrl);
    
        websocket.onopen = () => {
            addLog("WebSocket 连接成功。", "success");
        };

        websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            addLog(`[WS] ${data.status}: ${data.message}`);

            if (data.progress !== null && data.progress !== undefined) {
                updateProgress(data.progress, `${data.status}: ${data.message}`);
            } else if (data.status.includes("extracting") || data.status.includes("ocr_processing") || data.status.includes("pdf_generating")) {
                updateProgress(progressBar.getAttribute('aria-valuenow'), `${data.status}: ${data.message}`); // Keep current progress if only message updates
            }


            if (data.status === "ocr_completed" && data.preview_images) {
                previewArea.innerHTML = ''; // Clear old previews
                data.preview_images.forEach(imgUrl => {
                    const colDiv = document.createElement('div');
                    colDiv.className = 'col-6 col-sm-4 col-md-3 preview-item'; // Bootstrap responsive columns
                    const img = document.createElement('img');
                    img.src = imgUrl; // Server provides full URL
                    img.className = 'img-fluid rounded';
                    img.alt = 'Preview';
                    colDiv.appendChild(img);
                    previewArea.appendChild(colDiv);
                });
                if (data.preview_images.length > 0) {
                    setupSortable(); // Initialize sortable for new preview items
                }
            }

            if (data.status === "completed" && data.result_url) {
                downloadPdfButton.href = data.result_url;
                downloadPdfButton.classList.remove('disabled');
                addLog(`PDF准备就绪: <a href="${data.result_url}" target="_blank" download>点击下载</a>`, "success");
                updateProgress(100, "全部完成！PDF已生成。");
                processButton.disabled = false; // Allow reprocessing or new PDF
            } else if (data.status === "completed_no_pdf") {
                addLog("处理完成，但没有图片可用于生成PDF。");
                updateProgress(100, "处理完成，无PDF。");
                processButton.disabled = false;
            } else if (data.status === "error") {
                addLog(`处理错误: ${data.message}`, "error");
                updateProgress(progressBar.getAttribute('aria-valuenow') || 0, `错误: ${data.message}`); // Keep progress or reset
                processButton.disabled = false;
            }
        };

        websocket.onclose = (event) => {
            addLog(`WebSocket 连接已关闭。代码: ${event.code}, 原因: ${event.reason || '未知'}`, "warning");
            
            // 如果是意外关闭，尝试重新连接
            if (event.code !== 1000 && event.code !== 1001) { // 正常关闭或用户导航离开
                addLog("尝试重新连接...");
                setTimeout(connectWebSocket, 3000); // 3秒后重试
            }
        };

        websocket.onerror = (error) => {
            addLog(`WebSocket 错误: ${error.message || '未知错误'}`, "error");
        };
    }

    // Initial UI state
    resetUIForNewSession(); // Set initial state for disabled buttons etc.
});

// 添加主题切换按钮到HTML中
document.addEventListener('DOMContentLoaded', function() {
    // 创建主题切换按钮
    const themeToggle = document.createElement('button');
    themeToggle.className = 'theme-toggle';
    themeToggle.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M8 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm0 1a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM8 0a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 0zm0 13a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 13zm8-5a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2a.5.5 0 0 1 .5.5zM3 8a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2A.5.5 0 0 1 3 8zm10.657-5.657a.5.5 0 0 1 0 .707l-1.414 1.415a.5.5 0 1 1-.707-.708l1.414-1.414a.5.5 0 0 1 .707 0zm-9.193 9.193a.5.5 0 0 1 0 .707L3.05 13.657a.5.5 0 0 1-.707-.707l1.414-1.414a.5.5 0 0 1 .707 0zm9.193 2.121a.5.5 0 0 1-.707 0l-1.414-1.414a.5.5 0 0 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .707zM4.464 4.465a.5.5 0 0 1-.707 0L2.343 3.05a.5.5 0 1 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .708z"/></svg>';
    document.body.appendChild(themeToggle);

    // 获取当前主题（默认亮色主题）
    let currentTheme = localStorage.getItem('theme') || 'light';
    
    // 应用保存的主题
    applyTheme(currentTheme);
    
    // 切换主题事件
    themeToggle.addEventListener('click', function() {
        currentTheme = currentTheme === 'light' ? 'dark' : 'light';
        applyTheme(currentTheme);
        localStorage.setItem('theme', currentTheme);
    });

    // 更新主题图标
    updateThemeIcon(currentTheme);
});

// 应用主题到HTML
function applyTheme(theme) {
    if (theme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
    updateThemeIcon(theme);
}

// 更新主题切换按钮图标
function updateThemeIcon(theme) {
    const themeToggle = document.querySelector('.theme-toggle');
    if (!themeToggle) return;
    
    if (theme === 'dark') {
        themeToggle.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278z"/></svg>';
    } else {
        themeToggle.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16"><path d="M8 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm0 1a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM8 0a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 0zm0 13a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 13zm8-5a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2a.5.5 0 0 1 .5.5zM3 8a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2A.5.5 0 0 1 3 8zm10.657-5.657a.5.5 0 0 1 0 .707l-1.414 1.415a.5.5 0 1 1-.707-.708l1.414-1.414a.5.5 0 0 1 .707 0zm-9.193 9.193a.5.5 0 0 1 0 .707L3.05 13.657a.5.5 0 0 1-.707-.707l1.414-1.414a.5.5 0 0 1 .707 0zm9.193 2.121a.5.5 0 0 1-.707 0l-1.414-1.414a.5.5 0 0 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .707zM4.464 4.465a.5.5 0 0 1-.707 0L2.343 3.05a.5.5 0 1 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .708z"/></svg>';
    }
}
