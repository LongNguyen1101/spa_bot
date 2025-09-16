from core.tools.booking_tool import (
    create_appointment_tool,
    check_available_booking_tool,
    resolve_weekday_to_date_tool
)
from core.tools.modify_booking_tool import (
    cancel_booking_tool, 
    get_all_editable_booking
)
from core.tools.service_tool import add_service_tool
from core.tools.customer_tool import modify_customer_tool
from core.tools.services_search_tool import get_services_tool

services_toolbox = [
    get_services_tool
]

booking_toolbox = [
    get_services_tool,
    add_service_tool,
    create_appointment_tool,
    check_available_booking_tool,
    modify_customer_tool,
    resolve_weekday_to_date_tool
]

modify_booking_toolbox = [
    cancel_booking_tool,
    get_all_editable_booking,
    modify_customer_tool
]