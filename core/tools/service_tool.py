import traceback
from typing import Optional, Annotated
from datetime import date, time, timedelta, datetime

from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId


from database.connection import supabase_client
from repository.sync_repo import AppointmentRepo, RoomRepo, StaffRepo
from core.utils.function import build_update, time_to_str, date_to_str
from core.graph.state import AgentState, BookInfo, Customer, Services, Staff

from log.logger_config import setup_logging

logger = setup_logging(__name__)

def _return_selective_services(
    services: dict,
    total_time: int,
    total_price: int
) -> str:
    index = 1
    service_detail = ""
    
    for service_key in services.keys():
        service_detail += (
            f"STT: {index}\n"
            f"Loại dịch vụ: {services[service_key]["service_type"]}\n"
            f"Tên dịch vụ: {services[service_key]["service_name"]}\n"
            f"Thời gian: {services[service_key]["duration_minutes"]}\n"
            f"Giá: {services[service_key]["price"]}\n"
        )
        
        index += 1
        
    service_detail += (
        f"Tổng thời gian: {total_time}\n"
        f"Tổng giá tiền: {total_price}\n"
    )
    
    return service_detail

def _update_services_state(
    services_state: dict,
    seen_services: dict,
    service_id_list: list[dict]
) -> tuple[dict, int, int]:
    if services_state is not None:
        services_state = {}

    total_time = 0
    total_price = 0
    
    for id in service_id_list:
        services_state[id] = Services(
            service_id=id,
            service_type=seen_services[id]["service_type"],
            service_name=seen_services[id]["service_name"],
            duration_minutes=seen_services[id]["duration_minutes"],
            price=seen_services[id]["price"],
        )
        
        total_time += seen_services[id]["duration_minutes"]
        total_price += seen_services[id]["price"]
    
    return services_state, total_time, total_price

@tool
def add_service_tool(
    service_id_list: Annotated[Optional[list[int]], (
        "Đây là danh sách các id của các dịch vụ mà khách chọn, "
        "được lấy trong danh sách seen_services"
    )],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Sử dụng tool này để lưu lại các dịch vụ mà khách chọn

    """
    logger.info(f"add_service_tool được gọi")
    
    if not service_id_list:
        logger.info("Không xác định được dịch vụ khách chọn")
        return Command(
            update=build_update(
                content=(
                    "Không biết khách chọn dịch vụ nào, hỏi lại khách"
                ),
                tool_call_id=tool_call_id
            )
        )
        
    try:
        services_state, total_time, total_price = _update_services_state(
            services_state=state["services"] if state["services"] is not None else {},  
            seen_services=state["seen_services"],
            service_id_list=service_id_list
        )
        
        logger.info("Thêm dịch vụ khách chọn vào state thành công")
        
        service_detail = _return_selective_services(
            services=services_state,
            total_time=state["total_time"] + total_time if state["total_time"] is not None else total_time,
            total_price=state["total_price"] + total_price if state["total_price"] is not None else total_price
        )
        
        return Command(
            update=build_update(
                content=(
                    "Đây là thông tin các dịch vụ mà khách chọn:\n"
                    f"{service_detail}\n"
                ),
                tool_call_id=tool_call_id,
                services=services_state,
                total_time=total_time,
                total_price=total_price
            )
        )
        
    except Exception as e:
        error_details = traceback.format_exc()
        logger.error(f"Exception: {e}")
        logger.error(f"Chi tiết lỗi: \n{error_details}")
        raise