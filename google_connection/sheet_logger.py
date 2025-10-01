import os
import time
import json
import gspread
from typing import Literal
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from core.utils.function import convert_date_str
from log.logger_config import setup_logging

logger = setup_logging(__name__)

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
        booking_info: dict,
        service_items: list[dict]
    ):
        booking_date = convert_date_str(booking_info["booking_date"])

        if booking_info["customer"]["email"]:
            email = booking_info["customer"]["email"]
        else:
            email = "Không có"
            
        price = service_items[0]["services"]["price"]
        discount_value = service_items[0]["services"]["service_discounts"][0]["discount_value"]
        price_after_discount = int(price * (1 - discount_value / 100))

        main_row = [
            booking_info["id"],
            booking_info["customer"]["name"],
            booking_info["customer"]["phone"],
            email,
            booking_info["staff"]["name"],
            booking_info["room"]["name"],
            
            str(service_items[0]["services"]["type"]),
            str(service_items[0]["services"]["name"]),
            str(service_items[0]["services"]["duration_minutes"]),
            str(price),
            str(discount_value),
            str(price_after_discount),
            
            booking_info["start_time"],
            booking_info["end_time"],
            booking_info["total_time"],
            booking_date,
            booking_info["status"],
            booking_info["note"],
            booking_info["total_price"]
        ]
         
        rows_to_append = []
        rows_to_append.append(main_row)
        
        for item in service_items[1:]:
            price = item["services"]["price"]
            discount_value = item["services"]["service_discounts"][0]["discount_value"]
            price_after_discount = int(price * (1 - discount_value / 100))
            
            # indent hoặc dấu gạch để phân biệt dòng con
            row_child = [
                "",  # id trống
                "",  # customer_name trống
                "",  # phone
                "",  # email
                "",  # staff
                "",  # room
                str(item["services"]["type"]),
                str(item["services"]["name"]),
                str(item["services"]["duration_minutes"]),
                str(price),
                str(discount_value),
                str(price_after_discount),
                "",  # start_time
                "",  # end_time
                "",  # total_time
                "",  # booking_date
                "",  # status
                "",  # note
                ""   # total_price
            ]
            rows_to_append.append(row_child)
        
        try:
            # Gspread có method append_rows để append nhiều hàng cùng lúc. :contentReference[oaicite:0]{index=0}
            self.worksheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
        except Exception as e:
            logger.error(f"Error when appending multiple rows: {e}")
            time.sleep(3)
            try:
                # fallback: append từng hàng
                for r in rows_to_append:
                    self.worksheet.append_row(r, value_input_option='USER_ENTERED')
            except Exception as e2:
                logger.error(f"Second fallback failed: {e2}")