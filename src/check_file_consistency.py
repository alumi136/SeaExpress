import os
import logging
from datetime import datetime

# ================= 配置區 =================

# 設定專案根目錄 (根據您的環境結構)
# 假設此 script 在 SeaExpress_Core/src/ 底下，往上兩層回到 SeaExpress_Core
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Excel 目錄
DIR_EXCEL = os.path.join(BASE_DIR, 'uploads', 'daily_excel')

# XML/Zip 目錄
DIR_HISTORY = os.path.join(BASE_DIR, 'uploads', 'xml_history')

# 紀錄檔名稱
LOG_FILE = "consistency_report.log"

# ==========================================

# 設定 Log (同時輸出到檔案與螢幕)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 檔案 Handler
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8', mode='w') # mode='w' 每次執行覆寫舊報表
file_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(file_handler)

# 螢幕 Handler
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(stream_handler)

def get_file_info(directory, target_exts):
    """
    讀取目錄下特定副檔名的檔案
    回傳:
      - file_set: 檔名主體集合 (不含副檔名，用於比對)
      - file_map: {檔名主體: 完整檔名} (用於顯示)
      - count: 檔案總數
    """
    file_set = set()
    file_map = {}
    count = 0

    if not os.path.exists(directory):
        logger.error(f"錯誤: 找不到目錄 {directory}")
        return file_set, file_map, 0

    try:
        for f in os.listdir(directory):
            if any(f.lower().endswith(ext) for ext in target_exts):
                # 取得主檔名 (例如: IPC123.xlsx -> IPC123)
                base_name = os.path.splitext(f)[0].strip()
                file_set.add(base_name)
                file_map[base_name] = f
                count += 1
    except Exception as e:
        logger.error(f"讀取目錄失敗: {e}")
    
    return file_set, file_map, count

def main():
    logger.info("=" * 50)
    logger.info(f"海快報關自動化 - 檔案一致性檢核報告")
    logger.info(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)

    # 1. 讀取 Excel 資料夾 (.xlsx, .xls, .csv)
    logger.info(f"掃描 Excel 目錄: {DIR_EXCEL}")
    excel_keys, excel_map, excel_count = get_file_info(DIR_EXCEL, ['.xlsx', '.xls', '.csv'])
    
    # 2. 讀取 History 資料夾 (.zip, .xml)
    logger.info(f"掃描 History 目錄: {DIR_HISTORY}")
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
    logger.info("\n" + "-" * 20 + " 統計摘要 " + "-" * 20)
    logger.info(f"【Excel 目錄檔案數】: {excel_count} 筆")
    logger.info(f"【History 目錄檔案數】: {history_count} 筆")
    logger.info(f"------------------------------------------")
    logger.info(f"✅ 一致 (成對) 筆數 : {len(consistent_keys)} 筆")
    logger.info(f"❌ 不一致 (缺漏) 筆數 : {total_inconsistent} 筆")
    logger.info("-" * 50)

    # 5. 輸出詳細不一致清單
    if total_inconsistent > 0:
        logger.info("\n【不一致詳細清單】")
        
        if missing_in_history:
            logger.info(f"\n[Excel 有，但 History 缺漏 XML/ZIP] - 共 {len(missing_in_history)} 筆:")
            for k in sorted(missing_in_history):
                logger.info(f"  - {excel_map[k]}")

        if missing_in_excel:
            logger.info(f"\n[History 有，但 Excel 缺漏 XLSX] - 共 {len(missing_in_excel)} 筆:")
            for k in sorted(missing_in_excel):
                logger.info(f"  - {history_map[k]}")
    else:
        logger.info("\n恭喜！所有檔案皆完美對應。")

    logger.info("\n" + "=" * 50)
    print(f"\n報告已產生於: {os.path.abspath(LOG_FILE)}")

if __name__ == "__main__":
    main()