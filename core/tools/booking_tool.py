from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

from typing import Optional, Annotated
from datetime import date, time, timedelta, datetime

from sqlalchemy import over

from core.graph.state import AgentState
from core.utils.function import build_update
from database.connection import supabase_client
from repository.sync_repo import AppointmentRepo, RoomRepo, StaffRepo

from log.logger_config import setup_logging

logger = setup_logging(__name__)

appointment_repo = AppointmentRepo(supabase_client=supabase_client)
room_repo = RoomRepo(supabase_client=supabase_client)
staff_repo = StaffRepo(supabase_client=supabase_client)

def _check_available_time_without_total_time(
    booking_date: date,
    start_time: time
):
    pass

def _check_available_time_with_total_time(
    booking_date_new: date,
    start_time_new: time,
    total_time: timedelta
):
    dt_start = datetime.combine(booking_date_new, start_time_new)
    dt_end = dt_start + total_time
    end_time_new = dt_end.time()
    
    overlap_appointments = appointment_repo.get_overlap_appointments(
        booking_date_new=booking_date_new,
        start_time_new=start_time_new,
        end_time_new=end_time_new
    )
    
    staffs = staff_repo.get_all_staff_return_dict()
    rooms = room_repo.get_all_rooms_return_dict()

    # Check available 
    for appointment in overlap_appointments:
        # Check room overlap
        if rooms.get(appointment["room_id"], None) is not None:
            rooms[appointment["room_id"]] = rooms[appointment["room_id"]] - 1

            # Delete room overlap
            if rooms[appointment["room_id"]] == 0:
                del rooms[appointment["room_id"]]

        # Delete staff overlap
        if staffs.get(appointment["staff_id"], None) is not None:
            del staffs[appointment["staff_id"]]
            
    return rooms, staffs
    



@tool
def check_available_booking(
    booking_date: Annotated[Optional[date], "Ngày tháng năm khách đặt lịch"],
    start_time: Annotated[Optional[time], "Thời gian khách muốn đặt lịch"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
):
    """
    """
    if not booking_date:
        logger.info("Không xác định được ngày khách đặt")
        return Command(
            build_update(
                content=(
                    "Khách chưa chọn ngày, hỏi khách"
                ),
                tool_call_id=tool_call_id
            )
        )
        
    if not start_time:
        logger.info("Không xác định được thời gian khách đặt")
        return Command(
            build_update(
                content=(
                    "Khách chưa chọn thời gian cụ thể, hỏi khách"
                ),
                tool_call_id=tool_call_id,
                booking_date=booking_date
            )
        )
        
    logger.info(f"Khách đặt ngày: {booking_date} vào lúc: {start_time}")