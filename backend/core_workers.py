# backend/core_workers.py
import os
import glob
import shutil
import subprocess
import datetime
from typing import List, Tuple, Optional, Callable
from pathlib import Path
import difflib

from paddleocr import PaddleOCR
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Image as ReportLabImage, Spacer, PageBreak, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors as reportlab_colors
from PIL import Image as PILImage, ImageFile

# 如果处理非常长的截图，增加 PIL 允许的最大图像像素
ImageFile.LOAD_TRUNCATED_IMAGES = True  # 允许加载可能被截断的图像
# 您可能需要根据预期的截图尺寸和系统内存调整 MAX_IMAGE_PIXELS
# Image.MAX_IMAGE_PIXELS = None # 移除限制（请谨慎使用）
# 或者设置一个特定的较大限制，例如：
# Image.MAX_IMAGE_PIXELS = 178956970 # 示例大数值

# --- 配置常量 ---
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")  # 允许通过环境变量覆盖
OVERLAP_CHECK_TAIL_LINES = 2  # OCR筛选时，用于比较的上一张保留帧的尾部行数
OVERLAP_CHECK_HEAD_LINES = 2  # OCR筛选时，用于比较的当前帧的头部行数
REFERENCE_FRAME_INDEX = 0  # 用于提取参考帧的帧索引

# --- 全局 OCR 引擎初始化 ---
OCR_ENGINE = None
try:
    print("正在初始化 PaddleOCR 引擎...")
    # 如果需要，可以考虑添加更具体的模型路径，或通过环境变量控制
    # lang='ch' 表示中文识别, use_angle_cls=True 开启方向分类
    OCR_ENGINE = PaddleOCR(use_angle_cls=True)
    print("✅ PaddleOCR 引擎初始化成功。")
except ImportError:
    print("⚠️ 错误: 未找到 paddleocr 或 paddlepaddle 库。OCR 功能将被禁用。")
except Exception as e:
    print(f"⚠️ 初始化 PaddleOCR 时出错: {e}。OCR 功能可能不可用。")
    # 可选地，添加更健壮的错误处理或回退机制

# --- FFmpeg 同步功能 ---


def _run_ffmpeg_sync(cmd_list: list[str], log_callback: Optional[Callable[[str], None]] = None) -> Tuple[int, str, str]:
    """
    辅助函数，用于同步运行 FFmpeg 命令，捕获其输出，并处理潜在错误。

    参数:
        cmd_list: 代表命令及其参数的字符串列表。
        log_callback: 用于接收日志消息的可选函数。

    返回:
        一个元组，包含: (返回码, 标准输出字符串, 标准错误字符串)。
        返回码 -1 表示 FileNotFoundError，-2 表示其他执行错误。
    """
    cmd_str = ' '.join(cmd_list)  # 用于日志记录
    if log_callback:
        log_callback(f"正在执行同步 FFmpeg: {cmd_str}")
    try:
        # 在 Windows 上使用 startupinfo 来防止控制台窗口弹出
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        process = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,            # 将 stdout/stderr 解码为文本
            errors='ignore',      # 忽略潜在的解码错误
            check=False,          # 不自动引发 CalledProcessError
            startupinfo=startupinfo  # 为 Windows 传递 startupinfo
        )

        # 首先记录 stderr，因为它通常包含更重要的信息/错误
        if process.stderr and log_callback:
            # log_callback("--- FFmpeg 标准错误输出 ---")
            for line in process.stderr.splitlines():
                if line.strip():
                    log_callback(f"[FFmpeg ERR]: {line.strip()}")
            # log_callback("--- FFmpeg 标准错误输出结束 ---")
        # 如果需要，记录 stdout
        # if process.stdout and log_callback:
        #     log_callback("--- FFmpeg 标准输出 ---")
        #     for line in process.stdout.splitlines():
        #         if line.strip(): log_callback(f"[FFmpeg OUT]: {line.strip()}")
        #     log_callback("--- FFmpeg 标准输出结束 ---")

        if log_callback:
            log_callback(f"FFmpeg 完成。返回码: {process.returncode}")
        return process.returncode, process.stdout or "", process.stderr or ""
    except FileNotFoundError:
        err_msg = f"错误: FFmpeg 可执行文件 '{cmd_list[0]}' 未找到。"
        if log_callback:
            log_callback(err_msg)
        return -1, "", err_msg  # 使用 -1 表示 FileNotFoundError
    except OSError as e:  # 捕获进程创建期间潜在的操作系统错误
        err_msg = f"运行 FFmpeg 时发生系统错误: {e}"
        if log_callback:
            log_callback(err_msg)
        return -2, "", err_msg  # 使用 -2 表示其他操作系统错误
    except Exception as e:
        err_msg = f"执行同步 FFmpeg 时发生未知错误: {e}"
        if log_callback:
            log_callback(err_msg)
        return -3, "", str(e)  # 使用 -3 表示其他异常


def extract_single_frame_ffmpeg_sync(
    video_file_path: str,
    output_frame_path: str,
    frame_index: int = REFERENCE_FRAME_INDEX,  # 使用常量
    log_callback: Optional[Callable[[str], None]] = None
) -> bool:
    """
    使用 FFmpeg 同步提取单个帧。

    参数:
        video_file_path: 输入视频文件的路径。
        output_frame_path: 提取的帧PNG文件应保存的路径。
        frame_index: 要提取的帧的索引（从0开始）。
        log_callback: 可选的日志回调函数。

    返回:
        如果提取成功则为 True，否则为 False。
    """
    output_frame_path_obj = Path(output_frame_path)
    video_file_path_obj = Path(video_file_path)

    if not video_file_path_obj.is_file():
        if log_callback:
            log_callback(f"错误: 输入视频文件未找到: {video_file_path}")
        return False

    if log_callback:
        log_callback(
            f"请求从 {video_file_path_obj.name} 提取第 {frame_index} 帧到 {output_frame_path_obj.name}")

    output_dir = output_frame_path_obj.parent
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        if log_callback:
            log_callback(f"错误: 创建目录 {output_dir} 失败: {e}")
        return False

    # 构建 FFmpeg 命令
    cmd = [
        FFMPEG_PATH, "-y",                # 不经询问覆盖输出
        "-i", str(video_file_path_obj),   # 输入文件
        "-vf", f"select='eq(n,{frame_index})'",  # 选择特定帧
        "-vsync", "vfr",                  # 可变帧率同步
        "-frames:v", "1",                 # 仅提取一帧视频
        "-q:v", "2",                      # 设置质量（2为高）
        str(output_frame_path_obj)        # 输出文件路径
    ]

    return_code, _, stderr = _run_ffmpeg_sync(cmd, log_callback)

    frame_exists = output_frame_path_obj.is_file()
    if log_callback:
        log_callback(f"单帧提取结果 - 返回码: {return_code}, 文件存在: {frame_exists}")

    if return_code == 0 and frame_exists:
        if log_callback:
            log_callback("单帧提取成功 (同步)。")
        return True
    else:
        if log_callback:
            log_callback(f"单帧提取失败 (同步)。")
        # 可选地，在失败时专门记录 stderr
        # if stderr and log_callback: log_callback(f"FFmpeg 标准错误输出: {stderr.strip()}")
        return False


def extract_frames_ffmpeg_sync(
    video_file_path: str,
    output_session_dir: str,
    frame_interval_seconds: float = 1.0,
    log_callback: Optional[Callable[[str], None]] = None
) -> Tuple[bool, str, int]:
    """
    使用 FFmpeg 按指定间隔同步提取多个帧。

    参数:
        video_file_path: 输入视频文件的路径。
        output_session_dir: 提取的帧PNG文件应保存的目录。
        frame_interval_seconds: 提取帧之间的时间间隔（秒）。
        log_callback: 可选的日志回调函数。

    返回:
        一个元组: (成功布尔值, 状态消息, 帧数量)。
    """
    output_dir = Path(output_session_dir)
    video_file_path_obj = Path(video_file_path)

    if not video_file_path_obj.is_file():
        msg = f"错误: 输入视频文件未找到: {video_file_path}"
        if log_callback:
            log_callback(msg)
        return False, msg, 0

    if log_callback:
        log_callback(f"请求从 {video_file_path_obj.name} 提取多帧到 {output_dir}")

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        msg = f"错误: 创建目录 {output_dir} 失败: {e}"
        if log_callback:
            log_callback(msg)
        return False, msg, 0

    # 首先清理旧的帧文件
    deleted_count = 0
    for f in output_dir.glob("frame_*.png"):
        try:
            f.unlink()
            deleted_count += 1
        except OSError as e:
            if log_callback:
                log_callback(f"警告: 无法删除旧帧 {f.name}: {e}")
    if deleted_count > 0 and log_callback:
        log_callback(f"已清理 {deleted_count} 个旧帧文件。")

    # 确保间隔为正数，计算 fps
    safe_interval = max(0.01, frame_interval_seconds)  # 避免除以零或 fps 过高
    fps = 1 / safe_interval
    vf_option = f"fps={fps}"
    output_pattern = str(output_dir / "frame_%06d.png")  # 确保是字符串路径

    # 构建 FFmpeg 命令
    cmd = [
        FFMPEG_PATH, '-y',
        '-i', str(video_file_path_obj),
        '-vf', vf_option,
        '-q:v', '2',          # 输出质量
        output_pattern
    ]

    return_code, _, stderr = _run_ffmpeg_sync(cmd, log_callback)

    if return_code == 0:
        # 通过计算创建的文件数量来验证
        frame_count = len(list(output_dir.glob("frame_*.png")))
        msg = f"FFmpeg 帧提取完成 (同步)。共提取 {frame_count} 帧。"
        if log_callback:
            log_callback(msg)
        return True, msg, frame_count
    else:
        msg = f"FFmpeg 帧提取错误 (同步)，返回码: {return_code}"
        if log_callback:
            log_callback(msg)
        # if stderr and log_callback: log_callback(f"FFmpeg 标准错误输出: {stderr.strip()}")
        return False, msg, 0


# --- 长图切片功能 (同步) ---
def slice_image_sync(
    source_image_path: str,
    slice_height: int,
    overlap: int,
    output_dir: str,
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> List[str]:
    """
    使用 Pillow 同步将长图切成多个重叠的片段。

    参数:
        source_image_path: 输入长图的路径。
        slice_height: 每个切片的期望高度（像素）。
        overlap: 连续切片之间的重叠高度（像素）。
        output_dir: 保存切片图像文件的目录。
        log_callback: 可选的日志回调函数。
        progress_callback: 可选的进度回调函数 (当前切片数, 总切片数)。

    返回:
        成功保存的切片图像路径列表。
    """
    sliced_image_paths = []
    source_path = Path(source_image_path)
    output_path = Path(output_dir)

    if not source_path.is_file():
        if log_callback:
            log_callback(f"错误: 源图片未找到 {source_path}")
        return []

    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        if log_callback:
            log_callback(f"错误: 创建切片输出目录 {output_path} 失败: {e}")
        return []

    try:
        if log_callback:
            log_callback(f"正在打开图片: {source_path.name}")
        img = PILImage.open(source_path)
        img_width, img_height = img.size
        img_format = img.format or 'PNG'  # 获取原始格式，或默认为 PNG

        if log_callback:
            log_callback(f"图片尺寸: 宽度={img_width}, 高度={img_height}")
        if log_callback:
            log_callback(f"裁剪参数: 切片高度={slice_height}, 重叠={overlap}")

        if slice_height <= overlap:
            if log_callback:
                log_callback("错误: 切片高度必须大于重叠高度。")
            return []
        if slice_height <= 0 or overlap < 0:
            if log_callback:
                log_callback("错误: 切片高度必须为正数，重叠不能为负数。")
            return []

        start_y = 0
        slice_index = 0
        # 有效步长决定了每次 start_y 前进多少
        effective_step = max(1, slice_height - overlap)

        # 估算总步数以报告进度
        # 如果完整步数后还有剩余部分，则加 1
        total_steps = (img_height // effective_step) + \
            (1 if img_height % effective_step > 0 else 0)
        if img_height <= slice_height:
            total_steps = 1  # 如果图像比切片高度短，则只有一个切片

        if log_callback:
            log_callback(f"预计切片数量: {total_steps}")

        while start_y < img_height:
            current_slice_num = slice_index + 1
            end_y = min(start_y + slice_height, img_height)
            box = (0, start_y, img_width, end_y)  # 左, 上, 右, 下

            # 避免在末尾创建过小的切片，如果它们远小于重叠区域
            # 这可以防止非常小且大多冗余的最终切片。根据需要调整阈值。
            current_slice_actual_height = end_y - start_y
            if start_y > 0 and current_slice_actual_height < (overlap * 0.5) and current_slice_actual_height < (slice_height * 0.2):
                if log_callback:
                    log_callback(
                        f"  跳过最后过小的切片 {current_slice_num} (高度: {current_slice_actual_height}px)")
                # 由于我们跳过了最后一步，将进度更新为 100%
                if progress_callback:
                    progress_callback(total_steps, total_steps)
                break  # 停止切片

            if log_callback:
                log_callback(
                    f"  正在裁剪切片 {current_slice_num}/{total_steps}: Y={start_y} 到 Y={end_y}")

            try:
                slice_img = img.crop(box)
                # 确定输出格式和文件名
                output_suffix = source_path.suffix.lower() if source_path.suffix else '.png'
                # 确保保存格式受 Pillow 支持（PNG 是安全的）
                save_format = 'PNG' if output_suffix not in [
                    '.jpg', '.jpeg', '.png', '.webp'] else img_format
                save_suffix = '.png' if save_format == 'PNG' else output_suffix

                slice_filename = f"slice_{slice_index:04d}{save_suffix}"
                slice_output_path_obj = output_path / slice_filename

                # 保存切片
                slice_img.save(slice_output_path_obj, format=save_format)
                slice_img.close()  # 关闭切片图像对象
                sliced_image_paths.append(str(slice_output_path_obj))
                slice_index += 1

                if progress_callback:
                    progress_callback(slice_index, total_steps)

            except Exception as crop_err:
                if log_callback:
                    log_callback(
                        f"  裁剪或保存切片 {current_slice_num} 出错: {crop_err}")
                # 决定在单个切片错误时是停止还是继续
                continue  # 继续到下一个切片

            # 为下一个切片前进 start_y
            start_y += effective_step

        img.close()  # 关闭主图像对象
        if log_callback:
            log_callback(f"裁剪完成，成功生成 {len(sliced_image_paths)} 个切片。")
        # 确保最终进度为 100%
        if progress_callback:
            progress_callback(total_steps, total_steps)
        return sliced_image_paths

    except FileNotFoundError:
        if log_callback:
            log_callback(f"错误: 文件未找到 {source_path}")
        return []
    except Exception as open_err:
        if log_callback:
            log_callback(f"错误: 打开或处理图片 {source_image_path} 失败: {open_err}")
        import traceback  # 仅在此处导入，因为不常用
        if log_callback:
            log_callback(traceback.format_exc())
        return []


# --- OCR 筛选类 ---
class OcrFilter:
    """处理视频帧的OCR、文本过滤和重叠检测。"""

    def __init__(self, image_session_folder: str, ocr_engine_instance,
                 exclusion_list: Optional[List[str]] = None,
                 analysis_rect_tuple: Optional[Tuple[int,
                                                     int, int, int]] = None,
                 log_callback: Optional[Callable[[str], None]] = None,
                 progress_callback: Optional[Callable[[int, int], None]] = None, similarity_threshold: float = 0.3):
        self.image_session_folder = image_session_folder  # 图片会话文件夹
        self.ocr_engine = ocr_engine_instance  # OCR 引擎实例
        self.exclusion_list = exclusion_list if exclusion_list else []  # 内容排除白名单
        # 可选的OCR分析区域 (x, y, width, height)
        self.analysis_rect_tuple = analysis_rect_tuple
        self.overlap_check_tail_lines = OVERLAP_CHECK_TAIL_LINES  # 例如，从上一张保留帧的底部取2行
        self.overlap_check_head_lines = OVERLAP_CHECK_HEAD_LINES  # 例如，从当前帧的顶部取2行
        self.log_callback = log_callback  # 日志回调
        self.progress_callback = progress_callback  # 进度回调
        self._is_running = True  # 控制运行状态的标志
        self.similarity_threshold = similarity_threshold  # 存储相似度阈值 - 降低为0.3以放宽匹配条件

    def _log(self, msg: str):
        """记录日志消息。"""
        if self.log_callback:
            self.log_callback(msg)

    def _progress(self, current: int, total: int):
        """报告进度。"""
        if self.progress_callback:
            self.progress_callback(current, total)

    def _preprocess_ocr_lines(self, ocr_text_lines: List[str]) -> List[str]:
        """过滤掉排除列表中的行和空行，并去除首尾空格。"""
        processed = []
        # 如果存在排除列表，预处理以便快速查找
        excluded_set = {ex.strip() for ex in self.exclusion_list if ex.strip(
        )} if self.exclusion_list else set()
        for line in ocr_text_lines:
            s_line = line.strip()  # 去除首尾空格
            if s_line and s_line not in excluded_set:  # 如果行不为空且不在排除列表中
                processed.append(s_line)  # 存储处理后的行
        return processed

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """使用 difflib 计算两段文本的相似度。"""
        if not text1 and not text2:  # 两者都为空
            return 1.0
        if not text1 or not text2:  # 其中一个为空
            return 0.0
        return difflib.SequenceMatcher(None, text1, text2).ratio()

    def _lines_overlap_fuzzy(self, lines1_tail: List[str], lines2_head: List[str]) -> bool:
        """
        使用模糊匹配检查 lines1 的尾部和 lines2 的头部之间是否存在文本重叠。
        我们将比较整个尾部文本块和整个头部文本块的相似度。
        """
        if not lines1_tail or not lines2_head:
            return False

        # 将行列表连接成单个字符串进行比较
        tail_text_block = "\n".join(lines1_tail)
        head_text_block = "\n".join(lines2_head)

        similarity = self._calculate_text_similarity(
            tail_text_block, head_text_block)
        self._log(
            f"    模糊重叠检查: 尾部块='{tail_text_block[:50]}...', 头部块='{head_text_block[:50]}...', 相似度={similarity:.2f}")

        # 如果相似度超过阈值，则认为存在重叠
        return similarity >= self.similarity_threshold

    def run_filter(self) -> List[str]:
        """执行对会话文件夹中图像的OCR过滤过程。"""
        if not self.ocr_engine:
            self._log("错误: OCR 引擎不可用。")
            return []
        self._log(f"开始视频帧 OCR 筛选: {self.image_session_folder}")

        session_path = Path(self.image_session_folder)
        image_files = sorted(session_path.glob("frame_*.png"))  # 获取并排序所有帧图像
        if not image_files:
            self._log("未找到视频帧文件。")
            return []

        kept_images = []  # 存储被保留的图像路径
        # 存储上一张被保留图像的实际处理后的行列表，用于提取尾部
        last_kept_processed_lines_list: List[str] = []
        last_kept_full_text_block = ""  # 上一张保留帧的完整文本

        total_files = len(image_files)
        ocr_temp_dir = session_path / "_ocr_temp_inputs"  # OCR临时输入目录
        ocr_temp_dir.mkdir(exist_ok=True)  # 创建临时目录
        last_processed_path = None  # 跟踪最后处理的帧

        try:
            for i, img_path in enumerate(image_files):
                is_last_frame = (i == len(image_files) - 1)  # 判断是否为最后一帧
                
                if not self._is_running:
                    self._log("OCR筛选被中断。")
                    break
                    
                self._progress(i + 1, total_files)  # 报告进度
                last_processed_path = img_path  # 更新最后处理的帧
                path_for_ocr = img_path  # 默认为原始帧路径
                should_keep = False  # 默认不保留

                try:
                    # --- 如果指定了OCR分析区域，则应用 ---
                    if self.analysis_rect_tuple:
                        try:
                            pil_img_full = PILImage.open(img_path)
                            x, y, w, h = self.analysis_rect_tuple
                            # 验证区域是否有效
                            if w > 0 and h > 0 and x >= 0 and y >= 0 and \
                               x + w <= pil_img_full.width and y + h <= pil_img_full.height:

                                img_cropped = pil_img_full.crop(
                                    (x, y, x + w, y + h))  # 裁剪图像
                                path_for_ocr = ocr_temp_dir / \
                                    f"cropped_{img_path.name}"  # 更新OCR路径为裁剪后的图像
                                img_cropped.save(path_for_ocr)
                                img_cropped.close()  # 关闭裁剪后的图像对象
                            else:
                                self._log(
                                    f"警告: OCR分析区域对 {img_path.name} 无效。将使用完整帧。")
                            pil_img_full.close()  # 关闭完整图像对象
                        except Exception as img_err:
                            self._log(
                                f"处理图片 {img_path.name} 时出错 (裁剪区域): {img_err}")
                            path_for_ocr = img_path  # 出错则回退到使用原始帧

                    # --- 执行 OCR ---
                    ocr_results = self.ocr_engine.ocr(
                        str(path_for_ocr), cls=True)

                    current_raw_lines = []  # 当前帧的原始OCR行
                    if ocr_results and ocr_results[0]:  # 检查结果是否有效
                        current_raw_lines = [item[1][0] for item in ocr_results[0] if item and len(
                            item) > 1 and len(item[1]) > 0]

                    # --- 预处理OCR结果 ---
                    current_processed_lines = self._preprocess_ocr_lines(
                        current_raw_lines)
                    current_full_text_block = "\n".join(current_processed_lines)
                    
                    if not current_processed_lines:  # 如果处理后没有有效内容
                        if is_last_frame:  # 如果是最后一帧但没有内容，仍然保留
                            should_keep = True
                            self._log(f"保留: {img_path.name} (最后一帧，即使没有有效内容)")
                        else:
                            self._log(f"跳过: {img_path.name} (预处理后无有效内容)")
                            continue  # 跳过此帧
                    
                    # --- 判断是否保留当前帧 ---
                    if not kept_images:  # 如果是第一张有效帧
                        should_keep = True
                        self._log(f"保留: {img_path.name} (首张有效帧)")
                    else:
                        # 只检查重叠条件，不再检查"足够的新内容"
                        tail_of_last_kept = last_kept_processed_lines_list[-self.overlap_check_tail_lines:] if last_kept_processed_lines_list else []
                        head_of_current = current_processed_lines[:self.overlap_check_head_lines] if current_processed_lines else []
                        
                        # 使用模糊匹配检查重叠
                        has_overlap_fuzzy = self._lines_overlap_fuzzy(tail_of_last_kept, head_of_current)
                        
                        if has_overlap_fuzzy or is_last_frame:  # 有重叠或者是最后一帧
                            should_keep = True
                            if has_overlap_fuzzy:
                                self._log(f"保留: {img_path.name} (模糊重叠通过)")
                            if is_last_frame:
                                self._log(f"保留: {img_path.name} (最后一帧)")
                        else:
                            self._log(f"跳过: {img_path.name} (模糊重叠未通过)")
                    
                    if should_keep:
                        kept_images.append(str(img_path))
                        last_kept_processed_lines_list = current_processed_lines
                        last_kept_full_text_block = current_full_text_block  # 更新为当前帧的完整文本块

                except Exception as ocr_err:
                    self._log(f"OCR处理 {img_path.name} 失败: {ocr_err}")
                    # 如果是最后一帧且处理失败，仍然保留
                    if is_last_frame:
                        kept_images.append(str(img_path))
                        self._log(f"尽管OCR失败，仍保留最后一帧: {img_path.name}")

        finally:
            if ocr_temp_dir.exists():
                try: shutil.rmtree(ocr_temp_dir)
                except Exception as clean_err: self._log(f"清理OCR临时目录失败: {clean_err}")

        self._log(f"OCR筛选完成。保留 {len(kept_images)} 张帧。")
        self._progress(total_files, total_files)
        return kept_images

    def stop(self):
        """向工作线程发送停止处理的信号。"""
        self._is_running = False
        self._log("OCR 筛选停止信号已接收。")


# --- PDF 生成器类 ---
class PdfGenerator:
    """根据指定的布局从图像路径列表生成PDF文档。"""

    def __init__(self, image_paths: List[str], output_pdf_path: str,
                 images_per_row: int, images_per_col: int,
                 layout: str = 'grid',  # 'grid' (行优先) 或 'column' (列优先)
                 page_title: str = "聊天记录",  # PDF 页面标题（此参数目前未在生成内容中使用，但可保留供未来扩展）
                 log_callback: Optional[Callable[[str], None]] = None,
                 progress_callback: Optional[Callable[[int, int], None]] = None):
        self.image_paths = image_paths  # 图片路径列表
        self.output_pdf_path = output_pdf_path  # 输出PDF的路径
        self.images_per_row = max(1, images_per_row)  # 每页列数 (C)
        self.images_per_col = max(1, images_per_col)  # 每页行数 (R)
        self.layout = layout.lower()  # 布局方式：'grid' 或 'column'
        self.page_title = page_title  # PDF文档标题 (此参数当前未使用在文档内容中，但可用于文件名或元数据)
        self.styles = getSampleStyleSheet()  # 获取ReportLab样式表
        self.log_callback = log_callback  # 日志回调
        self.progress_callback = progress_callback  # 进度回调
        self._is_running = True  # 控制运行状态的标志

    def _log(self, msg: str):
        """记录日志消息。"""
        if self.log_callback:
            self.log_callback(msg)

    def _progress(self, current: int, total: int):
        """报告进度。"""
        if self.progress_callback:
            self.progress_callback(current, total)

    def _create_rl_image(self, img_path: str, container_width: float, container_height: float) -> Optional[ReportLabImage]:
        """创建按比例缩放以适应容器的 ReportLab Image 对象。"""
        try:
            img_obj = Path(img_path)
            if not img_obj.is_file():
                raise FileNotFoundError(f"图片文件未找到: {img_path}")

            # 使用上下文管理器打开图像，确保其被关闭
            with PILImage.open(img_obj) as pil_img:
                original_w, original_h = pil_img.size
                if original_w <= 0 or original_h <= 0:
                    raise ValueError("无效的图片尺寸")

                # 计算缩放尺寸
                ratio_w = container_width / original_w
                ratio_h = container_height / original_h
                ratio = min(ratio_w, ratio_h)  # 保持宽高比
                img_display_w = original_w * ratio
                img_display_h = original_h * ratio
                self._log(
                    f"  图像: {Path(img_path).name}, 原始尺寸: {original_w}x{original_h}")
                self._log(
                    f"  容器尺寸: {container_width:.2f}x{container_height:.2f}")
                self._log(
                    f"  缩放比例: {ratio:.2f}, 显示尺寸: {img_display_w:.2f}x{img_display_h:.2f}")

            # 在 'with' 块外部创建 ReportLabImage
            return ReportLabImage(img_path, width=img_display_w, height=img_display_h)
        except Exception as e:
            self._log(f"创建图片对象 {Path(img_path).name} 失败: {e}")
            return None

    def generate_pdf(self) -> Tuple[bool, str]:
        """生成PDF文档。"""
        if not self.image_paths:
            self._log("无图片可生成PDF。")
            return False, "无图片可处理。"

        output_pdf_path_obj = Path(self.output_pdf_path)
        self._log(
            f"开始生成PDF: {output_pdf_path_obj.name} (布局: {self.layout}, {self.images_per_col}行x{self.images_per_row}列)")

        try:
            pdf_dir = output_pdf_path_obj.parent
            pdf_dir.mkdir(parents=True, exist_ok=True)  # 创建输出目录
        except OSError as e:
            err_msg = f"创建PDF输出目录 {pdf_dir} 失败: {e}"
            self._log(err_msg)
            return False, err_msg

        try:
            # 设置文档模板
            doc = SimpleDocTemplate(str(output_pdf_path_obj), pagesize=A4,
                                    topMargin=10*mm, bottomMargin=10*mm,
                                    leftMargin=10*mm, rightMargin=10*mm)
            story = []  # PDF内容元素列表

            # 计算内容区域和单元格尺寸
            content_width, content_height = doc.width, doc.height  # 可用内容区域
            self._log(f"  文档可用内容区 (doc.width, doc.height): {content_width:.2f}pt x {content_height:.2f}pt")
            
            # 增加安全系数，确保全部内容能够容纳
            safety_factor = 0.98  # 整体减少2%的空间来避免边界问题
            adjusted_content_height = content_height * safety_factor
            
            # 单元格内边距，适当减小以腾出更多空间
            cell_padding = 1.0 * mm
            
            # 计算单元格高度和宽度，确保余量充足
            cell_total_height = adjusted_content_height / self.images_per_col
            cell_total_width = content_width / self.images_per_row
            
            self._log(f"  每页行数: {self.images_per_col}, 每页列数: {self.images_per_row}")
            self._log(f"  调整后内容高度: {adjusted_content_height:.2f}pt")
            self._log(f"  单元格总高度: {cell_total_height:.2f}pt")
            
            if cell_total_height < 10*mm:
                self._log(f"警告: 计算出的单元格高度 {cell_total_height:.2f}pt 过小，可能导致问题。检查页边距和行列数设置。")
            
            # 确保容器尺寸为正
            img_container_width = max(1*mm, cell_total_width - 2 * cell_padding)
            img_container_height = max(1*mm, cell_total_height - 2 * cell_padding)
            self._log(f"  单元格内图片容器尺寸: {img_container_width:.2f}pt x {img_container_height:.2f}pt")
            
            images_per_page = self.images_per_row * self.images_per_col  # 每页图片数量
            total_images = len(self.image_paths)  # 总图片数量
            num_pages = (total_images + images_per_page - 1) // images_per_page  # 计算总页数

            # 定义表格样式 - 减小网格线宽度，减少占用空间
            img_style = TableStyle([
                ('GRID', (0,0), (-1,-1), 0.25, reportlab_colors.lightgrey),  # 减小网格线宽度
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('LEFTPADDING', (0,0), (-1,-1), cell_padding),
                ('RIGHTPADDING', (0,0), (-1,-1), cell_padding),
                ('TOPPADDING', (0,0), (-1,-1), cell_padding),
                ('BOTTOMPADDING', (0,0), (-1,-1), cell_padding)
            ])
            
            # 明确设置每列宽度和每行高度
            col_widths = [cell_total_width] * self.images_per_row
            
            # 关键修改：固定行高，不依赖动态计算
            # 为每一行预先分配确定的高度，避免reportlab的自动计算导致问题
            row_heights = [cell_total_height] * self.images_per_col
            
            # 遍历每一页
            for page_num in range(num_pages):
                if not self._is_running:
                    self._log("PDF生成中断。")
                    return False, "用户中断。"
                self._log(f"  正在处理 PDF 第 {page_num + 1}/{num_pages} 页...")

                start_idx = page_num * images_per_page
                end_idx = min(start_idx + images_per_page, total_images)
                # 当前页的图片路径
                page_image_paths = self.image_paths[start_idx:end_idx]
                if not page_image_paths:
                    continue  # 如果没有图片则跳过

                # 用占位符初始化表格数据
                page_table_data = [[Spacer(1, 1) for _ in range(self.images_per_row)] 
                                  for _ in range(self.images_per_col)]
                img_idx_on_page = 0  # 当前页上的图片索引

                # 根据布局填充表格
                if self.layout == 'column':  # 列优先 (上下优先)
                    for c in range(self.images_per_row):  # 遍历列
                        for r in range(self.images_per_col):  # 遍历行
                            if img_idx_on_page < len(page_image_paths):
                                img_path = page_image_paths[img_idx_on_page]
                                # 修改这里确保图像正确缩放
                                rl_image = self._create_rl_image(
                                    img_path, img_container_width, img_container_height)
                                if rl_image:
                                    page_table_data[r][c] = rl_image
                                self._progress(
                                    start_idx + img_idx_on_page + 1, total_images)
                                img_idx_on_page += 1
                            else:
                                break  # 当前页的图片已处理完毕
                        if img_idx_on_page >= len(page_image_paths):
                            break
                else:  # 默认为 'grid' (行优先, 左右优先)
                    if self.layout != 'grid':
                        self._log(f"    未知布局 '{self.layout}', 使用 grid 布局。")
                    for r in range(self.images_per_col):  # 遍历行
                        for c in range(self.images_per_row):  # 遍历列
                            if img_idx_on_page < len(page_image_paths):
                                img_path = page_image_paths[img_idx_on_page]
                                rl_image = self._create_rl_image(
                                    img_path, img_container_width, img_container_height)
                                if rl_image:
                                    page_table_data[r][c] = rl_image
                                self._progress(
                                    start_idx + img_idx_on_page + 1, total_images)
                                img_idx_on_page += 1
                            else:
                                break  # 当前页的图片已处理完毕
                        if img_idx_on_page >= len(page_image_paths):
                            break

                # 创建表格时明确指定行高和列宽
                table = Table(page_table_data, 
                              colWidths=col_widths,
                              rowHeights=row_heights)
                table.setStyle(img_style)
                story.append(table)

                if page_num < num_pages - 1:  # 如果不是最后一页，则添加分页符
                    story.append(PageBreak())

            # 构建最终的PDF文档
            self._log("正在构建最终 PDF 文档...")
            doc.build(story)
            self._log(f"✅ PDF 成功生成: {self.output_pdf_path}")
            self._progress(total_images, total_images)  # 确保进度为100%
            self._log(f"  文档可用内容区: {content_width:.2f}x{content_height:.2f}")
            self._log(f"  调整后内容区: {adjusted_content_height:.2f}pt")
            self._log(f"  单元格总尺寸: {cell_total_width:.2f}x{cell_total_height:.2f}")
            self._log(f"  单元格内图片容器尺寸: {img_container_width:.2f}x{img_container_height:.2f}")
            return True, str(output_pdf_path_obj)

        except Exception as e:
            err_msg = f"PDF 生成过程中发生错误: {e}"
            self._log(err_msg)
            import traceback  # 仅在此处导入，因为不常用
            self._log(traceback.format_exc())  # 记录完整的堆栈跟踪信息以便调试
            return False, f"PDF 生成失败: {e}"

    def stop(self):
        """向PDF生成过程发送停止信号。"""
        self._is_running = False
        self._log("PDF 生成停止信号已接收。")
