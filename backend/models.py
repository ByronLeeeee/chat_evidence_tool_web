# backend/models.py
from typing import List, Optional, Tuple, Literal # 添加 Literal
from pydantic import BaseModel, Field # 添加 Field

# 定义允许的 PDF 布局类型
PdfLayoutType = Literal['grid', 'column']

class ProcessSettings(BaseModel):
    """Settings specific to processing video files."""
    frame_interval_seconds: float = Field(default=1.0, gt=0, description="帧提取间隔 (秒), 必须大于 0")
    exclusion_list: List[str] = Field(default=[], description="内容排除白名单列表")
    # OCR rect: x, y, width, height - 坐标相对于原始帧
    ocr_analysis_rect: Optional[Tuple[int, int, int, int]] = Field(default=None, description="可选的OCR分析区域 (x, y, width, height)")
    pdf_rows: int = Field(default=3, ge=1, description="PDF每页行数")
    pdf_cols: int = Field(default=2, ge=1, description="PDF每页列数")
    pdf_title: str = Field(default="聊天记录证据", description="PDF文档标题")
    pdf_layout: PdfLayoutType = Field(default='grid', description="PDF图片排列方式: 'grid' (行优先) 或 'column' (列优先)")
    image_order: Optional[List[str]] = Field(default=None, description="可选的图片文件名排序列表 (用于PDF生成)")

class LongImageProcessSettings(BaseModel):
    """Settings specific to processing long screenshot files."""
    slice_height: int = Field(default=1000, gt=0, description="每个切片的高度 (像素)")
    overlap: int = Field(default=100, ge=0, description="切片之间的重叠高度 (像素)")
    pdf_rows: int = Field(default=3, ge=1, description="PDF每页行数")
    pdf_cols: int = Field(default=1, ge=1, description="PDF每页列数")
    pdf_title: str = Field(default="长截图证据", description="PDF文档标题")
    pdf_layout: PdfLayoutType = Field(default='column', description="PDF图片排列方式: 'grid' (行优先) 或 'column' (列优先)")
    image_order: Optional[List[str]] = Field(default=None, description="可选的切片文件名排序列表 (用于PDF生成)")

    # 可以添加 Pydantic 验证器来确保 slice_height > overlap
    # from pydantic import validator
    # @validator('overlap')
    # def check_overlap_less_than_height(cls, v, values):
    #     if 'slice_height' in values and v >= values['slice_height']:
    #         raise ValueError('Overlap height must be less than slice height')
    #     return v

class TaskStatus(BaseModel):
    """Represents the status update sent via WebSocket."""
    session_id: str
    status: str # e.g., "uploading", "extracting_frames", "ocr_processing", "slicing", "pdf_generating", "completed", "error", "preview_ready"
    message: str
    progress: Optional[int] = Field(default=None, ge=0, le=100, description="任务进度 (0-100)")
    # total_steps: Optional[int] = None # 通常 progress 百分比就够了
    # current_step: Optional[int] = None
    result_url: Optional[str] = Field(default=None, description="最终结果 (如PDF) 的下载链接")
    preview_images: Optional[List[str]] = Field(default=None, description="用于前端预览的图片URL列表")
    # 可以添加一个字段来区分消息对应的任务类型，如果前端需要的话
    # task_type: Optional[Literal['video', 'long_image']] = None