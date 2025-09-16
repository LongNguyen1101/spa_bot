from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

from typing import Optional, Annotated

from core.graph.state import AgentState
from database.connection import supabase_client
from repository.sync_repo import AppointmentRepo, RoomRepo, StaffRepo
from core.utils.function import (
    build_update, 
    return_appoointments,
    update_book_info
)

from log.logger_config import setup_logging

logger = setup_logging(__name__)

appointment_repo = AppointmentRepo(supabase_client=supabase_client)
room_repo = RoomRepo(supabase_client=supabase_client)
staff_repo = StaffRepo(supabase_client=supabase_client)

@tool
def cancel_booking_tool(
    appointment_id: Annotated[Optional[int], "ID của lịch hẹn mà khách muốn huỷ"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Sử dụng tool này để huỷ đặt lịch
    
    Tham số:
        - appointment_id (int | None): ID của lịch hẹn mà khách muốn huỷ, lấy trong book_info
    """
    logger.info(f"cancel_booking_tool được gọi")
    
    if not appointment_id:
        logger.info("Không xác định được lịch hẹn khách muốn huỷ")
        return Command(
            update=build_update(
                content=(
                    "Không biết khách muốn huỷ lịch hẹn nào, hỏi lại khách"
                ),
                tool_call_id=tool_call_id
            )
        )
    
    book_info = state["book_info"].copy()
    if appointment_id not in book_info:
        logger.info(f"Lịch hẹn với ID {appointment_id} không tồn tại trong book_info")
        return Command(
            update=build_update(
                content=(
                    f"Lịch hẹn với ID {appointment_id} không tồn tại"
                ),
                tool_call_id=tool_call_id
            )
        )
    
    try:
        success = appointment_repo.update_appointment_status(
            appointment_id=appointment_id,
            update_payload={"status": "cancelled"}
        )
        
        if not success:
            logger.error(f"Lỗi ở cấp DB -> Không thể huỷ lịch hẹn với ID {appointment_id}")
            return Command(
                update=build_update(
                    content=(
                        "Không thể huỷ lịch hẹn, xin lỗi khách và hứa sẽ khắc phục sớm nhất."
                    ),
                    tool_call_id=tool_call_id
                )
            )
            
        del book_info[appointment_id]
        logger.info(f"Huỷ lịch hẹn với ID {appointment_id} thành công")
        
        return Command(
            update=build_update(
                content=(
                    f"Đã huỷ lịch hẹn thành công. ID lịch hẹn: {appointment_id}."
                ),
                tool_call_id=tool_call_id,
                book_info=book_info
            )
        )
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise
    
@tool
def get_all_editable_booking(
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Sử dụng tool này để lấy tất cả các lịch hẹn có thể chỉnh sửa (status = 'booked') theo customer_id.

    Args:
        - customer_id (int): ID của khách hàng.
        - state (AgentState): Trạng thái hiện tại của agent.
        - tool_call_id (str): ID của tool call.
    """
    logger.info(f"get_all_editable_booking được gọi")
    
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
        booked_appointments = appointment_repo.get_all_booked_appointments(
            customer_id=state["customer_id"]
        )
        
        if not booked_appointments:
            logger.info("Không có lịch hẹn nào có thể chỉnh sửa")
            return Command(
                update=build_update(
                    content="Hiện tại không có lịch hẹn nào có thể chỉnh sửa.",
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
                f"{return_appoointments(appointment_details=booked)}\n\n"
            )
            
            index += 1
        
        logger.info("Lấy danh sách lịch hẹn thành công")
        return Command(
            update=build_update(
                content=(
                    "Đây là danh sách các lịch hẹn mà khách có thể chỉnh sửa:\n"
                    f"{formatted_appointments}"
                ),
                tool_call_id=tool_call_id,
                book_info=book_info
            )
        )
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise