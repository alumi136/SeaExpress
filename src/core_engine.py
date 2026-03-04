import os
import math
import json
import logging
import pandas as pd
import re
from datetime import datetime
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import text
from database_models import SessionLocal, SeaExpressOrder, BlacklistKeyword
import unicodedata
import zhconv  # 🌟 新增：用於繁簡轉換

# --- 設定 Log ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SeaExpressEngine:
    def __init__(self):
        """初始化核心引擎，預載入知識庫與黑名單到記憶體"""
        self.session = SessionLocal()
        self.knowledge_base = self._load_knowledge_base()
        self.blacklist = self._load_blacklist()
        self.valid_cccs = self._load_valid_cccs()

    def __del__(self):
        self.session.close()

    def _load_knowledge_base(self):
        """
        將知識庫載入記憶體。
        回傳 dict: { '原始品名': {'official': '通關品名', 'ccc': '稅則', 'freq': 出現頻率} }
        """
        kb = {}
        try:
            # 🌟 新增：一併抓取 frequency，以便在模糊比對時決定優先順序
            result = self.session.execute(text("SELECT original_description, official_description, ccc_code, frequency FROM standard_knowledge_base"))
            for row in result:
                # 確保存入記憶體時都是大寫，方便比對
                key = str(row[0]).strip().upper() if row[0] else ""
                if key:
                    kb[key] = {'official': row[1], 'ccc': row[2], 'freq': row[3] or 1}
        except Exception as e:
            logging.error(f"載入知識庫失敗: {e}")
        return kb
        
    def _load_valid_cccs(self):
        cccs = set()
        try:
            result = self.session.execute(text("SELECT DISTINCT ccc_code FROM standard_knowledge_base"))
            for row in result:
                if row[0]: cccs.add(str(row[0]).strip())
        except Exception as e:
            pass
        return cccs

    def _load_blacklist(self):
        bl = []
        try:
            keywords = self.session.query(BlacklistKeyword).all()
            bl = [k.keyword for k in keywords]
        except Exception as e:
            pass
        return bl

    def _normalize_text(self, text_str):
        if not text_str or pd.isna(text_str): return ""
        val = unicodedata.normalize('NFKC', str(text_str)).upper()
        if '/' in val: val = val.split('/')[-1]
        val = re.sub(r'[^\w\s]', ' ', val)
        return re.sub(r'\s+', ' ', val).strip()

    def _format_ccc(self, ccc_str):
        ccc_str = str(ccc_str).strip()
        if ccc_str.endswith('.0'): ccc_str = ccc_str[:-2]
        clean_str = re.sub(r'\D', '', ccc_str)
        if len(clean_str) != 11: return clean_str, False
        return f"{clean_str[:4]}.{clean_str[4:6]}.{clean_str[6:8]}.{clean_str[8:10]}-{clean_str[10]}", True

    # ==========================================
    # 🌟 核心升級：繁簡與模糊比對引擎
    # ==========================================
    def _search_knowledge_base(self, raw_desc):
        """
        多階段搜尋知識庫：
        1. 精確比對 (原字串)
        2. 精確比對 (轉簡體)
        3. 精確比對 (轉繁體)
        4. 模糊比對 (包含查找，以 freq 與長度決選)
        """
        if not raw_desc:
            return None

        # 步驟 0：基礎清洗 (轉大寫、去符號)
        clean_desc = self._normalize_text(raw_desc)
        if not clean_desc:
            return None

        # 步驟 1：原字串精確比對
        if clean_desc in self.knowledge_base:
            return self.knowledge_base[clean_desc]

        # 步驟 2：轉簡體精確比對
        desc_zh_cn = zhconv.convert(clean_desc, 'zh-cn')
        if desc_zh_cn != clean_desc and desc_zh_cn in self.knowledge_base:
            return self.knowledge_base[desc_zh_cn]

        # 步驟 3：轉繁體精確比對
        desc_zh_tw = zhconv.convert(clean_desc, 'zh-tw')
        if desc_zh_tw != clean_desc and desc_zh_tw in self.knowledge_base:
            return self.knowledge_base[desc_zh_tw]

        # 步驟 4：模糊包含比對 (Substring Matching)
        # 尋找知識庫中，有哪些 key 是「包含」在客戶匯入品名中的 (例如 "保溫杯" 包含於 "黑色不鏽鋼保溫杯")
        # 為了提高命中率，我們用「簡體版本」的客戶品名來進行包容比對
        matches = []
        for kb_key, kb_data in self.knowledge_base.items():
            # kb_key 是知識庫裡的短詞，desc_zh_cn 是客戶匯入的長詞
            # 這裡同時比對原字串、簡體、繁體，只要其中一種被包含就算中獎
            if kb_key in clean_desc or kb_key in desc_zh_cn or kb_key in desc_zh_tw:
                matches.append({
                    'key': kb_key,
                    'data': kb_data
                })

        if matches:
            # 若找到多個可能 (例如同時包含 "玩具" 與 "汽車玩具")
            # 排序邏輯：1. frequency 高的優先 -> 2. 長度長的優先 (越長通常越精確)
            matches.sort(key=lambda x: (x['data']['freq'], len(x['key'])), reverse=True)
            
            # 取第一名 (The Winner)
            winner = matches[0]
            logging.info(f"🔍 模糊比對成功: '{clean_desc}' -> 匹配到 '{winner['key']}' (頻率: {winner['data']['freq']})")
            return winner['data']

        # 若經過 4 個階段都找不到，回傳 None 交由人工處理
        return None

    # ==========================================
    # 欄位驗證與格式化輔助函式
    # ==========================================
    def clean_and_validate_phone(self, phone_str):
        """清洗並驗證電話號碼 (過濾符號，檢查 09 或 0 開頭)"""
        if not phone_str or pd.isna(phone_str): 
            return "", True
            
        phone_str = str(phone_str).strip()
        if phone_str.endswith('.0'):
            phone_str = phone_str[:-2]
            
        clean_phone = re.sub(r'[\s\-\(\)]', '', phone_str)
        if not clean_phone:
            return "", True
            
        if len(clean_phone) == 9 and clean_phone.startswith('9'):
            clean_phone = '0' + clean_phone
            
        if re.match(r'^0\d{8,9}$', clean_phone):
            return clean_phone, True
        return clean_phone, False

    def validate_vat_id(self, vat_str):
        """驗證並格式化身分證與統編"""
        if not vat_str or pd.isna(vat_str): 
            return "", True
            
        vat_str = str(vat_str).strip()
        if vat_str.endswith('.0'):
            vat_str = vat_str[:-2]
            
        clean_vat = vat_str.upper()
        if not clean_vat:
            return "", True
            
        if re.match(r'^[A-Z]\d{9}$', clean_vat) or re.match(r'^\d{8}$', clean_vat):
            return clean_vat, True
        return clean_vat, False

    def normalize_for_tracking(self, text_str):
        """將字串忽略大小寫並去除所有空白，用於化整為零追蹤"""
        if not text_str or pd.isna(text_str): 
            return ""
        return re.sub(r'\s+', '', str(text_str)).upper()

    # ==========================================
    
    def _find_col(self, columns, keywords, exclude_words=None):
        exclude_words = exclude_words or []
        for i, col in enumerate(columns):
            col_str = str(col).lower().replace('\n', '').replace(' ', '')
            for kw in keywords:
                if col_str == kw.lower(): return i
        for i, col in enumerate(columns):
            col_str = str(col).lower().replace('\n', '').replace(' ', '')
            if any(excl.lower() in col_str for excl in exclude_words): continue
            for kw in keywords:
                if kw.lower() in col_str: return i
        return None

    def _find_col_fallback(self, row, columns, keywords):
        idx = self._find_col(columns, keywords)
        return str(row.iloc[idx]).strip() if idx is not None and pd.notna(row.iloc[idx]) else ""

    def parse_excel(self, filepath):
        """智慧解析 Excel (全欄位抓取)"""
        df_preview = pd.read_excel(filepath, header=None, nrows=10)
        header_idx = 2 
        
        for i in range(10):
            row_values = [str(x).replace('\n', '').strip() for x in df_preview.iloc[i].values]
            if any('分提單' in val or '貨物名稱' in val or '品名' in val for val in row_values):
                header_idx = i
                break
                
        df = pd.read_excel(filepath, header=header_idx)
        columns = df.columns.tolist()
        
        idx = {
            'hawb': self._find_col(columns, ['分提單']),
            'item': self._find_col(columns, ['貨物編號', '項次']),
            'desc': self._find_col(columns, ['貨物名稱', '品名']),
            'ccc': self._find_col(columns, ['貨品分類號列', '稅則'], exclude_words=['代碼']),
            'brand': self._find_col(columns, ['品牌']),
            'spec': self._find_col(columns, ['規格']),
            'qty': self._find_col(columns, ['數量'], exclude_words=['單位', '代碼']),
            'qty_unit': self._find_col(columns, ['數量單位']),
            'price': self._find_col(columns, ['單價'], exclude_words=['代碼', '幣']),
            'currency': self._find_col(columns, ['單價幣代碼', '幣別']),
            'total': self._find_col(columns, ['總金額', '發票總金額'], exclude_words=['幣', '代碼']),
            'nw': self._find_col(columns, ['淨重']),
            'gw': self._find_col(columns, ['毛重']),
            'trade_term': self._find_col(columns, ['交易條件']),
            'origin': self._find_col(columns, ['生產國別', '產地']),
            'marks': self._find_col(columns, ['標記', 'marks']),
            'cartons': self._find_col(columns, ['總件數', '件數', '箱數'], exclude_words=['單位']),
            'ctn_unit': self._find_col(columns, ['件數單位']),
            'courier_vat': self._find_col(columns, ['快遞業者統一編號']),
            'shp_name': self._find_col(columns, ['寄件人英文名稱', '寄件人名稱']),
            'shp_phone': self._find_col(columns, ['寄件人電話']),
            'shp_addr': self._find_col(columns, ['寄件人英文地址', '寄件人地址']),
            'cne_name': self._find_col(columns, ['收貨人英文名稱']),
            'cne_name_ch': self._find_col(columns, ['收貨人中文名稱']),
            'cne_addr': self._find_col(columns, ['收貨人英文地址']),
            'cne_addr_ch': self._find_col(columns, ['收貨人中文地址']),
            'cne_phone': self._find_col(columns, ['收貨人電話', '收件電話']),
            'cne_vat': self._find_col(columns, ['收貨人統一編號', '統編']),
            'cne_id_type': self._find_col(columns, ['收貨人身分識別碼']),
            'manifest': self._find_col(columns, ['艙單號碼', '裝貨單號碼']),
            'container': self._find_col(columns, ['貨櫃資料']),
            'tax_note': self._find_col(columns, ['申報繳納稅款']),
            'remark': self._find_col(columns, ['備註']),
            'logistics_no': self._find_col(columns, ['物流单号', '物流單號']),
            'no_711': self._find_col(columns, ['7-11單號'])
        }

        raw_data = []
        current_hawb = None
        
        def get_str(row, i): 
            if i is None or pd.isna(row.iloc[i]):
                return ""
            val = str(row.iloc[i]).strip()
            if val.endswith('.0') and val[:-2].isdigit():
                val = val[:-2]
            return val
            
        def get_float(row, i):
            try:
                if i is not None and pd.notna(row.iloc[i]):
                    val_str = str(row.iloc[i]).replace(',', '').strip()
                    return float(val_str) if val_str else 0.0
                return 0.0
            except: 
                return 0.0

        for index, row in df.iterrows():
            hawb_val = get_str(row, idx['hawb'])
            if hawb_val and hawb_val.lower() != 'nan': 
                current_hawb = hawb_val
                
            if not current_hawb: continue
            
            desc_val = get_str(row, idx['desc'])
            if not desc_val or desc_val.lower() == 'nan': continue

            item_no_val = get_str(row, idx['item'])
            parsed_item_no = int(float(item_no_val)) if item_no_val and item_no_val.replace('.', '', 1).isdigit() else 0

            item_data = {'hawb_no': current_hawb, 'item_no': parsed_item_no, 'description_original': desc_val}
            for key in idx:
                if key not in ['hawb', 'item', 'desc']:
                    item_data[key] = get_float(row, idx[key]) if key in ['qty', 'price', 'total', 'nw', 'gw', 'cartons'] else get_str(row, idx[key])
            
            if not item_data['cne_name'] and idx['cne_name'] is None: 
                item_data['cne_name'] = self._find_col_fallback(row, columns, ['收件人', '收貨人'])
            if not item_data['cne_addr'] and idx['cne_addr'] is None: 
                item_data['cne_addr'] = self._find_col_fallback(row, columns, ['地址'])
                
            raw_data.append(item_data)
            
        return raw_data

    def apply_business_rules(self, raw_data, mawb_no):
        orders = []
        hawb_groups = defaultdict(list)
        consignee_tracker = defaultdict(set)
        hawb_item_counter = defaultdict(int)
        
        hawb_net_weights = defaultdict(float)
        hawb_gross_weights = defaultdict(float)

        # 第一階段：逐項次處理
        for item in raw_data:
            hawb = item['hawb_no']
            desc = item['description_original']
            warnings = []
            status = "PENDING"
            
            hawb_item_counter[hawb] += 1
            final_item_no = item['item_no'] if item['item_no'] > 0 else hawb_item_counter[hawb]
            
            hawb_net_weights[hawb] += item['nw']
            if item['gw'] > hawb_gross_weights[hawb]: 
                hawb_gross_weights[hawb] = item['gw']
            
            # 🌟 呼叫升級版的多階段 AI 知識庫比對
            pred = self._search_knowledge_base(desc)
            official_desc = pred['official'] if pred else None

            client_ccc = item.get('ccc')
            final_ccc = None
            
            if client_ccc and str(client_ccc).lower() != 'nan' and str(client_ccc).strip() != '':
                formatted_ccc, is_valid_len = self._format_ccc(client_ccc)
                if not is_valid_len:
                    status = "MANUAL_REQUIRED"
                    warnings.append(f"客戶提供之稅則號列格式錯誤 (非11碼): {client_ccc}")
                    final_ccc = client_ccc
                else:
                    final_ccc = formatted_ccc
                    if len(self.valid_cccs) > 0 and final_ccc not in self.valid_cccs:
                        status = "MANUAL_REQUIRED"
                        warnings.append(f"客戶指定之稅則號不在系統知識庫中: {final_ccc}")
            else:
                final_ccc = pred['ccc'] if pred else None
                if not pred:
                    status = "MANUAL_REQUIRED"
                    warnings.append("AI 查無此品名稅號 (且客戶未提供)")

            for kw in self.blacklist:
                if kw in desc:
                    status = "MANUAL_REQUIRED"
                    warnings.append(f"觸發黑名單關鍵字: {kw}")
                    break

            raw_price = item['price']
            raw_total = item['total']
            qty = item['qty']
            new_price = math.floor(raw_price)
            new_total = new_price * qty
            
            if new_total != raw_total or raw_price != new_price:
                warnings.append(f"金額已校正 (原單價:{raw_price}, 原總價:{raw_total} -> 新單價:{new_price}, 新總價:{new_total})")

            # --- 電話格式清洗與驗證 ---
            clean_phone, is_phone_valid = self.clean_and_validate_phone(item.get('cne_phone'))
            if item.get('cne_phone') and not is_phone_valid:
                status = "MANUAL_REQUIRED"
                warnings.append(f"收件電話格式異常: {item.get('cne_phone')}")
            item['cne_phone'] = clean_phone

            # --- 統編/身分證格式驗證 ---
            clean_vat, is_vat_valid = self.validate_vat_id(item.get('cne_vat'))
            if item.get('cne_vat') and not is_vat_valid:
                status = "MANUAL_REQUIRED"
                warnings.append(f"收貨人統編/身分證格式異常: {item.get('cne_vat')}")
            item['cne_vat'] = clean_vat

            # 建立 ORM
            order = SeaExpressOrder(
                mawb_no=mawb_no, hawb_no=hawb, item_no=final_item_no,
                description_original=desc, description_official=official_desc, ccc_code=final_ccc,
                brand=item['brand'], spec=item['spec'], qty=qty, qty_unit=item['qty_unit'],
                unit_price=new_price, currency=item['currency'], total_amount=new_total,
                net_weight=item['nw'] if item['nw'] > 0 else None, gross_weight=item['gw'] if item['gw'] > 0 else None,
                trade_term=item['trade_term'], origin_country=item['origin'], marks=item['marks'],
                cartons=item['cartons'] if item['cartons'] > 0 else None, ctn_unit=item['ctn_unit'],
                courier_vat_no=item['courier_vat'],
                shipper_name=item['shp_name'], shipper_phone=item['shp_phone'], shipper_address=item['shp_addr'],
                consignee_name=item['cne_name'], consignee_name_ch=item['cne_name_ch'],
                consignee_address=item['cne_addr'], consignee_address_ch=item['cne_addr_ch'],
                consignee_phone=item['cne_phone'], consignee_vat_no=item['cne_vat'], consignee_id_type=item['cne_id_type'],
                manifest_no=item['manifest'], container_data=item['container'], tax_payment_note=item['tax_note'],
                remark=item['remark'], tracking_no_logistics=item['logistics_no'], tracking_no_711=item['no_711'],
                processing_status=status, warnings=warnings
            )
            orders.append(order)
            hawb_groups[hawb].append(order)
            
            # --- 追蹤化整為零：去除空白並統一轉大寫 ---
            norm_name = self.normalize_for_tracking(item.get('cne_name'))
            norm_addr = self.normalize_for_tracking(item.get('cne_addr'))
            norm_vat = self.normalize_for_tracking(item.get('cne_vat'))
            
            if norm_name: consignee_tracker[f"NAME:{norm_name}"].add(hawb)
            if norm_addr: consignee_tracker[f"ADDR:{norm_addr}"].add(hawb)
            if norm_vat: consignee_tracker[f"VAT:{norm_vat}"].add(hawb)

        # 第二階段：HAWB 彙總與驗證
        for hawb, items in hawb_groups.items():
            hawb_total_amt = sum(i.total_amount for i in items)
            
            total_nw = round(hawb_net_weights[hawb], 2)
            max_gw = round(hawb_gross_weights[hawb], 2)
            if max_gw > 0 and total_nw > max_gw:
                for i in items:
                    i.warnings.append(f"重量異常: 該單總淨重 ({total_nw}kg) 大於 總毛重 ({max_gw}kg)")
                    i.processing_status = "MANUAL_REQUIRED"
            
            carton_counts = [i for i in items if i.cartons and float(i.cartons) > 0]
            if len(carton_counts) > 1:
                for i in items:
                    i.warnings.append("多個項次填寫了箱數，請人工確認並保留第一行")
                    i.processing_status = "MANUAL_REQUIRED"
            elif len(carton_counts) == 1:
                if float(carton_counts[0].cartons) > 6:
                    for i in items: i.warnings.append(f"總箱數超過 6 箱 (目前 {carton_counts[0].cartons}箱)")

            if hawb_total_amt > 48000:
                for i in items: 
                    i.warnings.append(f"分提單總金額超標 (>48000): {hawb_total_amt}元")
                    i.processing_status = "MANUAL_REQUIRED"

            if any(i.processing_status == "MANUAL_REQUIRED" for i in items):
                for i in items: i.processing_status = "MANUAL_REQUIRED"

        # 第三階段：MAWB 化整為零防範 (降低門檻為 >= 3 件)
        suspicious_names = {k: v for k, v in consignee_tracker.items() if k.startswith("NAME:") and len(v) >= 3}
        suspicious_addrs = {k: v for k, v in consignee_tracker.items() if k.startswith("ADDR:") and len(v) >= 3}
        suspicious_vats = {k: v for k, v in consignee_tracker.items() if k.startswith("VAT:") and len(v) >= 3}
        
        for order in orders:
            norm_name = self.normalize_for_tracking(order.consignee_name)
            norm_addr = self.normalize_for_tracking(order.consignee_address)
            norm_vat = self.normalize_for_tracking(order.consignee_vat_no)
            
            # 使用 Set 避免同一個 HAWB 的多個 Items 被重複寫入同一條警告
            added_warnings = set() 
            
            if norm_name and f"NAME:{norm_name}" in suspicious_names:
                msg = f"相同收件人超過{len(suspicious_names[f'NAME:{norm_name}'])}件 (姓名重複)"
                if msg not in added_warnings:
                    order.warnings.append(msg)
                    added_warnings.add(msg)
                    order.processing_status = "MANUAL_REQUIRED"
                    
            if norm_addr and f"ADDR:{norm_addr}" in suspicious_addrs:
                msg = f"相同收件人超過{len(suspicious_addrs[f'ADDR:{norm_addr}'])}件 (地址重複)"
                if msg not in added_warnings:
                    order.warnings.append(msg)
                    added_warnings.add(msg)
                    order.processing_status = "MANUAL_REQUIRED"
                    
            if norm_vat and f"VAT:{norm_vat}" in suspicious_vats:
                msg = f"相同收件人超過{len(suspicious_vats[f'VAT:{norm_vat}'])}件 (統編/身分證重複)"
                if msg not in added_warnings:
                    order.warnings.append(msg)
                    added_warnings.add(msg)
                    order.processing_status = "MANUAL_REQUIRED"

        # 將 Warnings 轉換為 JSON 字串
        for order in orders:
            if not order.warnings and order.processing_status == "PENDING":
                order.processing_status = "PROCESSED"
            order.warnings = json.dumps(order.warnings, ensure_ascii=False)

        return orders

    def process_and_save(self, filepath, mawb_no, import_mode='NEW', operator_id=None):
        try:
            logging.info(f"開始處理 Excel [{import_mode}]: MAWB={mawb_no}")
            raw_data = self.parse_excel(filepath)
            if not raw_data: return False, "無法從 Excel 中提取有效資料"
            
            existing_hawbs = set()
            if import_mode == 'NEW':
                count = self.session.query(SeaExpressOrder).filter(SeaExpressOrder.mawb_no == mawb_no).count()
                if count > 0:
                    return False, f"主單號 {mawb_no} 已存在！若要加入資料，請選擇「附加到現存主單」模式。"
            elif import_mode == 'APPEND':
                result = self.session.query(SeaExpressOrder.hawb_no).filter(SeaExpressOrder.mawb_no == mawb_no).distinct().all()
                existing_hawbs = {row[0] for row in result}

            filtered_data = []
            skipped_hawbs = set()
            for item in raw_data:
                if item['hawb_no'] in existing_hawbs:
                    skipped_hawbs.add(item['hawb_no'])
                    continue
                filtered_data.append(item)

            if not filtered_data:
                return False, f"匯入失敗：Excel 中的所有分提單號 ({len(skipped_hawbs)}筆) 在該主單中皆已存在，全部略過。"

            orders = self.apply_business_rules(filtered_data, mawb_no)
            
            for order in orders:
                if operator_id: order.updated_by = operator_id
                self.session.add(order)
            self.session.commit()
            
            msg = f"成功匯入 {len(orders)} 筆資料。"
            if skipped_hawbs: msg += f" (另有 {len(skipped_hawbs)} 筆分提單因重複已自動略過)"
            
            return True, msg
            
        except Exception as e:
            self.session.rollback()
            logging.error(f"處理失敗: {e}", exc_info=True)
            return False, str(e)