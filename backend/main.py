# backend/main.py
import uuid
import os
import shutil
import asyncio
from pathlib import Path
import datetime
from typing import Dict, List, Optional, Callable, Any, Tuple

from fastapi import (
    FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect,
    Form, HTTPException, Query, BackgroundTasks
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel # Assuming models are defined here or imported

# --- Assuming Models are defined or imported ---
# Example definitions if not in backend.models
class TaskStatus(BaseModel):
    session_id: str
    status: str
    message: str
    progress: Optional[int] = None
    result_url: Optional[str] = None
    preview_images: Optional[List[str]] = None

class ProcessSettings(BaseModel):
    frame_interval_seconds: float = 1.0
    exclusion_list: List[str] = []
    ocr_analysis_rect: Optional[Tuple[int, int, int, int]] = None
    pdf_rows: int = 3
    pdf_cols: int = 2
    pdf_title: str = "聊天记录证据"
    pdf_layout: str = 'grid' # 'grid' or 'column'
    image_order: Optional[List[str]] = None

class LongImageProcessSettings(BaseModel):
    slice_height: int = 1000
    overlap: int = 100
    pdf_rows: int = 3
    pdf_cols: int = 1
    pdf_title: str = "长截图证据"
    pdf_layout: str = 'column' # 'grid' or 'column'
    image_order: Optional[List[str]] = None

# --- Import core worker functions/classes ---
from backend.core_workers import (
    extract_single_frame_ffmpeg_sync,
    extract_frames_ffmpeg_sync,
    slice_image_sync, # ** Ensure you have implemented this function **
    OcrFilter,
    PdfGenerator,
    OCR_ENGINE,
    REFERENCE_FRAME_INDEX
)

APP_NAME = "易存讯 - 聊天记录与长截图取证"
APP_VERSION = "0.2.0" # Updated version
TEMP_SESSIONS_BASE_DIR = Path("temp_sessions")
OUTPUT_BASE_DIR = Path("output")
os.makedirs(TEMP_SESSIONS_BASE_DIR, exist_ok=True)
os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

app = FastAPI(title=APP_NAME, version=APP_VERSION)

# Serve frontend static files (assuming frontend is one level up)
# Adjust directory path if your structure is different
BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "frontend"), name="static_frontend")


# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {} # session_id -> WebSocket

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        print(f"WebSocket connection accepted for session: {session_id}")

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            print(f"WebSocket connection removed for session: {session_id}")

    async def send_status_update(self, session_id: str, status: TaskStatus):
        websocket = self.active_connections.get(session_id)
        if websocket:
            try:
                await websocket.send_json(status.dict())
            except WebSocketDisconnect:
                print(f"WebSocketDisconnect while sending to {session_id}")
                self.disconnect(session_id)
            except RuntimeError as e:
                print(f"RuntimeError sending WS message for {session_id}: {e}")
                # Handle cases where the socket might already be closed
                if "WebSocket is closed" in str(e):
                    self.disconnect(session_id)

manager = ConnectionManager()
# Session Data Store (In-memory, consider Redis/DB for production)
# Structure: session_id -> Dict[str, Any]
SESSIONS_DATA: Dict[str, Dict[str, Any]] = {}

# --- Thread-safe Callback Creation ---
def create_async_callback_for_sync_task(
    session_id: str,
    status_str: str,
    main_loop: asyncio.AbstractEventLoop,
    is_progress: bool = False,
    max_updates_for_progress: int = 20
) -> Callable:
    """Creates a thread-safe callback for updating WebSocket from sync tasks."""
    progress_state = {'updates_sent': 0}

    def sync_callback_handler(*args):
        if not main_loop or main_loop.is_closed():
            print(f"[Callback Ignored - LOOP CLOSED/NONE - {session_id}]")
            return

        try:
            if is_progress:
                current, total = args[0], args[1]
                progress_state['updates_sent'] += 1
                if total > 0:
                    update_frequency = max(1, total // max_updates_for_progress if max_updates_for_progress > 0 and total >= max_updates_for_progress else 1)
                    should_send = (current == total) or (progress_state['updates_sent'] % update_frequency == 0)
                    if should_send:
                        progress_val = int((current / total) * 100)
                        message = f"进度: {current}/{total}"
                        status_update = TaskStatus(session_id=session_id, status=status_str, message=message, progress=progress_val)
                        main_loop.call_soon_threadsafe(asyncio.create_task, manager.send_status_update(session_id, status_update))
            else:
                message = args[0]
                status_update = TaskStatus(session_id=session_id, status=status_str, message=message)
                main_loop.call_soon_threadsafe(asyncio.create_task, manager.send_status_update(session_id, status_update))
        except Exception as e:
            print(f"Error in sync_callback_handler for session {session_id}: {e}")

    return sync_callback_handler

# --- API Endpoints ---

@app.get("/")
async def read_root():
    """Serves the main HTML page."""
    return FileResponse(BASE_DIR / "frontend/index.html")

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """Handles WebSocket connections for real-time updates."""
    await manager.connect(websocket, session_id)
    status_msg = "WebSocket reconnected." if session_id in SESSIONS_DATA else "WebSocket connected. Waiting for upload..."
    status_key = "reconnected" if session_id in SESSIONS_DATA else "pending_upload"
    # Send initial status immediately after connection
    await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status=status_key, message=status_msg))
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
            # Handle other client messages if needed
    except WebSocketDisconnect:
        print(f"Client {session_id} disconnected WS normally.")
    except Exception as e:
        print(f"WebSocket error for {session_id}: {e}")
    finally:
        manager.disconnect(session_id)

@app.post("/upload_video/")
async def upload_video(video_file: UploadFile = File(...)):
    """Handles video file uploads and initializes a video processing session."""
    session_id = str(uuid.uuid4())
    session_dir = TEMP_SESSIONS_BASE_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    video_path = session_dir / video_file.filename

    try:
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(video_file.file, buffer)
    except Exception as e:
        print(f"Error saving video for session {session_id}: {e}")
        # Attempt to notify client if WS connected early, otherwise just return error
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message=f"上传文件保存失败: {e}"))
        return JSONResponse(status_code=500, content={"message": f"Error saving video: {e}"})
    finally:
        video_file.file.close()

    SESSIONS_DATA[session_id] = {
        "type": "video",
        "video_path": str(video_path),
        "frames_dir": str(session_dir / "raw_frames"),
        "kept_images": [],
        "video_pdf_path": None, # Use specific key
        "original_video_filename": video_file.filename
    }
    await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="upload_complete", message=f"视频 '{video_file.filename}' 上传成功。"))
    print(f"Video session created: {session_id}")
    return {"session_id": session_id, "filename": video_file.filename, "message": "Video uploaded successfully."}

@app.get("/get_reference_frame/{session_id}")
async def get_reference_frame(session_id: str):
    """Extracts and returns the reference frame for OCR area selection."""
    if session_id not in SESSIONS_DATA or SESSIONS_DATA[session_id].get("type") != "video":
        raise HTTPException(status_code=404, detail="Video session not found or invalid type.")
    session_data = SESSIONS_DATA[session_id]
    video_path = Path(session_data["video_path"])
    ref_frame_dir = TEMP_SESSIONS_BASE_DIR / session_id / "ref_frame"
    ref_frame_dir.mkdir(parents=True, exist_ok=True)
    ref_frame_filename = f"ref_frame_{video_path.stem}_{REFERENCE_FRAME_INDEX}.png"
    ref_frame_path = ref_frame_dir / ref_frame_filename

    current_loop = asyncio.get_running_loop()
    log_cb = create_async_callback_for_sync_task(session_id, "ref_frame_extraction", current_loop)

    print(f"Extracting reference frame for {session_id} to {ref_frame_path}")
    success = await current_loop.run_in_executor(
        None, extract_single_frame_ffmpeg_sync,
        str(video_path), str(ref_frame_path), REFERENCE_FRAME_INDEX, log_cb
    )

    if success and ref_frame_path.exists():
        print(f"Reference frame extracted successfully for {session_id}")
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="ref_frame_ready", message="参考帧提取成功。"))
        return FileResponse(str(ref_frame_path), media_type="image/png")
    else:
        print(f"Failed to extract reference frame for {session_id}")
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message="参考帧提取失败。"))
        raise HTTPException(status_code=500, detail="Failed to extract reference frame.")

# --- Background Task for Video Processing ---
async def run_full_process(session_id: str, settings: ProcessSettings):
    """Runs the full video processing pipeline in the background."""
    if session_id not in SESSIONS_DATA or SESSIONS_DATA[session_id].get("type") != "video":
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message="无效的视频处理会话。"))
        return

    session_data = SESSIONS_DATA[session_id]
    video_path_str = session_data["video_path"]
    frames_dir_path = Path(session_data["frames_dir"])
    frames_dir_path.mkdir(parents=True, exist_ok=True)
    current_loop = asyncio.get_running_loop()

    try:
        # 1. Extract Frames
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="extracting_frames", message="开始提取视频帧...", progress=0))
        ffmpeg_log_cb = create_async_callback_for_sync_task(session_id, "extracting_frames", current_loop)
        ffmpeg_success, ffmpeg_msg, frame_count = await current_loop.run_in_executor(
            None, extract_frames_ffmpeg_sync,
            video_path_str, str(frames_dir_path), settings.frame_interval_seconds, ffmpeg_log_cb
        )
        if not ffmpeg_success: raise RuntimeError(f"帧提取失败: {ffmpeg_msg}")
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="frames_extracted", message=f"帧提取完成，共 {frame_count} 帧。", progress=100))

        # 2. OCR & Filter
        if OCR_ENGINE is None: raise RuntimeError("OCR引擎未初始化。")
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="ocr_processing", message="开始OCR与筛选...", progress=0))
        ocr_log_cb = create_async_callback_for_sync_task(session_id, "ocr_processing", current_loop)
        ocr_progress_cb = create_async_callback_for_sync_task(session_id, "ocr_processing", current_loop, is_progress=True)
        ocr_filter = OcrFilter(
            str(frames_dir_path), OCR_ENGINE, settings.exclusion_list, settings.ocr_analysis_rect,
            log_callback=ocr_log_cb, progress_callback=ocr_progress_cb
        )
        kept_image_paths = await current_loop.run_in_executor(None, ocr_filter.run_filter)
        session_data["kept_images"] = kept_image_paths
        preview_image_urls = [f"/get_processed_image/{session_id}/{Path(p).name}" for p in kept_image_paths] if kept_image_paths else []
        await manager.send_status_update(session_id, TaskStatus(
            session_id=session_id, status="ocr_completed", message=f"OCR与筛选完成，保留 {len(kept_image_paths)} 张图片。",
            preview_images=preview_image_urls, progress=100
        ))
        if not kept_image_paths:
            await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="completed_no_pdf", message="没有保留的图片，无法生成PDF。"))
            return

        # 3. Generate PDF
        ordered_kept_images = kept_image_paths # Default order
        if settings.image_order:
            ordered_map = {Path(p).name: p for p in kept_image_paths}
            ordered_kept_images = [ordered_map[fname] for fname in settings.image_order if fname in ordered_map] or kept_image_paths

        output_pdf_dir = OUTPUT_BASE_DIR / session_id
        output_pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_filename_base = "".join(c if c.isalnum() or c in [' ', '-'] else "_" for c in settings.pdf_title).replace(' ', '_')[:50] or "video_evidence"
        output_pdf_path = output_pdf_dir / f"{pdf_filename_base}_video_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        session_data["video_pdf_path"] = str(output_pdf_path) # Store specific PDF path

        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="pdf_generating", message="开始生成PDF...", progress=0))
        pdf_log_cb = create_async_callback_for_sync_task(session_id, "pdf_generating", current_loop)
        pdf_progress_cb = create_async_callback_for_sync_task(session_id, "pdf_generating", current_loop, is_progress=True)
        pdf_generator = PdfGenerator(
            ordered_kept_images, str(output_pdf_path), settings.pdf_cols, settings.pdf_rows,
            layout=settings.pdf_layout, # Pass layout
            page_title=settings.pdf_title,
            log_callback=pdf_log_cb, progress_callback=pdf_progress_cb
        )
        pdf_success, pdf_msg_or_path = await current_loop.run_in_executor(None, pdf_generator.generate_pdf)
        if not pdf_success: raise RuntimeError(f"PDF生成失败: {pdf_msg_or_path}")

        pdf_download_url = f"/download_pdf/{session_id}/{output_pdf_path.name}"
        await manager.send_status_update(session_id, TaskStatus(
            session_id=session_id, status="completed", message=f"PDF生成成功: {output_pdf_path.name}",
            result_url=pdf_download_url, progress=100
        ))

    except Exception as e:
        print(f"Error in run_full_process for session {session_id}: {e}")
        import traceback
        traceback.print_exc()
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message=f"处理过程中出错: {e}"))


@app.post("/process_video/{session_id}")
async def process_video_endpoint(session_id: str, settings: ProcessSettings, background_tasks: BackgroundTasks):
    """Endpoint to start the video processing background task."""
    if session_id not in SESSIONS_DATA or SESSIONS_DATA[session_id].get("type") != "video":
        # Send error via WS if possible, then raise HTTP Exception
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message="无效的视频处理会话。"))
        raise HTTPException(status_code=404, detail="无效的视频处理会话。")

    # Add type marker if missing (e.g., if session existed before type field)
    SESSIONS_DATA[session_id]["type"] = "video"

    print(f"Received video process request for session {session_id} with settings: {settings}")
    background_tasks.add_task(run_full_process, session_id, settings)
    return {"message": "视频处理已启动。", "session_id": session_id}


# --- Background Task for Long Image Processing ---
async def run_long_image_process(session_id: str, image_path_str: str, settings: LongImageProcessSettings):
    """Runs the long image slicing and PDF generation in the background."""
    if session_id not in SESSIONS_DATA or SESSIONS_DATA[session_id].get("type") != "long_image":
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message="无效的长截图处理会话。"))
        return

    current_loop = asyncio.get_running_loop()
    log_cb = create_async_callback_for_sync_task(session_id, "longImageProcessing", current_loop)
    progress_cb = create_async_callback_for_sync_task(session_id, "longImageProcessing", current_loop, is_progress=True)

    try:
        # 1. Slice Image
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="slicing", message="开始裁剪长截图...", progress=0))
        temp_slice_dir = TEMP_SESSIONS_BASE_DIR / session_id / "sliced_images"
        temp_slice_dir.mkdir(parents=True, exist_ok=True)

        # ** Ensure slice_image_sync is implemented in core_workers.py **
        try:
            from backend.core_workers import slice_image_sync
            sliced_image_paths = await current_loop.run_in_executor(
                None, slice_image_sync,
                image_path_str, settings.slice_height, settings.overlap, str(temp_slice_dir),
                log_cb, progress_cb # Pass both callbacks
            )
        except ImportError:
             log_cb("错误: slice_image_sync 函数未在 core_workers.py 中实现!")
             raise RuntimeError("slice_image_sync function not implemented.")
        except Exception as slice_err:
            log_cb(f"裁剪过程中出错: {slice_err}")
            raise RuntimeError(f"Error during slicing: {slice_err}")

        if not sliced_image_paths: raise RuntimeError("长截图裁剪失败或未生成图片。")
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="slicing_complete", message=f"长截图裁剪完成，共 {len(sliced_image_paths)} 张。", progress=100))

        # Update Session Data
        SESSIONS_DATA[session_id]["sliced_images"] = sliced_image_paths

        # Provide Preview URLs
        preview_urls = [f"/get_processed_image/{session_id}/{Path(p).name}?type=sliced" for p in sliced_image_paths]
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="preview_ready", message="预览已生成", preview_images=preview_urls))

        # 2. Handle Sorting
        ordered_sliced_images = sliced_image_paths # Default order
        if settings.image_order:
            log_cb(f"Applying custom image order: {settings.image_order}")
            ordered_map = {Path(p).name: p for p in sliced_image_paths}
            ordered_sliced_images = [ordered_map[fname] for fname in settings.image_order if fname in ordered_map]
            if not ordered_sliced_images:
                log_cb("警告: 提供的排序列表无效或与切片不匹配，使用默认顺序。")
                ordered_sliced_images = sliced_image_paths

        # 3. Generate PDF
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="pdf_generating", message="开始生成PDF...", progress=0))
        pdf_log_cb_gen = create_async_callback_for_sync_task(session_id, "pdfGenerating", current_loop)
        pdf_progress_cb_gen = create_async_callback_for_sync_task(session_id, "pdfGenerating", current_loop, is_progress=True)

        output_pdf_dir = OUTPUT_BASE_DIR / session_id
        output_pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_filename_base = "".join(c if c.isalnum() or c in [' ', '-'] else "_" for c in settings.pdf_title).replace(' ', '_')[:50] or "long_screenshot"
        output_pdf_path = output_pdf_dir / f"{pdf_filename_base}_long_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        SESSIONS_DATA[session_id]["long_image_pdf_path"] = str(output_pdf_path)

        pdf_generator = PdfGenerator(
            ordered_sliced_images, str(output_pdf_path),
            images_per_row=settings.pdf_cols, images_per_col=settings.pdf_rows,
            layout=settings.pdf_layout, # Use layout from settings
            page_title=settings.pdf_title,
            log_callback=pdf_log_cb_gen, progress_callback=pdf_progress_cb_gen
        )
        pdf_success, pdf_msg_or_path = await current_loop.run_in_executor(None, pdf_generator.generate_pdf)
        if not pdf_success: raise RuntimeError(f"PDF生成失败: {pdf_msg_or_path}")

        pdf_download_url = f"/download_pdf/{session_id}/{output_pdf_path.name}"
        await manager.send_status_update(session_id, TaskStatus(
            session_id=session_id, status="completed", message=f"PDF生成成功: {output_pdf_path.name}",
            result_url=pdf_download_url, progress=100
        ))

    except Exception as e:
        print(f"Error in run_long_image_process for session {session_id}: {e}")
        import traceback
        traceback.print_exc()
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message=f"长截图处理出错: {e}"))

# --- New API Endpoint for Long Image ---
@app.post("/slice_long_image/")
async def slice_long_image_endpoint(
    # Use Form for parameters when Content-Type is multipart/form-data
    long_image_file: UploadFile = File(...),
    slice_height: int = Form(...),
    overlap: int = Form(...),
    pdf_rows: int = Form(...),
    pdf_cols: int = Form(...),
    pdf_title: str = Form(...),
    pdf_layout: str = Form(...),
    image_order_json: Optional[str] = Form(None), # Receive image order as JSON string
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Handles long image uploads and starts the slicing/PDF generation task."""
    session_id = str(uuid.uuid4())
    session_dir = TEMP_SESSIONS_BASE_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    image_filename = f"original_long_{long_image_file.filename}"
    image_path = session_dir / image_filename

    try:
        with open(image_path, "wb") as buffer: shutil.copyfileobj(long_image_file.file, buffer)
    except Exception as e: return JSONResponse(status_code=500, content={"message": f"Error saving image: {e}"})
    finally: long_image_file.file.close()

    image_order_list = None
    if image_order_json:
        try:
            import json
            image_order_list = json.loads(image_order_json)
            if not isinstance(image_order_list, list): image_order_list = None
        except json.JSONDecodeError:
            print(f"Warning: Could not decode image_order_json for session {session_id}")
            image_order_list = None

    SESSIONS_DATA[session_id] = {
        "type": "long_image",
        "long_image_path": str(image_path),
        "sliced_images": [],
        "long_image_pdf_path": None,
        "original_long_image_filename": long_image_file.filename
    }

    settings = LongImageProcessSettings(
        slice_height=slice_height, overlap=overlap, pdf_rows=pdf_rows,
        pdf_cols=pdf_cols, pdf_title=pdf_title, pdf_layout=pdf_layout,
        image_order=image_order_list # Pass the parsed list
    )

    print(f"Received long image process request, session {session_id}, settings: {settings}")
    await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="upload_complete", message=f"长截图 '{long_image_file.filename}' 上传成功。"))
    background_tasks.add_task(run_long_image_process, session_id, str(image_path), settings)
    return {"message": "长截图处理已启动。", "session_id": session_id}


# --- Modified Endpoints for Image/PDF Retrieval and Cleanup ---

@app.get("/get_processed_image/{session_id}/{image_name}")
async def get_processed_image(session_id: str, image_name: str, type: Optional[str] = Query(None)):
    """Serves processed images (video frames or sliced images)."""
    if session_id not in SESSIONS_DATA: raise HTTPException(status_code=404, detail="会话未找到")
    session_data = SESSIONS_DATA[session_id]

    base_dir = None
    if type == "sliced" and session_data.get("type") == "long_image":
        base_dir = TEMP_SESSIONS_BASE_DIR / session_id / "sliced_images"
    elif session_data.get("type") == "video":
        frames_dir_str = session_data.get("frames_dir")
        if frames_dir_str: base_dir = Path(frames_dir_str)
    else: # Fallback or unknown type
         raise HTTPException(status_code=400, detail=f"无效的图片类型 '{type}' 或会话类型不匹配。")

    if not base_dir or not base_dir.is_dir():
         raise HTTPException(status_code=404, detail=f"图片基础目录未找到: {base_dir}")

    image_path = base_dir / image_name
    if not image_path.is_file(): # Use is_file() for better check
        print(f"Image not found at expected path: {image_path}")
        raise HTTPException(status_code=404, detail=f"图片 '{image_name}' 未找到。")

    # Add cache control headers if desired
    # headers = {"Cache-Control": "no-cache, no-store, must-revalidate"}
    # return FileResponse(str(image_path), headers=headers)
    return FileResponse(str(image_path))


@app.get("/download_pdf/{session_id}/{pdf_name}")
async def download_pdf_file(session_id: str, pdf_name: str):
    """Serves the generated PDF file."""
    if session_id not in SESSIONS_DATA: raise HTTPException(status_code=404, detail="会话未找到")
    session_data = SESSIONS_DATA[session_id]

    pdf_path_str = None
    # Check both potential PDF path keys based on the name matching
    long_pdf_path = session_data.get("long_image_pdf_path")
    video_pdf_path = session_data.get("video_pdf_path")

    if long_pdf_path and Path(long_pdf_path).name == pdf_name:
        pdf_path_str = long_pdf_path
    elif video_pdf_path and Path(video_pdf_path).name == pdf_name:
         pdf_path_str = video_pdf_path

    if not pdf_path_str:
        raise HTTPException(status_code=404, detail=f"名为 '{pdf_name}' 的 PDF 记录未在会话 {session_id} 中找到。")

    pdf_path = Path(pdf_path_str)
    if not pdf_path.is_file():
        print(f"PDF file not found at expected path: {pdf_path}")
        raise HTTPException(status_code=404, detail=f"PDF 文件在路径 {pdf_path} 未找到。")

    return FileResponse(str(pdf_path), media_type='application/pdf', filename=pdf_name)

@app.post("/cleanup_session/{session_id}")
async def cleanup_session(session_id: str):
    """Cleans up temporary files and session data."""
    session_dir = TEMP_SESSIONS_BASE_DIR / session_id
    output_dir = OUTPUT_BASE_DIR / session_id
    cleaned_temp, cleaned_output, session_removed = False, False, False

    print(f"Attempting to cleanup session: {session_id}")

    if session_dir.exists():
        try:
            shutil.rmtree(session_dir)
            cleaned_temp = True
            print(f"Cleaned temp directory: {session_dir}")
        except Exception as e: print(f"清理临时目录 {session_id} 出错: {e}")
    else: print(f"Temp directory not found: {session_dir}")

    if output_dir.exists():
        try:
            shutil.rmtree(output_dir)
            cleaned_output = True
            print(f"Cleaned output directory: {output_dir}")
        except Exception as e: print(f"清理输出目录 {session_id} 出错: {e}")
    else: print(f"Output directory not found: {output_dir}")

    if session_id in SESSIONS_DATA:
        del SESSIONS_DATA[session_id]
        session_removed = True
        print(f"Removed session data entry for: {session_id}")

    manager.disconnect(session_id) # Also disconnect WebSocket

    if cleaned_temp or cleaned_output or session_removed:
        return {"message": f"会话 {session_id} 已清理。"}
    else:
        # If session data didn't exist initially, maybe it was already cleaned
        print(f"Session {session_id} not found in data or directories.")
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 未找到或已清理。")

# --- Main execution ---
if __name__ == "__main__":
    import uvicorn
    print("-" * 30)
    if OCR_ENGINE is None: print("⚠️ 警告: PaddleOCR 未能初始化。OCR功能将无法工作。")
    else: print("✅ PaddleOCR 引擎已成功初始化。")
    print(f"🚀 启动应用 '{APP_NAME}' 版本 '{APP_VERSION}'")
    print(f"    临时会话目录: {TEMP_SESSIONS_BASE_DIR.resolve()}")
    print(f"    输出目录: {OUTPUT_BASE_DIR.resolve()}")
    print("-" * 30)
    # Use the port specified in Dockerfile/README (18765) for consistency
    uvicorn.run(app, host="0.0.0.0", port=18765, log_level="info")