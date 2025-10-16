import asyncio
from math import log
import os
import uuid
import aiohttp
import traceback
from zoneinfo import ZoneInfo
from langgraph.graph import StateGraph
from schemas.response import ChatResponse
from fastapi.responses import PlainTextResponse
from datetime import timedelta, datetime, timezone

from core.graph.state import AgentState, init_state
from schemas.response import ResponseModel
from repository.async_repo import AsyncCustomerRepo, AsyncEventRepo, AsyncSessionRepo

from log.logger_config import setup_logging
from dotenv import load_dotenv

load_dotenv()
logger = setup_logging(__name__)
async_customer_repo = AsyncCustomerRepo()
async_session_repo = AsyncSessionRepo()
async_event_repo = AsyncEventRepo()

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
N_DAYS = int(os.getenv("N_DAYS"))

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
    customer: dict,
    config: dict,
    graph: StateGraph
) -> ResponseModel:
    try:
        state: AgentState = customer["sessions"][0]["state_base64"]
        if not state:
            state = init_state()

        state["user_input"] = user_input
        state["chat_id"] = chat_id
        
        state["customer_id"] = customer["id"]
        state["name"] = customer["name"]
        state["phone"] = customer["phone"]
        state["email"] = customer["email"]
        state["session_id"] = customer["sessions"][0]["id"]

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
            new_session = await async_session_repo.create_session(
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

            end_session = await async_session_repo.update_end_session(session_id=session["id"])
            if not end_session:
                logger.error(f"Error in DB -> Cannot update session id: {session["id"]}")
                return ResponseModel(
                    content=None,
                    error="Lỗi không thể cập nhật thread_id"
                )
            logger.info(f"Close session successfully id: {end_session["id"]}")
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
    customer_id: int
) -> ResponseModel:
    try:
        deleted_customer = await async_customer_repo.delete_customer(customer_id=customer_id)

        if not deleted_customer:
            logger.error(f"Lỗi ở cấp DB -> Không xóa khách với id: {customer_id}")
            return ResponseModel(
                content=None,
                error="Lỗi không thể xóa khách hàng"
            )
            
        else:
            logger.info(f"Xóa thành công khách với id: {customer_id}")

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
        
async def send_to_webhook(text: str, chat_id: str):
    """
    Gửi response data đến webhook URL
    Args:
        text (str): Nội dung tin nhắn
        chat_id (str): ID của chat
    """
    try:
        payload = {
            "chat_id": chat_id,
            "response": text,
            "timestamp": traceback.format_exc()
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

async def _create_session_and_event(customer: dict, thread_id: str, event_type: str) -> bool:
    new_session = await async_session_repo.create_session(
        customer_id=customer["id"],
        thread_id=thread_id
    )
    if not new_session:
        logger.error("Error in DB -> Cannot create session")
        return False
    logger.info(f"Create session successfully id: {new_session["id"]}")
    
    new_event = await async_event_repo.create_event(
        customer_id=customer["id"],
        session_id=new_session["id"],
        event_type=event_type
    )
    if not new_event:
        logger.error("Error in DB -> Cannot create event")
        return False
    logger.info(f"Create event successfully id: {new_event["id"]}")
    
    return True

async def _handle_old_customer(customer: dict):
    if customer["sessions"]:
        session = customer["sessions"][0]
        last_active_at = session["last_active_at"]
        
        if _is_expired_over_n_days_vn(last_active_at=last_active_at):
            logger.info("Customer last active exceed specify day -> create new session")
            thread_id = str(uuid.uuid4())

            # Create new session -> end old session -> add new event
            session_and_event = await _create_session_and_event(
                customer=customer, 
                thread_id=thread_id,
                event_type="returning_customer"
            )
            if not session_and_event:
                return None, None

            end_session = await async_session_repo.update_end_session(session_id=session["id"])
            if not end_session:
                logger.error(f"Error in DB -> Cannot close session id: {session["id"]}")
                return None, None
            logger.info(f"Close session successfully id: {end_session["id"]}")
        else:
            logger.info("Customer last active does not exceed specify day -> update last active session")
            update_session = await async_session_repo.update_last_active_session(session_id=session["id"])
            if not update_session:
                logger.error(f"Error in DB -> Cannot update last active session id: {session["id"]}")
            logger.info(f"Update last active session successfully id: {update_session["id"]}")

            thread_id = session["thread_id"]
    else:
        # Trường hợp này sảy ra chỉ khi đã tạo khách thành công nhưng có lỗi trong quá
        # trình tạo session -> session không tồn tại
        thread_id = str(uuid.uuid4())
        session_and_event = await _create_session_and_event(
            customer=customer, 
            thread_id=thread_id,
            event_type="new_customer"
        )
        if not session_and_event:
            return None, None

    customer = await async_customer_repo.find_customer(chat_id=customer["chat_id"])
    if not customer:
        logger.error("Error in DB -> Cannot find customer after create")
        return None, None
    
    return customer, thread_id

async def _handle_new_customer(chat_id: str) -> tuple[None, None] | tuple[dict, str]:
    # Create new thread_id -> create new customer -> create new_session -> add new event
    thread_id = str(uuid.uuid4())
    
    customer = await async_customer_repo.create_customer(chat_id=chat_id)
    if not customer:
        logger.error("Error in DB -> Cannot create customer")
        return None, None
    logger.info(f"Create customer successfully id: {customer["id"]}")
    
    session_and_event = await _create_session_and_event(
        customer=customer, 
        thread_id=thread_id,
        event_type="new_customer"
    )
    if not session_and_event:
        return None, None
    
    customer = await async_customer_repo.find_customer(chat_id=chat_id)
    if not customer:
        logger.error("Error in DB -> Cannot find customer after create")
        return None, None
    
    return customer, thread_id

async def _handle_customer(chat_id: str) -> tuple[None, None, None] | tuple[dict, str, bool]:
    customer = await async_customer_repo.find_customer(chat_id=chat_id)
    new_customer_flag = False
        
    if customer:
        logger.info(f"Customer exist id: {customer["id"]}")
        
        customer, thread_id = await _handle_old_customer(customer=customer)
        logger.info(f"Handle old customer id: {customer["id"]} | thread_id: {thread_id}")
    else:
        # Customer is new -> create customer and add event
        logger.info("Not found customer -> create customer")
        
        customer, thread_id = await _handle_new_customer(chat_id=chat_id)
        logger.info(f"Handle new customer id: {customer["id"]} | thread_id: {thread_id}")
        new_customer_flag = True
    
    if not customer or not thread_id:
        return None, None, None
    
    return customer, thread_id, new_customer_flag

async def _handle_final_process(
    customer: dict,
    graph: StateGraph,
    config: dict,
    thread_id: str
):
    # Create event chatbot response successfully
    event = await async_event_repo.create_event(
        customer_id=customer["id"],
        session_id=customer["sessions"][0]["id"],
        event_type="bot_response_success"
    )
    if not event:
        logger.error("Error in DB -> Cannot add event record")
    logger.info(f"Add event bot_response_success successfully id: {event["id"]}")
    
    # Update state to session table
    session = await async_session_repo.update_state_session(
        state=graph.get_state(config).values,
        session_id=customer["sessions"][0]["id"],
    )
    if not session:
        logger.error("Error in DB -> Cannot update state in session record")
    logger.info(f"Update state to session record successfully id: {session["id"]}")
    
    # Delete the state in graph
    graph.checkpointer.delete_thread(thread_id)
    
async def _process_webhook_message(
    chat_id: str, 
    user_input: str, 
    graph: StateGraph
):
    messages = None
    try:
        customer, thread_id, new_customer_flag = await _handle_customer(chat_id=chat_id)
        if not customer or not thread_id:
            logger.error("Not found customer or thread_id")
            raise
        
        if customer["control_mode"] == "ADMIN":
            logger.info(f"Customer {chat_id} is under ADMIN control. Skipping bot response.")
            return
        
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(f"Tin nhắn của khách: {user_input}")

        if any(cmd in user_input for cmd in ["/start", "/restart"]):
            messages = await handle_new_chat(
                customer=customer,
                new_customer_flag=new_customer_flag
            )

            if not messages["error"]:
                logger.info("Create new chat session successfully")

        elif user_input == "/delete_me":
            messages = await handle_delete_me(customer_id=customer["id"])

            if not messages["error"]:
                logger.info("Delete new customer in DB successfully")
        else:
            messages = await handle_normal_chat(
                user_input=user_input,
                chat_id=chat_id,
                customer=customer,
                config=config,
                graph=graph
            )

            if not messages["error"]:
                logger.info("Chat process successfully -> add event")
                await _handle_final_process(
                    customer=customer,
                    graph=graph,
                    config=config,
                    thread_id=thread_id
                )
        
        if messages:
            if messages["error"]:
                logger.error(f"Error in processing chat: {messages['error']}")
                await send_to_webhook(
                    text="Lỗi server, xin vui lòng thử lại sau", 
                    chat_id=chat_id
                )
                raise
            else:
                await send_to_webhook(data=messages["content"], chat_id=chat_id)
                logger.info(f"Send to webhook: {messages}")
        else:
            logger.error("Messages is None")
            raise
            
        
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")

# ---------------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------------

async def handle_invoke_request(
    chat_id: str, 
    user_input: str, 
    graph: StateGraph
) -> ChatResponse:
    customer, thread_id, new_customer_flag = await _handle_customer(chat_id=chat_id)
    if not customer or not thread_id:
        return ChatResponse(
            status="error", 
            reply="Có lỗi xảy ra"
        )
    
    config = {"configurable": {"thread_id": thread_id}}
    
    logger.info(f"Tin nhắn của khách: {user_input}")

    if any(cmd in user_input for cmd in ["/start", "/restart"]):
        messages = await handle_new_chat(
            customer=customer,
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
        messages = await handle_delete_me(customer_id=customer["id"])
        
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
        customer=customer,
        config=config,
        graph=graph
    )
    
    if messages["error"]:
        return ChatResponse(
            status="error", 
            reply="Có lỗi xảy ra khi xử lý chat"
        )
    
    try:
        await _handle_final_process(
            customer=customer,
            graph=graph,
            config=config,
            thread_id=thread_id
        )
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")
    
    return ChatResponse(
        status="ok", 
        reply=messages["content"]
    )

async def handle_webhook_request(
    chat_id: str, 
    user_input: str, 
    graph: StateGraph
) -> ChatResponse:
    asyncio.create_task(
        _process_webhook_message(
            chat_id=chat_id,
            user_input=user_input,
            graph=graph
        )
    )
    
    return PlainTextResponse(content="OK", status_code=200)
