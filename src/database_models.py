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
# 2. 報關主資料表
# =========================================
class SeaExpressOrder(Base):
    __tablename__ = "sea_express_orders"
    id = Column(Integer, primary_key=True, index=True)
    
    mawb_no = Column(String(50), index=True)     
    hawb_no = Column(String(50), index=True)     
    item_no = Column(Integer)                    
    
    description_original = Column(String(255))   
    description_official = Column(String(255))   
    ccc_code = Column(String(20))                
    brand = Column(String(100))                  
    spec = Column(String(100))                   
    qty = Column(Float)                          
    qty_unit = Column(String(20))                
    unit_price = Column(Float)                   
    currency = Column(String(10))                
    total_amount = Column(Float)                 
    net_weight = Column(Float)                   
    gross_weight = Column(Float)                 
    trade_term = Column(String(20))              
    origin_country = Column(String(20))          
    marks = Column(String(100))                  
    
    cartons = Column(Float)                      
    ctn_unit = Column(String(20))                
    courier_vat_no = Column(String(50))          
    
    shipper_name = Column(String(255))           
    shipper_phone = Column(String(50))           
    shipper_address = Column(String(500))        
    
    consignee_name = Column(String(255))         
    consignee_name_ch = Column(String(255))      
    consignee_address = Column(String(500))      
    consignee_address_ch = Column(String(500))   
    consignee_phone = Column(String(50))         
    consignee_vat_no = Column(String(50))        
    consignee_id_type = Column(String(50))       
    
    manifest_no = Column(String(100))            
    container_data = Column(String(200))         
    tax_payment_note = Column(String(200))       
    remark = Column(Text)                        
    tracking_no_logistics = Column(String(100))  
    tracking_no_711 = Column(String(100))        

    processing_status = Column(String(50), default="PENDING")
    warnings = Column(Text)                      
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
    details = Column(JSON)                       
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
    tax_rate_1 = Column(String(255), comment="第一欄稅率")
    tax_rate_2 = Column(String(255), comment="第二欄稅率")
    tax_rate_3 = Column(String(255), comment="第三欄稅率")
    qty_unit = Column(String(50), comment="統計數量單位")
    weight_unit = Column(String(50), comment="統計重量單位")
    tax_regulation = Column(String(255), comment="稽徵規定")
    import_regulation = Column(String(255), comment="輸入規定")
    export_regulation = Column(String(255), comment="輸出規定")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# =========================================
# 🌟 6. 新增：品名分類輔助字典
# =========================================
class ProductCategoryDict(Base):
    __tablename__ = "product_category_dict"
    id = Column(Integer, primary_key=True, index=True)
    category_name = Column(String(100), index=True, nullable=False, comment="大分類")
    suggested_name = Column(String(200), nullable=False, comment="建議品名")
    ccc_code = Column(String(20), nullable=False, comment="稅則號")
    created_at = Column(DateTime, default=datetime.utcnow)

# =========================================
# 初始化與連線設定
# =========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(BASE_DIR, '.env')

if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
else:
    print(f"警告: 找不到 .env 設定檔於 {dotenv_path}")

user = os.getenv('DB_USER', 'sea_user')
password = os.getenv('DB_PASSWORD', '1qaz2wsx')
host = os.getenv('DB_HOST', '127.0.0.1')
port = os.getenv('DB_PORT', '3306')
dbname = os.getenv('DB_NAME', 'sea_express')

SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{user}:{password}@{host}:{port}/{dbname}?charset=utf8mb4"
engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ 資料庫表結構同步成功！")
    except Exception as e:
        print(f"❌ 資料庫建立失敗: {e}")

if __name__ == "__main__":
    init_db()