# backend/main.py
import uuid
import os
import shutil
import asyncio
from pathlib import Path
import datetime # 确保导入 datetime
from typing import Dict, List, Optional, Callable

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect, Form, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTasks

from backend.models import ProcessSettings, TaskStatus
from backend.core_workers import (
    extract_single_frame_ffmpeg_sync,
    extract_frames_ffmpeg_sync,
    OcrFilter, PdfGenerator, OCR_ENGINE, REFERENCE_FRAME_INDEX
)

APP_NAME = "聊天记录证据生成工具 Web"
APP_VERSION = "0.1.1-web-sync-ffmpeg-cbfix"
TEMP_SESSIONS_BASE_DIR = Path("temp_sessions")
OUTPUT_BASE_DIR = Path("output")
os.makedirs(TEMP_SESSIONS_BASE_DIR, exist_ok=True)
os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)

app = FastAPI(title=APP_NAME, version=APP_VERSION)

app.mount("/static", StaticFiles(directory="frontend"), name="static_frontend")

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        print(f"WebSocket connection accepted for session: {session_id}")

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            print(f"WebSocket connection removed for session: {session_id}")

    async def send_status_update(self, session_id: str, status: TaskStatus):
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            try:
                await websocket.send_json(status.dict())
            except WebSocketDisconnect:
                print(f"WebSocketDisconnect while sending to {session_id}")
                self.disconnect(session_id)
            except RuntimeError as e:
                print(f"RuntimeError sending WS message for {session_id}: {e}")
                if "Cannot call send() more than once" in str(e) or "WebSocket is closed" in str(e):
                     self.disconnect(session_id)

manager = ConnectionManager()
SESSIONS_DATA: Dict[str, Dict] = {}

# --- Thread-safe Callback Creation ---
def create_async_callback_for_sync_task(
    session_id: str,
    status_str: str,
    main_loop: asyncio.AbstractEventLoop,
    is_progress: bool = False,
    max_updates_for_progress: int = 20
) -> Callable:
    
    progress_state = {'updates_sent': 0} # For progress callback

    def sync_callback_handler(*args):
        if not main_loop or main_loop.is_closed():
            print(f"[Callback - LOOP CLOSED/NONE - {session_id}]: Args - {args}")
            return

        if is_progress:
            current, total = args[0], args[1]
            progress_state['updates_sent'] += 1
            if total > 0:
                # Calculate how often to send updates based on total and max_updates
                # Ensure at least one update for small totals, and avoid division by zero
                update_frequency = max(1, total // max_updates_for_progress if max_updates_for_progress > 0 and total >= max_updates_for_progress else 1)

                should_send = (current == total) or (progress_state['updates_sent'] % update_frequency == 0)
                if should_send:
                    progress_val = int((current / total) * 100)
                    message = f"Progress: {current}/{total}"
                    task_to_run = manager.send_status_update(
                        session_id,
                        TaskStatus(session_id=session_id, status=status_str, message=message, progress=progress_val)
                    )
                    main_loop.call_soon_threadsafe(asyncio.create_task, task_to_run)
        else:
            message = args[0] # Assuming log callback takes a single string message
            task_to_run = manager.send_status_update(
                session_id,
                TaskStatus(session_id=session_id, status=status_str, message=message)
            )
            main_loop.call_soon_threadsafe(asyncio.create_task, task_to_run)

    return sync_callback_handler

@app.get("/")
async def read_root(): return FileResponse("frontend/index.html")

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(websocket, session_id)
    status_msg = "WebSocket reconnected." if session_id in SESSIONS_DATA else "WebSocket connected. Waiting for video upload..."
    status_key = "reconnected" if session_id in SESSIONS_DATA else "pending_upload"
    await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status=status_key, message=status_msg))
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping": await websocket.send_text("pong")
    except WebSocketDisconnect: print(f"Client {session_id} disconnected WS.")
    except Exception as e: print(f"WebSocket error for {session_id}: {e}")
    finally: manager.disconnect(session_id)

@app.post("/upload_video/")
async def upload_video(video_file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())
    session_dir = TEMP_SESSIONS_BASE_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    video_path = session_dir / video_file.filename
    try:
        with open(video_path, "wb") as buffer: shutil.copyfileobj(video_file.file, buffer)
    except Exception as e: return JSONResponse(status_code=500, content={"message": f"Error saving video: {e}"})
    finally: video_file.file.close()

    SESSIONS_DATA[session_id] = {
        "video_path": str(video_path), "frames_dir": str(session_dir / "raw_frames"),
        "kept_images": [], "pdf_path": None, "original_video_filename": video_file.filename
    }
    await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="upload_complete", message=f"Video '{video_file.filename}' uploaded."))
    return {"session_id": session_id, "filename": video_file.filename, "message": "Video uploaded successfully."}

@app.get("/get_reference_frame/{session_id}")
async def get_reference_frame(session_id: str):
    if session_id not in SESSIONS_DATA: raise HTTPException(status_code=404, detail="Session not found")
    session_data = SESSIONS_DATA[session_id]
    video_path = Path(session_data["video_path"]) # Use Path object
    ref_frame_dir = TEMP_SESSIONS_BASE_DIR / session_id / "ref_frame"
    ref_frame_dir.mkdir(parents=True, exist_ok=True)
    ref_frame_filename = f"ref_frame_{video_path.stem}_{REFERENCE_FRAME_INDEX}.png"
    ref_frame_path = ref_frame_dir / ref_frame_filename

    current_loop = asyncio.get_running_loop()
    log_cb = create_async_callback_for_sync_task(session_id, "ref_frame_extraction", current_loop)
    
    success = await current_loop.run_in_executor(
        None, extract_single_frame_ffmpeg_sync,
        str(video_path), str(ref_frame_path), REFERENCE_FRAME_INDEX, log_cb
    )

    if success and ref_frame_path.exists():
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="ref_frame_ready", message="Reference frame extracted."))
        return FileResponse(str(ref_frame_path), media_type="image/png")
    else:
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message="Failed to extract reference frame."))
        raise HTTPException(status_code=500, detail="Failed to extract reference frame (sync execution).")

async def run_full_process(session_id: str, settings: ProcessSettings):
    if session_id not in SESSIONS_DATA:
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message="Session not found for processing."))
        return
    
    session_data = SESSIONS_DATA[session_id]
    video_path_str = session_data["video_path"]
    frames_dir_path = Path(session_data["frames_dir"])
    frames_dir_path.mkdir(parents=True, exist_ok=True)
    current_loop = asyncio.get_running_loop()

    # 1. Extract Frames
    await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="extracting_frames", message="开始提取视频帧...", progress=0))
    ffmpeg_log_cb = create_async_callback_for_sync_task(session_id, "extracting_frames", current_loop)
    ffmpeg_success, ffmpeg_msg, frame_count = await current_loop.run_in_executor(
        None, extract_frames_ffmpeg_sync,
        video_path_str, str(frames_dir_path), settings.frame_interval_seconds, ffmpeg_log_cb
    )
    if not ffmpeg_success:
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message=f"帧提取失败: {ffmpeg_msg}"))
        return
    await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="frames_extracted", message=f"帧提取完成，共 {frame_count} 帧。", progress=100))

    # 2. OCR & Filter
    if OCR_ENGINE is None:
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message="OCR引擎未初始化。"))
        return
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
    ordered_kept_images = [] # Populate this based on settings.image_order and kept_image_paths
    if settings.image_order and kept_image_paths:
        for fname in settings.image_order:
            full_path = str(frames_dir_path / fname) # Correct path construction
            if full_path in kept_image_paths: ordered_kept_images.append(full_path)
        if not ordered_kept_images : ordered_kept_images = kept_image_paths # Fallback
    else: ordered_kept_images = kept_image_paths

    output_pdf_dir = OUTPUT_BASE_DIR / session_id
    output_pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_filename_base = "".join(c if c.isalnum() or c in [' ', '-'] else "_" for c in settings.pdf_title).replace(' ', '_')[:50]
    output_pdf_path = output_pdf_dir / f"{pdf_filename_base}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    session_data["pdf_path"] = str(output_pdf_path)
    await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="pdf_generating", message="开始生成PDF...", progress=0))
    pdf_log_cb = create_async_callback_for_sync_task(session_id, "pdf_generating", current_loop)
    pdf_progress_cb = create_async_callback_for_sync_task(session_id, "pdf_generating", current_loop, is_progress=True)
    pdf_generator = PdfGenerator(
        ordered_kept_images, str(output_pdf_path), settings.pdf_cols, settings.pdf_rows, settings.pdf_title,
        log_callback=pdf_log_cb, progress_callback=pdf_progress_cb
    )
    pdf_success, pdf_msg_or_path = await current_loop.run_in_executor(None, pdf_generator.generate_pdf)
    if pdf_success:
        pdf_download_url = f"/download_pdf/{session_id}/{output_pdf_path.name}"
        await manager.send_status_update(session_id, TaskStatus(
            session_id=session_id, status="completed", message=f"PDF生成成功: {output_pdf_path.name}",
            result_url=pdf_download_url, progress=100
        ))
    else:
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message=f"PDF生成失败: {pdf_msg_or_path}"))

@app.post("/process_video/{session_id}")
async def process_video_endpoint(session_id: str, settings: ProcessSettings, background_tasks: BackgroundTasks):
    if session_id not in SESSIONS_DATA:
        await manager.send_status_update(session_id, TaskStatus(session_id=session_id, status="error", message="会话未找到。请先上传视频。"))
        raise HTTPException(status_code=404, detail="会话未找到。")
    background_tasks.add_task(run_full_process, session_id, settings)
    return {"message": "处理已启动。请关注WebSocket更新。", "session_id": session_id}

@app.get("/get_processed_image/{session_id}/{image_name}")
async def get_processed_image(session_id: str, image_name: str):
    if session_id not in SESSIONS_DATA: raise HTTPException(status_code=404, detail="会话未找到")
    image_path = Path(SESSIONS_DATA[session_id]["frames_dir"]) / image_name
    if not image_path.exists(): raise HTTPException(status_code=404, detail=f"图片 '{image_name}' 未找到.")
    return FileResponse(str(image_path))

@app.get("/download_pdf/{session_id}/{pdf_name}")
async def download_pdf_file(session_id: str, pdf_name: str):
    if session_id not in SESSIONS_DATA: raise HTTPException(status_code=404, detail="会话未找到")
    pdf_path_str = SESSIONS_DATA[session_id].get("pdf_path")
    if not pdf_path_str: raise HTTPException(status_code=404, detail=f"PDF '{pdf_name}' 尚未生成。")
    pdf_path = Path(pdf_path_str)
    if not pdf_path.exists() or pdf_path.name != pdf_name:
        raise HTTPException(status_code=404, detail=f"PDF '{pdf_name}' 未找到或名称不匹配。")
    return FileResponse(str(pdf_path), media_type='application/pdf', filename=pdf_name)

@app.post("/cleanup_session/{session_id}")
async def cleanup_session(session_id: str):
    # ... (cleanup logic from previous version, ensure manager.disconnect is called)
    session_dir = TEMP_SESSIONS_BASE_DIR / session_id
    output_dir = OUTPUT_BASE_DIR / session_id
    cleaned_temp, cleaned_output = False, False
    if session_dir.exists():
        try: shutil.rmtree(session_dir); cleaned_temp = True
        except Exception as e: print(f"清理临时会话 {session_id} 出错: {e}")
    if output_dir.exists():
        try: shutil.rmtree(output_dir); cleaned_output = True
        except Exception as e: print(f"清理输出会话 {session_id} 出错: {e}")
    if session_id in SESSIONS_DATA: del SESSIONS_DATA[session_id]
    manager.disconnect(session_id)
    if cleaned_temp or cleaned_output or session_id not in SESSIONS_DATA: # If data was removed or dirs cleaned
        return {"message": f"会话 {session_id} 已清理。"}
    raise HTTPException(status_code=404, detail=f"会话 {session_id} 未找到或已清理。")

if __name__ == "__main__":
    import uvicorn
    if OCR_ENGINE is None: print("严重: PaddleOCR 未能初始化。OCR功能将无法工作。")
    else: print("PaddleOCR 引擎已成功初始化。")
    print(f"运行应用 '{APP_NAME}' 版本 '{APP_VERSION}'")
    print(f"临时会话目录: {TEMP_SESSIONS_BASE_DIR.resolve()}")
    print(f"输出目录: {OUTPUT_BASE_DIR.resolve()}")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")