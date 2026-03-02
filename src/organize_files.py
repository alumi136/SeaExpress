import os
import shutil
import logging
import re
from datetime import datetime

# --- 設定 Log 紀錄 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler() # 只輸出到螢幕，方便預覽
    ]
)

# ================= 配置區 (Configuration) =================

# 1. 來源目錄 (Source)
SOURCE_DIR = r"I:\我的雲端硬碟\簡易報關資料"

# 2. 目標目錄 (Destinations)
# 注意: 路徑若包含中文或空白，Python 通常能處理，但建議使用 raw string (r"...")
DEST_XML_DIR = r"G:\我的雲端硬碟\SeaExpress_Automation_Project\SeaExpress_Core\uploads\xml_history"
DEST_EXCEL_DIR = r"G:\我的雲端硬碟\SeaExpress_Automation_Project\SeaExpress_Core\uploads\daily_excel"

# 3. 模擬執行模式 (True=只顯示不執行, False=正式執行)
# ★★★ 確認 Log 無誤後，請將此處改為 False ★★★
DRY_RUN = False

# 4. 日期界限 (截止日)
# 邏輯: 包含 2026年1月9日 (直到當天 23:59:59)
CUTOFF_DATE = datetime(2026, 1, 9, 23, 59, 59)

# ========================================================

def get_file_modification_time(filepath):
    """取得檔案最後修改時間 (datetime 物件)"""
    timestamp = os.path.getmtime(filepath)
    return datetime.fromtimestamp(timestamp)

def clean_excel_filename(filename):
    """
    清洗 Excel 檔名邏輯
    規則: 擷取開頭的 [英文+數字] 直到 "EX" 結束
    例如: "IPC250217732EX清关数据...xlsx" -> "IPC250217732EX.xlsx"
    """
    name, ext = os.path.splitext(filename)
    
    # Regex: ^([A-Za-z0-9]+EX)
    # 解釋: 
    #   ^ : 從頭開始
    #   [A-Za-z0-9]+ : 至少一個英文或數字
    #   EX : 必須以 EX 結尾
    match = re.match(r'^([A-Za-z0-9]+EX)', name, re.IGNORECASE)
    
    if match:
        new_name = match.group(1) + ext
        return new_name
    
    # 不符合規則，回傳原檔名
    return filename

def process_files():
    logging.info(f"🚀 開始檔案整理作業 (模擬模式: {DRY_RUN})")
    logging.info(f"來源: {SOURCE_DIR}")
    logging.info(f"日期限制: {CUTOFF_DATE} 之前 (含)")

    if not os.path.exists(SOURCE_DIR):
        logging.error(f"找不到來源目錄: {SOURCE_DIR}")
        return

    # 確保目標資料夾存在
    if not DRY_RUN:
        os.makedirs(DEST_XML_DIR, exist_ok=True)
        os.makedirs(DEST_EXCEL_DIR, exist_ok=True)

    # 取得來源目錄下的所有檔案 (不遞迴，只掃描第一層)
    try:
        files = [f for f in os.listdir(SOURCE_DIR) if os.path.isfile(os.path.join(SOURCE_DIR, f))]
    except Exception as e:
        logging.error(f"讀取目錄失敗: {e}")
        return

    count_zip = 0
    count_xlsx = 0
    count_skip_date = 0

    for filename in files:
        filepath = os.path.join(SOURCE_DIR, filename)
        
        # 1. 檢查修改日期
        mod_time = get_file_modification_time(filepath)
        
        if mod_time > CUTOFF_DATE:
            # logging.info(f"跳過 (日期太新): {filename} ({mod_time})")
            count_skip_date += 1
            continue

        # 2. 處理 .zip 檔案
        if filename.lower().endswith('.zip'):
            target_path = os.path.join(DEST_XML_DIR, filename)
            
            logging.info(f"[ZIP] 複製: {filename} -> xml_history")
            if not DRY_RUN:
                try:
                    shutil.copy2(filepath, target_path) # copy2 保留檔案元數據(時間等)
                    count_zip += 1
                except Exception as e:
                    logging.error(f"  -> 複製失敗: {e}")

        # 3. 處理 .xlsx 檔案
        elif filename.lower().endswith('.xlsx'):
            # 檔名清洗
            new_filename = clean_excel_filename(filename)
            target_path = os.path.join(DEST_EXCEL_DIR, new_filename)
            
            action_msg = "複製"
            if new_filename != filename:
                action_msg = f"複製並改名 ({new_filename})"
            
            logging.info(f"[XLSX] {action_msg}: {filename} -> daily_excel")
            
            if not DRY_RUN:
                try:
                    shutil.copy2(filepath, target_path)
                    count_xlsx += 1
                except Exception as e:
                    logging.error(f"  -> 複製失敗: {e}")

    # 總結
    if DRY_RUN:
        logging.info("-" * 30)
        logging.info("【模擬結束】")
        logging.info(f"預計複製 ZIP: {count_zip} 筆") # 模擬模式下此計數為 0 是正常的(因為沒進 copy 區塊)，看 Log 條數即可
        logging.info(f"預計複製 XLSX: {count_xlsx} 筆")
        logging.info(f"因日期略過: {count_skip_date} 筆")
        logging.info("請確認 Log 無誤後，將程式碼中的 DRY_RUN 改為 False 再執行。")
    else:
        logging.info("-" * 30)
        logging.info("【作業完成】")
        logging.info(f"成功複製 ZIP: {count_zip} 筆")
        logging.info(f"成功複製 XLSX: {count_xlsx} 筆")

if __name__ == "__main__":
    process_files()