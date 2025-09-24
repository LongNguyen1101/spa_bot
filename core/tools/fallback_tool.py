import os
import traceback
from dotenv import load_dotenv
from typing import Annotated, Literal, Optional

from httpcore import AnyIOBackend
from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

from core.graph.state import AgentState
from core.utils.function import build_update
from repository.sync_repo import CustomerRepo
from database.connection import supabase_client
from repository.sync_repo import AppointmentRepo
from core.utils.function import (
    build_update, 
    return_appointments,
    update_book_info
)

from google_connection.sheet_logger import SheetLogger
from log.logger_config import setup_logging

load_dotenv()
logger = setup_logging(__name__)
appointment_repo = AppointmentRepo(supabase_client=supabase_client)

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDS_PATH = os.getenv("CREDS_PATH")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME")

customer_repo = CustomerRepo(supabase_client=supabase_client)
sheet_logger = SheetLogger()

def _get_chat_histories(chat_histories: list) -> list:
    formatted_histories = []
    for message in chat_histories:
        if message.type == "tool" or message.content == "":
            continue
        
        formatted_histories.append({
            "type": message.type,
            "content": message.content
        })
    
    return formatted_histories

@tool
def send_fallback_tool(
    summary: Annotated[str, "Tóm tắt nội dung yêu cầu của khách"],
    type: Annotated[Literal[
            "service_quality", 
            "hygiene_cleanliness", 
            "staff_behavior",
            "booking_scheduling"
        ] | None, 
        "Loại khiếu nại, nếu có"
    ],
    priority: Annotated[Literal["low", "medium", "high"], "Mức độ ưu tiên"],
    appointment_id: Annotated[int | None, "ID đơn đặt lịch liên quan đến khiếu nại, nếu có"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Log a customer request to Google Sheets and notify the chatbot.

    Parameters:
        - summary (str): 
            - Short description of the request. 
            - Using messages and context from the conversation to summarize.
            - Using Vietnamese.
        - type (Literal | None):
            - Complaint category (service_quality, hygiene_cleanliness, staff_behavior, booking_scheduling).
            - If customer's request is not a complaint, set to None.
        - priority (Literal): Urgency level (low, medium, high).
        - appointment_id (int, optional): Related order ID in book_info, if applicable.

    Returns: Command: Updates chatbot to confirm complaint submission.
    """
    try:
        logger.info("send_complaint_tool được gọi")
        sheet_logger.log(
            customer_id=state["customer_id"],
            chat_id=state["chat_id"],
            customer_name=state["name"],
            customer_phone=state["phone"],
            chat_histories=_get_chat_histories(state["messages"]),
            summary=summary,
            type=type,
            appointment_id=appointment_id,
            priority=priority,
            platform="telegram"
        )
        
        logger.info("Send to google sheet successfully")
        
        response = customer_repo.add_complaints(
            complaint_payload={
                "customer_id": state["customer_id"],
                "chat_id": state["chat_id"],
                "customer_name": state["name"],
                "customer_phone": state["phone"],
                "chat_histories": _get_chat_histories(state["messages"]),
                "summary": summary,
                "type": type,
                "appointment_id": appointment_id,
                "priority": priority,
                "platform": "telegram"
            }
        )
        
        if not response:
            logger.error("Lỗi ở cấp DB -> Không thể cập nhật khiếu nại")
            return Command(
                update=build_update(
                    content=(
                        "Có lỗi trong quá trình gửi khiếu nại, xin lỗi khách"
                    ),
                    tool_call_id=tool_call_id
                )
            )
        
        logger.info("Send to supabase successfully")
        logger.info("Send complaint successfully")
        
        return Command(
            update=build_update(
                content="Khiếu nại đã được gửi đi, thông báo cho khách",
                tool_call_id=tool_call_id
            )
        )
        
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")
        raise
    
@tool
def get_all_booking_tool(
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Sử dụng tool này để lấy tất cả các lịch hẹn của khách theo customer_id.

    Parameters:
        - customer_id (int): ID của khách hàng.
    """
    logger.info(f"get_all_booking_tool được gọi")
    
    if not state["customer_id"]:
        logger.error("Không xác định được ID của khách hàng")
        return Command(
            update=build_update(
                content=(
                    "Có lỗi trong quá trình xác định khách hàng, xin lỗi khách"
                ),
                tool_call_id=tool_call_id
            )
        )
        
    try:
        # Lấy danh sách các lịch hẹn có trạng thái 'booked' theo customer_id
        booked_appointments = appointment_repo.get_all_appointments(
            customer_id=state["customer_id"]
        )
        
        if not booked_appointments:
            logger.info("Không có lịch hẹn nào của khách")
            return Command(
                update=build_update(
                    content="Hiện tại khách chưa đặt lịch hẹn nào, có thể khách nhầm lẫn",
                    tool_call_id=tool_call_id
                )
            )
        
        book_info = state["book_info"].copy() if state["book_info"] else {}
        formatted_appointments = ""
        index = 1
        
        for booked in booked_appointments:
            book_info[booked["id"]] = update_book_info(
                appointment_details=booked
            )
            
            formatted_appointments += (
                f"Đơn thứ {index}:\n"
                f"{return_appointments(appointment_details=booked)}\n\n"
            )
            
            index += 1
        
        logger.info("Lấy danh sách lịch hẹn thành công")
        return Command(
            update=build_update(
                content=(
                    "Đây là danh sách các lịch hẹn của khách:\n"
                    f"{formatted_appointments}"
                ),
                tool_call_id=tool_call_id,
                book_info=book_info
            )
        )
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")
        raise