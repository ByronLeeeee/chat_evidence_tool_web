// frontend/script.js
document.addEventListener("DOMContentLoaded", () => {
  // --- 获取所有元素引用 (确保 ID 与 index.html 对应) ---
  const videoFileInput = document.getElementById("videoFile");
  const uploadVideoButton = document.getElementById("uploadVideoButton"); // 确认HTML中的ID
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
  const lightbox = document.getElementById("imageLightbox");
  const lightboxImg = document.getElementById("lightboxImg");
  const lightboxCaption = document.getElementById("lightboxCaption");
  const lightboxClose = document.querySelector(".lightbox-close");

  let activeWebSocket = null;
  let videoSessionId = null;
  let longImageSessionId = null;
  let activeTaskType = "video";
  let cropper = null;
  let ocrSelection = null;
  let videoSortable = null;
  let longImageSortable = null;
  let activeSessionId = null; // Store the session ID of the currently active WS connection

  function addLog(message, type = "info", taskType = activeTaskType) {
    const targetLog =
      taskType === "video" ? videoLogOutput : longImageLogOutput;
    if (!targetLog) {
      console.error("Target log output not found for:", taskType, message);
      return;
    }
    const time = new Date().toLocaleTimeString();
    const logEntry = document.createElement("div");
    logEntry.textContent = `[${time}] ${message}`;
    logEntry.className = `log-entry log-${type}`;
    targetLog.appendChild(logEntry);
    targetLog.scrollTop = targetLog.scrollHeight;
  }

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
      console.error(
        "Target progress elements not found for:",
        taskType,
        statusText
      );
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

  function resetVideoUI(resetFileInput = true) {
    console.log("Resetting video UI, reset file input:", resetFileInput);
    videoSessionId = null;
    if (activeWebSocket && activeSessionId === videoSessionId) {
      // Only close if it's for this task type's old session
      activeWebSocket.close(1000, "Resetting video UI");
      activeWebSocket = null;
      activeSessionId = null;
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
    if (ocrCoordsP) ocrCoordsP.textContent = "选区: ..."; // Reset to placeholder
    ocrSelection = null;
    if (videoProgressBarContainer)
      videoProgressBarContainer.style.display = "none";
    updateProgress(0, "", "video");

    if (resetFileInput) addLog("请选择一个新的视频文件开始。", "info", "video");
  }

  function resetLongImageUI(resetFileInput = true) {
    console.log("Resetting long image UI, reset file input:", resetFileInput);
    longImageSessionId = null;
    if (activeWebSocket && activeSessionId === longImageSessionId) {
      activeWebSocket.close(1000, "Resetting long image UI");
      activeWebSocket = null;
      activeSessionId = null;
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
    updateProgress(0, "", "longImage");

    if (resetFileInput)
      addLog("请选择一个长截图文件开始。", "info", "longImage");
  }

  const toolTab = document.getElementById("toolTab");
  if (toolTab) {
    const tabButtons = toolTab.querySelectorAll('button[data-bs-toggle="tab"]');
    tabButtons.forEach((tabEl) => {
      tabEl.addEventListener("shown.bs.tab", (event) => {
        activeTaskType =
          event.target.id === "video-tab" ? "video" : "longImage";
        console.log(`Switched tab to ${activeTaskType}`);
      });
    });
  } else {
    console.warn(
      "#toolTab element not found. Tab switching logic might not work."
    );
  }

  function setupSortable(targetElement) {
    if (!targetElement) {
      console.error("Cannot setup Sortable: targetElement is null");
      return;
    }
    let sortableVarName =
      targetElement === videoPreviewArea
        ? "videoSortable"
        : "longImageSortable";
    if (
      window[sortableVarName] &&
      typeof window[sortableVarName].destroy === "function"
    ) {
      window[sortableVarName].destroy();
    }
    try {
      window[sortableVarName] = new Sortable(targetElement, {
        animation: 150,
        ghostClass: "sortable-ghost",
        chosenClass: "sortable-chosen",
        dragClass: "sortable-drag",
      });
      console.log(`Initialized Sortable for ${sortableVarName}`);
    } catch (e) {
      console.error(`Error initializing Sortable for ${sortableVarName}:`, e);
    }
  }

  function openLightbox(imageSrc, captionText = "") {
    if (!lightbox || !lightboxImg) return;
    document.body.classList.add("lightbox-open"); // Prevent background scroll
    lightboxImg.src = imageSrc;
    if (lightboxCaption) {
      lightboxCaption.textContent =
        captionText || decodeURIComponent(imageSrc.split("/").pop()); // Default caption to filename
    }
    lightbox.style.opacity = "0"; // Start transparent for fade-in
    lightbox.style.display = "block";
    setTimeout(() => {
      // Allow display block to take effect before starting opacity transition
      lightbox.style.opacity = "1";
    }, 10); // Small delay
  }

  function closeLightbox() {
    if (!lightbox) return;
    document.body.classList.remove("lightbox-open");
    lightbox.style.opacity = "0";
    setTimeout(() => {
      // Wait for fade-out before hiding
      lightbox.style.display = "none";
      if (lightboxImg) lightboxImg.src = ""; // Clear image to free memory
    }, 300); // Match CSS transition duration
  }

  if (lightboxClose) {
    lightboxClose.addEventListener("click", closeLightbox);
  }
  // Close lightbox if user clicks outside the image (on the overlay)
  if (lightbox) {
    lightbox.addEventListener("click", function (event) {
      if (event.target === lightbox) {
        // Clicked on the overlay itself
        closeLightbox();
      }
    });
  }
  // Close lightbox with Escape key
  document.addEventListener("keydown", function (event) {
    if (
      event.key === "Escape" &&
      lightbox &&
      lightbox.style.display === "block"
    ) {
      closeLightbox();
    }
  });

  if (videoFileInput && uploadVideoButton) {
    videoFileInput.addEventListener("change", () => {
      uploadVideoButton.disabled =
        !videoFileInput.files || videoFileInput.files.length === 0;
      if (videoFileInput.files && videoFileInput.files.length > 0) {
        addLog(`已选择文件: ${videoFileInput.files[0].name}`, "info", "video");
      } else {
        addLog("文件选择已清除。", "info", "video");
      }
    });
  }

  if (uploadVideoButton) {
    uploadVideoButton.addEventListener("click", async () => {
      const fileToUpload = videoFileInput?.files[0];
      if (!fileToUpload) {
        addLog("错误：未选择视频文件。", "error", "video");
        return;
      }
      activeTaskType = "video";
      resetVideoUI(false);
      uploadVideoButton.disabled = true;
      addLog("开始上传视频...", "info", "video");

      const formData = new FormData();
      formData.append("video_file", fileToUpload);

      try {
        const response = await fetch("/upload_video/", {
          method: "POST",
          body: formData,
        });
        const data = await response.json();
        if (response.ok && data.session_id) {
          videoSessionId = data.session_id;
          addLog(`视频上传成功。会话ID: ${videoSessionId}`, "success", "video");
          addLog(`文件名: ${data.filename}`, "info", "video");
          connectWebSocket(videoSessionId, "video");
          if (loadRefFrameButton) loadRefFrameButton.disabled = false;
          if (processVideoButton) processVideoButton.disabled = false;
          if (videoCleanupButton) videoCleanupButton.disabled = false;
        } else {
          addLog(
            `上传失败: ${data.message || response.statusText}`,
            "error",
            "video"
          );
          if (uploadVideoButton) uploadVideoButton.disabled = false;
        }
      } catch (error) {
        addLog(`上传出错: ${error}`, "error", "video");
        if (uploadVideoButton) uploadVideoButton.disabled = false;
      }
    });
  }

  if (
    loadRefFrameButton &&
    refImageElement &&
    ocrCropContainer &&
    ocrCoordsP &&
    clearOcrRegionButton
  ) {
    loadRefFrameButton.addEventListener("click", async () => {
      if (!videoSessionId) {
        addLog("无视频会话ID。", "error", "video");
        return;
      }
      addLog("正在加载参考帧...", "info", "video");
      loadRefFrameButton.disabled = true;
      clearOcrRegionButton.disabled = true;

      try {
        const response = await fetch(`/get_reference_frame/${videoSessionId}`);
        if (response.ok) {
          const imageBlob = await response.blob();
          const imageUrl = URL.createObjectURL(imageBlob);
          refImageElement.src = imageUrl;
          ocrCropContainer.style.display = "block";

          if (cropper) cropper.destroy();
          cropper = new Cropper(refImageElement, {
            aspectRatio: NaN,
            viewMode: 1, // 限制裁剪框不能超出画布
            autoCropArea: 0.8, // 默认选区占图片80%
            movable: true,
            zoomable: false,
            rotatable: false,
            scalable: false,
            // cropmove: function () { // 当裁剪框移动时触发 (可选调试)
            //   // console.log('cropmove');
            // },
            ready() {
              // 当 Cropper 初始化并准备好时触发
              console.log("Cropper is ready.");
              if (clearOcrRegionButton) clearOcrRegionButton.disabled = false;
              addLog("参考帧已加载。请框选OCR区域。", "success", "video");

              // 获取初始选区数据并更新UI
              const initialCropData = cropper.getData(true); // true for rounded values
              if (initialCropData) {
                ocrSelection = {
                  x: initialCropData.x,
                  y: initialCropData.y,
                  width: initialCropData.width,
                  height: initialCropData.height,
                };
                if (ocrCoordsP) {
                  ocrCoordsP.textContent = `选区: X=${ocrSelection.x}, Y=${ocrSelection.y}, W=${ocrSelection.width}, H=${ocrSelection.height}`;
                }
                console.log("Initial ocrSelection from ready:", ocrSelection);
              } else {
                console.warn(
                  "cropper.getData() returned no data on ready, ocrSelection remains:",
                  ocrSelection
                );
              }
            },
            cropend() {
              // 当用户停止拖动裁剪框时触发 (这是我们主要更新选区的地方)
              const cropData = cropper.getData(true); // true for rounded integer values
              console.log(
                "Cropper 'cropend' event fired. Crop data:",
                cropData
              );

              if (cropData) {
                ocrSelection = {
                  x: cropData.x,
                  y: cropData.y,
                  width: cropData.width,
                  height: cropData.height,
                };
                if (ocrCoordsP) {
                  ocrCoordsP.textContent = `选区: X=${ocrSelection.x}, Y=${ocrSelection.y}, W=${ocrSelection.width}, H=${ocrSelection.height}`;
                } else {
                  console.error(
                    "ocrCoordsP element is null or undefined inside cropend event!"
                  );
                }
                console.log("Updated ocrSelection from cropend:", ocrSelection);
              } else {
                console.error(
                  "cropper.getData() returned null or undefined in cropend."
                );
                // 即使 getData 失败，也可能需要重置 ocrSelection 或显示错误
                // ocrSelection = null;
                // if (ocrCoordsP) ocrCoordsP.textContent = "选区: 获取失败";
              }
            },
          });
        } else {
          let errorMsg = "加载参考帧失败";
          try {
            const errorData = await response.json();
            errorMsg += `: ${errorData.detail || response.statusText}`;
          } catch {
            errorMsg += `: ${response.statusText}`;
          }
          addLog(errorMsg, "error", "video");
        }
      } catch (error) {
        addLog(`加载参考帧出错: ${error}`, "error", "video");
      } finally {
        if (loadRefFrameButton) loadRefFrameButton.disabled = false;
      }
    });
  }

  if (clearOcrRegionButton && ocrCoordsP) {
    clearOcrRegionButton.addEventListener("click", () => {
      if (cropper) {
        cropper.clear();
      }
      ocrSelection = null;
      ocrCoordsP.textContent = "选区已清除。";
      addLog("OCR选区已清除。", "info", "video");
    });
  }

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
        frame_interval_seconds: parseFloat(frameIntervalInput?.value || "1"),
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
        pdf_rows: parseInt(pdfRowsVideoInput?.value || "3"),
        pdf_cols: parseInt(pdfColsVideoInput?.value || "2"),
        pdf_title: pdfTitleVideoInput?.value || "聊天记录证据",
        pdf_layout: pdfLayoutVideoSelect?.value || "grid",
        image_order: getVideoPreviewImageOrder(),
      };
      console.log("Processing video with settings:", settings);

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
          resetVideoUI();
        } else {
          addLog(`清理失败: ${data.detail || data.message}`, "error", "video");
          if (videoCleanupButton) videoCleanupButton.disabled = false;
        }
      } catch (error) {
        addLog(`清理出错: ${error}`, "error", "video");
        if (videoCleanupButton) videoCleanupButton.disabled = false;
      }
    });
  }

  function getVideoPreviewImageOrder() {
    if (!videoPreviewArea) return []; // Return empty array if area not found
    const items = videoPreviewArea.querySelectorAll(".preview-item img");
    return Array.from(items)
      .map((item) => {
        try {
          const url = new URL(item.src);
          const filenameWithQuery = url.pathname.split("/").pop();
          return decodeURIComponent(filenameWithQuery.split("?")[0]);
        } catch (e) {
          console.error("Error parsing image URL for order:", item.src, e);
          return null;
        }
      })
      .filter((name) => name);
  }

  // --- Long Image Event Listeners & Functions ---
  if (longImageFileInput && processLongImageButton) {
    longImageFileInput.addEventListener("change", () => {
      processLongImageButton.disabled =
        !longImageFileInput.files || longImageFileInput.files.length === 0;
      if (longImageFileInput.files && longImageFileInput.files.length > 0) {
        addLog(
          `已选择长截图: ${longImageFileInput.files[0].name}`,
          "info",
          "longImage"
        );
      } else {
        addLog("长截图选择已清除。", "info", "longImage");
      }
    });
  }

  if (processLongImageButton) {
    processLongImageButton.addEventListener("click", async () => {
      const fileToUpload = longImageFileInput?.files[0];
      if (!fileToUpload) {
        addLog("请选择长截图文件。", "error", "longImage");
        return;
      }
      activeTaskType = "longImage";
      resetLongImageUI(false);
      processLongImageButton.disabled = true;
      addLog("开始处理长截图...", "info", "longImage");

      const formData = new FormData();
      formData.append("long_image_file", fileToUpload);
      formData.append("slice_height", sliceHeightInput?.value || "1000");
      formData.append("overlap", overlapHeightInput?.value || "100");
      formData.append("pdf_rows", pdfRowsLongInput?.value || "3");
      formData.append("pdf_cols", pdfColsLongInput?.value || "1"); // Default to 1 col for long images usually
      formData.append("pdf_title", pdfTitleLongInput?.value || "长截图证据");
      formData.append("pdf_layout", pdfLayoutLongSelect?.value || "column"); // 'column' for long image default

      // For long images, image_order is usually determined by slicing order,
      // but if you implement reordering for sliced previews, you'd get it here.
      // formData.append('image_order', JSON.stringify(getLongImagePreviewImageOrder()));

      try {
        const response = await fetch("/slice_long_image/", {
          method: "POST",
          body: formData,
        });
        const data = await response.json();
        if (response.ok && data.session_id) {
          longImageSessionId = data.session_id;
          addLog(
            `长截图处理启动。会话ID: ${longImageSessionId}`,
            "success",
            "longImage"
          );
          connectWebSocket(longImageSessionId, "longImage");
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
          if (longImageCleanupButton) longImageCleanupButton.disabled = false;
        }
      } catch (error) {
        addLog(`清理出错: ${error}`, "error", "longImage");
        if (longImageCleanupButton) longImageCleanupButton.disabled = false;
      }
    });
  }

  function getLongImagePreviewImageOrder() {
    if (!longImagePreviewArea) return [];
    const items = longImagePreviewArea.querySelectorAll(".preview-item img");
    return Array.from(items)
      .map((item) => {
        try {
          const url = new URL(item.src);
          const filenameWithQuery = url.pathname.split("/").pop();
          return decodeURIComponent(filenameWithQuery.split("?")[0]);
        } catch (e) {
          console.error("Error parsing image URL for order:", item.src, e);
          return null;
        }
      })
      .filter((name) => name);
  }

  // --- WebSocket Handling ---
  function connectWebSocket(sessionId, taskTypeOfOrigin) {
    if (!sessionId) {
      addLog("无效会话ID，无法连接WebSocket。", "error", taskTypeOfOrigin);
      return;
    }

    if (activeWebSocket) {
      // If trying to connect for a *different* session, close the old one.
      // If it's for the *same* session (e.g. page refresh, or re-initiating for same task),
      // it might already be connecting or open.
      if (activeSessionId && activeSessionId !== sessionId) {
        console.log(
          `Closing WebSocket for old session ${activeSessionId} to connect to ${sessionId}`
        );
        activeWebSocket.close(1000, "Switching to new session");
        activeWebSocket = null;
      } else if (
        activeWebSocket.readyState === WebSocket.OPEN ||
        activeWebSocket.readyState === WebSocket.CONNECTING
      ) {
        console.log(
          `WebSocket already open or connecting for session ${sessionId}`
        );
        // We might still want to ensure activeTaskType is correctly set if this was a re-initiation
        activeTaskType = taskTypeOfOrigin;
        activeSessionId = sessionId; // Ensure activeSessionId is updated
        return;
      }
    }

    activeTaskType = taskTypeOfOrigin; // 更新当前关注的任务类型
    if (taskTypeOfOrigin === "video")
      videoSessionId = sessionId; // 更新相应的会话ID变量
    else if (taskTypeOfOrigin === "longImage") longImageSessionId = sessionId;

    activeSessionId = sessionId; // 更新活动会话ID

    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/${sessionId}`;
    addLog(
      `正在连接 WebSocket (${taskTypeOfOrigin}): ${wsUrl}`,
      "info",
      taskTypeOfOrigin
    );

    activeWebSocket = new WebSocket(wsUrl);

    activeWebSocket.onopen = () => {
      addLog("WebSocket 连接成功。", "success", taskTypeOfOrigin);
    };

    activeWebSocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        let messageTaskType = "unknown"; // Determine task type from message's session_id

        if (data.session_id === videoSessionId) messageTaskType = "video";
        else if (data.session_id === longImageSessionId)
          messageTaskType = "longImage";
        else {
          // If session_id in message doesn't match known ones,
          // assume it's for the task type that initiated this WebSocket.
          messageTaskType =
            activeWebSocket && activeWebSocket.url.includes(videoSessionId)
              ? "video"
              : activeWebSocket &&
                activeWebSocket.url.includes(longImageSessionId)
              ? "longImage"
              : activeTaskType; // Fallback
          console.warn(
            "WS message session_id doesn't match current known session IDs. Using task type:",
            messageTaskType,
            data
          );
        }

        // Get target UI elements based on messageTaskType
        const targetLog =
          messageTaskType === "video" ? videoLogOutput : longImageLogOutput;
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

        if (!targetLog) {
          // Should not happen if IDs are correct
          console.error("Could not determine target log for WS message:", data);
          return;
        }

        addLog(`[WS] ${data.status}: ${data.message}`, "info", messageTaskType);

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
          const progressBarForType =
            messageTaskType === "video"
              ? videoProgressBar
              : longImageProgressBar;
          const currentProgress =
            progressBarForType?.getAttribute("aria-valuenow") || 0;
          updateProgress(
            currentProgress,
            `${data.status}: ${data.message}`,
            messageTaskType
          );
        }

        if (
          (data.status === "ocr_completed" ||
            data.status === "preview_ready" ||
            data.status === "slicing_complete") &&
          data.preview_images
        ) {
          if (targetPreviewArea) {
            targetPreviewArea.innerHTML = "";
            data.preview_images.forEach((imgUrl) => {
              const colDiv = document.createElement("div");
              colDiv.className = "col-6 col-sm-4 col-md-3 preview-item";
              const img = document.createElement("img");
              img.src = imgUrl; // Backend now provides full, correct URLs
              img.className = "img-fluid rounded preview-image";
              img.alt = "预览";
              img.style.cursor = "pointer";
              img.title = "双击预览";
              img.addEventListener('click', function() {
                openLightbox(this.src, this.alt); // Pass src and alt (or filename)
            });
              colDiv.appendChild(img);
              targetPreviewArea.appendChild(colDiv);
            });
            if (data.preview_images.length > 0) {
              setupSortable(targetPreviewArea);
            }
          }
        }

        const isCompleted = data.status === "completed";
        const isCompletedNoPdf = data.status === "completed_no_pdf";
        const isError = data.status === "error";

        if (isCompleted && data.result_url) {
          if (targetDownloadButton) {
            targetDownloadButton.href = data.result_url;
            targetDownloadButton.classList.remove("disabled");
          }
          addLog(`PDF准备就绪，请在下方点击下载`, "success", messageTaskType);
          updateProgress(100, "全部完成！", messageTaskType);
        } else if (isCompletedNoPdf) {
          addLog("处理完成，无PDF。", "info", messageTaskType);
          updateProgress(100, "处理完成，无PDF。", messageTaskType);
        } else if (isError) {
          addLog(`处理错误: ${data.message}`, "error", messageTaskType);
          const progressBarForError =
            messageTaskType === "video"
              ? videoProgressBar
              : longImageProgressBar;
          const currentProgressOnError =
            progressBarForError?.getAttribute("aria-valuenow") || 0;
          updateProgress(
            currentProgressOnError,
            `错误: ${data.message}`,
            messageTaskType
          );
        }

        if (isCompleted || isCompletedNoPdf || isError) {
          if (targetProcessButton) targetProcessButton.disabled = false;
          if (targetCleanupButton) targetCleanupButton.disabled = false;
        }
      } catch (e) {
        console.error(
          "Failed to parse WebSocket message or update UI:",
          e,
          event.data
        );
        addLog("接收到无效的 WebSocket 消息。", "error", activeTaskType);
      }
    };

    activeWebSocket.onclose = (event) => {
      let taskTypeForLog = "unknown"; // Determine task type from the closing socket's associated session ID
      if (
        activeSessionId === videoSessionId &&
        event.target.url.includes(videoSessionId)
      )
        taskTypeForLog = "video";
      else if (
        activeSessionId === longImageSessionId &&
        event.target.url.includes(longImageSessionId)
      )
        taskTypeForLog = "longImage";

      addLog(
        `WebSocket 连接已关闭 (${taskTypeForLog} - ${
          activeSessionId || "N/A"
        })。代码: ${event.code}`,
        "warning",
        taskTypeForLog === "unknown" ? activeTaskType : taskTypeForLog
      );

      if (event.code !== 1000) {
        // 1000 is normal closure
        if (taskTypeForLog === "video" && processVideoButton)
          processVideoButton.disabled = false;
        if (taskTypeForLog === "longImage" && processLongImageButton)
          processLongImageButton.disabled = false;
      }
      if (activeWebSocket === event.target) {
        // Only nullify if it's THE active socket
        activeWebSocket = null;
        activeSessionId = null; // Clear active session ID as well
      }
    };

    activeWebSocket.onerror = (error) => {
      let taskTypeForLog = "unknown";
      if (activeSessionId === videoSessionId) taskTypeForLog = "video";
      else if (activeSessionId === longImageSessionId)
        taskTypeForLog = "longImage";

      addLog(
        `WebSocket 错误 (${taskTypeForLog} - ${activeSessionId || "N/A"}): ${
          error.message || "未知错误"
        }`,
        "error",
        taskTypeForLog === "unknown" ? activeTaskType : taskTypeForLog
      );

      if (taskTypeForLog === "video" && processVideoButton)
        processVideoButton.disabled = false;
      if (taskTypeForLog === "longImage" && processLongImageButton)
        processLongImageButton.disabled = false;
      if (activeWebSocket) {
        // Defensive nullification on error
        activeWebSocket = null;
        activeSessionId = null;
      }
    };
  }

  // --- Theme Toggle Logic ---
  console.log("Attempting to add theme toggle button logic.");
  if (!document.querySelector(".theme-toggle")) {
    try {
      const themeToggle = document.createElement("button");
      themeToggle.className = "theme-toggle btn";
      themeToggle.setAttribute("aria-label", "Toggle theme");
      themeToggle.style.position = "fixed";
      themeToggle.style.bottom = "20px";
      themeToggle.style.right = "20px";
      themeToggle.style.width = "48px";
      themeToggle.style.height = "48px";
      themeToggle.style.borderRadius = "50%";
      themeToggle.style.zIndex = "1000";
      themeToggle.style.border = "1px solid var(--border-color)";
      themeToggle.style.backgroundColor = "var(--secondary-bg-color)";
      themeToggle.style.color = "var(--main-text-color)";
      themeToggle.style.display = "flex";
      themeToggle.style.alignItems = "center";
      themeToggle.style.justifyContent = "center";
      themeToggle.style.cursor = "pointer";
      themeToggle.style.transition =
        "background-color 0.2s, transform 0.2s, border-color 0.2s, color 0.2s";

      // Apply hover styles via JS if needed, or use CSS :hover with CSS variables
      themeToggle.onmouseenter = () => {
        themeToggle.style.backgroundColor = "var(--hover-bg)";
        themeToggle.style.transform = "scale(1.05)";
      };
      themeToggle.onmouseleave = () => {
        themeToggle.style.backgroundColor = "var(--secondary-bg-color)";
        themeToggle.style.transform = "scale(1)";
      };

      document.body.appendChild(themeToggle);
      console.log("Theme toggle button appended to body.");

      let currentTheme = localStorage.getItem("theme") || "light";
      applyTheme(currentTheme); // This will also call updateThemeIcon

      themeToggle.addEventListener("click", function () {
        currentTheme = currentTheme === "light" ? "dark" : "light";
        applyTheme(currentTheme);
        localStorage.setItem("theme", currentTheme);
      });
    } catch (error) {
      console.error("Error creating or attaching theme toggle button:", error);
    }
  } else {
    console.log("Theme toggle button already exists, skipping creation.");
    // If it exists, ensure its event listener is attached if this script re-runs (though DOMContentLoaded shouldn't re-run)
    // Or better, ensure this whole theme part runs only once.
    // For simplicity, if it exists, we assume it's already set up by a previous script execution.
    // To be robust, one might re-apply theme or re-attach listener if needed.
    // For now, if it exists, re-apply stored theme to ensure consistency.
    let storedTheme = localStorage.getItem("theme") || "light";
    applyTheme(storedTheme);
  }

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
    if (!themeToggle) {
      console.warn("Cannot update theme icon: .theme-toggle button not found.");
      return;
    }
    // Update icon based on theme
    if (theme === "dark") {
      themeToggle.innerHTML =
        '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 16 16" class="bi bi-moon-stars-fill"><path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278z"/><path d="M10.794 3.148a.217.217 0 0 1 .412 0l.387 1.162c.173.518.579.924 1.097 1.097l1.162.387a.217.217 0 0 1 0 .412l-1.162.387a1.734 1.734 0 0 0-1.097 1.097l-.387 1.162a.217.217 0 0 1-.412 0l-.387-1.162A1.734 1.734 0 0 0 9.31 6.593l-1.162-.387a.217.217 0 0 1 0-.412l1.162-.387a1.734 1.734 0 0 0 1.097-1.097l.387-1.162zM13.863.099a.145.145 0 0 1 .274 0l.258.774c.115.346.386.617.732.732l.774.258a.145.145 0 0 1 0 .274l-.774.258a1.156 1.156 0 0 0-.732.732l-.258.774a.145.145 0 0 1-.274 0l-.258-.774a1.156 1.156 0 0 0-.732-.732l-.774-.258a.145.145 0 0 1 0-.274l.774-.258c.346-.115.617-.386.732-.732L13.863.1z"/></svg>';
    } else {
      themeToggle.innerHTML =
        '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 16 16" class="bi bi-sun-fill"><path d="M8 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM8 0a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 0zm0 13a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 13zm8-5a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2a.5.5 0 0 1 .5.5zM3 8a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2A.5.5 0 0 1 3 8zm10.657-5.657a.5.5 0 0 1 0 .707l-1.414 1.415a.5.5 0 1 1-.707-.708l1.414-1.414a.5.5 0 0 1 .707 0zm-9.193 9.193a.5.5 0 0 1 0 .707L3.05 13.657a.5.5 0 0 1-.707-.707l1.414-1.414a.5.5 0 0 1 .707 0zm9.193 2.121a.5.5 0 0 1-.707 0l-1.414-1.414a.5.5 0 0 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .707zM4.464 4.465a.5.5 0 0 1-.707 0L2.343 3.05a.5.5 0 1 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .708z"/></svg>';
    }
  }
  // --- End Theme Toggle Code ---

  // Initial UI state setup for both panels
  resetVideoUI();
  resetLongImageUI();
  // Initial theme application (if button wasn't found by the separate DOMContentLoaded for theme)
  if (!document.querySelector(".theme-toggle")) {
    // Check again, just in case
    console.warn(
      "Theme toggle might not have been initialized by its own DOMContentLoaded listener if this main one ran first."
    );
  }
}); // End Main DOMContentLoaded listener
