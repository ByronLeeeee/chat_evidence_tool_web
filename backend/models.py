from typing import List, Optional, Tuple
from pydantic import BaseModel

class ProcessSettings(BaseModel):
    frame_interval_seconds: float = 1.0
    exclusion_list: List[str] = []
    # OCR rect: x, y, width, height
    ocr_analysis_rect: Optional[Tuple[int, int, int, int]] = None
    pdf_rows: int = 3
    pdf_cols: int = 2
    pdf_title: str = "聊天记录证据"
    image_order: Optional[List[str]] = None # list of image filenames in desired order

class TaskStatus(BaseModel):
    session_id: str
    status: str # e.g., "uploading", "extracting_frames", "ocr_processing", "pdf_generating", "completed", "error"
    message: str
    progress: Optional[int] = None # 0-100
    total_steps: Optional[int] = None
    current_step: Optional[int] = None
    result_url: Optional[str] = None # e.g., URL to download PDF or view preview images
    preview_images: Optional[List[str]] = None # List of URLs/paths for preview images