from langgraph.types import Command
from typing import Annotated, Optional
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

from core.utils.function import build_update
from core.graph.state import AgentState, Cart, SeenProducts

from log.logger_config import setup_logging

logger = setup_logging(__name__)

def _return_cart(
    seen_products: dict[int, SeenProducts], 
    cart: dict[int, Cart],
    name: Optional[str] = None,
    phone_number: Optional[str] = None,
    address: Optional[str] = None
) -> str:
    """
    Kết xuất thông tin giỏ hàng và tổng hợp thành chuỗi mô tả chi tiết.

    Args:
        seen_products (dict[int, SeenProducts]): Tập các sản phẩm đã xem dùng để tra cứu thông tin hiển thị.
        cart (dict[int, Cart]): Giỏ hàng hiện tại (product_des_id -> dòng hàng).
        name (Optional[str]): Tên người nhận nếu đã có.
        phone_number (Optional[str]): Số điện thoại người nhận nếu đã có.
        address (Optional[str]): Địa chỉ người nhận nếu đã có.

    Returns:
        str: Chuỗi mô tả giỏ hàng, tổng tiền, phí ship và thông tin người nhận.
    """
    order_total = 0
    cart_detail = ""
    index = 1
    
    for item in cart.values():
        product = seen_products[item['product_des_id']]
        
        product_name = product["product_name"]
        product_id = product["product_id"]
        sku = product["sku"]
        variance_des = product["variance_des"]
        
        order_total += item['subtotal']
        cart_detail += (
            f"STT: {index}\n"
            f"Tên sản phẩm: {product_name}.\n"
            f"Mã sản phẩm: {product_id}.\n"
            f"SKU sản phẩm: {sku}.\n"
            f"Tên phân loại: {variance_des if variance_des else "Không có"}.\n"
            f"Giá 1 sản phẩm: {item['price']} VNĐ.\n"
            f"Số lượng: {item["quantity"]}.\n"
            f"Tổng giá: {item['subtotal']} VNĐ.\n\n"
        )
        
        index += 1
        
    cart_detail += (
        f"Tổng cộng giỏ hàng: {order_total} VNĐ.\n"
        f"Phí ship: 50.000 VNĐ.\n"
        f"Tổng giá trị sau khi thêm phí ship: {order_total + 50000} VNĐ.\n"
        f"Tên người nhận: {name if name else "Không có"}.\n"
        f"Số điện thoại người nhận: {phone_number if phone_number else "Không có"}.\n"
        f"Địa chỉ người nhận: {address if address else "Không có"}.\n"
    )
    
    return cart_detail

@tool
def add_item_cart_tool(
    product_des_id: Annotated[Optional[int], (
        "Là khoá của dict seen_products, đại diện "
        "cho sản phẩm khách muốn thêm"
    )],
    quantity: Annotated[int, "Số lượng sản phẩm khách muốn mua"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
    
) -> Command:
    """
    Sử dụng công cụ này để thêm sản phẩm vào giỏ hàng.

    Chức năng: Dùng để thêm một sản phẩm vào giỏ hàng.

    Tham số:
        - product_des_id (int, tùy chọn): Là ID của sản phẩm mà khách hàng muốn thêm vào giỏ hàng. ID này được lấy từ danh sách các sản phẩm mà khách hàng đã xem (seen_products).
        - quantity (int): Số lượng sản phẩm khách hàng muốn mua. Nếu không rõ, mặc định là 1.
    """
    logger.info("add_item_cart_tool được gọi")
    # Đảm bảo khách đã xem trước ít nhắt 1 sản phẩm
    if not state["seen_products"]:
        logger.info("seen_products rỗng -> khách chưa xem sản phẩm nào")
        return Command(
            update=build_update(
                content="Khách chưa xem sản phẩm nào, hỏi khách có muốn mua sản phẩm nào không",
                tool_call_id=tool_call_id
            )
        )
        
    if not product_des_id:
        logger.info("Không xác định được product_des_id")
        return Command(
            update=build_update(
                content="Không thể xác định được sản phẩm khách muốn mua, hỏi lại khách",
                tool_call_id=tool_call_id
            )
        )
    
    try:
        logger.info("seen_products có sản phẩm và xác định được product_des_id")
        cart = state["cart"].copy() if state["cart"] is not None else {}
        price = state["seen_products"][product_des_id]["price"]
        
        cart[product_des_id] = Cart(
            product_des_id=product_des_id,
            quantity=quantity,
            price=price,
            subtotal=quantity * price
        )
        
        cart_detail = _return_cart(
            seen_products=state["seen_products"],
            cart=cart,
            name=state["name"],
            phone_number=state["phone_number"],
            address=state["address"]
        )
        
        logger.info(f"Thêm sản phẩm {product_des_id} vào giỏ hàng thành công")
        
        return Command(
            update=build_update(
                content=(
                    "Thêm sản phẩm <bạn hãy tự điền tên> vào giỏ hàng thành công, đây là giỏ hàng:\n"
                    f"{cart_detail}\n"
                    "Bạn phải liệt kê đầy đủ, không được rút gọn hay bịa đặt thông tin mới\n"
                    "Nếu trong 3 thông tin name, phone_number, hoặc address thiếu thông tin nào "
                    "thì hỏi khách thông tin đó\n"
                    "Nếu khách có yêu cầu khác thì gọi tool thực hiện yêu cầu đó\n"
                    "Nếu khách không có yêu cầu khác thì BẮT BUỘC KHÔNG được gọi "
                    "tool nào nữa và phải dừng lại và tạo phản hồi để khách xác nhận.\n"
                ),
                tool_call_id=tool_call_id,
                cart=cart
            )
        )
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise


@tool
def update_qt_cart_tool(
    product_des_id: Annotated[Optional[int], (
        "Là khoá của dict seen_products, đại diện "
        "cho sản phẩm khách muốn thêm"
    )],
    new_quantity: Annotated[Optional[int], "Số lượng mới của sản phẩm"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
    
) -> Command:
    """
    Sử dụng công cụ này nếu khách muốn thay đổi số lượng sản phẩm có trong giỏ hàng.

    Chức năng: Cập nhật số lượng của một sản phẩm trong giỏ hàng. Có thể dùng để tăng, giảm số lượng hoặc xóa sản phẩm khỏi giỏ hàng.

    Tham số:
        - product_des_id (int, tùy chọn): ID của sản phẩm trong giỏ hàng mà khách hàng muốn cập nhật.
        - new_quantity (int, tùy chọn): Số lượng mới của sản phẩm. Nếu khách muốn xoá sản phẩm thì new_quantity = 0.
    """
    logger.info("update_qt_cart_tool được gọi")
    
    cart = state["cart"].copy() if state["cart"] is not None else {}
    if not cart:
        logger.info("Giỏ hàng đang trống -> không thể cập nhật số lượng sản phẩm")
        return Command(
            update=build_update(
                content="Khách chưa muốn mua sản phẩm nào, hỏi khách có muốn xem sản phẩm nào không",
                tool_call_id=tool_call_id
            )
        )
        
    if not product_des_id:
        logger.info("Không xác định được product_des_id -> không thể cập nhật số lượng sản phẩm")
        return Command(
            update=build_update(
                content="Không xác định được sản phẩm khách muốn cập nhật, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
        
    if new_quantity == None:
        logger.info("Không xác định được số lượng khách muốn thay đổi -> không thể cập nhật số lượng sản phẩm")
        return Command(
            update=build_update(
                content="Không xác định được số lượng sản phẩm khách muốn cập nhật, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
        
    try:
        logger.info("Xác định được các thông tin cart, product_des_id, new_quantity")
        
        if new_quantity == 0:
            logger.info("Khách muốn xoá sản phẩm")
            del cart[product_des_id]
        else:
            logger.info("Khách muốn cập nhật số lượng sản phẩm")
            price = cart[product_des_id]["price"]
            cart[product_des_id]["quantity"] = new_quantity
            cart[product_des_id]["subtotal"] = new_quantity * price
        
        if not cart:
            logger.info("Sau khi xoá sản phẩm thì giỏ hàng không còn sản phẩm nào")
            cart_detail = "Không còn sản phẩm nào trong giỏ hàng"
        else:
            cart_detail = _return_cart(
                seen_products=state["seen_products"],
                cart=cart,
                name=state["name"],
                phone_number=state["phone_number"],
                address=state["address"]
            )
            
        logger.info("Cập nhật sản phẩm trong giỏ hàng thành công")
        
        return Command(
            update=build_update(
                content=(
                    "<Cập nhật nếu khách nói thay đổi số lượng | Xoá nếu khách nói xoá sản phẩm> "
                    "sản phẩm <bạn hãy tự điền tên> vào giỏ hàng thành công, "
                    "đây là các sản phẩm khách đã xem:\n"
                    f"{cart_detail}\n"
                    "Bạn phải liệt kê đầy đủ, không được rút gọn hay bịa đặt thông tin mới.\n"
                    "Nếu trong 3 thông tin name, phone_number, hoặc address thiếu thông tin nào "
                    "thì hỏi khách thông tin đó.\n"
                    "Nếu khách có yêu cầu khác thì gọi tool thực hiện yêu cầu đó\n"
                    "Nếu khách không có yêu cầu khác thì BẮT BUỘC KHÔNG được gọi "
                    "tool nào nữa và phải dừng lại và tạo phản hồi để khách xác nhận.\n"
                ),
                tool_call_id=tool_call_id,
                cart=cart
            )
        )
            
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise
    
@tool
def alter_item_cart_tool(
    new_product_des_id: Annotated[Optional[int], (
        "Là khoá của dict seen_products, đại diện "
        "cho sản phẩm thay đổi"
    )],
    new_quantity: Annotated[Optional[int], (
        "Số lượng của sản phẩm mới mà khách muốn thay thế sản phẩm cũ. "
        "Mặc định bằng với số lượng sản phẩm cũ mà khách muốn đổi"
    )],
    old_product_des_id: Annotated[Optional[int], (
        "Là khoá của dict seen_products, đại diện "
        "cho sản phẩm bị thay đổi"
    )],
    old_quantity: Annotated[Optional[int], (
        "Số lượng của sản phẩm cũ mà khách muốn thay thế."
        "Nếu khách muốn thay thế hoàn toàn sản phẩm cũ "
        "bằng sản phẩm mới thì old_quantity = 0."
    )],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
    
) -> Command:
    """
    Sử dụng công cụ này nếu khách muốn thay thế sản phẩm <A> có trong giỏ hàng bằng sản phẩm <B> không có trong giỏ hàng.

    Chức năng: Thay thế một sản phẩm trong giỏ hàng bằng một sản phẩm khác.

    Tham số:
        - new_product_des_id (int, tuỳ chọn): ID của sản phẩm mới sẽ được thêm vào đơn hàng.
        - new_quantity (int, tuỳ chọn): Số lượng sản phẩm mới sẽ được thêm vào.
        - old_product_des_id (int, tuỳ chọn): ID của sản phẩm cũ cần thay thế.
        - old_quantity (int, tuỳ chọn): Số lượng còn lại của sản phẩm cũ sau khi thay thế. Nếu > 0: sản phẩm cũ chỉ bị giảm bớt số lượng (trường hợp thay thế một phần). Nếu = 0: sản phẩm cũ sẽ bị xóa hoàn toàn khỏi đơn hàng (trường hợp thay thế toàn bộ).
        
    Vi dụ:
        - Context: <A> có 5 sản phẩm
        - Input: Thay 3 cái sản phẩm <A> thành 5 cái sản phẩm <B>
        - Args: 
            - new_product_des_id = <product_des_id của B>
            - new_quantity = 5
            - old_product_des_id = <product_des_id của A>
            - old_quantity = 2 (ban đầu <A> có 5 cái nên thay 3 cái của <A> tức là <A> còn 5 - 3 = 2 cái)
    """
    logger.info("alter_item_cart_tool được gọi")
    
    cart = state["cart"].copy() if state["cart"] is not None else {}
    if not cart:
        logger.info("Giỏ hàng rỗng")
        return Command(
            update=build_update(
                content="Khách chưa muốn mua sản phẩm nào, hỏi khách có muốn xem sản phẩm nào không",
                tool_call_id=tool_call_id
            )
        )
        
    if not new_product_des_id:
        logger.info("Không xác định được new_product_des_id")
        return Command(
            update=build_update(
                content="Không xác định được sản phẩm mới mà khách muốn thay thế sản phẩm cũ, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
        
    if not old_product_des_id:
        logger.info("Không xác định được old_product_des_id")
        return Command(
            update=build_update(
                content="Không xác định được sản phẩm cũ mà khách muốn thay thế bởi sản phẩm mới, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
        
    if not new_quantity:
        logger.info("Không xác định được new_quantity")
        return Command(
            update=build_update(
                content="Không xác định được số lượng sản phẩm mới mà khách muốn thay thế sản phẩm cũ, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
    
    
    if old_quantity is None:
        logger.info("Không xác định được old_quantity")
        return Command(
            update=build_update(
                content="Không xác định được số lượng sản phẩm cũ mà bị thay thế bởi sản phẩm mới, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
    
    try:
        logger.info("Đã có đầy đủ thông tin")
        # Trường hợp thay thế hoàn toàn sản phẩm cũ bằng sản phẩm mới
        if old_quantity == 0:
            logger.info(f"old_quantity = {old_quantity} -> Thay thế hoàn toàn sản phẩm cũ")
            
            del cart[old_product_des_id]
            price = state["seen_products"][new_product_des_id]["price"]

            cart[new_product_des_id] = Cart(
                product_des_id=new_product_des_id,
                quantity=new_quantity,
                price=price,
                subtotal= new_quantity * price
            )
            logger.info("Xoá sản phẩm cũ thành công")
        else:
            # Trường hợp thay thế 1 phần sản phẩm cũ bằng sản phẩm mới
            logger.info(f"old_quantity = {old_quantity} -> Thay thế một phần sản phẩm cũ")
            logger.info(
                f"Thay thế {cart[old_product_des_id]["quantity"] - old_quantity} "
                f"sản phẩm {old_product_des_id} "
                f"bằng {new_quantity} sản phẩm {new_product_des_id}"
            )
            
            # Cập nhật sản phẩm cũ
            price = cart[old_product_des_id]["price"]
            cart[old_product_des_id]["quantity"] = old_quantity
            cart[old_product_des_id]["subtotal"] = old_quantity * price
            logger.info(f"Cập nhật số lượng sản phẩm cũ thành công")
            
            # Thêm sản phẩm mới
            price = state["seen_products"][new_product_des_id]["price"]
            cart[new_product_des_id] = Cart(
                product_des_id=new_product_des_id,
                quantity=new_quantity,
                price=price,
                subtotal= new_quantity * price
            )
            logger.info(f"Thêm sản phẩm mới thành công")
            
        cart_detail = _return_cart(
            seen_products=state["seen_products"],
            cart=cart,
            name=state["name"],
            phone_number=state["phone_number"],
            address=state["address"]
        )
        
        return Command(
            update=build_update(
                content=(
                    "Thêm sản phẩm <bạn hãy tự điền tên> vào giỏ hàng thành công, đây là các sản phẩm khách đã xem:\n"
                    f"{cart_detail}\n"
                    "Bạn phải liệt kê đầy đủ, không được rút gọn hay bịa đặt thông tin mới.\n"
                    "Nếu trong 3 thông tin name, phone_number, hoặc address thiếu thông tin nào "
                    "thì hỏi khách thông tin đó."
                ),
                tool_call_id=tool_call_id,
                cart=cart
            )
        )
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise
        