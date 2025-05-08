// frontend/script.js
document.addEventListener("DOMContentLoaded", () => {
  // --- 获取所有元素引用 (确保 ID 与 index.html 对应) ---
  // Video Panel Elements
  const videoFileInput = document.getElementById("videoFile");
  const uploadVideoButton = document.getElementById("uploadVideoButton");
  const frameIntervalInput = document.getElementById("frameInterval");
  const exclusionListInput = document.getElementById("exclusionList");
  const loadRefFrameButton = document.getElementById("loadRefFrameButton");
  const clearOcrRegionButton = document.getElementById("clearOcrRegionButton");
  const ocrCropContainer = document.getElementById("ocrCropContainer");
  const refImageElement = document.getElementById("refImage");
  const ocrCoordsP = document.getElementById("ocrCoords");
  const pdfRowsVideoInput = document.getElementById("pdfRowsVideo");
  const pdfColsVideoInput = document.getElementById("pdfColsVideo");
  const pdfLayoutVideoSelect = document.getElementById("pdfLayoutVideo");
  const pdfTitleVideoInput = document.getElementById("pdfTitleVideo");
  const processVideoButton = document.getElementById("processVideoButton");
  const videoProgressBarContainer = document.getElementById(
    "videoProgressBarContainer"
  );
  const videoProgressBar = document.getElementById("videoProgressBar");
  const videoProgressStatus = document.getElementById("videoProgressStatus");
  const videoLogOutput = document.getElementById("videoLogOutput");
  const videoPreviewArea = document.getElementById("videoPreviewArea");
  const videoDownloadPdfButton = document.getElementById(
    "videoDownloadPdfButton"
  );
  const videoCleanupButton = document.getElementById("videoCleanupButton");

  // Long Image Panel Elements
  const longImageFileInput = document.getElementById("longImageFile");
  const sliceHeightInput = document.getElementById("sliceHeight");
  const overlapHeightInput = document.getElementById("overlapHeight");
  const pdfRowsLongInput = document.getElementById("pdfRowsLong");
  const pdfColsLongInput = document.getElementById("pdfColsLong");
  const pdfLayoutLongSelect = document.getElementById("pdfLayoutLong");
  const pdfTitleLongInput = document.getElementById("pdfTitleLong");
  const processLongImageButton = document.getElementById(
    "processLongImageButton"
  );
  const longImageProgressBarContainer = document.getElementById(
    "longImageProgressBarContainer"
  );
  const longImageProgressBar = document.getElementById("longImageProgressBar");
  const longImageProgressStatus = document.getElementById(
    "longImageProgressStatus"
  );
  const longImageLogOutput = document.getElementById("longImageLogOutput");
  const longImagePreviewArea = document.getElementById("longImagePreviewArea");
  const longImageDownloadPdfButton = document.getElementById(
    "longImageDownloadPdfButton"
  );
  const longImageCleanupButton = document.getElementById(
    "longImageCleanupButton"
  );

  // --- 全局状态管理 ---
  let activeWebSocket = null; // 当前活动的 WebSocket 连接
  let videoSessionId = null; // 视频处理任务的会话 ID
  let longImageSessionId = null; // 长截图处理任务的会话 ID
  let activeTaskType = "video"; // 当前用户界面关注的任务类型 ('video' 或 'longImage')
  let cropper = null; // Cropper.js 实例 (只用于视频处理的参考帧)
  let ocrSelection = null; // OCR 裁剪区域 { x, y, width, height } (只用于视频处理)
  let videoSortable = null; // SortableJS 实例 (视频预览区)
  let longImageSortable = null; // SortableJS 实例 (长截图预览区)

  // --- Helper Functions ---
  /**
   * 向指定任务类型的日志区域添加日志。
   * @param {string} message 日志消息
   * @param {string} type 日志类型 ('info', 'success', 'error', 'warning')
   * @param {string} taskType 目标任务类型 ('video' 或 'longImage')
   */
  function addLog(message, type = "info", taskType = activeTaskType) {
    const targetLog =
      taskType === "video" ? videoLogOutput : longImageLogOutput;
    if (!targetLog) {
      console.error("Target log output not found for:", taskType);
      return;
    }
    const time = new Date().toLocaleTimeString();
    const logEntry = document.createElement("div");
    // 使用 textContent 防止 XSS，并通过 CSS white-space: pre-wrap 处理换行
    logEntry.textContent = `[${time}] ${message}`;
    logEntry.className = `log-entry log-${type}`; // 添加 class 以便 CSS 控制颜色
    targetLog.appendChild(logEntry);
    targetLog.scrollTop = targetLog.scrollHeight;
  }

  /**
   * 更新指定任务类型的进度条。
   * @param {number} percentage 进度百分比 (0-100)
   * @param {string} statusText 状态文本
   * @param {string} taskType 目标任务类型 ('video' 或 'longImage')
   */
  function updateProgress(
    percentage,
    statusText = "",
    taskType = activeTaskType
  ) {
    const targetContainer =
      taskType === "video"
        ? videoProgressBarContainer
        : longImageProgressBarContainer;
    const targetBar =
      taskType === "video" ? videoProgressBar : longImageProgressBar;
    const targetStatus =
      taskType === "video" ? videoProgressStatus : longImageProgressStatus;
    if (!targetContainer || !targetBar || !targetStatus) {
      console.error("Target progress elements not found for:", taskType);
      return;
    }

    targetContainer.style.display = "block";
    const clampedPercentage = Math.max(
      0,
      Math.min(100, Math.round(percentage))
    );
    targetBar.style.width = `${clampedPercentage}%`;
    targetBar.setAttribute("aria-valuenow", clampedPercentage);
    targetBar.textContent = `${clampedPercentage}%`;
    targetStatus.textContent = statusText;
  }

  // --- UI Reset Functions ---
  /**
   * 重置视频处理面板的 UI 状态。
   * @param {boolean} resetFileInput 是否清空文件输入框
   */
  function resetVideoUI(resetFileInput = true) {
    console.log("Resetting video UI, reset file input:", resetFileInput);
    videoSessionId = null;
    if (activeWebSocket && activeTaskType === "video") {
      console.log("Closing active WebSocket for video task.");
      activeWebSocket.close(1000, "Resetting UI");
      activeWebSocket = null;
    }
    if (resetFileInput && videoFileInput) videoFileInput.value = "";
    if (uploadVideoButton)
      uploadVideoButton.disabled =
        !videoFileInput ||
        !videoFileInput.files ||
        videoFileInput.files.length === 0;

    if (loadRefFrameButton) loadRefFrameButton.disabled = true;
    if (clearOcrRegionButton) clearOcrRegionButton.disabled = true;
    if (processVideoButton) processVideoButton.disabled = true;
    if (videoDownloadPdfButton) {
      videoDownloadPdfButton.classList.add("disabled");
      videoDownloadPdfButton.href = "#";
    }
    if (videoCleanupButton) videoCleanupButton.disabled = true;
    if (videoLogOutput) videoLogOutput.innerHTML = "";
    if (videoPreviewArea) videoPreviewArea.innerHTML = "";
    if (ocrCropContainer) ocrCropContainer.style.display = "none";
    if (cropper) {
      cropper.destroy();
      cropper = null;
    }
    if (refImageElement) refImageElement.src = "#";
    if (ocrCoordsP) ocrCoordsP.textContent = "";
    ocrSelection = null;
    if (videoProgressBarContainer)
      videoProgressBarContainer.style.display = "none";
    updateProgress(0, "", "video"); // Pass taskType explicitly

    if (resetFileInput) addLog("请选择一个新的视频文件开始。", "info", "video");
  }

  /**
   * 重置长截图处理面板的 UI 状态。
   * @param {boolean} resetFileInput 是否清空文件输入框
   */
  function resetLongImageUI(resetFileInput = true) {
    console.log("Resetting long image UI, reset file input:", resetFileInput);
    longImageSessionId = null;
    if (activeWebSocket && activeTaskType === "longImage") {
      console.log("Closing active WebSocket for long image task.");
      activeWebSocket.close(1000, "Resetting UI");
      activeWebSocket = null;
    }
    if (resetFileInput && longImageFileInput) longImageFileInput.value = "";
    if (processLongImageButton)
      processLongImageButton.disabled =
        !longImageFileInput ||
        !longImageFileInput.files ||
        longImageFileInput.files.length === 0;

    if (longImageDownloadPdfButton) {
      longImageDownloadPdfButton.classList.add("disabled");
      longImageDownloadPdfButton.href = "#";
    }
    if (longImageCleanupButton) longImageCleanupButton.disabled = true;
    if (longImageLogOutput) longImageLogOutput.innerHTML = "";
    if (longImagePreviewArea) longImagePreviewArea.innerHTML = "";
    if (longImageProgressBarContainer)
      longImageProgressBarContainer.style.display = "none";
    updateProgress(0, "", "longImage"); // Pass taskType explicitly

    if (resetFileInput)
      addLog("请选择一个长截图文件开始。", "info", "longImage");
  }

  // --- Tab Switching Logic ---
  document
    .querySelectorAll('#toolTab button[data-bs-toggle="tab"]')
    .forEach((tabEl) => {
      tabEl.addEventListener("shown.bs.tab", (event) => {
        const previousTaskType = activeTaskType;
        activeTaskType =
          event.target.id === "video-tab" ? "video" : "longImage";
        console.log(
          `Switched tab from ${previousTaskType} to ${activeTaskType}`
        );
        // Optionally reset the other panel's UI or handle active connections
        // if (previousTaskType === 'video' && activeTaskType === 'longImage') {
        //     // Maybe reset video UI slightly? Or just leave it.
        // } else if (previousTaskType === 'longImage' && activeTaskType === 'video') {
        //     // Maybe reset long image UI?
        // }
      });
    });

  // --- Sortable Setup ---
  /**
   * 为指定的目标元素设置 SortableJS。
   * @param {HTMLElement} targetElement 要应用排序的容器元素
   */
  function setupSortable(targetElement) {
    if (!targetElement) return;
    let sortableVar =
      targetElement === videoPreviewArea
        ? "videoSortable"
        : "longImageSortable";
    if (window[sortableVar]) {
      // Access global var by name
      window[sortableVar].destroy();
      console.log(`Destroyed existing Sortable for ${sortableVar}`);
    }

    window[sortableVar] = new Sortable(targetElement, {
      animation: 150,
      ghostClass: "sortable-ghost", // Use a custom class for theme compatibility
      chosenClass: "sortable-chosen",
      dragClass: "sortable-drag",
    });
    console.log(`Initialized Sortable for ${sortableVar}`);
  }

  // --- Event Listeners ---

  // Video File Input Change
  if (videoFileInput && uploadVideoButton) {
    // Check if both exist
    videoFileInput.addEventListener("change", () => {
      uploadVideoButton.disabled = !videoFileInput.files.length;
      if (videoFileInput.files.length > 0) {
        addLog(`已选择文件: ${videoFileInput.files[0].name}`, "info", "video");
        // Reset UI *before* starting new upload process if needed
        // resetVideoUI(false); // Or handle this in the upload click
      } else {
        addLog("文件选择已清除。", "info", "video");
      }
    });
  } else {
    console.error("Video file input or upload button not found.");
  }

  // Upload Video Button Click
  if (uploadVideoButton) {
    uploadVideoButton.addEventListener("click", async () => {
      const fileToUpload = videoFileInput?.files[0];
      if (!fileToUpload) {
        addLog("错误：未选择视频文件。", "error", "video");
        return;
      }

      uploadVideoButton.disabled = true;
      addLog("开始上传视频...", "info", "video");
      resetVideoUI(false); // Reset video UI, keeping file input value

      const formData = new FormData();
      formData.append("video_file", fileToUpload);

      try {
        const response = await fetch("/upload_video/", {
          method: "POST",
          body: formData,
        });
        const data = await response.json();
        if (response.ok && data.session_id) {
          // Check for session_id in response
          videoSessionId = data.session_id;
          activeTaskType = "video"; // Set focus
          addLog(`视频上传成功。会话ID: ${videoSessionId}`, "success", "video");
          addLog(`文件名: ${data.filename}`, "info", "video");
          connectWebSocket(videoSessionId); // Connect WebSocket
          if (loadRefFrameButton) loadRefFrameButton.disabled = false;
          if (processVideoButton) processVideoButton.disabled = false;
          if (videoCleanupButton) videoCleanupButton.disabled = false;
        } else {
          addLog(
            `上传失败: ${data.message || response.statusText}`,
            "error",
            "video"
          );
          uploadVideoButton.disabled = false;
        }
      } catch (error) {
        addLog(`上传出错: ${error}`, "error", "video");
        uploadVideoButton.disabled = false;
      }
    });
  }

  // Load Reference Frame Button Click
  if (loadRefFrameButton) {
    loadRefFrameButton.addEventListener("click", async () => {
      if (!videoSessionId) {
        addLog("无视频会话ID。", "error", "video");
        return;
      }
      addLog("正在加载参考帧...", "info", "video");
      loadRefFrameButton.disabled = true;
      if (clearOcrRegionButton) clearOcrRegionButton.disabled = true;

      try {
        const response = await fetch(`/get_reference_frame/${videoSessionId}`);
        if (response.ok) {
          const imageBlob = await response.blob();
          const imageUrl = URL.createObjectURL(imageBlob);
          if (refImageElement) refImageElement.src = imageUrl;
          if (ocrCropContainer) ocrCropContainer.style.display = "block";

          if (cropper) cropper.destroy();
          if (refImageElement) {
            cropper = new Cropper(refImageElement, {
              aspectRatio: NaN,
              viewMode: 1,
              autoCropArea: 0.8,
              ready() {
                // Ensure cropper is ready before enabling clear button
                if (clearOcrRegionButton) clearOcrRegionButton.disabled = false;
                addLog("参考帧已加载。请框选区域。", "success", "video");
              },
              crop(event) {
                ocrSelection = {
                  /* ... get coords ... */
                };
                if (ocrCoordsP) ocrCoordsP.textContent = `选区: ...`;
              },
            });
          } else {
            addLog("错误: 参考图像元素不存在。", "error", "video");
            if (clearOcrRegionButton) clearOcrRegionButton.disabled = true; // Keep disabled
          }
        } else {
          let errorMsg = "加载参考帧失败";
          try {
            const errorData = await response.json();
            errorMsg += `: ${errorData.detail || response.statusText}`;
          } catch {
            errorMsg += `: ${response.statusText}`;
          }
          addLog(errorMsg, "error", "video");
          if (clearOcrRegionButton) clearOcrRegionButton.disabled = true;
        }
      } catch (error) {
        addLog(`加载参考帧出错: ${error}`, "error", "video");
        if (clearOcrRegionButton) clearOcrRegionButton.disabled = true;
      } finally {
        if (loadRefFrameButton) loadRefFrameButton.disabled = false;
        // Clear button only enabled if cropper is successfully initialized (in ready event)
      }
    });
  }

  // Clear OCR Region Button Click
  if (clearOcrRegionButton) {
    clearOcrRegionButton.addEventListener("click", () => {
      if (cropper) cropper.clear();
      ocrSelection = null;
      if (ocrCoordsP) ocrCoordsP.textContent = "选区已清除。";
      addLog("OCR选区已清除。", "info", "video");
    });
  }

  // Process Video Button Click
  if (processVideoButton) {
    processVideoButton.addEventListener("click", async () => {
      if (!videoSessionId) {
        addLog("无视频会话ID。", "error", "video");
        return;
      }
      activeTaskType = "video";

      addLog("开始处理视频...", "info", "video");
      processVideoButton.disabled = true;
      if (videoDownloadPdfButton)
        videoDownloadPdfButton.classList.add("disabled");
      if (videoPreviewArea) videoPreviewArea.innerHTML = "";
      updateProgress(0, "准备处理...", "video");

      const settings = {
        frame_interval_seconds: parseFloat(frameIntervalInput?.value || 1),
        exclusion_list:
          exclusionListInput?.value
            .split("\n")
            .map((s) => s.trim())
            .filter((s) => s) || [],
        ocr_analysis_rect: ocrSelection
          ? [
              ocrSelection.x,
              ocrSelection.y,
              ocrSelection.width,
              ocrSelection.height,
            ]
          : null,
        pdf_rows: parseInt(pdfRowsVideoInput?.value || 3),
        pdf_cols: parseInt(pdfColsVideoInput?.value || 2),
        pdf_title: pdfTitleVideoInput?.value || "聊天记录证据",
        pdf_layout: pdfLayoutVideoSelect?.value || "grid",
        image_order: getVideoPreviewImageOrder(),
      };
      console.log("Processing video with settings:", settings); // Log settings

      try {
        const response = await fetch(`/process_video/${videoSessionId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(settings),
        });
        const data = await response.json();
        if (response.ok) {
          addLog(data.message || "处理已启动...", "success", "video");
        } else {
          addLog(
            `启动处理失败: ${
              data.detail || data.message || response.statusText
            }`,
            "error",
            "video"
          );
          if (processVideoButton) processVideoButton.disabled = false;
        }
      } catch (error) {
        addLog(`启动处理出错: ${error}`, "error", "video");
        if (processVideoButton) processVideoButton.disabled = false;
      }
    });
  }

  // Video Cleanup Button Click
  if (videoCleanupButton) {
    videoCleanupButton.addEventListener("click", async () => {
      if (!videoSessionId) {
        addLog("无视频会话可清理。", "warning", "video");
        return;
      }
      if (!confirm(`确定清理视频会话 ${videoSessionId} 吗？`)) return;
      addLog(`清理视频会话 ${videoSessionId}...`, "info", "video");
      videoCleanupButton.disabled = true;
      try {
        const response = await fetch(`/cleanup_session/${videoSessionId}`, {
          method: "POST",
        });
        const data = await response.json();
        if (response.ok) {
          addLog(data.message, "success", "video");
          resetVideoUI(); // Reset UI on success
        } else {
          addLog(`清理失败: ${data.detail || data.message}`, "error", "video");
          videoCleanupButton.disabled = false;
        }
      } catch (error) {
        addLog(`清理出错: ${error}`, "error", "video");
        videoCleanupButton.disabled = false;
      }
    });
  }

  // Get Video Preview Order
  function getVideoPreviewImageOrder() {
    if (!videoPreviewArea) return null;
    const items = videoPreviewArea.querySelectorAll(".preview-item img");
    return Array.from(items)
      .map((item) => {
        try {
          const urlParts = new URL(item.src).pathname.split("/");
          // Extract filename, removing potential query string part if any was added
          const filenameWithQuery = urlParts[urlParts.length - 1];
          const filename = filenameWithQuery.split("?")[0]; // Remove query string if present
          return decodeURIComponent(filename);
        } catch (e) {
          console.error("Error parsing image URL for order:", item.src, e);
          return null;
        }
      })
      .filter((name) => name);
  }

  // --- Long Image Event Listeners ---

  // Long Image File Input Change
  if (longImageFileInput && processLongImageButton) {
    longImageFileInput.addEventListener("change", () => {
      processLongImageButton.disabled = !longImageFileInput.files.length;
      if (longImageFileInput.files.length > 0)
        addLog(
          `已选择长截图: ${longImageFileInput.files[0].name}`,
          "info",
          "longImage"
        );
      else addLog("长截图选择已清除。", "info", "longImage");
    });
  } else {
    console.error("Long image file input or process button not found.");
  }

  // Process Long Image Button Click
  if (processLongImageButton) {
    processLongImageButton.addEventListener("click", async () => {
      const fileToUpload = longImageFileInput?.files[0];
      if (!fileToUpload) {
        addLog("请选择长截图文件。", "error", "longImage");
        return;
      }

      activeTaskType = "longImage";
      processLongImageButton.disabled = true;
      addLog("开始处理长截图...", "info", "longImage");
      resetLongImageUI(false);

      const formData = new FormData();
      formData.append("long_image_file", fileToUpload);
      formData.append("slice_height", sliceHeightInput?.value || "1000");
      formData.append("overlap", overlapHeightInput?.value || "100");
      formData.append("pdf_rows", pdfRowsLongInput?.value || "3");
      formData.append("pdf_cols", pdfColsLongInput?.value || "1");
      formData.append("pdf_title", pdfTitleLongInput?.value || "长截图证据");
      formData.append("pdf_layout", pdfLayoutLongSelect?.value || "column");
      // Get image order *before* sending request if needed for backend processing immediately
      // const imageOrder = getLongImagePreviewImageOrder();
      // if (imageOrder && imageOrder.length > 0) {
      //      formData.append('image_order', JSON.stringify(imageOrder));
      // }

      try {
        const response = await fetch("/slice_long_image/", {
          method: "POST",
          body: formData,
        });
        const data = await response.json();
        if (response.ok && data.session_id) {
          longImageSessionId = data.session_id;
          activeTaskType = "longImage"; // Ensure active type
          addLog(
            `长截图处理启动。会话ID: ${longImageSessionId}`,
            "success",
            "longImage"
          );
          connectWebSocket(longImageSessionId);
          if (longImageCleanupButton) longImageCleanupButton.disabled = false;
        } else {
          addLog(
            `启动处理失败: ${data.message || response.statusText}`,
            "error",
            "longImage"
          );
          if (processLongImageButton) processLongImageButton.disabled = false;
        }
      } catch (error) {
        addLog(`启动处理出错: ${error}`, "error", "longImage");
        if (processLongImageButton) processLongImageButton.disabled = false;
      }
    });
  }

  // Long Image Cleanup Button Click
  if (longImageCleanupButton) {
    longImageCleanupButton.addEventListener("click", async () => {
      if (!longImageSessionId) {
        addLog("无长截图会话可清理。", "warning", "longImage");
        return;
      }
      if (!confirm(`确定清理长截图会话 ${longImageSessionId} 吗？`)) return;
      addLog(`清理长截图会话 ${longImageSessionId}...`, "info", "longImage");
      longImageCleanupButton.disabled = true;
      try {
        const response = await fetch(`/cleanup_session/${longImageSessionId}`, {
          method: "POST",
        });
        const data = await response.json();
        if (response.ok) {
          addLog(data.message, "success", "longImage");
          resetLongImageUI();
        } else {
          addLog(
            `清理失败: ${data.detail || data.message}`,
            "error",
            "longImage"
          );
          longImageCleanupButton.disabled = false;
        }
      } catch (error) {
        addLog(`清理出错: ${error}`, "error", "longImage");
        longImageCleanupButton.disabled = false;
      }
    });
  }

  // Get Long Image Preview Order
  function getLongImagePreviewImageOrder() {
    if (!longImagePreviewArea) return null;
    const items = longImagePreviewArea.querySelectorAll(".preview-item img");
    return Array.from(items)
      .map((item) => {
        try {
          const urlParts = new URL(item.src).pathname.split("/");
          const filenameWithQuery = urlParts[urlParts.length - 1];
          const filename = filenameWithQuery.split("?")[0]; // Remove query string
          return decodeURIComponent(filename);
        } catch (e) {
          console.error("Error parsing image URL for order:", item.src, e);
          return null;
        }
      })
      .filter((name) => name);
  }

  // --- WebSocket Handling ---
  function connectWebSocket(sessionId) {
    if (!sessionId) {
      const taskType = activeTaskType; // Log to the current active tab
      addLog("无效的会话ID，无法连接WebSocket。", "error", taskType);
      return;
    }
    if (activeWebSocket) {
      // Don't close if connecting for the *same* active session (e.g., page refresh)
      if (
        sessionId !==
        (activeTaskType === "video" ? videoSessionId : longImageSessionId)
      ) {
        console.log(
          "Closing previous WebSocket connection for different session."
        );
        activeWebSocket.close(1000, "Starting new task connection");
      } else {
        console.log(
          "WebSocket already connected or connecting for this session."
        );
        // Optionally send a ping or check readyState if needed
        return; // Already connected for this session
      }
    }

    const taskType = sessionId === videoSessionId ? "video" : "longImage"; // Determine task type based on session ID
    activeTaskType = taskType; // Set active task type based on connection attempt

    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${sessionId}`;
    addLog(`正在连接 WebSocket (${taskType}): ${wsUrl}`, "info", taskType);

    activeWebSocket = new WebSocket(wsUrl);

    activeWebSocket.onopen = () => {
      addLog("WebSocket 连接成功。", "success", taskType);
    };

    activeWebSocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Determine target UI based on session ID in the message, fallback to current active task type
        let messageSessionId = data.session_id; // Assume backend includes session_id
        let messageTaskType = "unknown";
        if (messageSessionId === videoSessionId) messageTaskType = "video";
        else if (messageSessionId === longImageSessionId)
          messageTaskType = "longImage";
        else {
          console.warn(
            "Received WS message with mismatched session ID:",
            data.session_id,
            "Current video:",
            videoSessionId,
            "Current long:",
            longImageSessionId
          );
          messageTaskType = activeTaskType; // Fallback to currently active tab's type
          messageSessionId = activeSessionId; // Assume message is for the active session if ID doesn't match known ones
          if (!messageSessionId) {
            console.error("Cannot determine target UI for WS message:", data);
            return; // Cannot process if session ID is unknown and no active session
          }
        }

        // Get target UI elements
        const targetLog =
          messageTaskType === "video" ? videoLogOutput : longImageLogOutput;
        const targetProgressContainer =
          messageTaskType === "video"
            ? videoProgressBarContainer
            : longImageProgressBarContainer;
        const targetProgressBar =
          messageTaskType === "video" ? videoProgressBar : longImageProgressBar;
        const targetProgressStatus =
          messageTaskType === "video"
            ? videoProgressStatus
            : longImageProgressStatus;
        const targetPreviewArea =
          messageTaskType === "video" ? videoPreviewArea : longImagePreviewArea;
        const targetDownloadButton =
          messageTaskType === "video"
            ? videoDownloadPdfButton
            : longImageDownloadPdfButton;
        const targetProcessButton =
          messageTaskType === "video"
            ? processVideoButton
            : processLongImageButton;
        const targetCleanupButton =
          messageTaskType === "video"
            ? videoCleanupButton
            : longImageCleanupButton;

        if (!targetLog) return; // Essential check

        addLog(`[WS] ${data.status}: ${data.message}`, "info", messageTaskType);

        // Update Progress
        if (data.progress !== null && data.progress !== undefined) {
          updateProgress(
            data.progress,
            `${data.status}: ${data.message}`,
            messageTaskType
          );
        } else if (
          [
            "extracting_frames",
            "ocr_processing",
            "pdf_generating",
            "slicing",
          ].some((s) => data.status.includes(s))
        ) {
          const currentProgress =
            targetProgressBar?.getAttribute("aria-valuenow") || 0;
          updateProgress(
            currentProgress,
            `${data.status}: ${data.message}`,
            messageTaskType
          );
        }

        // Update Preview Area
        if (
          (data.status === "ocr_completed" ||
            data.status === "preview_ready" ||
            data.status === "slicing_complete") &&
          data.preview_images
        ) {
          targetPreviewArea.innerHTML = ""; // Clear previous items
          data.preview_images.forEach((imgUrl) => {
            const colDiv = document.createElement("div");
            colDiv.className = "col-6 col-sm-4 col-md-3 preview-item"; // Responsive grid
            const img = document.createElement("img");
            // Add type=sliced query param for long image previews
            const finalImgUrl =
              messageTaskType === "longImage"
                ? `${imgUrl}?type=sliced`
                : imgUrl;
            img.src = finalImgUrl;
            img.className = "img-fluid rounded preview-image";
            img.alt = "Preview";
            img.style.cursor = "pointer";
            img.title = "Double-click to open in new tab"; // Tooltip
            img.addEventListener("dblclick", () =>
              window.open(finalImgUrl, "_blank")
            );
            colDiv.appendChild(img);
            targetPreviewArea.appendChild(colDiv);
          });
          if (data.preview_images.length > 0) {
            setupSortable(targetPreviewArea); // Initialize sortable for the specific preview area
          }
        }

        // Handle Completion / Error Status
        const isCompleted = data.status === "completed";
        const isCompletedNoPdf = data.status === "completed_no_pdf";
        const isError = data.status === "error";

        if (isCompleted && data.result_url) {
          targetDownloadButton.href = data.result_url;
          targetDownloadButton.classList.remove("disabled");
          addLog(
            `PDF准备就绪: <a href="${data.result_url}" target="_blank" download class="fw-bold text-decoration-underline">点击下载</a>`,
            "success",
            messageTaskType
          );
          updateProgress(100, "全部完成！", messageTaskType);
        } else if (isCompletedNoPdf) {
          addLog("处理完成，无PDF。", "info", messageTaskType);
          updateProgress(100, "处理完成，无PDF。", messageTaskType);
        } else if (isError) {
          addLog(`处理错误: ${data.message}`, "error", messageTaskType);
          const currentProgress =
            targetProgressBar?.getAttribute("aria-valuenow") || 0;
          updateProgress(
            currentProgress,
            `错误: ${data.message}`,
            messageTaskType
          );
        }

        // Re-enable process button on completion or error
        if (isCompleted || isCompletedNoPdf || isError) {
          if (targetProcessButton) targetProcessButton.disabled = false;
          // Keep cleanup button enabled as session might still exist for inspection/redownload
          if (targetCleanupButton) targetCleanupButton.disabled = false;
        }
      } catch (e) {
        console.error(
          "Failed to parse WebSocket message or update UI:",
          e,
          event.data
        );
        addLog("接收到无效的 WebSocket 消息。", "error", activeTaskType); // Log to active tab
      }
    };

    activeWebSocket.onclose = (event) => {
      // Determine type based on which session ID the closing socket was associated with
      let taskTypeForLog = "unknown";
      if (activeSessionId === videoSessionId) taskTypeForLog = "video";
      else if (activeSessionId === longImageSessionId)
        taskTypeForLog = "longImage";

      addLog(
        `WebSocket 连接已关闭 (${taskTypeForLog} - ${activeSessionId})。代码: ${event.code}`,
        "warning",
        taskTypeForLog
      );
      // Re-enable the corresponding process button if the socket closed unexpectedly
      if (event.code !== 1000) {
        // 1000 is normal closure
        if (taskTypeForLog === "video" && processVideoButton)
          processVideoButton.disabled = false;
        if (taskTypeForLog === "longImage" && processLongImageButton)
          processLongImageButton.disabled = false;
      }
      // Only nullify if it's the currently active socket that closed
      if (activeWebSocket === event.target) {
        activeWebSocket = null;
      }
    };

    activeWebSocket.onerror = (error) => {
      const taskTypeForLog =
        activeSessionId === videoSessionId ? "video" : "longImage";
      addLog(
        `WebSocket 错误 (${taskTypeForLog} - ${activeSessionId}): ${
          error.message || "未知错误"
        }`,
        "error",
        taskTypeForLog
      );
      if (taskTypeForLog === "video" && processVideoButton)
        processVideoButton.disabled = false;
      if (taskTypeForLog === "longImage" && processLongImageButton)
        processLongImageButton.disabled = false;
    };
  };

  // --- Theme Toggle Logic ---
  // (Assuming the previously provided theme toggle code is placed here)
  // --- Start Theme Toggle Code ---
  document.addEventListener("DOMContentLoaded", function () {
    console.log(
      "DOM fully loaded and parsed, attempting to add theme toggle button."
    ); // 添加调试日志

    // 检查按钮是否已存在
    if (document.querySelector(".theme-toggle")) {
      console.log("Theme toggle button already exists.");
      return;
    }

    try {
      // 包裹在 try...catch 中以便捕获潜在错误
      // 创建主题切换按钮
      const themeToggle = document.createElement("button");
      themeToggle.className = "theme-toggle btn"; // 添加 btn 类以便基础样式生效
      themeToggle.setAttribute("aria-label", "Toggle theme");
      // 直接在 JS 中设置基本样式，确保它可见且可交互
      themeToggle.style.position = "fixed";
      themeToggle.style.bottom = "20px";
      themeToggle.style.right = "20px";
      themeToggle.style.width = "48px"; // 明确尺寸
      themeToggle.style.height = "48px";
      themeToggle.style.borderRadius = "50%"; // 圆形
      themeToggle.style.zIndex = "1000";
      themeToggle.style.border = "1px solid var(--border-color)"; // 使用 CSS 变量
      themeToggle.style.backgroundColor = "var(--secondary-bg-color)"; // 使用 CSS 变量
      themeToggle.style.color = "var(--main-text-color)"; // 使用 CSS 变量
      themeToggle.style.display = "flex"; // 用于内部图标居中
      themeToggle.style.alignItems = "center";
      themeToggle.style.justifyContent = "center";
      themeToggle.style.cursor = "pointer";
      themeToggle.style.transition = "background-color 0.2s, transform 0.2s"; // 添加过渡

      console.log("Theme toggle button element created:", themeToggle);

      document.body.appendChild(themeToggle); // 添加到 body 末尾
      console.log("Theme toggle button appended to body.");

      // 获取当前主题或默认值
      let currentTheme = localStorage.getItem("theme") || "light";

      // 应用初始主题（会设置图标）
      applyTheme(currentTheme);
      console.log("Initial theme applied:", currentTheme);

      // 添加点击事件监听器
      themeToggle.addEventListener("click", function () {
        console.log("Theme toggle button clicked.");
        currentTheme = currentTheme === "light" ? "dark" : "light";
        applyTheme(currentTheme);
        localStorage.setItem("theme", currentTheme); // 保存用户选择
        console.log("Theme changed to:", currentTheme);
      });
    } catch (error) {
      console.error("Error creating or attaching theme toggle button:", error); // 捕获并打印错误
    }
  });

  function applyTheme(theme) {
    if (theme === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    updateThemeIcon(theme);
  }

  function updateThemeIcon(theme) {
    const themeToggle = document.querySelector(".theme-toggle");
    if (!themeToggle) return;
    if (theme === "dark") {
      themeToggle.innerHTML =
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16" class="bi bi-moon-stars-fill"><path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278z"/><path d="M10.794 3.148a.217.217 0 0 1 .412 0l.387 1.162c.173.518.579.924 1.097 1.097l1.162.387a.217.217 0 0 1 0 .412l-1.162.387a1.734 1.734 0 0 0-1.097 1.097l-.387 1.162a.217.217 0 0 1-.412 0l-.387-1.162A1.734 1.734 0 0 0 9.31 6.593l-1.162-.387a.217.217 0 0 1 0-.412l1.162-.387a1.734 1.734 0 0 0 1.097-1.097l.387-1.162zM13.863.099a.145.145 0 0 1 .274 0l.258.774c.115.346.386.617.732.732l.774.258a.145.145 0 0 1 0 .274l-.774.258a1.156 1.156 0 0 0-.732.732l-.258.774a.145.145 0 0 1-.274 0l-.258-.774a1.156 1.156 0 0 0-.732-.732l-.774-.258a.145.145 0 0 1 0-.274l.774-.258c.346-.115.617-.386.732-.732L13.863.1z"/></svg>';
    } else {
      themeToggle.innerHTML =
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16" class="bi bi-sun-fill"><path d="M8 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM8 0a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 0zm0 13a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 13zm8-5a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2a.5.5 0 0 1 .5.5zM3 8a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2A.5.5 0 0 1 3 8zm10.657-5.657a.5.5 0 0 1 0 .707l-1.414 1.415a.5.5 0 1 1-.707-.708l1.414-1.414a.5.5 0 0 1 .707 0zm-9.193 9.193a.5.5 0 0 1 0 .707L3.05 13.657a.5.5 0 0 1-.707-.707l1.414-1.414a.5.5 0 0 1 .707 0zm9.193 2.121a.5.5 0 0 1-.707 0l-1.414-1.414a.5.5 0 0 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .707zM4.464 4.465a.5.5 0 0 1-.707 0L2.343 3.05a.5.5 0 1 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .708z"/></svg>';
    }
  }
  // --- End Theme Toggle Code ---
}); // End Main DOMContentLoaded listener
