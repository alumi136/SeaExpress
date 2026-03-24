import os
import shutil
import json
import re
import unicodedata
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, status, File, UploadFile, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, validator
from typing import List, Optional
from sqlalchemy.orm import Session
import jwt
import io
import urllib.parse
import pandas as pd

from database_models import SessionLocal, User, SeaExpressOrder, AuditLog, StandardKnowledgeBase, BlacklistKeyword, ProductCategoryDict
from auth import verify_password
from core_engine import SeaExpressEngine

SECRET_KEY = "your_super_secret_key_change_this_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 720 

app = FastAPI(title="海快報關自動化系統 API")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="無法驗證憑證", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None: raise credentials_exception
    except jwt.PyJWTError: raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active: raise credentials_exception
    return user

def normalize_kb_text(text_str):
    if not text_str or pd.isna(text_str): return ""
    val = unicodedata.normalize('NFKC', text_str).upper()
    if '/' in val: val = val.split('/')[-1]
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', val)).strip()

def format_ccc_for_kb(ccc_str):
    if not ccc_str: return None
    clean_str = re.sub(r'\D', '', str(ccc_str))
    if len(clean_str) != 11: return ccc_str
    return f"{clean_str[:4]}.{clean_str[4:6]}.{clean_str[6:8]}.{clean_str[8:10]}-{clean_str[10]}"

def parse_tax_rate(rate_str):
    if not rate_str or rate_str == '免稅': return 0.0
    matches = re.findall(r'(\d+(\.\d+)?)%', str(rate_str))
    if matches: return max([float(m[0]) for m in matches]) / 100.0
    return 0.0

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

@app.get("/api/mawbs")
def get_mawbs(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    mawbs = db.query(SeaExpressOrder.mawb_no).distinct().order_by(SeaExpressOrder.mawb_no.desc()).all()
    return [m[0] for m in mawbs if m[0]]

@app.get("/api/orders")
def get_orders(mawb_no: str = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not mawb_no: return []
    orders = db.query(SeaExpressOrder).filter(SeaExpressOrder.mawb_no == mawb_no).order_by(SeaExpressOrder.id).all()
    engine = SeaExpressEngine()
    hawb_groups = {}
    
    for o in orders:
        if o.hawb_no not in hawb_groups:
            hawb_groups[o.hawb_no] = {
                "hawb_no": o.hawb_no, "mawb_no": o.mawb_no,
                "processing_status": o.processing_status,
                "consignee_name": o.consignee_name, "consignee_phone": o.consignee_phone,
                "consignee_address": o.consignee_address, "consignee_vat_no": o.consignee_vat_no,
                "gross_weight": o.gross_weight, "cartons": o.cartons,
                "warnings": [], "total_amount": 0, "estimated_tax": 0.0, "items": [],
                "split_group": ""
            }
        
        try:
            item_warns = json.loads(o.warnings) if o.warnings else []
            for w in item_warns:
                if w not in hawb_groups[o.hawb_no]["warnings"]:
                    hawb_groups[o.hawb_no]["warnings"].append(w)
                if w.startswith("化整為零"):
                    hawb_groups[o.hawb_no]["split_group"] = w
        except: pass

        if o.processing_status == "MANUAL_REQUIRED":
            hawb_groups[o.hawb_no]["processing_status"] = "MANUAL_REQUIRED"

        hawb_groups[o.hawb_no]["total_amount"] += (o.total_amount or 0)
        
        candidates = []
        if o.processing_status == "MANUAL_REQUIRED" and (not o.ccc_code or "模糊" in str(o.warnings) or "查無" in str(o.warnings)):
            candidates = engine.get_candidates(o.description_original)
            
        hawb_groups[o.hawb_no]["items"].append({
            "id": o.id, "item_no": o.item_no, "description_original": o.description_original,
            "description_official": o.description_official, "ccc_code": o.ccc_code,
            "qty": o.qty, "unit_price": o.unit_price, "total_amount": o.total_amount,
            "net_weight": o.net_weight, "candidates": candidates
        })

    for group in hawb_groups.values():
        hawb_total = group["total_amount"]
        hawb_tax = 0.0
        if hawb_total >= 2000:
            total_import_duty = 0.0
            for item in group["items"]:
                if item["ccc_code"]:
                    kb_entry = db.query(StandardKnowledgeBase).filter(StandardKnowledgeBase.ccc_code == item["ccc_code"]).first()
                    rate_str = kb_entry.tax_rate_1 if kb_entry else '0%'
                else: rate_str = '0%'
                total_import_duty += (item["total_amount"] or 0.0) * parse_tax_rate(rate_str)
            hawb_tax = total_import_duty + ((hawb_total + total_import_duty) * 0.05)
        group["estimated_tax"] = hawb_tax
        
    grouped_list = list(hawb_groups.values())
    
    def sort_key(g):
        if g["processing_status"] == "MANUAL_REQUIRED":
            if g["split_group"]: priority = 0  
            else: priority = 1                 
        else: priority = 2                     
        return (priority, g["split_group"], g["hawb_no"])
        
    grouped_list.sort(key=sort_key)
    return grouped_list

@app.post("/api/upload")
async def upload_excel(
    file: UploadFile = File(...), mawb_no: str = Form(...), import_mode: str = Form(...),
    rules_config: str = Form(None), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_dir = os.path.join(BASE_DIR, "uploads", "daily_excel")
    os.makedirs(upload_dir, exist_ok=True)
    file_location = os.path.join(upload_dir, file.filename)
    with open(file_location, "wb+") as file_object: shutil.copyfileobj(file.file, file_object)
        
    config_dict = {}
    if rules_config:
        try: config_dict = json.loads(rules_config)
        except Exception as e: pass

    import_engine = SeaExpressEngine()
    success, msg = import_engine.process_and_save(file_location, mawb_no, import_mode=import_mode, operator_id=current_user.id, rules_config=config_dict)
    if not success: raise HTTPException(status_code=400, detail=msg)
    return {"message": "匯入成功", "detail": msg}


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
    consignee_vat_no: Optional[str] = None
    gross_weight: Optional[float] = None
    cartons: Optional[float] = None
    items: List[ItemUpdate]

    @validator('consignee_vat_no')
    def validate_vat(cls, v):
        if not v: return v
        clean_vat = str(v).strip().upper()
        if not clean_vat: return v
        if not (re.match(r'^[A-Z]\d{9}$', clean_vat) or re.match(r'^\d{8}$', clean_vat)):
            raise ValueError("統編或身分證格式錯誤！必須為 8 碼數字或 1 碼英文加 9 碼數字。")
        return clean_vat

@app.put("/api/hawb/{hawb_no}")
def update_hawb(hawb_no: str, update_data: HAWBUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(SeaExpressOrder).filter(SeaExpressOrder.hawb_no == hawb_no, SeaExpressOrder.mawb_no == update_data.mawb_no).all()
    if not orders: raise HTTPException(status_code=404, detail="找不到該分提單資料")

    old_data = [{"id": o.id, "desc": o.description_original, "ccc": o.ccc_code, "price": o.unit_price, "qty": o.qty} for o in orders]
    item_updates_dict = {item.id: item for item in update_data.items}
    learned_count = 0
    local_kb_cache = {} 

    for order in orders:
        order.consignee_name = update_data.consignee_name
        order.consignee_phone = update_data.consignee_phone
        order.consignee_address = update_data.consignee_address
        order.consignee_vat_no = update_data.consignee_vat_no
        order.gross_weight = update_data.gross_weight
        order.cartons = update_data.cartons
        
        if order.id in item_updates_dict:
            item_data = item_updates_dict[order.id]
            order.description_original = item_data.description_original
            order.description_official = item_data.description_official
            order.ccc_code = item_data.ccc_code
            order.qty = item_data.qty
            order.unit_price = item_data.unit_price
            order.total_amount = item_data.total_amount
            order.net_weight = item_data.net_weight
            
            if item_data.description_official and item_data.ccc_code:
                clean_orig_desc = normalize_kb_text(item_data.description_original)
                clean_ccc = format_ccc_for_kb(item_data.ccc_code)
                if clean_orig_desc:
                    if clean_orig_desc in local_kb_cache:
                        kb_entry = local_kb_cache[clean_orig_desc]
                        if kb_entry.ccc_code != clean_ccc or kb_entry.official_description != item_data.description_official:
                            kb_entry.official_description = item_data.description_official
                            kb_entry.ccc_code = clean_ccc
                            kb_entry.last_trained_at = datetime.utcnow()
                        kb_entry.frequency += 1
                    else:
                        kb_entry = db.query(StandardKnowledgeBase).filter(StandardKnowledgeBase.original_description == clean_orig_desc).first()
                        if kb_entry:
                            if kb_entry.ccc_code != clean_ccc or kb_entry.official_description != item_data.description_official:
                                kb_entry.official_description = item_data.description_official
                                kb_entry.ccc_code = clean_ccc
                                kb_entry.last_trained_at = datetime.utcnow()
                                learned_count += 1
                            kb_entry.frequency += 1
                            local_kb_cache[clean_orig_desc] = kb_entry
                        else:
                            new_kb = StandardKnowledgeBase(
                                original_description=clean_orig_desc, official_description=item_data.description_official,
                                ccc_code=clean_ccc, frequency=1, last_trained_at=datetime.utcnow()
                            )
                            db.add(new_kb)
                            local_kb_cache[clean_orig_desc] = new_kb
                            learned_count += 1
            
        order.processing_status = "PROCESSED"
        order.warnings = "[]"
        order.updated_by = current_user.id
        
    audit_log = AuditLog(
        user_id=current_user.id, mawb_no=update_data.mawb_no, hawb_no=hawb_no, action="HAWB_MANUAL_OVERRIDE_AND_LEARN",
        details={"old": old_data, "new": update_data.model_dump() if hasattr(update_data, 'model_dump') else update_data.dict()}
    )
    db.add(audit_log)
    db.commit()
    msg = "整單修改並完成審查！"
    if learned_count > 0: msg += f" (AI 已自動學習 {learned_count} 筆新詞彙)"
    return {"message": msg}

# ==========================================
# 黑名單 API
# ==========================================
@app.get("/api/blacklist")
def get_blacklist(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(BlacklistKeyword).order_by(BlacklistKeyword.id.desc()).all()
    return [{"id": i.id, "keyword": i.keyword, "created_at": i.created_at} for i in items]

class BlacklistCreate(BaseModel):
    keyword: str

@app.post("/api/blacklist")
def add_blacklist(item: BlacklistCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not item.keyword.strip(): raise HTTPException(status_code=400, detail="關鍵字不可為空")
    existing = db.query(BlacklistKeyword).filter(BlacklistKeyword.keyword == item.keyword.strip()).first()
    if existing: raise HTTPException(status_code=400, detail="該關鍵字已存在")
    new_kw = BlacklistKeyword(keyword=item.keyword.strip())
    db.add(new_kw)
    db.commit()
    return {"message": "新增成功"}

@app.delete("/api/blacklist/{item_id}")
def delete_blacklist(item_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    kw = db.query(BlacklistKeyword).filter(BlacklistKeyword.id == item_id).first()
    if not kw: raise HTTPException(status_code=404, detail="找不到該關鍵字")
    db.delete(kw)
    db.commit()
    return {"message": "刪除成功"}

# ==========================================
# 🌟 新增：分類字典 API
# ==========================================
class CategoryDictCreateUpdate(BaseModel):
    category_name: str
    suggested_name: str
    ccc_code: str

@app.get("/api/category_dict")
def get_category_dict(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(ProductCategoryDict).order_by(ProductCategoryDict.category_name, ProductCategoryDict.suggested_name).all()
    return [{"id": i.id, "category_name": i.category_name, "suggested_name": i.suggested_name, "ccc_code": i.ccc_code} for i in items]

@app.post("/api/category_dict")
def add_category_dict(item: CategoryDictCreateUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not item.category_name.strip() or not item.suggested_name.strip() or not item.ccc_code.strip():
        raise HTTPException(status_code=400, detail="欄位不可為空")
    new_cat = ProductCategoryDict(
        category_name=item.category_name.strip(),
        suggested_name=item.suggested_name.strip(),
        ccc_code=item.ccc_code.strip()
    )
    db.add(new_cat)
    db.commit()
    return {"message": "新增成功"}

@app.put("/api/category_dict/{item_id}")
def update_category_dict(item_id: int, item: CategoryDictCreateUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cat = db.query(ProductCategoryDict).filter(ProductCategoryDict.id == item_id).first()
    if not cat: raise HTTPException(status_code=404, detail="找不到該分類字典紀錄")
    if not item.category_name.strip() or not item.suggested_name.strip() or not item.ccc_code.strip():
        raise HTTPException(status_code=400, detail="欄位不可為空")
    
    cat.category_name = item.category_name.strip()
    cat.suggested_name = item.suggested_name.strip()
    cat.ccc_code = item.ccc_code.strip()
    db.commit()
    return {"message": "修改成功"}

@app.delete("/api/category_dict/{item_id}")
def delete_category_dict(item_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cat = db.query(ProductCategoryDict).filter(ProductCategoryDict.id == item_id).first()
    if not cat: raise HTTPException(status_code=404, detail="找不到該分類字典紀錄")
    db.delete(cat)
    db.commit()
    return {"message": "刪除成功"}

@app.get("/api/export/{mawb_no}")
def export_mawb_excel(mawb_no: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(SeaExpressOrder).filter(SeaExpressOrder.mawb_no == mawb_no).order_by(SeaExpressOrder.hawb_no, SeaExpressOrder.item_no).all()
    if not orders: raise HTTPException(status_code=404, detail="找不到該主單號的資料")

    export_data = []
    for o in orders:
        export_data.append({
            "主提單號 (MAWB)": o.mawb_no, "分提單號 (HAWB)": o.hawb_no, "項次": o.item_no,
            "通關品名": o.description_official or "", "原始品名": o.description_original or "",
            "稅則號列 (CCC Code)": o.ccc_code or "", "數量": o.qty, "數量單位": o.qty_unit or "",
            "單價": o.unit_price, "幣別": o.currency or "TWD", "總金額": o.total_amount,
            "淨重 (KG)": o.net_weight, "毛重 (KG)": o.gross_weight, "總件數 (箱數)": o.cartons,
            "件數單位": o.ctn_unit or "", "收件人名稱": o.consignee_name or "",
            "收件人電話": o.consignee_phone or "", "收件人地址": o.consignee_address or "",
            "收件人統編": o.consignee_vat_no or "", "寄件人名稱": o.shipper_name or "",
            "寄件人電話": o.shipper_phone or "", "寄件人地址": o.shipper_address or "",
            "產地": o.origin_country or "", "交易條件": o.trade_term or "", "標記 (Marks)": o.marks or "",
            "系統處理狀態": "已審查" if o.processing_status == "PROCESSED" else "異常未處理"
        })

    df = pd.DataFrame(export_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False, sheet_name='標準報關資料')
    output.seek(0)
    filename = f"海快報關資料_{mawb_no}.xlsx"
    encoded_filename = urllib.parse.quote(filename)
    return StreamingResponse(
        output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"}
    )

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "src", "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path): return FileResponse(index_path)
    return {"message": "找不到 index.html"}

if __name__ == "__main__":
    import uvicorn
    print("🚀 啟動海快報關 Web 伺服器...")
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)