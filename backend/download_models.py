# download_models.py
import os
import sys
from paddleocr import PaddleOCR

# 从环境变量获取模型主目录，提供默认值
paddleocr_home = os.getenv('PADDLEOCR_HOME', '/app/paddleocr_models')

print(f"--- Starting PaddleOCR Model Pre-download ---")
print(f"Target directory (PADDLEOCR_HOME): {paddleocr_home}")

# 确保目标目录存在
try:
    os.makedirs(paddleocr_home, exist_ok=True)
    print(f"Directory {paddleocr_home} ensured.")
except Exception as e:
    print(f"Error creating directory {paddleocr_home}: {e}")
    sys.exit(1) # 创建目录失败则退出

# 定义模型版本和对应的子目录名称 (根据你使用的PaddleOCR版本可能需要调整)
# 这些通常是 PaddleOCR 内部下载时使用的默认子目录名结构
# 你可以通过运行一次 PaddleOCR().ocr('dummy.png') 来观察它下载到了哪些子目录
det_model_sub_dir = 'whl/det/ch/ch_PP-OCRv5_det_infer' # 示例，可能需要根据版本调整
rec_model_sub_dir = 'whl/rec/ch/ch_PP-OCRv5_rec_infer' # 示例
cls_model_sub_dir = 'whl/cls/ch_ppocr_mobile_v2.0_cls_infer' # 示例

print(f"Attempting to download models using PaddleOCR initialization...")
print(f"  Det model expected relative path: {det_model_sub_dir}")
print(f"  Rec model expected relative path: {rec_model_sub_dir}")
print(f"  Cls model expected relative path: {cls_model_sub_dir}")

try:
    # 通过指定完整的模型目录路径来触发下载（如果模型不存在）
    # 注意：PaddleOCR 可能不会严格按照这里指定的子目录名来存储，
    # 它的内部逻辑可能会覆盖。这里指定路径主要是为了触发下载到 PADDLEOCR_HOME 下。
    # 更可靠的方式是让 PaddleOCR 在 PADDLEOCR_HOME 下自动创建其标准子目录。
    # 因此，一个更通用的触发下载方式可能只是简单地初始化一次。
    PaddleOCR(use_angle_cls=True, lang='ch', show_log=True) # 让它使用默认下载逻辑，但会下载到 PADDLEOCR_HOME 下

    # 或者，如果你确定子目录结构，可以尝试指定：
    # PaddleOCR(use_angle_cls=True, lang='ch', ocr_version='PP-OCRv4',
    #           det_model_dir=os.path.join(paddleocr_home, det_model_sub_dir),
    #           rec_model_dir=os.path.join(paddleocr_home, rec_model_sub_dir),
    #           cls_model_dir=os.path.join(paddleocr_home, cls_model_sub_dir),
    #           show_log=True)

    print(f"--- PaddleOCR model pre-download process finished. Check logs above for details. ---")

except Exception as e:
    print(f"--- Error during PaddleOCR pre-download: {e} ---")

# 脚本成功完成
sys.exit(0)