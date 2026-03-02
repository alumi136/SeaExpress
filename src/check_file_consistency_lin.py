import os
import logging
from datetime import datetime

# --- 路徑設定 (跨平台通用) ---
# 取得目前檔案 (src/check_file_consistency.py) 的上一層目錄 (src) 的上一層 (SeaExpress_Core)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Excel 來源目錄 (Linux 相對路徑)
DIR_EXCEL = os.path.join(BASE_DIR, 'uploads', 'daily_excel')

# XML/Zip 歷史目錄 (Linux 相對路徑)
DIR_HISTORY = os.path.join(BASE_DIR, 'uploads', 'xml_history')

# 報告輸出檔案
LOG_FILE = os.path.join(BASE_DIR, "consistency_report.log")

# --- 設定 Log (同時輸出到檔案與螢幕) ---
# 先清除舊的 handlers 避免重複 (若是在互動式環境執行)
logger = logging.getLogger()
if logger.hasHandlers():
    logger.handlers.clear()

logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(message)s')

# 1. 檔案 Handler (覆寫模式 'w')
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='w')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 2. 螢幕 Handler
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

def get_file_info(directory, target_exts):
    """
    掃描目錄並回傳檔案資訊
    Args:
        directory: 目標資料夾路徑
        target_exts: 要掃描的副檔名列表 (如 ['.xlsx', '.csv'])
    Returns:
        file_set: 主檔名集合 (不含副檔名)
        file_map: {主檔名: 原始完整檔名}
        count: 符合條件的檔案數量
    """
    file_set = set()
    file_map = {}
    count = 0

    if not os.path.exists(directory):
        logging.error(f"錯誤: 找不到目錄 {directory}")
        return file_set, file_map, 0

    try:
        # os.listdir 在 Linux 下區分大小寫，但我們這裡只做簡單遍歷
        for f in os.listdir(directory):
            # 檢查副檔名 (忽略大小寫差異)
            if any(f.lower().endswith(ext) for ext in target_exts):
                # 取得主檔名 (去除路徑與副檔名)
                base_name = os.path.splitext(f)[0].strip()
                
                file_set.add(base_name)
                file_map[base_name] = f
                count += 1
    except Exception as e:
        logging.error(f"讀取目錄失敗: {e}")
    
    return file_set, file_map, count

def main():
    logging.info("=" * 50)
    logging.info(f"海快報關自動化 - 檔案一致性檢核報告")
    logging.info(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=" * 50)

    # 1. 讀取 Excel 資料夾
    logging.info(f"掃描 Excel 目錄: {DIR_EXCEL}")
    excel_keys, excel_map, excel_count = get_file_info(DIR_EXCEL, ['.xlsx', '.xls', '.csv'])
    
    # 2. 讀取 History 資料夾
    logging.info(f"掃描 History 目錄: {DIR_HISTORY}")
    history_keys, history_map, history_count = get_file_info(DIR_HISTORY, ['.zip', '.xml'])

    # 3. 進行比對
    # 交集 (Consistent): 兩個目錄都有
    consistent_keys = excel_keys.intersection(history_keys)
    
    # 差集 (Inconsistent)
    # Excel 有，但 History 沒有
    missing_in_history = excel_keys - history_keys
    # History 有，但 Excel 沒有
    missing_in_excel = history_keys - excel_keys

    total_inconsistent = len(missing_in_history) + len(missing_in_excel)

    # 4. 輸出統計結果
    logging.info("-" * 50)
    logging.info(f"【統計摘要】")
    logging.info(f"  Excel 檔案數   : {excel_count}")
    logging.info(f"  History 檔案數 : {history_count}")
    logging.info("-" * 20)
    logging.info(f"✅ 一致 (成對) 筆數 : {len(consistent_keys)}")
    logging.info(f"❌ 不一致 (缺漏) 筆數 : {total_inconsistent}")
    logging.info("-" * 50)

    # 5. 輸出詳細不一致清單
    if total_inconsistent > 0:
        logging.info("\n【不一致詳細清單】")
        
        if missing_in_history:
            logging.info(f"\n[Excel 有，但 History 缺漏 XML/ZIP] - 共 {len(missing_in_history)} 筆:")
            for k in sorted(missing_in_history):
                logging.info(f"  - {excel_map[k]}")

        if missing_in_excel:
            logging.info(f"\n[History 有，但 Excel 缺漏 XLSX] - 共 {len(missing_in_excel)} 筆:")
            for k in sorted(missing_in_excel):
                logging.info(f"  - {history_map[k]}")
    else:
        logging.info("\n恭喜！所有檔案皆完美對應。")

    logging.info("\n" + "=" * 50)
    # 在 Linux 終端機顯示報告位置提示
    print(f"\n報告已產生於: {os.path.abspath(LOG_FILE)}")

if __name__ == "__main__":
    main()
