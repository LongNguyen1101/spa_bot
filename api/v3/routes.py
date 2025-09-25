from email.policy import HTTP
import traceback

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from services.utils import get_or_create_customer
from core.graph.build_graph import create_main_graph
from services.v3.process_chat import (
    handle_delete_me, 
    handle_normal_chat, 
    handle_new_chat,
    stream_messages
)

from log.logger_config import setup_logging

logger = setup_logging(__name__)

router = APIRouter()
graph = create_main_graph()

class ChatRequest(BaseModel):
    chat_id: str
    user_input: str

class ChatResponse(BaseModel):
    status: str
    data: dict

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Xử lý yêu cầu chat dạng streaming (v2) có kiểm soát luồng nghiệp vụ.

    Args:
        request (ChatRequest): Dữ liệu gồm `chat_id`, `user_input`.

    Returns:
        StreamingResponse: Dòng sự kiện SSE phản hồi.
    """
    user_input = request.user_input
    chat_id = request.chat_id
    
    try:    
        customer = await get_or_create_customer(chat_id=chat_id)
        
        logger.info(f"Lấy hoặc tạo mới khách: {customer}")
        logger.info(f"Tin nhắn của khách: {user_input}")

        if any(cmd in user_input for cmd in ["/start", "/restart"]):
            messages = await handle_new_chat(chat_id=chat_id)
            if messages["error"]:
                return ChatResponse(status="error", data=messages)
            return ChatResponse(status="ok", data=messages)
        
        if user_input == "/delete_me":
            deletion_result = await handle_delete_me(chat_id=chat_id)
            if deletion_result["error"]:
                return ChatResponse(status="error", data=deletion_result)
            return ChatResponse(status="ok", data=deletion_result)

        response = await handle_normal_chat(
            user_input=user_input,
            chat_id=chat_id,
            customer=customer,
            graph=graph
        )
        if response["error"]:
            return ChatResponse(status="error", data=response)
        return ChatResponse(status="ok", data=response)
            
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")
        
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")