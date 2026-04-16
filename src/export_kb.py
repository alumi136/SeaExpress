import os
import pandas as pd
from database import get_db_engine

def export_knowledge_base():
    engine = get_db_engine()
    if not engine:
        print("❌ 無法連線至資料庫，請檢查 .env 設定檔。")
        return

    # 包含 GROUP_CONCAT 的強大 SQL 語法
    sql = """
    SELECT 
        ccc_code AS `稅則號`, 
        GROUP_CONCAT(DISTINCT official_description SEPARATOR ';') AS `合併品名清單`
    FROM 
        standard_knowledge_base
    WHERE 
        ccc_code IS NOT NULL AND ccc_code != ''
    GROUP BY 
        ccc_code
    ORDER BY 
        ccc_code;
    """
    
    print("⏳ 正在從 MySQL 資料庫撈取並彙整知識庫資料...")
    
    try:
        # 透過 Pandas 執行 SQL 並直接轉為 DataFrame
        df = pd.read_sql(sql, engine)
        
        if df.empty:
            print("⚠️ 知識庫中目前沒有資料可以匯出。")
            return

        # 設定輸出的 txt 檔案名稱與路徑 (放在專案根目錄)
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_file = os.path.join(BASE_DIR, "稅則號與品名對照總表.txt")
        
        # 存成 txt 檔 (使用 Tab 作為欄位分隔符號，最適合人類閱讀與 Excel 開啟)
        df.to_csv(output_file, sep='\t', index=False, encoding='utf-8')
        
        print(f"✅ 匯出成功！共彙整了 {len(df)} 筆不重複的稅則號。")
        print(f"📁 檔案已存至: {output_file}")
        
    except Exception as e:
        print(f"❌ 匯出過程中發生錯誤: {e}")

if __name__ == "__main__":
    export_knowledge_base()