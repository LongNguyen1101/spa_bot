import os
import uuid
import aiohttp
import traceback
from typing import Any, TypedDict
from langgraph.graph import StateGraph

from core.graph.state import init_state
from database.connection import supabase_client
from repository.async_repo import AsyncCustomerRepo

from log.logger_config import setup_logging
from dotenv import load_dotenv

load_dotenv()
logger = setup_logging(__name__)
async_customer_repo = AsyncCustomerRepo(supabase_client=supabase_client)

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

class ResponseModel(TypedDict):
    content: str | None
    error: str | None   

async def _get_or_create_uuid(chat_id: str) -> str:
    """
    Lấy `uuid` hiện tại của khách theo `chat_id`, nếu chưa tồn tại thì tạo mới và lưu.

    Args:
        chat_id (str): Định danh cuộc hội thoại/khách hàng.

    Returns:
        str: UUID hiện có hoặc mới tạo.
    """
    current_uuid = await async_customer_repo.get_uuid(chat_id=chat_id)
    
    if not current_uuid:
        new_uuid = str(uuid.uuid4())
        await async_customer_repo.update_uuid(chat_id=chat_id, new_uuid=new_uuid)
        return new_uuid

    return current_uuid

async def handle_normal_chat(
    user_input: str,
    chat_id: str,
    thread_id: str,
    customer: dict,
    graph: StateGraph
) -> ResponseModel:
    """
    Xử lý luồng chat thông thường: nạp state, cập nhật thông tin khách, gọi graph và trả về `events`.

    Args:
        user_input (str): Nội dung người dùng nhập.
        chat_id (str): Mã cuộc hội thoại.
        customer (dict): Thông tin khách hàng lấy từ DB.
        graph (StateGraph): Đồ thị tác vụ chính để suy luận.

    Returns:
        tuple[Any, str] | tuple[None, None]: Cặp (events, thread_id) hoặc (None, None) nếu lỗi.
    """
    try:
        config = {"configurable": {"thread_id": thread_id}}

        state = (graph.get_state(config).values 
                 if graph.get_state(config).values 
                 else init_state())

        state["user_input"] = user_input
        state["chat_id"] = chat_id
        
        state["customer_id"] = customer["id"]
        state["name"] = customer["name"]
        state["phone"] = customer["phone"]
        state["email"] = customer["email"]

        result = graph.invoke(state, config=config)
        data = result["messages"][-1].content

        return ResponseModel(
            content=data, 
            error=None
        )
    
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")
        
        return ResponseModel(
            content=None,
            error=str(e)
        )
        
async def handle_new_chat(
    customer: dict,
    new_customer_flag: bool
) -> ResponseModel:
    try:
        if new_customer_flag is False:
            logger.info("Old customer -> create new thread_id")
            session = customer["sessions"][0]
            thread_id = str(uuid.uuid4())

            # Create new session -> end old session -> NO add new event
            new_session = await async_customer_repo.create_session(
                customer_id=customer["id"],
                thread_id=thread_id
            )
            if not new_session:
                logger.error("Error in DB -> Cannot create session")
                return ResponseModel(
                    content=None,
                    error="Lỗi không thể cập nhật thread_id"
                )
            logger.info(f"Create session successfully id: {new_session["id"]}")

            end_session = await async_customer_repo.update_end_session(session_id=session["id"])
            if not end_session:
                logger.error(f"Error in DB -> Cannot update session id: {session["id"]}")
                return ResponseModel(
                    content=None,
                    error="Lỗi không thể cập nhật thread_id"
                )
            logger.info(f"Create session successfully id: {new_session["id"]}")
            logger.info(f"Cập nhật thread_id của khách: {customer["id"]} là {thread_id}")
        else:
            logger.info("New customer -> no need to update thread_id")

        response = (
            "Dạ em chào mừng khách đến với AnVie Spa 🌸 – "
            "nơi khách có thể dễ dàng đặt lịch và tìm hiểu các "
            "dịch vụ chăm sóc sắc đẹp, thư giãn trong không gian "
            "sang trọng, dịu nhẹ. Em rất hân hạnh được đồng hành và "
            "hỗ trợ khách để có trải nghiệm thư giãn trọn vẹn ạ."
        )

        return ResponseModel(
            content=response,
            error=None
        )
        
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")
        
        return ResponseModel(
            content=None,
            error=str(e)
        )
        
async def handle_delete_me(
    chat_id: str
) -> ResponseModel:
    """
    Dev only (delete customer with chat id): Xóa khách hàng khỏi DB.

    Args:
        chat_id (str): Định danh cuộc hội thoại.

    Yields:
        str: Chuỗi SSE dạng `data: {...}` và token `[DONE]` khi hoàn tất.
    """
    try:
        deleted_customer = await async_customer_repo.delete_customer(chat_id=chat_id)

        if not deleted_customer:
            logger.error(f"Lỗi ở cấp DB -> Không xóa khách với chat_id: {chat_id}")
            return ResponseModel(
                content=None,
                error="Lỗi không thể xóa khách hàng"
            )
            
        else:
            logger.info(f"Xóa thành công khách với chat_id: {chat_id}")

            response = (
                "Dev only: Đã xóa thành công khách hàng khỏi hệ thống."
            )

            return ResponseModel(
                content=response,
                error=None
            )
        
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")
        
        return ResponseModel(
            content=None,
            error=str(e)
        )
        
async def send_to_webhook(data: dict, chat_id: str):
    """
    Gửi response data đến webhook URL
    Args:
        data (dict): Dữ liệu response cần gửi
        chat_id (str): ID của chat
    """
    try:
        payload = {
            "chat_id": chat_id,
            "response": data,
            "timestamp": traceback.format_exc()  # Có thể thay bằng datetime.now().isoformat()
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                WEBHOOK_URL, 
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    logger.info(f"Đã gửi thành công response đến webhook cho chat_id: {chat_id}")
                else:
                    logger.error(f"Lỗi khi gửi đến webhook. Status: {response.status}, chat_id: {chat_id}")
                    
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")
        raise