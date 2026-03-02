import sys
import os
from database_models import SessionLocal, User, init_db
from auth import get_password_hash

def create_admin():
    print("=== 海快報關自動化系統 - 初始管理員建立工具 ===")
    
    # 關鍵修復：在建立帳號前，確保資料庫與所有資料表已經建立！
    print("正在檢查並初始化資料庫表結構...")
    init_db()
    
    username = input("請輸入管理員帳號 (預設: admin): ").strip() or "admin"
    password = input("請輸入管理員密碼 (預設: 123456): ").strip() or "123456"

    session = SessionLocal()
    try:
        # 檢查是否已存在
        existing_user = session.query(User).filter(User.username == username).first()
        if existing_user:
            print(f"❌ 帳號 '{username}' 已經存在！")
            return

        # 建立新管理員
        hashed_pw = get_password_hash(password)
        new_admin = User(
            username=username,
            password_hash=hashed_pw,
            role="ADMIN",
            is_active=True
        )
        session.add(new_admin)
        session.commit()
        print(f"✅ 成功建立超級管理員！帳號: {username} / 密碼: {password}")
        
    except Exception as e:
        session.rollback()
        print(f"❌ 建立失敗: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    create_admin()