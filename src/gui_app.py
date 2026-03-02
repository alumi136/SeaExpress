import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QDialog, QStackedWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

# 匯入資料庫與驗證模組
from database_models import SessionLocal
from auth import authenticate_user

class LoginDialog(QDialog):
    """系統登入視窗"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("海快報關自動化系統 - 登入")
        self.setFixedSize(350, 250)
        self.logged_in_user = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        # 標題
        title_label = QLabel("系統登入")
        title_label.setFont(QFont("Microsoft JhengHei", 18, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # 帳號輸入框
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("請輸入帳號")
        self.username_input.setMinimumHeight(35)
        layout.addWidget(self.username_input)

        # 密碼輸入框
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("請輸入密碼")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(35)
        layout.addWidget(self.password_input)

        # 登入按鈕
        self.login_btn = QPushButton("登 入")
        self.login_btn.setMinimumHeight(40)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D7;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #005A9E;
            }
        """)
        self.login_btn.clicked.connect(self.handle_login)
        layout.addWidget(self.login_btn)

        self.setLayout(layout)

    def handle_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "警告", "請輸入帳號與密碼！")
            return

        # 連線資料庫驗證
        session = SessionLocal()
        try:
            user = authenticate_user(session, username, password)
            if user:
                if not user.is_active:
                    QMessageBox.warning(self, "登入失敗", "此帳號已被停用，請聯絡管理員。")
                    return
                
                self.logged_in_user = {"id": user.id, "username": user.username, "role": user.role}
                self.accept() # 關閉登入視窗並回傳成功
            else:
                QMessageBox.critical(self, "登入失敗", "帳號或密碼錯誤！")
        except Exception as e:
            QMessageBox.critical(self, "系統錯誤", f"無法連線至資料庫：\n{e}")
        finally:
            session.close()

class MainWindow(QMainWindow):
    """系統主視窗"""
    def __init__(self, user_info):
        super().__init__()
        self.user_info = user_info
        self.setWindowTitle(f"海快報關自動化系統 v1.0 - 使用者: {self.user_info['username']} ({self.user_info['role']})")
        self.resize(1200, 800)
        self.init_ui()

    def init_ui(self):
        # 建立主選單
        menubar = self.menuBar()
        
        # 檔案選單
        file_menu = menubar.addMenu('檔案(&F)')
        import_action = file_menu.addAction('匯入客戶 Excel...')
        export_action = file_menu.addAction('匯出標準報關單...')
        file_menu.addSeparator()
        exit_action = file_menu.addAction('登出並離開(&X)')
        exit_action.triggered.connect(self.close)

        # 管理員專屬選單
        if self.user_info['role'] == 'ADMIN':
            admin_menu = menubar.addMenu('系統管理(&A)')
            admin_menu.addAction('帳號管理')
            admin_menu.addAction('黑名單管理')
            admin_menu.addAction('檢視修改軌跡 (Audit Log)')

        # 中央工作區 (先放一個歡迎標籤，下一階段會換成 Data Grid)
        central_widget = QWidget()
        layout = QVBoxLayout()
        
        welcome_label = QLabel(f"歡迎回來，{self.user_info['username']}！\n\n請從左上角「檔案」選單開始匯入 Excel 作單。")
        welcome_label.setFont(QFont("Microsoft JhengHei", 24))
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_label.setStyleSheet("color: #666666;")
        
        layout.addWidget(welcome_label)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # 狀態列
        self.statusBar().showMessage('系統就緒。')

def main():
    app = QApplication(sys.argv)
    
    # 設定全域字型
    font = QFont("Microsoft JhengHei", 10)
    app.setFont(font)

    # 1. 顯示登入視窗
    login_dialog = LoginDialog()
    if login_dialog.exec() == QDialog.DialogCode.Accepted:
        # 2. 登入成功，顯示主視窗
        user_info = login_dialog.logged_in_user
        main_window = MainWindow(user_info)
        main_window.show()
        sys.exit(app.exec())
    else:
        # 取消登入，結束程式
        sys.exit(0)

if __name__ == "__main__":
    main()