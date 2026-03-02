import os
import shutil
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
import jwt
import io
import urllib.parse
import pandas as pd

# 匯入資料庫與驗證模組
from database_models import SessionLocal, User, SeaExpressOrder, AuditLog
from auth import verify_password
from core_engine import SeaExpressEngine

# --- JWT 設定 ---
SECRET_KEY = "your_super_secret_key_change_this_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 720 

app = FastAPI(title="海快報關自動化系統 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="無法驗證憑證",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise credentials_exception
    except jwt.PyJWTError: raise credentials_exception
        
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active: raise credentials_exception
    return user

# ==========================================
# 登入 API
# ==========================================
@app.post("/api/login")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="帳號或密碼錯誤")
    if not user.is_active: raise HTTPException(status_code=400, detail="此帳號已被停用")

    access_token = create_access_token(data={"sub": user.username, "role": user.role, "id": user.id})
    return {"access_token": access_token, "token_type": "bearer", "role": user.role, "username": user.username}

@app.get("/api/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return {"id": current_user.id, "username": current_user.username, "role": current_user.role}

# ==========================================
# 業務 API
# ==========================================

@app.get("/api/mawbs")
def get_mawbs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """取得資料庫中所有的主提單號 (MAWB) 清單"""
    mawbs = db.query(SeaExpressOrder.mawb_no).distinct().order_by(SeaExpressOrder.mawb_no.desc()).all()
    return [m[0] for m in mawbs if m[0]]

@app.get("/api/orders")
def get_orders(mawb_no: str = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """依照 MAWB 取得訂單，並以 HAWB 為單位分組 (支援手風琴介面)"""
    if not mawb_no:
        return []
        
    orders = db.query(SeaExpressOrder).filter(SeaExpressOrder.mawb_no == mawb_no).order_by(SeaExpressOrder.hawb_no, SeaExpressOrder.item_no).all()
    
    hawb_groups = {}
    for o in orders:
        if o.hawb_no not in hawb_groups:
            hawb_groups[o.hawb_no] = {
                "hawb_no": o.hawb_no,
                "mawb_no": o.mawb_no,
                "processing_status": o.processing_status,
                "consignee_name": o.consignee_name,
                "consignee_phone": o.consignee_phone,
                "consignee_address": o.consignee_address,
                "gross_weight": o.gross_weight,
                "cartons": o.cartons,
                "warnings": [],
                "total_amount": 0,
                "items": []
            }
        
        # 彙整警告訊息 (去重複)
        try:
            item_warns = json.loads(o.warnings) if o.warnings else []
            for w in item_warns:
                if w not in hawb_groups[o.hawb_no]["warnings"]:
                    hawb_groups[o.hawb_no]["warnings"].append(w)
        except: pass

        # 狀態連動 (任一項次紅燈，整單紅燈)
        if o.processing_status == "MANUAL_REQUIRED":
            hawb_groups[o.hawb_no]["processing_status"] = "MANUAL_REQUIRED"

        hawb_groups[o.hawb_no]["total_amount"] += (o.total_amount or 0)
        
        # 加入單一項次明細
        hawb_groups[o.hawb_no]["items"].append({
            "id": o.id,
            "item_no": o.item_no,
            "description_original": o.description_original,
            "description_official": o.description_official,
            "ccc_code": o.ccc_code,
            "qty": o.qty,
            "unit_price": o.unit_price,
            "total_amount": o.total_amount,
            "net_weight": o.net_weight
        })
        
    return list(hawb_groups.values())

@app.post("/api/upload")
async def upload_excel(
    file: UploadFile = File(...),
    mawb_no: str = Form(...),
    import_mode: str = Form(...), # NEW 或 APPEND
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """上傳 Excel (支援匯入模式切換)"""
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_dir = os.path.join(BASE_DIR, "uploads", "daily_excel")
    os.makedirs(upload_dir, exist_ok=True)
    file_location = os.path.join(upload_dir, file.filename)
    
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
        
    engine = SeaExpressEngine()
    success, msg = engine.process_and_save(file_location, mawb_no, import_mode=import_mode, operator_id=current_user.id)
    
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": "匯入成功", "detail": msg}


# ==========================================
# 人工修改 Pydantic 模型定義
# ==========================================
class ItemUpdate(BaseModel):
    id: int
    description_original: str
    description_official: Optional[str] = None
    ccc_code: Optional[str] = None
    qty: float
    unit_price: float
    total_amount: float
    net_weight: Optional[float] = None

class HAWBUpdate(BaseModel):
    mawb_no: str
    consignee_name: Optional[str] = None
    consignee_phone: Optional[str] = None
    consignee_address: Optional[str] = None
    gross_weight: Optional[float] = None
    cartons: Optional[float] = None
    items: List[ItemUpdate]

@app.put("/api/hawb/{hawb_no}")
def update_hawb(hawb_no: str, update_data: HAWBUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """以 HAWB 為單位，一次性儲存整單與所有項次的修改"""
    orders = db.query(SeaExpressOrder).filter(SeaExpressOrder.hawb_no == hawb_no, SeaExpressOrder.mawb_no == update_data.mawb_no).all()
    if not orders:
        raise HTTPException(status_code=404, detail="找不到該分提單資料")

    # 記錄舊資料 (Audit Log 準備)
    old_data = [{"id": o.id, "desc": o.description_original, "ccc": o.ccc_code, "price": o.unit_price, "qty": o.qty} for o in orders]
    item_updates_dict = {item.id: item for item in update_data.items}
    
    for order in orders:
        # 更新 HAWB 共用層級
        order.consignee_name = update_data.consignee_name
        order.consignee_phone = update_data.consignee_phone
        order.consignee_address = update_data.consignee_address
        order.gross_weight = update_data.gross_weight
        order.cartons = update_data.cartons
        
        # 更新 Item 專屬層級
        if order.id in item_updates_dict:
            item_data = item_updates_dict[order.id]
            order.description_original = item_data.description_original
            order.description_official = item_data.description_official
            order.ccc_code = item_data.ccc_code
            order.qty = item_data.qty
            order.unit_price = item_data.unit_price
            order.total_amount = item_data.total_amount
            order.net_weight = item_data.net_weight
            
        # 解除警報狀態
        order.processing_status = "PROCESSED"
        order.warnings = "[]"
        order.updated_by = current_user.id
        
    # 寫入 Audit Log
    audit_log = AuditLog(
        user_id=current_user.id,
        mawb_no=update_data.mawb_no,
        hawb_no=hawb_no,
        action="HAWB_MANUAL_OVERRIDE",
        details={"old": old_data, "new": update_data.dict()}
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": "整單修改並放行成功"}

@app.get("/api/export/{mawb_no}")
def export_mawb_excel(mawb_no: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """匯出指定 MAWB 的標準報關 Excel 檔案"""
    orders = db.query(SeaExpressOrder).filter(SeaExpressOrder.mawb_no == mawb_no).order_by(SeaExpressOrder.hawb_no, SeaExpressOrder.item_no).all()
    
    if not orders:
        raise HTTPException(status_code=404, detail="找不到該主單號的資料")

    # 定義輸出的欄位順序與標題 (您可依據海關或下游系統需求自由調換順序)
    export_data = []
    for o in orders:
        export_data.append({
            "主提單號 (MAWB)": o.mawb_no,
            "分提單號 (HAWB)": o.hawb_no,
            "項次": o.item_no,
            "通關品名": o.description_official or "",
            "原始品名": o.description_original or "",
            "稅則號列 (CCC Code)": o.ccc_code or "",
            "數量": o.qty,
            "數量單位": o.qty_unit or "",
            "單價": o.unit_price,
            "幣別": o.currency or "TWD",
            "總金額": o.total_amount,
            "淨重 (KG)": o.net_weight,
            "毛重 (KG)": o.gross_weight,
            "總件數 (箱數)": o.cartons,
            "件數單位": o.ctn_unit or "",
            "收件人名稱": o.consignee_name or "",
            "收件人電話": o.consignee_phone or "",
            "收件人地址": o.consignee_address or "",
            "收件人統編": o.consignee_vat_no or "",
            "寄件人名稱": o.shipper_name or "",
            "寄件人電話": o.shipper_phone or "",
            "寄件人地址": o.shipper_address or "",
            "產地": o.origin_country or "",
            "交易條件": o.trade_term or "",
            "標記 (Marks)": o.marks or "",
            "系統處理狀態": "已放行" if o.processing_status == "PROCESSED" else "異常未處理"
        })

    df = pd.DataFrame(export_data)
    
    # 將 DataFrame 寫入記憶體中的 BytesIO
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='標準報關資料')
    
    output.seek(0)
    
    # 設定下載檔名 (處理 URL 中文編碼避免亂碼)
    filename = f"海快報關資料_{mawb_no}.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    
    return StreamingResponse(
        output, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"}
    )

# ==========================================
# 靜態網頁託管
# ==========================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "src", "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "找不到 index.html"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 啟動海快報關 Web 伺服器...")
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)