from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

from typing import Optional, Annotated, Literal
from datetime import date, time, timedelta, datetime

from core.graph.state import AgentState
from database.connection import supabase_client
from repository.sync_repo import AppointmentRepo, RoomRepo, StaffRepo
from core.utils.function import (
    build_update, 
    time_to_str, 
    date_to_str,
    return_appoointments,
    update_book_info
)

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

def _check_available_with_end_time(
    booking_date_new: date,
    start_time_new: time,
    end_time_new: time
) -> tuple[dict, dict]:  
    overlap_appointments = appointment_repo.get_overlap_appointments(
        booking_date_new=booking_date_new,
        start_time_new=start_time_new,
        end_time_new=end_time_new
    )
    
    staffs = staff_repo.get_all_staff_return_dict()
    rooms = room_repo.get_all_rooms_return_dict()

    if not overlap_appointments:
        return rooms, staffs
    
    # Check available 
    for appointment in overlap_appointments:
        # Check room overlap
        if rooms.get(appointment["room_id"], None) is not None:
            rooms[appointment["room_id"]]["capacity"] = rooms[appointment["room_id"]]["capacity"] - 1

            # Delete room overlap
            if rooms[appointment["room_id"]] == 0:
                del rooms[appointment["room_id"]]

        # Delete staff overlap
        if staffs.get(appointment["staff_id"], None) is not None:
            del staffs[appointment["staff_id"]]
            
    return rooms, staffs

@tool
def resolve_weekday_to_date_tool(
    weekday: Annotated[Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], (
        "Thứ trong tuần mà khách muốn đặt lịch"
    )],
    next_week: Annotated[Literal[1, 2, 3], (
        "Số tuần tiếp theo (hoặc hiện tại) mà khách muốn đặt lịch"
    )],
    tool_call_id: Annotated[str, InjectedToolCallId]
):
    """
    Sử dụng tool này để chuyển đổi từ thứ trong tuần sang ngày tháng năm cụ thể
    
    Args:
        - weekday (str): Thứ trong tuần mà khách muốn đặt lịch, bắt buộc 1 trong các từ "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
        - next_week (int): Số tuần tiếp theo (hoặc hiện tại) mà khách muốn đặt lịch. 
        Nếu khách muốn đặt trong tuần hiện tại, thì next_week là 1.
        Nếu khách muốn đặt vào tuần sau, thì next_week là 2.
        Nếu khách muốn đặt vào tuần kế tiếp nữa, thì next_week là 3.
    """
    
    # map tên ngày sang số tuần theo Python datetime.weekday(): Monday=0 .. Sunday=6
    name_to_weekday = {
        "Monday": 0,
        "Tuesday": 1,
        "Wednesday": 2,
        "Thursday": 3,
        "Friday": 4,
        "Saturday": 5,
        "Sunday": 6
    }

    # kiểm tra weekday hợp lệ
    wd = name_to_weekday.get(weekday)
    if wd is None:
        raise ValueError(f"Invalid weekday name: {weekday}")

    reference_date = date.today()
    # tìm weekday của reference_date
    ref_wd = reference_date.weekday()  # 0..6

    days_until = (wd - ref_wd) % 7
    
    additional_weeks = next_week - 1
    total_days = days_until + additional_weeks * 7

    target_date = reference_date + timedelta(days=total_days)
    
    return Command(
        update=build_update(
            content=f"Ngày khách đặt: {target_date.isoformat()}",
            tool_call_id=tool_call_id
        )
    )


@tool
def check_available_booking_tool(
    booking_date_new: Annotated[Optional[str], "Ngày tháng năm cụ thể khách đặt lịch"],
    start_time_new: Annotated[Optional[str], "Thời gian khách muốn đặt lịch"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
):
    """
    Sử dụng tool này để kiểm tra ngày đặt và thời gian đặt của khách có còn lịch trống không
    
    Args:
        - booking_date_new (str | None): Ngày tháng năm mà khách đặt, có định dạng "%Y-%m-%d", bạn bắt buộc phải tuân theo định dạng này, dựa vào current_date để lấy ra ngày mà khách muốn đặt.
        - start_time_new (str | None): Giờ phút giây mà khách đặt, có định dạng "%H:%M:%S", bạn bắt buộc phải tuân theo định dạng này.
    """
    logger.info(f"check_available_booking được gọi")
    
    if not booking_date_new:
        logger.info("Không xác định được ngày khách đặt")
        return Command(
            update=build_update(
                content=(
                    "Khách chưa chọn ngày, hỏi khách"
                ),
                tool_call_id=tool_call_id
            )
        )
    booking_date_new = datetime.strptime(booking_date_new, "%Y-%m-%d").date()
    
    if not start_time_new:
        logger.info("Không xác định được thời gian khách đặt")
        return Command(
            update=build_update(
                content=(
                    "Khách chưa chọn thời gian cụ thể, hỏi khách"
                ),
                tool_call_id=tool_call_id,
                booking_date=booking_date_new
            )
        )
        
    try:
        start_time_new = datetime.strptime(start_time_new, "%H:%M:%S").time()
        logger.info(f"Khách đặt ngày: {booking_date_new} vào lúc: {start_time_new}")

        # Calculate end time
        dt_start = datetime.combine(booking_date_new, start_time_new)
        if state["total_time"]:
            dt_end = dt_start + timedelta(minutes=state["total_time"])
        else:
            dt_end = dt_start + timedelta(minutes=60)
        end_time_new = dt_end.time()

        rooms, staffs = _check_available_with_end_time(
            booking_date_new=booking_date_new,
            start_time_new=start_time_new,
            end_time_new=end_time_new
        )

        if not rooms or not staffs:
            logger.info(
                "Không có phòng trống hoặc nhân viên khả dụng "
                f"Danh sách phòng: {rooms} ||||| "
                f"Danh sách nhân viên: {staffs}"
            )

        logger.info("Tìm thấy phòng và nhân viên khả dụng")
        available_room, available_staff = list(rooms.keys())[0], list(staffs.keys())[0]

        logger.info(f"ID phòng khả dụng: {available_room} | ID nhân viên khả dụng: {available_staff}")
        logger.info("Kiểm tra phòng và nhân viên thành công")

        return Command(
            update=build_update(
                content=(
                    "Thông báo khách có lịch trống\n"
                    f"Đây là tên phòng của khách: {rooms[available_room]["name"]}\n"
                    f"Đây là tên nhân viên: {staffs[available_staff]}"
                ),
                tool_call_id=tool_call_id,
                booking_date=booking_date_new,
                start_time=start_time_new,
                end_time=end_time_new,
                room_id=available_room,
                room_name=rooms[available_room]["name"],
                staff_id=available_staff,
                staff_name=staffs[available_staff]
            )
        )
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise
    
@tool
def create_appointment_tool(
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """Sử dụng tool này để thêm lịch hẹn cho khách

    Chức năng: Tạo một đơn hàng mới dựa trên các sản phẩm có trong giỏ hàng và thông tin khách hàng (tên, SĐT, địa chỉ) đã được lưu trong state.
    """
    logger.info("create_appointment_tool được gọi")
    
    services = state["services"].copy()
    if not services:
        logger.info("Services rỗng")
        return Command(
            update=build_update(
                content="Khách chưa chọn dịch vụ nào, hỏi khách",
                tool_call_id=tool_call_id
            )
        )
    
    logger.info("Service có thông tin")
    customer_id = state.get("customer_id")
    name = state.get("name")
    phone = state.get("phone")

    # Không có đủ thông tin khách
    if not all([customer_id, name, phone]):
        logger.info(
            "Không có đủ thông tin khách "
            f"id: {customer_id} | "
            f"name: {name} | "
            f"phone: {phone}"
        )
        return Command(
            update=build_update(
                content=(
                    "Đây là các thông tin của khách:\n"
                    f"- Tên người nhận: {name if name else "Không có"}\n"
                    f"- Số điện thoại người nhận: {phone if phone else "Không có"}\n"
                    "Hỏi khách các thông tin còn thiếu"
                ),
                tool_call_id=tool_call_id
            )
        )

    try:
        logger.info("Đã đủ thông tin của khách -> tạo lịch hẹn")
        
        appointment_payload = {
            "customer_id": customer_id,
            "room_id": state["room_id"],
            "booking_date": date_to_str(state["booking_date"]),
            "start_time": time_to_str(state["start_time"]),
            "end_time": time_to_str(state["end_time"]),
            "status": "booked",
            "total_price": state["total_price"],
            "staff_id": state["staff_id"]
        }
        
        appointment_res = appointment_repo.create_appointment(
            appointment_payload=appointment_payload
        )
        
        if not appointment_res:
            logger.error("Lỗi ở cấp DB -> Không thể tạo lịch đặt")
            return Command(
                update=build_update(
                    content="Lỗi không thể tạo lịch đặt, xin khách thử lại"
                ),
                tool_call_id=tool_call_id
            )
        
        new_appointment_id = appointment_res.get("id")
        services_to_insert = []
        logger.info(f"Tạo bản ghi trong appointments thành công với ID: {new_appointment_id}")
        
        for item in services.values():
            services_to_insert.append({
                "appointment_id": new_appointment_id, 
                "service_id": item["service_id"]
            })
        
        item_res = appointment_repo.create_appointment_services_item_bulk(
            services_to_insert=services_to_insert
        ) 
        
        if not item_res:
            logger.error("Lỗi ở cấp DB -> Không thể thêm bản ghi vào trong appointment_services")
            return Command(
                update=build_update(
                    content=(
                        "Không thể đặt lịch cho khách hàng, "
                        "xin lỗi khách và hứa sẽ khắc phục sớm nhất"
                    ),
                    tool_call_id=tool_call_id
                )
            )
        
        logger.info("Thêm các bản ghi vào trong appointment_services thành công")
        
        appointment_details = appointment_repo.get_appointment_details(
            appointment_id=new_appointment_id
        )
        
        booking_detail = return_appoointments(
            appointment_details=appointment_details
        )
        
        book_info = state["book_info"].copy() if state["book_info"] else {}
        book_info[appointment_details["id"]] = update_book_info(
            appointment_details=appointment_details
        )
        
        logger.info("Đặt lịch thành công")
        
        return Command(
            update=build_update(
                content=(
                    "Đặt lịch cho khách thành công, đây là chi tiết đặt lịch của khách:\n"
                    f"{booking_detail}\n"
                ),
                tool_call_id=tool_call_id,
                book_info=book_info,
                services={},
                seen_services={}
            )
        )

    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise