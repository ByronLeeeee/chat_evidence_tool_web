# backend/core_workers.py
import os
import glob
import shutil
import subprocess  # 确保导入
import datetime  # 确保导入
from typing import List, Tuple, Optional, Callable
from pathlib import Path  # 确保导入

from paddleocr import PaddleOCR
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Image as ReportLabImage, Spacer, PageBreak, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors as reportlab_colors
from PIL import Image as PILImage

# --- Config ---
FFMPEG_PATH = "ffmpeg"
OVERLAP_CHECK_TAIL_LINES = 2
OVERLAP_CHECK_HEAD_LINES = 2
REFERENCE_FRAME_INDEX = 0

# Global OCR engine
try:
    print("Initializing PaddleOCR...")
    OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang='ch',
                           show_log=False, use_gpu=False)
    print("PaddleOCR initialized.")
except Exception as e:
    print(f"Error initializing PaddleOCR: {e}")
    OCR_ENGINE = None

# --- FFmpeg Synchronous Functions ---


def _run_ffmpeg_sync(cmd_list: list[str], log_callback: Optional[Callable[[str], None]] = None) -> Tuple[int, str, str]:
    """Helper to run ffmpeg synchronously and capture output."""
    if log_callback:
        log_callback(f"Executing sync FFmpeg: {' '.join(cmd_list)}")
    try:
        process = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            errors='ignore',
            check=False
        )
        if process.stdout and log_callback:
            for line in process.stdout.splitlines():
                if line.strip():
                    log_callback(f"[FFmpeg STDOUT]: {line.strip()}")
        if process.stderr and log_callback:
            for line in process.stderr.splitlines():
                if line.strip():
                    log_callback(f"[FFmpeg STDERR]: {line.strip()}")

        if log_callback:
            log_callback(
                f"FFmpeg process finished with return code: {process.returncode}")
        return process.returncode, process.stdout, process.stderr
    except FileNotFoundError:
        if log_callback:
            log_callback(
                f"Error: FFmpeg executable '{cmd_list[0]}' not found.")
        return -1, "", f"FFmpeg not found at {cmd_list[0]}"
    except Exception as e:
        if log_callback:
            log_callback(f"Error executing sync FFmpeg: {e}")
        return -2, "", str(e)


def extract_single_frame_ffmpeg_sync(
    video_file_path: str,
    output_frame_path: str,
    frame_index: int = 0,
    log_callback: Optional[Callable[[str], None]] = None
) -> bool:
    if log_callback:
        log_callback(
            f"extract_single_frame_ffmpeg_sync called with video: {video_file_path}, output: {output_frame_path}, index: {frame_index}")

    output_dir = os.path.dirname(output_frame_path)
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
            if log_callback:
                log_callback(f"Created directory: {output_dir}")
        except Exception as e:
            if log_callback:
                log_callback(f"Failed to create directory {output_dir}: {e}")
            return False

    cmd = [
        FFMPEG_PATH, "-y", "-i", video_file_path,
        "-vf", f"select='eq(n,{frame_index})'",
        "-vsync", "vfr", "-frames:v", "1", output_frame_path
    ]

    return_code, _, stderr = _run_ffmpeg_sync(cmd, log_callback)

    frame_exists = os.path.exists(output_frame_path)
    if log_callback:
        log_callback(
            f"FFmpeg return code for single frame: {return_code}, Frame exists: {frame_exists} at {output_frame_path}")

    if return_code == 0 and frame_exists:
        if log_callback:
            log_callback("Single frame extraction successful (sync).")
        return True
    else:
        if log_callback:
            log_callback(
                f"Single frame extraction failed (sync). RC: {return_code}, Exists: {frame_exists}")
            if stderr:
                log_callback(
                    f"FFmpeg STDERR during single frame failure: {stderr.strip()}")
        return False


def extract_frames_ffmpeg_sync(
    video_file_path: str,
    output_session_dir: str,
    frame_interval_seconds: float = 1.0,
    log_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str, int]:
    if log_callback:
        log_callback(
            f"extract_frames_ffmpeg_sync called for video: {video_file_path}")
    if not os.path.exists(output_session_dir):
        os.makedirs(output_session_dir, exist_ok=True)
    else:
        for f in glob.glob(os.path.join(output_session_dir, "frame_*.png")):
            try:
                os.remove(f)
            except OSError as e:
                if log_callback:
                    log_callback(f"无法删除旧帧 {f}: {e}")

    vf_option = f"fps=1/{frame_interval_seconds}"
    output_pattern = os.path.join(output_session_dir, "frame_%06d.png")
    cmd = [
        FFMPEG_PATH, '-y', '-i', video_file_path,
        '-vf', vf_option, '-q:v', '2', output_pattern
    ]

    return_code, _, stderr = _run_ffmpeg_sync(cmd, log_callback)

    if return_code == 0:
        frame_count = len(glob.glob(os.path.join(
            output_session_dir, "frame_*.png")))
        msg = f"FFmpeg 帧提取完成 (同步)。共提取 {frame_count} 帧。"
        if log_callback:
            log_callback(msg)
        return True, msg, frame_count
    else:
        msg = f"FFmpeg 错误 (同步)，返回码: {return_code}"
        if log_callback:
            log_callback(msg)
            if stderr:
                log_callback(
                    f"FFmpeg STDERR during multi-frame failure: {stderr.strip()}")
        return False, msg, 0

# --- OCR --- (OcrFilter class from your previous code, ensure log_callback and progress_callback are handled)


class OcrFilter:
    def __init__(self, image_session_folder: str, ocr_engine_instance,
                 exclusion_list: Optional[List[str]] = None,
                 analysis_rect_tuple: Optional[Tuple[int,
                                                     int, int, int]] = None,
                 overlap_check_tail_lines: int = OVERLAP_CHECK_TAIL_LINES,
                 overlap_check_head_lines: int = OVERLAP_CHECK_HEAD_LINES,
                 log_callback: Optional[Callable[[str], None]] = None,
                 progress_callback: Optional[Callable[[int, int], None]] = None):
        self.image_session_folder = image_session_folder
        self.ocr_engine = ocr_engine_instance
        self.exclusion_list = exclusion_list if exclusion_list else []
        self.analysis_rect_tuple = analysis_rect_tuple
        self.overlap_check_tail_lines = max(1, overlap_check_tail_lines)
        self.overlap_check_head_lines = max(1, overlap_check_head_lines)
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
        if not self.exclusion_list:
            return ocr_text_lines
        processed_lines = []
        for line in ocr_text_lines:
            line_stripped = line.strip()
            is_excluded = any(line_stripped == excluded_item.strip()
                              for excluded_item in self.exclusion_list if line_stripped)
            if not is_excluded:
                processed_lines.append(line)
        return processed_lines

    def _lines_overlap(self, lines1_processed: List[str], lines2_processed: List[str]) -> bool:
        set1 = set(line.strip() for line in lines1_processed if line.strip())
        set2 = set(line.strip() for line in lines2_processed if line.strip())
        return not set1.isdisjoint(set2)

    def run_filter(self) -> List[str]:
        if not self.ocr_engine:
            self._log("OCR引擎未初始化。")
            return []
        self._log(f"开始动态重叠OCR与筛选于: {self.image_session_folder}")
        image_files = sorted(glob.glob(os.path.join(
            self.image_session_folder, "frame_*.png")))
        if not image_files:
            self._log("未找到提取的帧文件。")
            return []

        kept_images, last_kept_processed_lines, last_kept_processed_full_text = [], [], None
        total_files = len(image_files)
        ocr_temp_image_dir = Path(
            self.image_session_folder) / "_ocr_temp_inputs"
        if not ocr_temp_image_dir.exists():
            ocr_temp_image_dir.mkdir(parents=True, exist_ok=True)

        last_processed_image_path = None
        for i, img_path_str in enumerate(image_files):
            img_path = Path(img_path_str)
            if not self._is_running:
                self._log("OCR与筛选被中断.")
                break
            self._progress(i + 1, total_files)
            last_processed_image_path = img_path
            path_for_ocr = img_path

            try:
                if self.analysis_rect_tuple:
                    pil_img_full = PILImage.open(img_path)
                    x, y, w, h = self.analysis_rect_tuple
                    if w > 0 and h > 0 and x >= 0 and y >= 0 and \
                       x + w <= pil_img_full.width and y + h <= pil_img_full.height:
                        img_cropped_for_ocr = pil_img_full.crop(
                            (x, y, x + w, y + h))
                        path_for_ocr = ocr_temp_image_dir / \
                            f"cropped_for_ocr_{img_path.name}"
                        img_cropped_for_ocr.save(path_for_ocr)
                    else:
                        self._log(f"警告: OCR分析区域对 {img_path.name} 无效。OCR完整帧。")

                ocr_results = self.ocr_engine.ocr(str(path_for_ocr), cls=True)
                if ocr_results and ocr_results[0]:
                    raw_ocr_text_lines = [line_info[1][0]
                                          for line_info in ocr_results[0]]
                    current_processed_lines = self._preprocess_ocr_lines(
                        raw_ocr_text_lines)
                    current_processed_full_text = "\n".join(
                        current_processed_lines)

                    if not current_processed_lines:
                        continue
                    should_keep = False
                    if not kept_images:  # First valid image
                        if current_processed_lines:
                            should_keep = True
                            self._log(f"保留: {img_path.name} (首张)")
                    else:  # Subsequent images
                        tail_of_last = last_kept_processed_lines[-self.overlap_check_tail_lines:]
                        head_of_current = current_processed_lines[:self.overlap_check_head_lines]
                        if self._lines_overlap(tail_of_last, head_of_current):
                            if current_processed_full_text != last_kept_processed_full_text:
                                should_keep = True
                                self._log(f"保留: {img_path.name} (重叠但内容变)")
                        # else: # No overlap - new content, consider keeping
                        #    should_keep = True; self._log(f"保留: {img_path.name} (无重叠)")

                    if should_keep:
                        kept_images.append(str(img_path))  # Store as string
                        last_kept_processed_lines = current_processed_lines
                        last_kept_processed_full_text = current_processed_full_text
            except Exception as e:
                self._log(f"OCR处理 {img_path.name} 错误: {e}")
                import traceback
                self._log(traceback.format_exc())

        if self._is_running and last_processed_image_path and str(last_processed_image_path) not in kept_images:
            if last_processed_image_path.exists():  # Check if file still exists
                self._log(f"强制保留最后处理的帧: {last_processed_image_path.name}")
                kept_images.append(str(last_processed_image_path))

        if ocr_temp_image_dir.exists():
            shutil.rmtree(ocr_temp_image_dir)
        self._log(f"OCR与筛选完成。保留 {len(kept_images)} 张截图。")
        return kept_images

    def stop(self): self._is_running = False


# --- PDF --- (PdfGenerator class from your previous code, ensure log_callback and progress_callback are handled)
class PdfGenerator:
    def __init__(self, image_paths: List[str], output_pdf_path: str,
                 images_per_row: int, images_per_col: int, page_title: str = "聊天记录",
                 log_callback: Optional[Callable[[str], None]] = None,
                 progress_callback: Optional[Callable[[int, int], None]] = None):
        self.image_paths, self.output_pdf_path = image_paths, output_pdf_path
        self.images_per_row, self.images_per_col = max(
            1, images_per_row), max(1, images_per_col)
        self.page_title, self.styles = page_title, getSampleStyleSheet()
        self.log_callback, self.progress_callback = log_callback, progress_callback
        self._is_running = True

    def _log(self, msg):
        if self.log_callback:
            self.log_callback(msg)

    def _progress(self, current, total):
        if self.progress_callback:
            self.progress_callback(current, total)

    def generate_pdf(self) -> Tuple[bool, str]:
        if not self.image_paths:
            self._log("无图片生成PDF。")
            return False, "无图片。"
        self._log(f"开始生成PDF: {self.output_pdf_path}")
        pdf_dir = Path(self.output_pdf_path).parent
        if not pdf_dir.exists():
            pdf_dir.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(self.output_pdf_path, pagesize=A4, topMargin=20*mm,
                                bottomMargin=20*mm, leftMargin=15*mm, rightMargin=15*mm)
        story, images_per_page = [], self.images_per_row * self.images_per_col
        cell_padding = 1*mm
        cell_total_width, cell_total_height = doc.width / \
            self.images_per_row, doc.height / self.images_per_col
        img_container_width, img_container_height = cell_total_width - \
            2*cell_padding, cell_total_height - 2*cell_padding

        current_page_table_data, current_row_images, images_on_page_count = [], [], 0
        total_images = len(self.image_paths)

        for i, img_path_str in enumerate(self.image_paths):
            img_path = Path(img_path_str)
            if not self._is_running:
                self._log("PDF生成中断。")
                return False, "用户中断。"
            self._progress(i + 1, total_images)
            try:
                pil_img = PILImage.open(img_path)
                original_w, original_h = pil_img.size
                ratio = min(img_container_width / original_w,
                            img_container_height / original_h)
                rl_image = ReportLabImage(
                    img_path, width=original_w*ratio, height=original_h*ratio)
                current_row_images.append(rl_image)

                if len(current_row_images) == self.images_per_row:
                    current_page_table_data.append(current_row_images)
                    current_row_images = []
                images_on_page_count += 1

                if images_on_page_count == images_per_page or (i == total_images - 1):
                    if current_row_images:  # Fill remaining cells in the last row if any
                        current_row_images.extend(
                            [Spacer(1, 1)] * (self.images_per_row - len(current_row_images)))
                        current_page_table_data.append(current_row_images)
                    if current_page_table_data:
                        table = Table(current_page_table_data,
                                      colWidths=[cell_total_width] *
                                      self.images_per_row,
                                      rowHeights=[cell_total_height]*len(current_page_table_data))
                        table.setStyle(TableStyle([
                            ('GRID', (0, 0), (-1, -1), 0.5,
                             reportlab_colors.lightgrey), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('LEFTPADDING',
                                                                    (0, 0), (-1, -1), cell_padding),
                            ('RIGHTPADDING', (0, 0), (-1, -1),
                             cell_padding), ('TOPPADDING', (0, 0), (-1, -1), cell_padding),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), cell_padding)
                        ]))
                        story.append(table)
                        if i < total_images - 1:
                            story.append(PageBreak())
                    current_page_table_data, current_row_images, images_on_page_count = [], [], 0
            except Exception as e:
                self._log(f"处理图片 {img_path.name} 失败: {e}")

        try:
            doc.build(story)
            self._log(f"PDF成功: {self.output_pdf_path}")
            return True, self.output_pdf_path
        except Exception as e:
            self._log(f"PDF生成失败: {e}")
            return False, f"PDF生成失败: {e}"

    def stop(self): self._is_running = False
