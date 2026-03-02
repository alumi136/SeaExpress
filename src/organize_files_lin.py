import os
import shutil
import logging
import re
from datetime import datetime
from dotenv import load_dotenv

# --- 路徑設定 (跨平台通用) ---
# 取得目前檔案 (src/organize_files.py) 的上一層目錄 (src) 的上一層 (SeaExpress_Core)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(BASE_DIR, '.env')
load_dotenv(dotenv_path)

# --- 設定 Log ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# ================= 配置區 =================
# 1. 來源目錄 (從 .env 讀取 Rclone 掛載路徑)
SOURCE_DIR = os.getenv('RAW_SOURCE_DIR')

# 2. 目標目錄 (使用相對路徑)
DEST_XML_DIR = os.path.join(BASE_DIR, 'uploads', 'xml_history')
DEST_EXCEL_DIR = os.path.join(BASE_DIR, 'uploads', 'daily_excel')

# 3. 模擬模式 (True=只顯示不執行, False=正式執行)
# ★★★ 確認 Log 無誤後，請將此處改為 False ★★★
DRY_RUN = True

# 4. 日期界限 (2026/01/09 23:59:59)
CUTOFF_DATE = datetime(2026, 1, 9, 23, 59, 59)
# ==========================================

def get_file_modification_time(filepath):
    timestamp = os.path.getmtime(filepath)
    return datetime.fromtimestamp(timestamp)

def clean_excel_filename(filename):
    """保留開頭英文+數字直到EX，去除後續中文"""
    name, ext = os.path.splitext(filename)
    # Regex: ^([A-Za-z0-9]+EX)
    match = re.match(r'^([A-Za-z0-9]+EX)', name, re.IGNORECASE)
    if match:
        return match.group(1) + ext
    return filename

def process_files():
    logging.info(f"🚀 開始檔案整理作業 (模擬模式: {DRY_RUN})")
    
    if not SOURCE_DIR or not os.path.exists(SOURCE_DIR):
        logging.error(f"錯誤: 來源目錄不存在或未設定 (.env: RAW_SOURCE_DIR)。路徑: {SOURCE_DIR}")
        logging.info("提示: 請確認 Rclone 是否已掛載，且 .env 設定正確。")
        return

    logging.info(f"來源: {SOURCE_DIR}")
    logging.info(f"目標 XML: {DEST_XML_DIR}")
    logging.info(f"目標 Excel: {DEST_EXCEL_DIR}")

    if not DRY_RUN:
        os.makedirs(DEST_XML_DIR, exist_ok=True)
        os.makedirs(DEST_EXCEL_DIR, exist_ok=True)

    try:
        files = [f for f in os.listdir(SOURCE_DIR) if os.path.isfile(os.path.join(SOURCE_DIR, f))]
    except Exception as e:
        logging.error(f"讀取目錄失敗: {e}")
        return

    count_zip = 0
    count_xlsx = 0
    count_skip = 0

    for filename in files:
        filepath = os.path.join(SOURCE_DIR, filename)
        
        try:
            mod_time = get_file_modification_time(filepath)
        except:
            continue
            
        if mod_time > CUTOFF_DATE:
            count_skip += 1
            continue

        # 處理 ZIP
        if filename.lower().endswith('.zip'):
            target_path = os.path.join(DEST_XML_DIR, filename)
            logging.info(f"[ZIP] 複製: {filename}")
            if not DRY_RUN:
                try:
                    shutil.copy2(filepath, target_path)
                    count_zip += 1
                except Exception as e:
                    logging.error(f"  -> 複製失敗: {e}")

        # 處理 XLSX
        elif filename.lower().endswith('.xlsx'):
            new_filename = clean_excel_filename(filename)
            target_path = os.path.join(DEST_EXCEL_DIR, new_filename)
            action = f"複製並改名 ({new_filename})" if new_filename != filename else "複製"
            logging.info(f"[XLSX] {action}: {filename}")
            if not DRY_RUN:
                try:
                    shutil.copy2(filepath, target_path)
                    count_xlsx += 1
                except Exception as e:
                    logging.error(f"  -> 複製失敗: {e}")

    logging.info("-" * 30)
    logging.info(f"作業結束。ZIP: {count_zip}, XLSX: {count_xlsx}, 跳過: {count_skip}")

if __name__ == "__main__":
    process_files()
