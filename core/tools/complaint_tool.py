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
from google_connection.sheet_logger import SheetLogger

from log.logger_config import setup_logging

load_dotenv()
logger = setup_logging(__name__)

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDS_PATH = os.getenv("CREDS_PATH")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME")

sheet_logger = SheetLogger(
    creds_path=CREDS_PATH,
    spreadsheet_id=SPREADSHEET_ID,
    worksheet_name=WORKSHEET_NAME
)

customer_repo = CustomerRepo(supabase_client=supabase_client)

def _get_chat_histories(chat_histories: list) -> list:
    formatted_histories = []
    for message in chat_histories:
        formatted_histories.append({
            "type": message.type,
            "content": message.content
        })
    
    return formatted_histories

@tool
def send_complaint_tool(
    summary: Annotated[str, "Tóm tắt nội dung khiếu nại của khách"],
    type: Annotated[Literal[
            "service_quality", 
            "hygiene_cleanliness", 
            "staff_behavior",
            "booking_scheduling"
        ], "Loại khiếu nại"],
    priority: Annotated[Literal["low", "medium", "high"], "Mức độ ưu tiên"],
    appointment_id: Annotated[Optional[int], "ID đơn đặt lịch liên quan đến khiếu nại, nếu có"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Log a customer complaint to Google Sheets and notify the chatbot.

    Parameters:
        - summary (str): 
            - Short description of the complaint. 
            - Using messages and context from the conversation to summarize.
            - Using Vietnamese.
        - type (Literal): Complaint category (service_quality, hygiene_cleanliness, staff_behavior, booking_scheduling).
        - priority (Literal): Urgency level (low, medium, high).
        - order_id (int, optional): Related order ID, if applicable.

    Returns: Command: Updates chatbot to confirm complaint submission.
    """
    try:
        logger.info("send_complaint_tool được gọi")
        sheet_logger.log(
            customer_id=state["customer_id"],
            chat_id=state["chat_id"],
            name=state["name"],
            phone=state["phone"],
            chat_histories=_get_chat_histories(state["messages"]),
            summary=summary,
            type=type,
            appointment_id=appointment_id,
            priority=priority,
            platform="telegram"
        )
        
        logger.info("Send to google sheet successfully")
        
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
    