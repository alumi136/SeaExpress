import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from dotenv import load_dotenv

# 宣告對應基底
Base = declarative_base()

# =========================================
# 1. 系統使用者表 (User)
# =========================================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), default="OPERATOR")
    is_active = Column(Boolean, default=True)

# =========================================
# 2. 報關主資料表 (升級版：全欄位收錄)
# =========================================
class SeaExpressOrder(Base):
    __tablename__ = "sea_express_orders"
    id = Column(Integer, primary_key=True, index=True)
    
    # --- 主鍵與分類 ---
    mawb_no = Column(String(50), index=True)     # 主提單號
    hawb_no = Column(String(50), index=True)     # 分提單號
    item_no = Column(Integer)                    # 項次/貨物編號
    
    # --- 單一貨品 (Item) 層級 ---
    description_original = Column(String(255))   # 原始品名
    description_official = Column(String(255))   # 通關品名 (AI預測)
    ccc_code = Column(String(20))                # 貨品分類號列
    brand = Column(String(100))                  # 品牌
    spec = Column(String(100))                   # 規格
    qty = Column(Float)                          # 數量
    qty_unit = Column(String(20))                # 數量單位
    unit_price = Column(Float)                   # 單價
    currency = Column(String(10))                # 單價幣代碼
    total_amount = Column(Float)                 # 總金額
    net_weight = Column(Float)                   # 淨重
    gross_weight = Column(Float)                 # 毛重
    trade_term = Column(String(20))              # 交易條件代碼
    origin_country = Column(String(20))          # 生產國別代碼
    marks = Column(String(100))                  # 標記
    
    # --- 分提單 (HAWB) 共用層級 ---
    cartons = Column(Float)                      # 總件數(箱數)
    ctn_unit = Column(String(20))                # 件數單位
    courier_vat_no = Column(String(50))          # 快遞業者統一編號
    
    # 寄件人資訊
    shipper_name = Column(String(255))           # 寄件人英文名稱
    shipper_phone = Column(String(50))           # 寄件人電話
    shipper_address = Column(String(500))        # 寄件人英文地址
    
    # 收貨人資訊
    consignee_name = Column(String(255))         # 收貨人英文名稱
    consignee_name_ch = Column(String(255))      # 收貨人中文名稱
    consignee_address = Column(String(500))      # 收貨人英文地址
    consignee_address_ch = Column(String(500))   # 收貨人中文地址
    consignee_phone = Column(String(50))         # 收貨人電話
    consignee_vat_no = Column(String(50))        # 收貨人統一編號
    consignee_id_type = Column(String(50))       # 收貨人身分識別碼
    
    # 其他報關資訊
    manifest_no = Column(String(100))            # 艙單號碼（裝貨單號碼）
    container_data = Column(String(200))         # 貨櫃資料
    tax_payment_note = Column(String(200))       # 申報繳納稅款註記
    remark = Column(Text)                        # 備註
    tracking_no_logistics = Column(String(100))  # 物流单号
    tracking_no_711 = Column(String(100))        # 7-11單號

    # --- 系統管理欄位 ---
    processing_status = Column(String(50), default="PENDING")
    warnings = Column(Text)                      # 存放 JSON 陣列格式的警告訊息
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(Integer, nullable=True)

# =========================================
# 3. 系統操作軌跡 (Audit Log)
# =========================================
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    mawb_no = Column(String(50))
    hawb_no = Column(String(50))
    action = Column(String(50))
    details = Column(JSON)                       # 記錄修改前後的資料差異
    created_at = Column(DateTime, default=datetime.utcnow)

# =========================================
# 4. 黑名單與知識庫
# =========================================
class BlacklistKeyword(Base):
    __tablename__ = "blacklist_keywords"
    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class StandardKnowledgeBase(Base):
    __tablename__ = "standard_knowledge_base"
    id = Column(Integer, primary_key=True, index=True)
    original_description = Column(String(200), index=True)
    official_description = Column(String(200))
    ccc_code = Column(String(20))
    
    # --- 新增的兩個欄位：稅率與輸入規定 (評估後設為 50 即可) ---
    tax_rate_1 = Column(String(50), comment="第一欄稅率")
    import_regulation = Column(String(50), comment="輸入規定")
    
    frequency = Column(Integer, default=1)
    last_trained_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# =========================================
# 5. 官方海關進口稅則 (Standard HS Code)
# =========================================
class StandardHSCode(Base):
    __tablename__ = "standard_HSCODE"
    id = Column(Integer, primary_key=True, index=True)
    ccc_code = Column(String(20), unique=True, index=True, comment="貨品分類號列(稅則號)")
    chinese_name = Column(Text, comment="中文貨名")
    english_name = Column(Text, comment="英文貨名")
    
    # 稅率相關欄位長度放寬至 255 (容納冗長的 FTA 國家代碼)
    tax_rate_1 = Column(String(255), comment="第一欄稅率")
    tax_rate_2 = Column(String(255), comment="第二欄稅率")
    tax_rate_3 = Column(String(255), comment="第三欄稅率")
    
    qty_unit = Column(String(50), comment="統計數量單位")
    weight_unit = Column(String(50), comment="統計重量單位")
    
    # 規定相關欄位長度放寬至 255
    tax_regulation = Column(String(255), comment="稽徵規定")
    import_regulation = Column(String(255), comment="輸入規定")
    export_regulation = Column(String(255), comment="輸出規定")
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# =========================================
# 初始化與連線設定 (正式切換至 MySQL)
# =========================================
# 取得專案根目錄並載入 .env
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(BASE_DIR, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print(f"警告: 找不到 .env 設定檔於 {dotenv_path}")

# 讀取 MySQL 連線資訊
user = os.getenv('DB_USER', 'sea_user')
password = os.getenv('DB_PASSWORD', '')
host = os.getenv('DB_HOST', '127.0.0.1')
port = os.getenv('DB_PORT', '3306')
dbname = os.getenv('DB_NAME', 'sea_express')

# 建立 MySQL 連線字串
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{user}:{password}@{host}:{port}/{dbname}?charset=utf8mb4"

# 建立引擎 (pool_pre_ping=True 可防止 MySQL 連線逾時斷線)
engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False, pool_pre_ping=True)

# !!! 關鍵定義區 !!!
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """自動建立所有資料表結構"""
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ 資料庫表結構同步成功！")
    except Exception as e:
        print(f"❌ 資料庫建立失敗，請檢查 MySQL 服務是否啟動以及 .env 設定是否正確: {e}")

if __name__ == "__main__":
    init_db()