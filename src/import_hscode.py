import os
import pandas as pd
import logging
from sqlalchemy import text
from database import get_db_engine
from database_models import init_db

# --- 設定 Log ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def format_ccc(ccc_str):
    """將 11 碼純數字稅則號格式化為標準的 XXXX.XX.XX.XX-X 格式"""
    if pd.isna(ccc_str):
        return None
    clean_str = str(ccc_str).strip()
    
    # 解決 pandas 讀取數字自動加上 .0 的問題
    if clean_str.endswith('.0'):
        clean_str = clean_str[:-2]
        
    if len(clean_str) == 11 and clean_str.isdigit():
        return f"{clean_str[:4]}.{clean_str[4:6]}.{clean_str[6:8]}.{clean_str[8:10]}-{clean_str[10]}"
    return clean_str

def get_target_file(base_dir):
    """自動尋找目錄下的海關稅則檔案"""
    valid_extensions = ('.xls', '.xlsx', '.csv')
    for file in os.listdir(base_dir):
        if "海關進口稅則資料" in file and file.lower().endswith(valid_extensions):
            return os.path.join(base_dir, file)
    return None

def read_customs_file(filepath):
    """強健的檔案讀取機制，支援多種編碼與偽裝格式 (最高容錯等級)"""
    ext = filepath.lower().split('.')[-1]
    
    if ext == 'csv':
        # 台灣公部門資料高機率是 Big5 (CP950)
        try:
            logging.info(f"嘗試以 UTF-8 讀取 CSV: {filepath}")
            return pd.read_csv(filepath, dtype=str, encoding='utf-8')
        except UnicodeDecodeError:
            logging.info(f"UTF-8 解碼失敗，自動切換為 Big5 編碼並略過亂碼...")
            # 加入 errors='replace'，遇到無法解碼的字元會換成 ? 符號，而不會讓程式崩潰
            return pd.read_csv(filepath, dtype=str, encoding='big5', errors='replace')
    else:
        # 處理 .xls 或 .xlsx
        try:
            logging.info(f"嘗試以 Excel 格式讀取: {filepath}")
            # 若為舊版 .xls 檔案，pandas 底層會呼叫 xlrd 套件
            return pd.read_excel(filepath, dtype=str)
        except ImportError as ie:
            logging.error(f"嚴重錯誤: 缺少 xlrd 套件！請在終端機執行: pip install xlrd")
            raise ie
        except Exception as e:
            # 很多官方 .xls 其實是用 html 或是 tsv 假裝的文字檔
            logging.warning(f"Excel 引擎解析失敗 ({e})，嘗試使用 Big5 純文字解析 (最高容錯)...")
            try:
                # 嘗試以 Tab 分隔讀取 (略過亂碼)
                return pd.read_csv(filepath, dtype=str, encoding='big5', sep='\t', errors='replace')
            except Exception:
                # 嘗試以逗號分隔讀取 (略過亂碼)
                return pd.read_csv(filepath, dtype=str, encoding='big5', errors='replace')

def import_hscode_data():
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 1. 自動尋找檔案 (.xls, .xlsx, .csv 均可)
    target_file = get_target_file(BASE_DIR)
    
    if not target_file:
        logging.error("❌ 找不到海關稅則檔案！")
        logging.info("請確認檔名包含『海關進口稅則資料』且副檔名為 .xls, .xlsx 或 .csv，並放置於專案根目錄。")
        return

    # 2. 確保資料庫表結構已建立
    logging.info("確保 MySQL 資料表結構準備就緒...")
    init_db()

    engine = get_db_engine()
    if not engine:
        logging.error("❌ 無法連線至資料庫")
        return

    try:
        logging.info(f"開始讀取檔案: {os.path.basename(target_file)} (檔案較大，請稍候)...")
        # 3. 使用智慧型讀取函式
        df = read_customs_file(target_file)
        
        if df is None or df.empty:
            logging.error("❌ 檔案內容為空或無法解析。")
            return

        # 定義欄位對應關係
        column_mapping = {
            '貨品分類號列': 'ccc_code',
            '中文貨名': 'chinese_name',
            '英文貨名': 'english_name',
            '第一欄稅率': 'tax_rate_1',
            '第二欄稅率': 'tax_rate_2',
            '第三欄稅率': 'tax_rate_3',
            '統計數量單位': 'qty_unit',
            '統計重量單位': 'weight_unit',
            '稽徵規定': 'tax_regulation',
            '輸入規定': 'import_regulation',
            '輸出規定': 'export_regulation'
        }
        
        # 為了容錯，將表頭的空白與換行符號去除
        df.columns = [str(c).strip().replace('\n', '').replace('\r', '') for c in df.columns]
        
        # 只保留我們需要的欄位並重新命名
        df = df.rename(columns=column_mapping)
        existing_cols = [col for col in column_mapping.values() if col in df.columns]
        df = df[existing_cols].copy()
        
        # 4. 資料清洗
        logging.info("格式化稅則號列與資料清洗...")
        if 'ccc_code' in df.columns:
            df['ccc_code'] = df['ccc_code'].apply(format_ccc)
        
        # 將空白字串或 NaN 轉為 None (寫入 MySQL 時為 NULL)
        df = df.where(pd.notnull(df), None)

        # 5. 寫入資料庫
        logging.info("清理舊有稅則資料 (TRUNCATE TABLE)...")
        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
            conn.execute(text("TRUNCATE TABLE standard_HSCODE;"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

        logging.info(f"🚀 開始將 {len(df)} 筆稅則資料匯入 MySQL (standard_HSCODE) ...")
        
        # 批次寫入資料庫 (1000筆一批，增加效能並避免記憶體超載)
        df.to_sql('standard_HSCODE', con=engine, if_exists='append', index=False, chunksize=1000)
        
        logging.info("✅ 官方進口稅則資料庫匯入完成！您現在擁有一份完整的最新稅則對照表了！")
        
    except ImportError:
        # 已經在 read_customs_file 處理過 ImportError
        pass
    except Exception as e:
        logging.error(f"❌ 匯入失敗: {e}", exc_info=True)

if __name__ == "__main__":
    import_hscode_data()