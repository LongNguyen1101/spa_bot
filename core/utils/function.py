import json
import asyncio
from typing import Any
from datetime import date, time, datetime

from langgraph.types import Command
from langgraph.graph import StateGraph
from langchain_core.messages import ToolMessage
from langchain_core.messages import AIMessage, HumanMessage

from core.graph.state import AgentState, Room
from repository.sync_repo import CustomerRepo
from database.connection import supabase_client
from core.graph.state import AgentState, BookInfo, Customer, Services, Staff

from log.logger_config import setup_logging

logger = setup_logging(__name__)
customer_repo = CustomerRepo(supabase_client=supabase_client)

def build_update(
    content: str,
    tool_call_id: Any,
    **kwargs
) -> dict:
    """
    Tạo payload `update` chuẩn cho LangGraph `Command` với một `ToolMessage`.

    Args:
        content (str): Nội dung phản hồi hiển thị cho người dùng.
        tool_call_id (Any): ID gọi tool để liên kết message với lần gọi công cụ.
        **kwargs: Các trường trạng thái bổ sung để cập nhật vào state.

    Returns:
        dict: Payload cập nhật cho `Command(update=...)`.
    """
    return {
        "messages": [
            ToolMessage
            (
                content=content,
                tool_call_id=tool_call_id
            )
        ],
        **kwargs
    }
    
def fail_if_missing(condition, message, tool_call_id) -> Command:
    """
    Trả về `Command` chứa thông báo hướng dẫn nếu điều kiện tiền đề không thỏa.

    Args:
        condition (Any): Điều kiện cần thỏa để tiếp tục xử lý.
        message (str): Nội dung hướng dẫn/nhắc người dùng bổ sung.
        tool_call_id (Any): ID gọi tool hiện tại.

    Returns:
        Command: Cập nhật message nếu thiếu điều kiện, ngược lại trả None (fallthrough).
    """
    if not condition:
        return Command(
            update=build_update(
                content=message,
                tool_call_id=tool_call_id,
            )
        )
        
async def test_bot(
    graph: StateGraph,
    state: AgentState,
    config: dict,
    mode: str = "updates"
):
    async for data in graph.astream(state, subgraphs=True, config=config, mode=mode):
        for key, value in data[1].items():
            if "messages" in value and value["messages"]:
                print(value["messages"][-1].pretty_print())
                
def pack_state_messgaes(messages: list) -> list[dict]:
    process_mess = []
    for mess in messages:
        process_mess.append({
            "type": mess.type,
            "content": mess.content
        })
    
    return process_mess

def unpack_state_messages(messages: list) -> list[dict]:
    unpack_messages = []
    for mess in messages:
        if mess["type"] == "human":
            unpack_messages.append(HumanMessage(content=mess["content"]))
        else:
            unpack_messages.append(AIMessage(content=mess["content"]))
            
    return unpack_messages

async def stream_messages(events: Any, thread_id: str):
    """
    Chuyển đổi luồng sự kiện từ graph thành SSE để client nhận theo thời gian thực.

    Args:
        events (Any): Async iterator sự kiện từ graph.astream.
        thread_id (str): Định danh luồng hội thoại.

    Yields:
        str: Chuỗi SSE dạng `data: {...}\n\n`.
    """
    last_printed = None
    closed = False

    try:
        async for data in events:
            for key, value in data.items():
                    messages = value.get("messages", [])
                    if not messages:
                        continue

                    last_msg = messages[-1]
                    if isinstance(last_msg, AIMessage):
                        content = last_msg.content.strip()
                        if content and content != last_printed:
                            last_printed = content
                            msg = {"content": content}
                            yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0.01)  # slight delay for smoother streaming
    except GeneratorExit:
        closed = True
        raise
    except Exception as e:
        error_dict = {"error": str(e), "thread_id": thread_id}
        yield f"data: {json.dumps(error_dict, ensure_ascii=False)}\n\n"
    finally:
        if not closed:
            yield "data: [DONE]\n\n"

async def check_state(config: dict, graph: StateGraph) -> AgentState:
    state = graph.get_state(config).values
    
    return state if state else None

async def update_state_customer(
    chat_id: str,
    graph: StateGraph
) -> dict | None:
    try:
        config = {"configurable": {"thread_id": chat_id}}

        get_state = graph.get_state(config).values
        get_state["messages"] = pack_state_messgaes(
            messages=get_state["messages"]
        )

        update_customer = customer_repo.update_customer_by_chat_id(
            update_payload={"state": get_state},
            chat_id=chat_id
        )
        
        return update_customer if update_customer else None
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise

def time_to_str(t):
    if t is None:
        return None
    if isinstance(t, datetime):
        return t.time().strftime("%H:%M:%S")
    if isinstance(t, time):
        return t.strftime("%H:%M:%S")
    if isinstance(t, str):
        return t
    raise TypeError(f"Unsupported time type: {type(t)}")


def date_to_str(d):
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date().isoformat()   # YYYY-MM-DD
    if isinstance(d, date):
        return d.isoformat()         # YYYY-MM-DD
    if isinstance(d, str):
        return d
    raise TypeError(f"Unsupported date type: {type(d)}")

def return_appointments(appointment_details: dict) -> str:
    index = 1
    if appointment_details["customer"]["email"]:
        email = appointment_details["customer"]["email"]
    else:
        email = "Không có"
        
    service_detail = (
        f"Thời gian đặt: {appointment_details["booking_date"]}\n"
        f"Thơi gian bắt đầu: {appointment_details["start_time"]}\n"
        f"Thời gian kết thúc: {appointment_details["end_time"]}\n\n"
        f"Tên khách: {appointment_details["customer"]["name"]}\n"
        f"SĐT khách: {appointment_details["customer"]["phone"]}\n"
        f"Email khách: {email}\n\n"
        f"Nhân viên thực hiện: {appointment_details["staff"]["name"]}\n"
        f"Phòng: {appointment_details["room"]["name"]}\n\n"
        "Các dịch vụ khách đã đăng ký:\n"
    )
    
    for service in appointment_details["appointment_services"]:
        service_detail += (
            f"STT: {index}\n"
            f"Loại dịch vụ: {service["services"]["type"]}\n"
            f"Tên dịch vụ: {service["services"]["name"]}\n"
            f"Thời gian: {service["services"]["duration_minutes"]}\n"
            f"Giá: {service["services"]["price"]}\n"
        )
        
        index += 1
    
    service_detail += (
        f"\nTổng giá tiền: {appointment_details["total_price"]}\n"
    )
    
    return service_detail

def update_book_info(appointment_details: dict) -> BookInfo:
    booked_services = {}
    for service in appointment_details["appointment_services"]:
        service = service["services"]
        booked_services[service["id"]] = Services(
            service_id=service["id"],
            service_type=service["type"],
            service_name=service["name"],
            duration_minutes=service["duration_minutes"],
            price=service["price"]
        )
    
    book_info = BookInfo(
        appointment_id=appointment_details["id"],
        booking_date=appointment_details["booking_date"],
        start_time=appointment_details["start_time"],
        end_time=appointment_details["end_time"],
        status=appointment_details["status"],
        total_price=appointment_details["total_price"],
        create_date=appointment_details["create_date"],
        
        services=booked_services,
        customer=Customer(
            customer_id=appointment_details["customer"]["id"],
            name=appointment_details["customer"]["name"],
            phone=appointment_details["customer"]["phone"],
            email=appointment_details["customer"]["email"] if appointment_details["customer"]["email"] else ""
        ),
        staff=Staff(
            staff_id=appointment_details["staff"]["id"],
            name=appointment_details["staff"]["name"]
        ),
        room=Room(
            room_id=appointment_details["room"]["id"],
            room_name=appointment_details["room"]["name"]
        )
    )
    
    return book_info