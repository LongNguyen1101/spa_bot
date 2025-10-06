import os
import uuid
import traceback
from typing import Literal
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from datetime import timedelta, datetime, timezone

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from database.connection import supabase_client
from repository.async_repo import AsyncCustomerRepo
from core.graph.build_graph import create_main_graph
from services.v4.process_chat import (
    handle_delete_me, 
    handle_normal_chat, 
    handle_new_chat,
    send_to_webhook
)

from log.logger_config import setup_logging

load_dotenv()
logger = setup_logging(__name__)

N_DAYS = os.getenv("N_DAYS")

router = APIRouter()
graph = create_main_graph()
async_customer_repo = AsyncCustomerRepo(supabase_client=supabase_client)

class ChatRequest(BaseModel):
    chat_id: str
    user_input: str

class ChatResponse(BaseModel):
    status: Literal["ok", "error"]
    reply: str

def _is_expired_over_n_days_vn(last_active_at: str, n_days: int = N_DAYS) -> bool:
    """
    Returns:
        - True: Pass n days
        - False: Not pass n days
    """
    dt = datetime.fromisoformat(last_active_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    tz_vn = ZoneInfo("Asia/Ho_Chi_Minh")
    now_vn = datetime.now(tz_vn)

    dt_vn = dt.astimezone(tz_vn)
    delta = now_vn - dt_vn
    
    return delta > timedelta(days=n_days)

async def _handle_old_customer(last_active_at: str, session: dict, customer: dict) -> str | None:
    if _is_expired_over_n_days_vn(last_active_at=last_active_at):
        thread_id = str(uuid.uuid4())
        
        # Create new session -> end old session -> add new event
        new_session = await async_customer_repo.create_session(
            customer_id=customer["id"],
            thread_id=thread_id
        )
        if not new_session:
            logger.error("Error in DB -> Cannot create session")
            return None
        logger.info(f"Create session successfully id: {new_session["id"]}")
        
        end_session = await async_customer_repo.update_end_session(session_id=session["id"])
        if not end_session:
            logger.error(f"Error in DB -> Cannot update session id: {session["id"]}")
            return None
        logger.info(f"Create session successfully id: {new_session["id"]}")
        
        new_event = await async_customer_repo.create_event(
            customer_id=customer["id"],
            session_id=new_session["id"],
            event_type="returning_customer"
        )
        if not new_event:
            logger.error("Error in DB -> Cannot create event")
            return None
        logger.info(f"Create event successfully id: {new_event["id"]}")
        
        return thread_id
    return session["thread_id"]

async def _handle_new_customer(chat_id: str) -> tuple[None, None] | tuple[dict, str]:
    # Create new thread_id -> create new customer -> create new_session -> add new event
    thread_id = str(uuid.uuid4())
    
    customer = await async_customer_repo.create_customer(chat_id=chat_id)
    if not customer:
        logger.error("Error in DB -> Cannot create customer")
        return None, None
    logger.info(f"Create customer successfully id: {customer["id"]}")
    
    new_session = await async_customer_repo.create_session(
        customer_id=customer["id"],
        thread_id=thread_id
    )
    if not new_session:
        logger.error("Error in DB -> Cannot create session")
        return None, None
    logger.info(f"Create session successfully id: {new_session["id"]}")
    
    new_event = await async_customer_repo.create_event(
        customer_id=customer["id"],
        session_id=new_session["id"],
        event_type="new_customer"
    )
    if not new_event:
        logger.error("Error in DB -> Cannot create event")
        return None, None
    logger.info(f"Create event successfully id: {new_event["id"]}")
    
    return customer, thread_id

async def _handle_customer(chat_id: str) -> tuple[None, None, None] | tuple[dict, str, bool]:
    customer = await async_customer_repo.find_customer(chat_id=chat_id)
    new_customer_flag = True
        
    if customer:
        logger.info(f"Customer exist id: {customer["id"]}")
        
        session = customer["sessions"][0]
        last_active_at = session["last_active_at"]
        
        thread_id = await _handle_old_customer(
            last_active_at=last_active_at,
            session=session,
            customer=customer
        )
        
    else:
        # Customer is new -> create customer and add event
        logger.info("Not found customer -> create customer")
        
        customer, thread_id = await _handle_new_customer(chat_id=chat_id)
        new_customer_flag = False
    
    if not customer or not thread_id:
        return None, None, None
    
    return customer, thread_id, new_customer_flag


@router.post("/chat/invoke", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse | HTTPException:
    chat_id = request.chat_id
    user_input = request.user_input
    
    try:    
        customer, thread_id, new_customer_flag = await _handle_customer(chat_id=chat_id)
        if not customer or thread_id:
            return ChatResponse(
                status="error", 
                reply="Có lỗi xảy ra"
            )
            
        logger.info(f"Tin nhắn của khách: {user_input}")

        if any(cmd in user_input for cmd in ["/start", "/restart"]):
            messages = await handle_new_chat(
                chat_id=chat_id,
                new_customer_flag=new_customer_flag
            )

            if messages["error"]:
                return ChatResponse(
                    status="error", 
                    reply="Có lỗi xảy ra khi khởi tạo chat mới"
                )
            return ChatResponse(
                status="ok", 
                reply=messages["content"]
            )
        
        if user_input == "/delete_me":
            messages = await handle_delete_me(chat_id=chat_id)
            
            if messages["error"]:
                return ChatResponse(
                    status="error", 
                    reply="Có lỗi xảy ra khi xóa dữ liệu"
                )
            return ChatResponse(
                status="ok", 
                reply=messages["content"]
            )

        messages = await handle_normal_chat(
            user_input=user_input,
            chat_id=chat_id,
            thread_id=thread_id,
            customer=customer,
            graph=graph
        )
        
        if messages["error"]:
            return ChatResponse(
                status="error", 
                reply="Có lỗi xảy ra khi xử lý chat"
            )
        return ChatResponse(
            status="ok", 
            reply=messages["content"]
        )
            
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")
        
        raise HTTPException(
            status_code=500, 
            detail=f"Internal Server Error: {str(e)}"
        )