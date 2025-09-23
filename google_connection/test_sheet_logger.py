import json
import os
from dotenv import load_dotenv
from sheet_logger import SheetLogger

load_dotenv()

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDS_PATH = os.getenv("CREDS_PATH")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME")

# Khởi tạo logger
sheet_logger = SheetLogger(
    creds_path=CREDS_PATH,
    spreadsheet_id=SPREADSHEET_ID,
    worksheet_name=WORKSHEET_NAME
)

# Giả sử chatbot nhận được input mà không xử lý được:
user_id = 'user_12345'
user_input = "Spa em có mở cửa tới khuya không?"
bot_response = "Xin lỗi, mình chưa hiểu yêu cầu của bạn."

# Gọi log
sheet_logger.log(
    customer_id="1",
    chat_id="chat_12345",
    chat_histories=[
        {"role": "user", "content": user_input},
        {"role": "bot", "content": bot_response}
    ],
    summary="",
    type="service_quality",
    order_id=1,
    priority="medium",
    platform="telegram"
)

print("Đã gửi log lên Google Sheet.")
