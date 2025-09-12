from core.tools.product_search_tool import get_products_tool, get_qna_tool
from core.tools.cart_tool import add_item_cart_tool, update_qt_cart_tool, alter_item_cart_tool
from core.tools.customer_tool import modify_customer_tool
from core.tools.order_tool import (
    add_order_tool, 
    update_receiver_order_tool,
    cancel_order_tool,
    update_qt_item_tool,
    alter_item_order_tool,
    get_customer_orders_tool
)

product_toolbox = [
    get_products_tool,
    get_qna_tool
]

order_toolbox = [
    get_products_tool,
    add_order_tool,
    add_item_cart_tool,
    update_qt_cart_tool,
    alter_item_cart_tool,
    modify_customer_tool
]

modify_order_toolbox = [
    get_products_tool,
    get_customer_orders_tool,
    update_receiver_order_tool,
    cancel_order_tool,
    update_qt_item_tool,
    alter_item_order_tool,
    modify_customer_tool
]