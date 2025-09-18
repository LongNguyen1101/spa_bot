from ast import parse
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
    choose_room_and_staff,
    free_slots_all,
    free_slots_with_staff,
    parese_date,
    parse_time, 
    time_to_str, 
    date_to_str,
    return_appointments,
    update_book_info
)

from log.logger_config import setup_logging

logger = setup_logging(__name__)

appointment_repo = AppointmentRepo(supabase_client=supabase_client)
room_repo = RoomRepo(supabase_client=supabase_client)
staff_repo = StaffRepo(supabase_client=supabase_client)


def _handle_not_start_time(
    rooms: dict,
    orders: dict,
    staffs: dict
) -> str:
    response = ""
    for r_id, value in rooms.items():
        response += f"Room: {value["name"]} (capacity={value['capacity']}):\n"
        slots = free_slots_with_staff(
            orders=orders,
            room_id=r_id,
            room_capacity=value["capacity"],
            staffs=staffs,
            k=1
        )
        for slot in slots:
            response += f"- {slot['start_time']} - {slot['end_time']}, free_capacity={slot['free_capacity']}\n"
    
    return response
    

def _check_available_with_end_time(
    start_time_new: str,
    end_time_new: str,
    orders: dict,
    rooms: dict,
    staffs: dict
) -> dict:
    all_slots = {}
    for r_id, value in rooms.items():
        slots = free_slots_with_staff(
            orders,
            room_id=r_id,
            room_capacity=value["capacity"],
            staffs=staffs,
            k=3
        )
        all_slots[r_id] = slots
    
    available = choose_room_and_staff(
        free_dict=all_slots,
        s_req=start_time_new,
        e_req=end_time_new
    )
    
    return available

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
        - booking_date_new (str | None): Ngày tháng năm mà khách đặt, bắt buộc có định dạng "%Y-%m-%d". 
        **Tham số này chấp nhận None**
        - start_time_new (str | None): Giờ phút giây mà khách đặt, bắt buộc có định dạng "%H:%M:%S"
        **Tham số này chấp nhận None**
    """
    logger.info(f"check_available_booking được gọi")
    
    try:
        # Lấy ra danh sách phòng và nhân viên khả dụng trong ngày đó
            
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
        
        staffs = staff_repo.get_all_staff_return_dict()
        rooms = room_repo.get_all_rooms_return_dict()
        orders = appointment_repo.get_appointment_by_booking_date(
            booking_date=booking_date_new
        )
    
        if not start_time_new:
            logger.info("Khách không cung cấp thời gian cụ thể")

            response = _handle_not_start_time(
                rooms=rooms,
                orders=orders,
                staffs=staffs
            )

            logger.info("Tìm khung thời gian trống thành công")

            return Command(
                update=build_update(
                    content=(
                        f"{response}"
                    ),
                    tool_call_id=tool_call_id,
                    booking_date=booking_date_new
                )
            )
        
        
        logger.info(f"Khách đặt ngày: {booking_date_new} vào lúc: {start_time_new}")
    
        # Calculate end time
        parse_booking_date = parese_date(booking_date_new)
        parse_start_time = parse_time(start_time_new)
        dt_start = datetime.combine(parse_booking_date, parse_start_time)
        
        if state["total_time"]:
            dt_end = dt_start + timedelta(minutes=state["total_time"])
        else:
            dt_end = dt_start + timedelta(minutes=60)
        end_time_new = time_to_str(dt_end)

        available = _check_available_with_end_time(
            start_time_new=start_time_new,
            end_time_new=end_time_new,
            orders=orders,
            rooms=rooms,
            staffs=staffs
        )

        if not available["room_id"] or not available["staff_id"]:
            logger.info(
                "Không có phòng trống hoặc nhân viên khả dụng"
            )
        
        room_id = available["room_id"]
        staff_id = available["staff_id"]

        logger.info("Tìm thấy phòng và nhân viên khả dụng")
        logger.info(f"ID phòng khả dụng: {room_id} | ID nhân viên khả dụng: {staff_id}")
        logger.info("Kiểm tra phòng và nhân viên thành công")

        return Command(
            update=build_update(
                content=(
                    "Thông báo khách có lịch trống"
                ),
                tool_call_id=tool_call_id,
                booking_date=booking_date_new,
                start_time=start_time_new,
                end_time=end_time_new,
                room_id=room_id,
                room_name=rooms[room_id]["name"],
                staff_id=staff_id,
                staff_name=staffs[staff_id]
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
            "booking_date": state["booking_date"],
            "start_time": state["start_time"],
            "end_time": state["end_time"],
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
        
        booking_detail = return_appointments(
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