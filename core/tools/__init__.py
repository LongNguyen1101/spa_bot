from core.tools.booking_tool import (
    add_service_tool,
    create_appointment_tool,
    check_available_booking_tool
)
from core.tools.customer_tool import modify_customer_tool
from core.tools.services_search_tool import (
    get_services_tool
)

services_toolbox = [
    get_services_tool
]

booking_toolbox = [
    get_services_tool,
    add_service_tool,
    create_appointment_tool,
    check_available_booking_tool,
    modify_customer_tool
]