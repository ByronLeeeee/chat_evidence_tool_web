# backend/core_workers.py
import os
import glob
import shutil
import subprocess
import datetime
from typing import List, Tuple, Optional, Callable
from pathlib import Path

from paddleocr import PaddleOCR
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Image as ReportLabImage, Spacer, PageBreak, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors as reportlab_colors
from PIL import Image as PILImage, ImageFile

# Increase PIL max image pixels if dealing with very long screenshots
ImageFile.LOAD_TRUNCATED_IMAGES = True # Allow loading potentially truncated images
# You might need to adjust MAX_IMAGE_PIXELS depending on expected screenshot size and system memory
# Image.MAX_IMAGE_PIXELS = None # Remove limit (use with caution)
# Or set a specific large limit, e.g.:
# Image.MAX_IMAGE_PIXELS = 178956970 # Example large value

# --- Configuration Constants ---
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg") # Allow overriding via environment variable
OVERLAP_CHECK_TAIL_LINES = 2
OVERLAP_CHECK_HEAD_LINES = 2
REFERENCE_FRAME_INDEX = 0

# --- Global OCR Engine Initialization ---
OCR_ENGINE = None
try:
    print("Initializing PaddleOCR engine...")
    # Consider adding more specific model paths if needed, or control via env vars
    OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False, use_gpu=False)
    print("✅ PaddleOCR engine initialized successfully.")
except ImportError:
    print("⚠️ Error: paddleocr or paddlepaddle library not found. OCR features will be disabled.")
except Exception as e:
    print(f"⚠️ Error initializing PaddleOCR: {e}. OCR features may be unavailable.")
    # Optionally, add more robust error handling or fallback mechanism

# --- FFmpeg Synchronous Functions ---
def _run_ffmpeg_sync(cmd_list: list[str], log_callback: Optional[Callable[[str], None]] = None) -> Tuple[int, str, str]:
    """
    Helper function to run an FFmpeg command synchronously, capture its output,
    and handle potential errors.

    Args:
        cmd_list: A list of strings representing the command and its arguments.
        log_callback: An optional function to receive log messages.

    Returns:
        A tuple containing: (return_code, stdout_str, stderr_str).
        Return code -1 indicates FileNotFoundError, -2 indicates other execution error.
    """
    cmd_str = ' '.join(cmd_list) # For logging purposes
    if log_callback: log_callback(f"Executing sync FFmpeg: {cmd_str}")
    try:
        # Use startupinfo on Windows to prevent console window pop-up
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        process = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,            # Decode stdout/stderr as text
            errors='ignore',      # Ignore potential decoding errors
            check=False,          # Do not raise CalledProcessError automatically
            startupinfo=startupinfo # Pass startupinfo for Windows
        )

        # Log stderr first, as it often contains more critical info/errors
        if process.stderr and log_callback:
            # log_callback("--- FFmpeg STDERR ---")
            for line in process.stderr.splitlines():
                if line.strip(): log_callback(f"[FFmpeg ERR]: {line.strip()}")
            # log_callback("--- End FFmpeg STDERR ---")
        # Log stdout if needed
        # if process.stdout and log_callback:
        #     log_callback("--- FFmpeg STDOUT ---")
        #     for line in process.stdout.splitlines():
        #         if line.strip(): log_callback(f"[FFmpeg OUT]: {line.strip()}")
        #     log_callback("--- End FFmpeg STDOUT ---")


        if log_callback: log_callback(f"FFmpeg finished. Return Code: {process.returncode}")
        return process.returncode, process.stdout or "", process.stderr or ""
    except FileNotFoundError:
        err_msg = f"错误: FFmpeg 可执行文件 '{cmd_list[0]}' 未找到。"
        if log_callback: log_callback(err_msg)
        return -1, "", err_msg # Use -1 for FileNotFoundError
    except OSError as e: # Catch potential OS errors during process creation
        err_msg = f"运行 FFmpeg 时发生系统错误: {e}"
        if log_callback: log_callback(err_msg)
        return -2, "", err_msg # Use -2 for other OS errors
    except Exception as e:
        err_msg = f"执行同步 FFmpeg 时发生未知错误: {e}"
        if log_callback: log_callback(err_msg)
        return -3, "", str(e) # Use -3 for other exceptions

def extract_single_frame_ffmpeg_sync(
    video_file_path: str,
    output_frame_path: str,
    frame_index: int = REFERENCE_FRAME_INDEX, # Use constant
    log_callback: Optional[Callable[[str], None]] = None
) -> bool:
    """
    Extracts a single frame synchronously using FFmpeg.

    Args:
        video_file_path: Path to the input video file.
        output_frame_path: Path where the extracted frame PNG should be saved.
        frame_index: The index of the frame to extract (0-based).
        log_callback: Optional logging callback function.

    Returns:
        True if extraction was successful, False otherwise.
    """
    output_frame_path_obj = Path(output_frame_path)
    video_file_path_obj = Path(video_file_path)

    if not video_file_path_obj.is_file():
        if log_callback: log_callback(f"错误: 输入视频文件未找到: {video_file_path}")
        return False

    if log_callback: log_callback(f"请求提取单帧 {frame_index} 从 {video_file_path_obj.name} 到 {output_frame_path_obj.name}")

    output_dir = output_frame_path_obj.parent
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
         if log_callback: log_callback(f"错误: 创建目录失败 {output_dir}: {e}")
         return False

    # Construct FFmpeg command
    cmd = [
        FFMPEG_PATH, "-y",                # Overwrite output without asking
        "-i", str(video_file_path_obj),   # Input file
        "-vf", f"select='eq(n,{frame_index})'", # Select the specific frame
        "-vsync", "vfr",                  # Variable frame rate sync
        "-frames:v", "1",                 # Extract only one video frame
        "-q:v", "2",                      # Set quality (2 is high)
        str(output_frame_path_obj)        # Output file path
    ]

    return_code, _, stderr = _run_ffmpeg_sync(cmd, log_callback)

    frame_exists = output_frame_path_obj.is_file()
    if log_callback: log_callback(f"单帧提取结果 - RC: {return_code}, 文件存在: {frame_exists}")

    if return_code == 0 and frame_exists:
        if log_callback: log_callback("单帧提取成功 (同步)。")
        return True
    else:
        if log_callback: log_callback(f"单帧提取失败 (同步)。")
        # Optionally log stderr specifically on failure if needed
        # if stderr and log_callback: log_callback(f"FFmpeg STDERR: {stderr.strip()}")
        return False

def extract_frames_ffmpeg_sync(
    video_file_path: str,
    output_session_dir: str,
    frame_interval_seconds: float = 1.0,
    log_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str, int]:
    """
    Extracts multiple frames synchronously using FFmpeg at a specified interval.

    Args:
        video_file_path: Path to the input video file.
        output_session_dir: Directory where extracted frame PNGs should be saved.
        frame_interval_seconds: Time interval between extracted frames.
        log_callback: Optional logging callback function.

    Returns:
        A tuple: (success_boolean, status_message, frame_count).
    """
    output_dir = Path(output_session_dir)
    video_file_path_obj = Path(video_file_path)

    if not video_file_path_obj.is_file():
        msg = f"错误: 输入视频文件未找到: {video_file_path}"
        if log_callback: log_callback(msg)
        return False, msg, 0

    if log_callback: log_callback(f"请求从 {video_file_path_obj.name} 提取多帧到 {output_dir}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        msg = f"错误: 创建目录失败 {output_dir}: {e}"
        if log_callback: log_callback(msg)
        return False, msg, 0

    # Clean up old frames first
    deleted_count = 0
    for f in output_dir.glob("frame_*.png"):
        try:
            f.unlink()
            deleted_count += 1
        except OSError as e:
            if log_callback: log_callback(f"警告: 无法删除旧帧 {f.name}: {e}")
    if deleted_count > 0 and log_callback: log_callback(f"已清理 {deleted_count} 个旧帧文件。")

    # Ensure interval is positive, calculate fps
    safe_interval = max(0.01, frame_interval_seconds) # Avoid division by zero or too high fps
    fps = 1 / safe_interval
    vf_option = f"fps={fps}"
    output_pattern = str(output_dir / "frame_%06d.png") # Ensure string path

    # Construct FFmpeg command
    cmd = [
        FFMPEG_PATH, '-y',
        '-i', str(video_file_path_obj),
        '-vf', vf_option,
        '-q:v', '2',          # Output quality
        output_pattern
    ]

    return_code, _, stderr = _run_ffmpeg_sync(cmd, log_callback)

    if return_code == 0:
        # Verify by counting created files
        frame_count = len(list(output_dir.glob("frame_*.png")))
        msg = f"FFmpeg 帧提取完成 (同步)。共提取 {frame_count} 帧。"
        if log_callback: log_callback(msg)
        return True, msg, frame_count
    else:
        msg = f"FFmpeg 帧提取错误 (同步)，返回码: {return_code}"
        if log_callback: log_callback(msg)
        return False, msg, 0


# --- Long Image Slicing Function (Synchronous) ---
def slice_image_sync(
    source_image_path: str,
    slice_height: int,
    overlap: int,
    output_dir: str,
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> List[str]:
    """
    Slices a long image into multiple overlapping segments synchronously using Pillow.

    Args:
        source_image_path: Path to the long input image.
        slice_height: The desired height of each slice in pixels.
        overlap: The height of the overlap between consecutive slices in pixels.
        output_dir: Directory to save the sliced image files.
        log_callback: Optional logging callback function.
        progress_callback: Optional progress callback function (current_slice, total_slices).

    Returns:
        A list of paths to the successfully saved sliced images.
    """
    sliced_image_paths = []
    source_path = Path(source_image_path)
    output_path = Path(output_dir)

    if not source_path.is_file():
        if log_callback: log_callback(f"错误: 源图片未找到 {source_path}")
        return []

    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
         if log_callback: log_callback(f"错误: 创建切片输出目录失败 {output_path}: {e}")
         return []

    try:
        if log_callback: log_callback(f"正在打开图片: {source_path.name}")
        img = PILImage.open(source_path)
        img_width, img_height = img.size
        img_format = img.format or 'PNG' # Get original format or default to PNG

        if log_callback: log_callback(f"图片尺寸: Width={img_width}, Height={img_height}")
        if log_callback: log_callback(f"裁剪参数: Slice Height={slice_height}, Overlap={overlap}")

        if slice_height <= overlap:
             if log_callback: log_callback("错误: 切片高度必须大于重叠高度。")
             return []
        if slice_height <= 0 or overlap < 0:
             if log_callback: log_callback("错误: 切片高度必须为正数，重叠不能为负数。")
             return []

        start_y = 0
        slice_index = 0
        # Effective step determines how much the start_y advances each time
        effective_step = max(1, slice_height - overlap)

        # Estimate total steps for progress reporting
        # Add 1 if there's any remaining part after full steps
        total_steps = (img_height // effective_step) + (1 if img_height % effective_step > 0 else 0)
        if img_height <= slice_height: total_steps = 1 # Only one slice if image is shorter than slice height

        if log_callback: log_callback(f"预计切片数量: {total_steps}")

        while start_y < img_height:
            current_slice_num = slice_index + 1
            end_y = min(start_y + slice_height, img_height)
            box = (0, start_y, img_width, end_y) # left, upper, right, lower

            # Avoid creating tiny slivers at the end if they are much smaller than overlap
            # This prevents very small, mostly redundant final slices. Adjust threshold as needed.
            current_slice_actual_height = end_y - start_y
            if start_y > 0 and current_slice_actual_height < (overlap * 0.5) and current_slice_actual_height < (slice_height * 0.2):
                 if log_callback: log_callback(f"  跳过最后过小的切片 {current_slice_num} (高度: {current_slice_actual_height}px)")
                 # Update progress to 100% as we are skipping the last step
                 if progress_callback: progress_callback(total_steps, total_steps)
                 break # Stop slicing

            if log_callback: log_callback(f"  正在裁剪切片 {current_slice_num}/{total_steps}: Y={start_y} to Y={end_y}")

            try:
                slice_img = img.crop(box)
                # Determine output format and filename
                output_suffix = source_path.suffix.lower() if source_path.suffix else '.png'
                # Ensure save format is supported by Pillow (PNG is safe)
                save_format = 'PNG' if output_suffix not in ['.jpg', '.jpeg', '.png', '.webp'] else img_format
                save_suffix = '.png' if save_format == 'PNG' else output_suffix

                slice_filename = f"slice_{slice_index:04d}{save_suffix}"
                slice_output_path_obj = output_path / slice_filename

                # Save the slice
                slice_img.save(slice_output_path_obj, format=save_format)
                slice_img.close() # Close the slice image object
                sliced_image_paths.append(str(slice_output_path_obj))
                slice_index += 1

                if progress_callback:
                    progress_callback(slice_index, total_steps)

            except Exception as crop_err:
                 if log_callback: log_callback(f"  裁剪或保存切片 {current_slice_num} 出错: {crop_err}")
                 # Decide whether to stop or continue on individual slice error
                 continue # Continue to next slice

            # Advance start_y for the next slice
            start_y += effective_step

        img.close() # Close the main image object
        if log_callback: log_callback(f"裁剪完成，成功生成 {len(sliced_image_paths)} 个切片。")
        # Ensure final progress is 100%
        if progress_callback: progress_callback(total_steps, total_steps)
        return sliced_image_paths

    except FileNotFoundError:
         if log_callback: log_callback(f"错误: 文件未找到 {source_path}")
         return []
    except Exception as open_err:
        if log_callback: log_callback(f"错误: 打开或处理图片失败 {source_image_path}: {open_err}")
        import traceback
        if log_callback: log_callback(traceback.format_exc())
        return []


# --- OCR Filter Class ---
class OcrFilter:
    """Handles OCR processing, text filtering, and overlap detection for video frames."""
    def __init__(self, image_session_folder: str, ocr_engine_instance,
                 exclusion_list: Optional[List[str]] = None,
                 analysis_rect_tuple: Optional[Tuple[int, int, int, int]] = None,
                 log_callback: Optional[Callable[[str], None]] = None,
                 progress_callback: Optional[Callable[[int, int], None]] = None):
        self.image_session_folder = image_session_folder
        self.ocr_engine = ocr_engine_instance
        self.exclusion_list = exclusion_list if exclusion_list else []
        self.analysis_rect_tuple = analysis_rect_tuple
        self.overlap_check_tail_lines = OVERLAP_CHECK_TAIL_LINES # Use constant
        self.overlap_check_head_lines = OVERLAP_CHECK_HEAD_LINES # Use constant
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self._is_running = True

    def _log(self, msg):
        if self.log_callback:
            self.log_callback(msg)
    def _progress(self, current, total):
        if self.progress_callback:
            self.progress_callback(current, total)

    def _preprocess_ocr_lines(self, ocr_text_lines: List[str]) -> List[str]:
        """Filters out lines present in the exclusion list."""
        if not self.exclusion_list: return ocr_text_lines
        processed = []
        # Pre-process exclusion list for faster lookup
        excluded_set = {ex.strip() for ex in self.exclusion_list if ex.strip()}
        for line in ocr_text_lines:
            s_line = line.strip()
            if s_line and s_line not in excluded_set:
                processed.append(line)
        return processed

    def _lines_overlap(self, lines1: List[str], lines2: List[str]) -> bool:
        """Checks if there's significant textual overlap between line lists."""
        set1 = set(l.strip() for l in lines1 if l.strip())
        set2 = set(l.strip() for l in lines2 if l.strip())
        # Consider overlap significant if intersection is not empty
        return not set1.isdisjoint(set2)

    def run_filter(self) -> List[str]:
        """Executes the OCR filtering process on images in the session folder."""
        if not self.ocr_engine: self._log("错误: OCR 引擎不可用。"); return []
        self._log(f"开始视频帧 OCR 筛选: {self.image_session_folder}")
        try:
            session_path = Path(self.image_session_folder)
            image_files = sorted(session_path.glob("frame_*.png"))
        except Exception as e:
            self._log(f"错误: 访问会话目录失败 {self.image_session_folder}: {e}")
            return []

        if not image_files: self._log("未找到视频帧文件。"); return []

        kept_images, last_kept_lines, last_kept_text = [], [], None
        total_files = len(image_files)
        ocr_temp_dir = session_path / "_ocr_temp_inputs" # Use Path object

        try:
            ocr_temp_dir.mkdir(exist_ok=True)
            last_processed_path = None

            for i, img_path in enumerate(image_files):
                if not self._is_running: self._log("OCR筛选被中断。"); break
                self._progress(i + 1, total_files)
                last_processed_path = img_path
                path_for_ocr = img_path # Default to original frame

                try:
                    # --- Apply OCR Analysis Rect if specified ---
                    if self.analysis_rect_tuple:
                        try:
                            pil_img_full = PILImage.open(img_path)
                            x, y, w, h = self.analysis_rect_tuple
                            # Validate rect against image dimensions
                            if w > 0 and h > 0 and x >= 0 and y >= 0 and \
                               x + w <= pil_img_full.width and y + h <= pil_img_full.height:

                                img_cropped = pil_img_full.crop((x, y, x + w, y + h))
                                path_for_ocr = ocr_temp_dir / f"cropped_{img_path.name}"
                                img_cropped.save(path_for_ocr)
                                img_cropped.close() # Close cropped image
                            else:
                                self._log(f"警告: OCR分析区域对 {img_path.name} 无效。")
                            pil_img_full.close() # Close full image
                        except Exception as img_err:
                             self._log(f"处理图片 {img_path.name} 时出错 (裁剪区域): {img_err}")
                             path_for_ocr = img_path # Fallback to original on error

                    # --- Perform OCR ---
                    # Ensure path_for_ocr is string for PaddleOCR
                    ocr_results = self.ocr_engine.ocr(str(path_for_ocr), cls=True)

                    # --- Process OCR Results ---
                    if ocr_results and ocr_results[0]: # Check if results are valid
                        raw_lines = [item[1][0] for item in ocr_results[0] if item and len(item) > 1 and len(item[1]) > 0]
                        current_lines = self._preprocess_ocr_lines(raw_lines)
                        current_text = "\n".join(current_lines)

                        if not current_lines: continue # Skip if no meaningful content

                        should_keep = False
                        if not kept_images: # First valid frame
                            should_keep = True; self._log(f"保留: {img_path.name} (首张有效帧)")
                        else: # Subsequent frames: check overlap
                            tail = last_kept_lines[-self.overlap_check_tail_lines:]
                            head = current_lines[:self.overlap_check_head_lines]
                            has_overlap = self._lines_overlap(tail, head)

                            if not has_overlap: # Keep if no overlap (new content)
                                should_keep = True; self._log(f"保留: {img_path.name} (无重叠)")
                            elif current_text != last_kept_text: # Keep if overlap BUT content changed
                                should_keep = True; self._log(f"保留: {img_path.name} (重叠但内容变化)")
                            # else: overlapping and same content -> skip

                        if should_keep:
                            kept_images.append(str(img_path)) # Store original frame path
                            last_kept_lines = current_lines
                            last_kept_text = current_text

                except Exception as ocr_err:
                    self._log(f"OCR处理 {img_path.name} 失败: {ocr_err}")
                    # Optionally log full traceback for debugging
                    # import traceback; self._log(traceback.format_exc())

            # --- Final Checks ---
            # Ensure the very last processed frame is included if not already kept
            if self._is_running and last_processed_path and str(last_processed_path) not in kept_images:
                 if last_processed_path.exists():
                     self._log(f"强制保留最后处理帧: {last_processed_path.name}")
                     kept_images.append(str(last_processed_path))

        finally:
            # Clean up temporary directory
            if ocr_temp_dir.exists():
                try:
                    shutil.rmtree(ocr_temp_dir)
                except Exception as clean_err:
                    self._log(f"清理OCR临时目录失败: {clean_err}")

        self._log(f"OCR筛选完成。保留 {len(kept_images)} 张帧。")
        self._progress(total_files, total_files) # Ensure 100% progress
        return kept_images

    def stop(self):
        """Signals the worker to stop processing."""
        self._is_running = False
        self._log("OCR 筛选停止信号已接收。")


# --- PDF Generator Class ---
class PdfGenerator:
    """Generates a PDF document from a list of image paths based on specified layout."""
    def __init__(self, image_paths: List[str], output_pdf_path: str,
                 images_per_row: int, images_per_col: int,
                 layout: str = 'grid', # 'grid' (row-major) or 'column' (column-major)
                 page_title: str = "聊天记录",
                 log_callback: Optional[Callable[[str], None]] = None,
                 progress_callback: Optional[Callable[[int, int], None]] = None):
        self.image_paths = image_paths
        self.output_pdf_path = output_pdf_path
        self.images_per_row = max(1, images_per_row) # Columns C
        self.images_per_col = max(1, images_per_col) # Rows R
        self.layout = layout.lower()
        self.page_title = page_title
        self.styles = getSampleStyleSheet()
        self.log_callback = log_callback
        self.progress_callback = progress_callback
        self._is_running = True

    def _log(self, msg):
        if self.log_callback:
            self.log_callback(msg)
    def _progress(self, current, total): 
        if self.progress_callback: 
            self.progress_callback(current, total)

    def _create_rl_image(self, img_path: str, container_width: float, container_height: float) -> Optional[ReportLabImage]:
        """Creates a ReportLab Image object scaled to fit the container."""
        try:
            img_obj = Path(img_path)
            if not img_obj.is_file(): raise FileNotFoundError(f"Image file not found: {img_path}")
            with PILImage.open(img_obj) as pil_img: # Use context manager
                original_w, original_h = pil_img.size
                if original_w <= 0 or original_h <= 0: raise ValueError("Invalid image dimensions")
                # Calculate scaled dimensions
                ratio_w = container_width / original_w
                ratio_h = container_height / original_h
                ratio = min(ratio_w, ratio_h) # Preserve aspect ratio
                img_display_w = original_w * ratio
                img_display_h = original_h * ratio
            # Create ReportLabImage outside the 'with' block
            return ReportLabImage(img_path, width=img_display_w, height=img_display_h)
        except Exception as e:
            self._log(f"创建图片对象失败 {Path(img_path).name}: {e}")
            return None

    def generate_pdf(self) -> Tuple[bool, str]:
        """Generates the PDF document."""
        if not self.image_paths: self._log("无图片可生成PDF。"); return False, "无图片可处理。"
        output_pdf_path_obj = Path(self.output_pdf_path)
        self._log(f"开始生成PDF: {output_pdf_path_obj.name} (布局: {self.layout}, {self.images_per_col}x{self.images_per_row})")

        try:
            pdf_dir = output_pdf_path_obj.parent
            pdf_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            err_msg = f"创建PDF输出目录失败 {pdf_dir}: {e}"
            self._log(err_msg); return False, err_msg

        try:
            doc = SimpleDocTemplate(str(output_pdf_path_obj), pagesize=A4,
                                    topMargin=20*mm, bottomMargin=20*mm,
                                    leftMargin=15*mm, rightMargin=15*mm)
            story = []
            content_width, content_height = doc.width, doc.height
            cell_padding = 1.5 * mm # Slightly more padding
            cell_total_width = content_width / self.images_per_row
            cell_total_height = content_height / self.images_per_col
            # Ensure container dimensions are positive
            img_container_width = max(1*mm, cell_total_width - 2 * cell_padding)
            img_container_height = max(1*mm, cell_total_height - 2 * cell_padding)

            images_per_page = self.images_per_row * self.images_per_col
            total_images = len(self.image_paths)
            num_pages = (total_images + images_per_page - 1) // images_per_page

            img_style = TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, reportlab_colors.lightgrey),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('LEFTPADDING', (0,0), (-1,-1), cell_padding),
                ('RIGHTPADDING', (0,0), (-1,-1), cell_padding),
                ('TOPPADDING', (0,0), (-1,-1), cell_padding),
                ('BOTTOMPADDING', (0,0), (-1,-1), cell_padding)
            ])
            col_widths = [cell_total_width] * self.images_per_row
            row_heights = [cell_total_height] * self.images_per_col

            for page_num in range(num_pages):
                if not self._is_running: self._log("PDF生成中断。"); return False, "用户中断。"
                self._log(f"  正在处理 PDF 第 {page_num + 1}/{num_pages} 页...")

                start_idx = page_num * images_per_page
                end_idx = min(start_idx + images_per_page, total_images)
                page_image_paths = self.image_paths[start_idx:end_idx]
                if not page_image_paths: continue

                # Initialize table data with placeholders
                page_table_data = [[Spacer(1, 1) for _ in range(self.images_per_row)] for _ in range(self.images_per_col)]
                img_idx_on_page = 0

                # Populate based on layout
                if self.layout == 'column': # Column-major (上下优先)
                    for c in range(self.images_per_row):
                        for r in range(self.images_per_col):
                            if img_idx_on_page < len(page_image_paths):
                                img_path = page_image_paths[img_idx_on_page]
                                rl_image = self._create_rl_image(img_path, img_container_width, img_container_height)
                                if rl_image: page_table_data[r][c] = rl_image
                                self._progress(start_idx + img_idx_on_page + 1, total_images)
                                img_idx_on_page += 1
                            else: break # No more images for this page
                        if img_idx_on_page >= len(page_image_paths): break
                else: # Default to 'grid' (Row-major, 左右优先)
                    if self.layout != 'grid': self._log(f"    未知布局 '{self.layout}', 使用 grid。")
                    for r in range(self.images_per_col):
                        for c in range(self.images_per_row):
                             if img_idx_on_page < len(page_image_paths):
                                img_path = page_image_paths[img_idx_on_page]
                                rl_image = self._create_rl_image(img_path, img_container_width, img_container_height)
                                if rl_image: page_table_data[r][c] = rl_image
                                self._progress(start_idx + img_idx_on_page + 1, total_images)
                                img_idx_on_page += 1
                             else: break
                        if img_idx_on_page >= len(page_image_paths): break

                # Create and add table for the page
                table = Table(page_table_data, colWidths=col_widths, rowHeights=row_heights)
                table.setStyle(img_style)
                story.append(table)

                if page_num < num_pages - 1:
                    story.append(PageBreak())

            # Build the PDF document
            self._log("正在构建最终 PDF 文档...")
            doc.build(story)
            self._log(f"✅ PDF 成功生成: {self.output_pdf_path}")
            self._progress(total_images, total_images) # Ensure 100% progress
            return True, str(output_pdf_path_obj)

        except Exception as e:
            err_msg = f"PDF 生成过程中发生错误: {e}"
            self._log(err_msg)
            import traceback
            self._log(traceback.format_exc()) # Log full traceback for debugging
            return False, f"PDF 生成失败: {e}"

    def stop(self):
        """Signals the PDF generation process to stop."""
        self._is_running = False
        self._log("PDF 生成停止信号已接收。")