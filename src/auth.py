import bcrypt
from sqlalchemy.orm import Session
from database_models import User

def get_password_hash(password: str) -> str:
    """將明碼密碼加密為 bcrypt hash"""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """驗證使用者輸入的密碼是否正確"""
    password_byte_enc = plain_password.encode('utf-8')
    hashed_password_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_byte_enc, hashed_password_bytes)

def authenticate_user(session: Session, username: str, password: str):
    """資料庫帳密比對"""
    user = session.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user