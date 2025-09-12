from langgraph.graph.message import add_messages

from datetime import datetime
from typing import Annotated, Any, TypedDict, Optional
from langgraph.prebuilt.chat_agent_executor import AgentState as Origin_AgentState


def _remain_dict(old: dict, new: dict | None):
    return new if new is not None else old

def _remain_value(old: Optional[Any], new: Optional[Any]) -> Optional[Any]:
    return new if new is not None else old

class SeenProducts(TypedDict):
    product_des_id: int # ID của bản ghi chứa sản phẩm trong bảng products
    
    product_name: str
    product_id: int # ID của sản phẩm bảng products
    sku: str # SKU của sản phẩm bảng products
    variance_des: str
    brief_des: str
    price: int
    inventory: int
    
class Cart(TypedDict):
    product_des_id: int
    
    quantity: int
    price: int
    subtotal: int
    
class OrderItem(TypedDict):
    item_id: int
    
    product_des_id: int
    product_id: int
    sku: str
    product_name: str
    variance_des: str
    price: int
    quantity: int
    subtotal: int
    
class Order(TypedDict):
    order_id: int
    
    status: str
    payment: str
    order_total: int
    shipping_fee: int
    grand_total: int
    created_at: datetime
    receiver_name: str
    receiver_phone_number: str
    receiver_address: str
    
    items: dict[int, OrderItem]

class AgentState(Origin_AgentState):
    messages: Annotated[list, add_messages]
    user_input: Annotated[str, _remain_value]
    chat_id: Annotated[str, _remain_value]
    next: Annotated[str, _remain_value]
    
    customer_id: Annotated[Optional[int], _remain_value]
    name: Annotated[Optional[str], _remain_value]
    phone_number: Annotated[Optional[str], _remain_value]
    address: Annotated[Optional[str], _remain_value]
    
    seen_products: Annotated[Optional[dict[int, SeenProducts]], _remain_dict]
    cart: Annotated[Optional[dict[int, Cart]], _remain_dict]
    
    order: Annotated[Optional[dict[int, Order]], _remain_dict]
    
    
def init_state() -> AgentState:
    return AgentState(
        messages=[],
        user_input="",
        chat_id="",
        next="",
        
        customer_id=None,
        name=None,
        phone_number=None,
        address=None,
        
        seen_products=None,
        cart=None,
        
        order=None
    )