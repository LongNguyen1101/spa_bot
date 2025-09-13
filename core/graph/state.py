from langgraph.graph.message import add_messages

from datetime import timedelta, date, time
from typing import Annotated, Any, TypedDict, Optional
from langgraph.prebuilt.chat_agent_executor import AgentState as Origin_AgentState


def _remain_dict(old: dict, new: dict | None):
    return new if new is not None else old

def _remain_value(old: Optional[Any], new: Optional[Any]) -> Optional[Any]:
    return new if new is not None else old

class SeenServices(TypedDict):
    service_id: int
    duration_minutes: int
    price: int

class AgentState(Origin_AgentState):
    messages: Annotated[list, add_messages]
    user_input: Annotated[str, _remain_value]
    chat_id: Annotated[str, _remain_value]
    next: Annotated[str, _remain_value]
    
    customer_id: Annotated[Optional[int], _remain_value]
    name: Annotated[Optional[str], _remain_value]
    phone: Annotated[Optional[str], _remain_value]
    email: Annotated[Optional[str], _remain_value]
    
    seen_services: Annotated[Optional[dict[int, SeenServices]], _remain_dict]
    services: Annotated[Optional[dict[int, SeenServices]], _remain_dict]
    staff_id: Annotated[Optional[int], _remain_value]
    room_id: Annotated[Optional[int], _remain_value]
    
    booking_date: Annotated[Optional[date], _remain_value]
    start_time: Annotated[Optional[time], _remain_value]
    end_time: Annotated[Optional[time], _remain_value]
    total_time: Annotated[Optional[timedelta], _remain_value]
    
    total_price: Annotated[Optional[int], _remain_value]
    book_info: Annotated[Optional[dict], _remain_dict]
    
    
def init_state() -> AgentState:
    return AgentState(
        messages=[],               
        user_input="",
        chat_id="",
        next="",
        
        customer_id=None,
        name=None,
        phone=None,
        email=None,
        
        seen_services=None,
        services=None,
        staff_id=None,
        room_id=None,
        
        booking_date=None,
        start_time=None,
        end_time=None,
        total_time=None,
        
        total_price=None,
        book_info=None
    )