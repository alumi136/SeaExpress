import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

def reset_tables():
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(BASE_DIR, '.env'))

    user = os.getenv('DB_USER', 'sea_user')
    password = os.getenv('DB_PASSWORD', '1qaz2wsx')
    host = os.getenv('DB_HOST', '35.229.200.173')
    port = os.getenv('DB_PORT', '3306')
    dbname = os.getenv('DB_NAME', 'sea_express')

    SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{user}:{password}@{host}:{port}/{dbname}?charset=utf8mb4"
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

    with engine.begin() as conn:
        print("正在清除 MySQL 舊有系統資料表 (確保 100% 保留 AI 知識庫)...")
        
        # 關鍵修復：暫時關閉外鍵檢查限制
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        
        # 刪除需要重建的表
        conn.execute(text("DROP TABLE IF EXISTS sea_express_orders;"))
        conn.execute(text("DROP TABLE IF EXISTS audit_logs;"))
        conn.execute(text("DROP TABLE IF EXISTS users;"))
        
        # 重新開啟外鍵檢查限制
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
        
        print("✅ 清除完成！舊資料表已安全刪除。")

if __name__ == "__main__":
    reset_tables()