import os
import time
import json
import gspread
from typing import Literal
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDS_PATH = os.getenv("CREDS_PATH")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME")
SPREADSHEET_ID_DEMO = os.getenv("SPREADSHEET_ID_DEMO")
WORKSHEET_NAME_DEMO = os.getenv("WORKSHEET_NAME_DEMO")

class SheetLogger:
    def __init__(self):
        self.creds_path = CREDS_PATH
        self.spreadsheet_id = SPREADSHEET_ID
        self.worksheet_name = WORKSHEET_NAME
        self.client = None
        self.worksheet = None
        self._connect()

    def _connect(self):
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_file(self.creds_path, scopes=scopes)
        self.client = gspread.authorize(creds)
        sh = self.client.open_by_key(self.spreadsheet_id)
        try:
            self.worksheet = sh.worksheet(self.worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # nếu worksheet name không tồn tại, tạo mới
            self.worksheet = sh.add_worksheet(title=self.worksheet_name, rows="1000", cols="20")

    def log(
        self, 
        customer_id: str,
        chat_id: str,
        customer_name: str,
        customer_phone: str,
        chat_histories: list,
        summary: str,
        type: Literal[
            "service_quality", 
            "hygiene_cleanliness", 
            "staff_behavior",
            "booking_scheduling"
        ],
        appointment_id: int,
        priority: Literal["low", "medium", "high"] = "medium",
        platform: str = "telegram",
    ):
        vn_tz = ZoneInfo("Asia/Ho_Chi_Minh")
        now_vn = datetime.now(vn_tz).replace(microsecond=0)
        
        date_str = now_vn.strftime("%d-%m-%Y")
        time_str = now_vn.strftime("%H:%M:%S")  
        
        row = [
            customer_id,
            chat_id,
            customer_name,
            customer_phone,
            platform,
            json.dumps(chat_histories, ensure_ascii=False),
            summary,
            appointment_id,
            type,
            priority,
            date_str,
            time_str
        ]
        try:
            self.worksheet.insert_row(row, index=2, value_input_option='USER_ENTERED')
        except Exception as e:
            # thử.retry hoặc log lỗi vào file local
            print(f"Error when appending to sheet: {e}")
            # optional: sleep rồi thử lại
            time.sleep(5)
            try:
                self.worksheet.insert_row(row, index=2, value_input_option='USER_ENTERED')
            except Exception as e2:
                print(f"Second attempt failed: {e2}")

class DemoLogger:
    def __init__(self):
        self.creds_path = CREDS_PATH
        self.spreadsheet_id = SPREADSHEET_ID_DEMO
        self.worksheet_name = WORKSHEET_NAME_DEMO
        self.client = None
        self.worksheet = None
        self._connect()

    def _connect(self):
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_file(self.creds_path, scopes=scopes)
        self.client = gspread.authorize(creds)
        sh = self.client.open_by_key(self.spreadsheet_id)
        try:
            self.worksheet = sh.worksheet(self.worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # nếu worksheet name không tồn tại, tạo mới
            self.worksheet = sh.add_worksheet(title=self.worksheet_name, rows="1000", cols="20")

    def log(
        self, 
        id: str,
        customer_id: str,
        staff_id: str,
        room_id: str,
        booking_date: str,
        start_time: str,
        end_time: str,
        status: str,
        total_price: str,
        create_date: str,
        total_time: str,
        note: str
    ):    
        row = [
            id,
            customer_id,
            staff_id,
            room_id,
            booking_date,
            start_time,
            end_time,
            total_time,
            status,
            total_price,
            create_date,
            note
        ]
        try:
            self.worksheet.append_row(row, value_input_option='USER_ENTERED')
        except Exception as e:
            # thử.retry hoặc log lỗi vào file local
            print(f"Error when appending to sheet: {e}")
            # optional: sleep rồi thử lại
            time.sleep(5)
            try:
                self.worksheet.append_row(row, value_input_option='USER_ENTERED')
            except Exception as e2:
                print(f"Second attempt failed: {e2}")
