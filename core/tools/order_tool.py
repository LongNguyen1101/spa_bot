from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

from datetime import datetime
from typing import Optional, Annotated

from repository.sync_repo import OrderRepo
from core.utils.function import build_update
from database.connection import supabase_client
from core.graph.state import AgentState, Order, OrderItem

from log.logger_config import setup_logging

logger = setup_logging(__name__)

order_repo = OrderRepo(supabase_client=supabase_client)
    
    
def _format_order_details(
    raw_order_detail: dict
) -> str:
    """
    Định dạng thông tin chi tiết đơn hàng thành chuỗi văn bản thân thiện.

    Args:
        raw_order_detail (dict): Dữ liệu đơn hàng gồm `order_items` và trường thông tin liên quan.

    Returns:
        str: Nội dung mô tả chi tiết đơn hàng.
    """
    order_detail = f"Mã đơn: {raw_order_detail["order_id"]}\n\n"
    index = 1
    for item in raw_order_detail.get("order_items", []):
        prod = item.get("products", {})

        product_name = prod.get("product_name")
        product_id = prod.get("product_id")
        sku = prod.get("sku")
        variance_des = prod.get("variance_des") or "Không có"

        price = item.get("price", 0)
        quantity = item.get("quantity", 0)
        subtotal = item.get("subtotal", 0)

        order_detail += (
            f"STT: {index}\n"
            f"Tên sản phẩm: {product_name}.\n"
            f"Mã sản phẩm: {product_id}.\n"
            f"SKU sản phẩm: {sku}.\n"
            f"Tên phân loại: {variance_des}.\n"
            f"Giá 1 sản phẩm: {price} VNĐ.\n"
            f"Số lượng: {quantity}.\n"
            f"Tổng giá: {subtotal} VNĐ.\n\n"
        )

        index += 1
    
    # format datetime
    dt = datetime.fromisoformat(raw_order_detail["created_at"])
    formatted_date = dt.strftime("%H:%M:%S - %d/%m/%Y")
    
    order_detail += (
        f"Tổng cộng giỏ hàng: {raw_order_detail["order_total"]} VNĐ.\n"
        f"Phí ship: {raw_order_detail["shipping_fee"]} VNĐ.\n"
        f"Tổng cộng: {raw_order_detail["grand_total"]} VNĐ.\n"
        f"Phương thức thanh toán: {raw_order_detail["payment"]}.\n\n"
        f"Tên người nhận: {raw_order_detail["receiver_name"]}.\n"
        f"Số điện thoại người nhận: {raw_order_detail["receiver_phone_number"]}.\n"
        f"Địa chỉ người nhận: {raw_order_detail["receiver_address"]}.\n"
        f"Ngày đặt hàng: {formatted_date}\n\n"
    )
    
    return order_detail
        
def _return_all_editable_orders(
    customer_id: int,
    list_raw_order_detail: Optional[list[dict]] = None
) -> str:
    """
    Trả về chuỗi mô tả danh sách các đơn hàng có thể chỉnh sửa của một khách.

    Args:
        customer_id (int): Mã khách hàng.
        list_raw_order_detail (Optional[list[dict]]): Dữ liệu đơn hàng nếu đã có sẵn.

    Returns:
        str: Chuỗi mô tả tổng hợp nhiều đơn hàng.
    """
    try:
        if not list_raw_order_detail:
            list_raw_order_detail = order_repo.get_all_editable_orders(
                customer_id=customer_id
            )
            
            if not list_raw_order_detail:
                return f"Không tìm thấy đơn hàng khách với ID: {customer_id}"
            
        
        order_detail = ""
        order_index = 1
        for raw_order in list_raw_order_detail:
            order_detail += (
                f"Đơn thứ: {order_index}\n"
                f"{_format_order_details(
                    raw_order_detail=raw_order
                )}"
            )
            
            order_index += 1
        
        return order_detail
        
    except Exception as e:
        raise

def _return_order_details(
    order_id: int,
    raw_order_detail: Optional[dict] = None
) -> str:
    """
    Trả về mô tả chi tiết cho một đơn hàng theo `order_id`.

    Args:
        order_id (int): Mã đơn.
        raw_order_detail (Optional[dict]): Dữ liệu nếu đã có sẵn, tránh query lại.

    Returns:
        str: Chuỗi mô tả chi tiết đơn hàng.
    """
    try:
        if not raw_order_detail:
            raw_order_detail = order_repo.get_order_details(order_id=order_id)
            
            if not raw_order_detail:
                return f"Không tìm thấy đơn hàng với ID {order_id}"

        return _format_order_details(raw_order_detail=raw_order_detail)
    except Exception as e:
        raise


def _update_order_state(order: dict) -> dict:
    """
    Chuyển dữ liệu thô từ DB thành cấu trúc `Order` dùng trong `AgentState`.

    Args:
        order (dict): Dữ liệu đơn hàng bao gồm danh sách item và thông tin người nhận.

    Returns:
        dict: Cấu trúc `Order` sẵn sàng lưu vào state.
    """
    items_list: dict[int, OrderItem] = {}
    
    for ot in order.get("order_items", []):
        prod = ot.get("products", {})
       
        item = OrderItem(
            item_id=ot["item_id"],
            product_des_id=ot["product_des_id"],
            product_id=prod.get("product_id", 0),
            sku=prod.get("sku", ""),
            product_name=prod.get("product_name", ""),
            variance_des=prod.get("variance_des", ""),
            price=ot["price"],
            quantity=ot["quantity"],
            subtotal=ot["subtotal"],
        )

        items_list[ot["item_id"]] = item
        
    return Order(
        order_id=order["order_id"],
        status=order["status"],
        payment=order["payment"],
        order_total=order["order_total"],
        shipping_fee=order["shipping_fee"],
        grand_total=order["grand_total"],
        created_at=order["created_at"],
        receiver_name=order.get("receiver_name", ""),
        receiver_phone_number=order.get("receiver_phone_number", ""),
        receiver_address=order.get("receiver_address", ""),
        items=items_list,
    )
    

@tool
def add_order_tool(
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """Sử dụng công cụ này để tạo một đơn hàng mới.

    Chức năng: Tạo một đơn hàng mới dựa trên các sản phẩm có trong giỏ hàng và thông tin khách hàng (tên, SĐT, địa chỉ) đã được lưu trong state.
    """
    logger.info("add_order_tool được gọi")
    
    cart = state["cart"].copy()
    if not cart:
        logger.info("Giỏ hàng rỗng")
        return Command(
            update=build_update(
                content="Khách chưa muốn mua sản phẩm nào, hỏi khách",
                tool_call_id=tool_call_id
            )
        )
    
    logger.info("Giỏ hàng có sản phẩm")
    customer_id = state.get("customer_id")
    receiver_name = state.get("name")
    receiver_phone = state.get("phone_number")
    receiver_address = state.get("address")

    # Không có đủ thông tin khách
    if not all([customer_id, receiver_name, receiver_phone, receiver_address]):
        logger.info(
            "Không có đủ thông tin khách "
            f"id: {customer_id} | "
            f"name: {receiver_name} | "
            f"phone: {receiver_phone} | "
            f"address: {receiver_address}"
        )
        return Command(
            update=build_update(
                content=(
                    "Đây là các thông tin của khách:\n"
                    f"- Tên người nhận: {receiver_name if receiver_name else "Không có"}\n"
                    f"- Số điện thoại người nhận: {receiver_phone if receiver_phone else "Không có"}\n"
                    f"- Địa chỉ người nhận: {receiver_address if receiver_address else "KHông có"}\n"
                    "Hỏi khách các thông tin còn thiếu"
                ),
                tool_call_id=tool_call_id
            )
        )

    try:
        logger.info("Đã đủ thông tin của khách -> lên dơn")
        
        order_payload = {
            "customer_id": customer_id,
            "shipping_fee": 50000,
            "receiver_name": receiver_name, 
            "receiver_phone_number": receiver_phone, 
            "receiver_address": receiver_address, 
            "status": "pending"
        }
        
        order_res = order_repo.create_order(
            order_payload=order_payload
        )
        
        if not order_res:
            logger.error("Lỗi ở cấp DB -> Không thể tạo đơn hàng")
            return Command(
                update=build_update(
                    content="Lỗi không thể tạo đơn hàng, xin khách thử lại"
                ),
                tool_call_id=tool_call_id
            )
        
        new_order_id = order_res.get("order_id")
        items_to_insert = []
        logger.info(f"Tạo bản ghi trong orders thành công với ID: {new_order_id}")
        
        for item in cart.values():
            items_to_insert.append({
                "order_id": new_order_id, 
                "product_des_id": item["product_des_id"],
                "quantity": item["quantity"],
                "price": item["price"],
                "subtotal": item["subtotal"]
            })
        
        item_res = order_repo.create_order_item_bulk(
            items_to_insert=items_to_insert
        ) 
        
        if not item_res:
            logger.error("Lỗi ở cấp DB -> Không thể thêm sản phẩm vào trong order_items")
            return Command(
                update=build_update(
                    content=(
                        "Không thể thêm sản phẩm vào đơn hàng, "
                        "xin lỗi khách và hứa sẽ khắc phục sớm nhất"
                    ),
                    tool_call_id=tool_call_id
                )
            )
        
        logger.info("Thêm các sản phẩm trong giỏ hàng vào order items thành công")
        
        order = order_repo.get_order_details(order_id=new_order_id)
        order_detail = _return_order_details(
            order_id=order,
            raw_order_detail=order
        )
        
        order_state = state["order"].copy() if state["order"] is not None else {}
        order_state[new_order_id] = _update_order_state(order=order)
        
        logger.info("Lên đơn thành công")
        return Command(
            update=build_update(
                content=(
                    "Tạo đơn hàng thành công, đây là đơn hàng của khách:\n"
                    f"{order_detail}\n"
                    "Không được tóm gọn, phải liệt kê chi tiết, đầy đủ, không bịa đặt "
                    "không tạo phản hồi các thông tin dư thừa.\n"
                    "Thêm dòng thông báo đơn hàng sẽ vận chuyển từ 3-5 ngày, "
                    "nhân viên giao hàng sẽ gọi cho khách để giao hàng"
                ),
                tool_call_id=tool_call_id,
                order=order_state,
                cart={},
                seen_products={}
            )
        )

    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise

@tool
def update_receiver_order_tool(
    order_id: Annotated[Optional[int], "ID của đơn hàng cần cập nhật."],
    name: Annotated[Optional[str], "Tên mới của người nhận."],
    phone_number: Annotated[Optional[str], "Số điện thoại mới của người nhận."],
    address: Annotated[Optional[str], "Địa chỉ mới của người nhận."],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """Sử dụng công cụ này để cập nhật thông tin người nhận của một đơn hàng.

    Chức năng: Cập nhật thông tin người nhận (tên, SĐT, địa chỉ) cho một đơn hàng đã có.

    Tham số:
        - order_id (int, tùy chọn): ID của đơn hàng cần cập nhật.
        - name (str, tùy chọn): Tên mới của người nhận.
        - phone_number (str, tùy chọn): Số điện thoại mới của người nhận.
        - address (str, tùy chọn): Địa chỉ mới của người nhận.
    """
    logger.info("update_receiver_order_tool được gọi")
    
    order_state = state["order"].copy() if state["order"] is not None else {}
    
    if not order_state:
        logger.info("order trống -> không thể cập nhật")
        return Command(
            update=build_update(
                content="Không có thông tin đơn của khách, lấy các đơn của khách",
                tool_call_id=tool_call_id
            )
        )
    
    if not order_id:
        logger.info("Không thể xác định được order_id mà khách muốn")
        return Command(
            update=build_update(
                content="Không xác định được đơn hàng mà khách muốn chỉnh sửa, hỏi lại khách",
                tool_call_id=tool_call_id
            )
        )
    
    try:
        logger.info(f"Xác định được order_id mà khách muốn: {order_id}")
        
        update_payload = {}
        if name:
            update_payload["receiver_name"] = name
        if phone_number:
            update_payload["receiver_phone_number"] = phone_number
        if address:
            update_payload["receiver_address"] = address
        
        logger.info(f"Các thông tin cần cập nhật: {update_payload}")
        
        response = order_repo.update_order(
            update_payload=update_payload,
            order_id=order_id
        )
        
        if not response:
            logger.error("Lỗi ở cấp DB -> Không thể cập nhật thông tin người nhận")
            return Command(
                update=build_update(
                    content="Cập nhật thông tin người nhận không thành công, xin lỗi khách và sẽ khắc phục sớm nhất có thể",
                    tool_call_id=tool_call_id
                )
            )

        logger.info("Cập nhật thông tin người nhận thành công")
        
        order = order_repo.get_order_details(order_id=order_id)
        order_detail = _return_order_details(
            order_id=order,
            raw_order_detail=order
        )
        
        order_state[order_id] = _update_order_state(order=order)
        
        return Command(
            update=build_update(
                content=(
                    "Cập nhật thông tin người nhận thành công, đây là đơn hàng của khách:\n"
                    f"{order_detail}\n"
                    "Không được tóm gọn, phải liệt kê chi tiết, đầy đủ, không bịa đặt."
                ),
                tool_call_id=tool_call_id,
                order=order_state
            )
        )
        
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise

@tool
def cancel_order_tool(
    order_id: Annotated[Optional[int], "ID của đơn hàng cần hủy."],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """Sử dụng công cụ này để hủy một đơn hàng.

    Chức năng: Hủy một đơn hàng dựa trên ID của đơn hàng.

    Tham số:
        - order_id (int, tùy chọn): ID của đơn hàng cần hủy.
    """
    print("cancel_order_tool được gọi")
    
    order_state = state["order"].copy() if state["order"] is not None else {}
    
    if not order_state:
        logger.info("order trống -> không thể huỷ đơn")
        return Command(
            update=build_update(
                content="Không có thông tin đơn của khách, lấy các đơn của khách",
                tool_call_id=tool_call_id
            )
        )
    
    if not order_id:
        logger.info("Không thể xác định được order_id mà khách muốn huỷ")
        return Command(
            update=build_update(
                content="Không xác định được đơn hàng mà khách muốn chỉnh sửa, hỏi lại khách",
                tool_call_id=tool_call_id
            )
        )
    
    try:
        logger.info(f"Xác định được order_id mà khách muốn: {order_id}")
        
        response = order_repo.update_order(
            update_payload={"status": "cancelled"},
            order_id=order_id
        )
        
        if not response:
            logger.error("Lỗi ở cấp DB -> Không thể huỷ đơn hàng")
            return Command(
                update=build_update(
                    content=f"Xảy ra lỗi trong lúc huỷ đơn hàng {order_id}, xin lỗi khách và hứa sẽ khắc phục sớm nhất",
                    tool_call_id=tool_call_id
                )
            )
        
        logger.info("Huỷ dơn hàng thành công")
        
        # Cập nhật vào state
        order_state[order_id]["status"] = "cancelled"
        
        return Command(
            update=build_update(
                content=f"Đã hủy thành công đơn hàng có ID {order_id}",
                tool_call_id=tool_call_id,
                order=order_state
            )
        )
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise

@tool
def update_qt_item_tool(
    order_id: Annotated[Optional[int], "ID của đơn hàng chứa sản phẩm."],
    item_id: Annotated[Optional[int], "ID của mục sản phẩm (order item) cần cập nhật."],
    new_quantity: Annotated[Optional[int], "Số lượng mới cho sản phẩm."],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """Sử dụng công cụ này để cập nhật số lượng của một sản phẩm trong đơn hàng.

    Chức năng: Cập nhật số lượng hoặc xóa một sản phẩm trong một đơn hàng đã có.

    Tham số:
        - order_id (int, tùy chọn): ID của đơn hàng chứa sản phẩm cần cập nhật.
        - item_id (int, tùy chọn): ID của sản phẩm trong đơn hàng, xác định bằng cách nhìn vào order_id mà bạn đã xác định được, sau đó nhìn vào trường items, trường này chứa các sản phẩm trong đơn hàng đó, mỗi sản phẩm trong trường này có 1 item_id, đó chính là thông tin bạn cần lấy được.
        - new_quantity (int, tùy chọn): Số lượng mới của sản phẩm. Nếu khách yên cầu thêm bớt n sản phẩm thì bạn hãy lấy số lượng có sẵn và cộng cho n sản phẩm khách muốn thêm. Nếu là 0, sản phẩm sẽ được xóa khỏi đơn hàng.
    """
    print("update_qt_item_tool được gọi")
    
    order_state = state["order"].copy() if state["order"] is not None else {}
    
    if not order_state:
        logger.info("order trống -> không thể cập nhật")
        return Command(
            update=build_update(
                content="Không có thông tin đơn của khách, lấy các đơn của khách",
                tool_call_id=tool_call_id
            )
        )
    
    if not order_id:
        logger.info("Không thể xác định được order_id mà khách muốn")
        return Command(
            update=build_update(
                content="Không xác định đơn hàng khách muốn cập nhật, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
        
    if not item_id:
        logger.info("Không thể xác định được item_id mà khách muốn")
        return Command(
            update=build_update(
                content="Không xác định được sản phẩm khách muốn cập nhật, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
    
    if new_quantity is None:
        logger.info("Không thể xác định được số lượng mà khách muốn cập nhật")
        return Command(
            update=build_update(
                content="Không xác định được số lượng sản phẩm khách muốn cập nhật, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
        
    try:
        logger.info(f"Xác định được các thông tin order_id: {order_id} | item_id: {item_id} | new_quantity: {new_quantity}")
        
        if new_quantity == 0:
            logger.info("Khách muốn xoá sản phẩm trong đơn hàng")
            
            delete_item = order_repo.delete_order_item(
                item_id=item_id
            )
            
            if not delete_item:
                logger.error("Lỗi ở cấp DB -> Không thể xoá sản phẩm trong đơn hàng")
                return Command(
                    update=build_update(
                        content="Lỗi trong quá trình xoá sản phẩm, xin lỗi khách",
                        tool_call_id=tool_call_id
                    )
                )
        else:
            logger.info("Khách muốn cập nhật số lượng sản phẩm trong đơn hàng")
            
            response = order_repo.update_order_item(
                item_id=item_id,
                update_payload={"quantity": new_quantity}
            )

            if not response:
                logger.error("Lỗi ở cấp DB -> Không thể cập nhật sản phẩm trong đơn hàng")
                return Command(
                    update=build_update(
                        content="Lỗi trong quá trình cập nhật số lượng, xin lỗi khách",
                        tool_call_id=tool_call_id
                    )
                )
        
        logger.info("Cập nhật sản phẩm trong đơn hàng thành công")
        
        order = order_repo.get_order_details(order_id=order_id)
        order_detail = _return_order_details(
            order_id=order,
            raw_order_detail=order
        )
        order_state[order_id] = _update_order_state(order=order)
        
        return Command(
            update=build_update(
                content=(
                    "Xoá sản phẩm thành công, đây là đơn hàng của khách sau khi cập nhật:\n"
                    f"{order_detail}\n"
                    "Không được tóm gọn, phải liệt kê chi tiết, đầy đủ, không bịa đặt."
                ),
                tool_call_id=tool_call_id,
                order=order_state
            )
        )
            
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise
    
@tool
def alter_item_order_tool(
    order_id: Annotated[Optional[int], "ID của đơn hàng chứa sản phẩm."],
    item_id: Annotated[Optional[int], "ID của mục sản phẩm (order item) cần cập nhật."],
    
    new_product_des_id: Annotated[int, (
        "Là khoá của dict seen_products, đại diện "
        "cho sản phẩm thay đổi"
    )],
    new_quantity: Annotated[int, (
        "Số lượng của sản phẩm mới mà khách muốn thay thế sản phẩm cũ. "
        "Mặc định bằng với số lượng sản phẩm cũ mà khách muốn đổi"
    )],
    old_product_des_id: Annotated[int, (
        "Là khoá của dict seen_products, đại diện "
        "cho sản phẩm bị thay đổi"
    )],
    old_quantity: Annotated[int, (
        "Số lượng của sản phẩm cũ mà khách muốn thay thế."
        "Nếu khách muốn thay thế hoàn toàn sản phẩm cũ "
        "bằng sản phẩm mới thì old_quantity = 0."
    )],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
    
) -> Command:
    """Sử dụng công cụ này để thay thế một sản phẩm trong đơn hàng bằng một sản phẩm khác.

    Chức năng: Thay thế một sản phẩm trong đơn hàng bằng một sản phẩm khác.

    Tham số:
        - order_id (int, tùy chọn): ID của đơn hàng cần cập nhật.
        - item_id (int, tùy chọn): ID của mục sản phẩm trong đơn hàng (order item) sẽ bị thay thế.
        - new_product_des_id (int): ID của sản phẩm mới sẽ được thêm vào đơn hàng.
        - new_quantity (int): Số lượng sản phẩm mới sẽ được thêm vào.
        - old_product_des_id (int): ID của sản phẩm cũ cần thay thế.
        - old_quantity (int): Số lượng còn lại của sản phẩm cũ sau khi thay thế. Nếu > 0: sản phẩm cũ chỉ bị giảm bớt số lượng (trường hợp thay thế một phần). Nếu = 0: sản phẩm cũ sẽ bị xóa hoàn toàn khỏi đơn hàng (trường hợp thay thế toàn bộ).
        
    Vi dụ:
        - Context: <A> có 5 sản phẩm, order_id = 100, item_id = 200
        - Input: Thay 3 cái sản phẩm <A> thành 5 cái sản phẩm <B>
        - Args: 
            - order_id = 100
            - item_id = 200
            - new_product_des_id = <product_des_id của A>
            - new_quantity = 2 (ban đầu A có 5 cái nên thay 3 cái của A tức là A còn 5 - 3 = 2 cái)
            - old_product_des_id = <product_des_id của B>
            - old_quantity = 5
    """
    logger.info("alter_item_order_tool được gọi")
    
    order_state = state["order"].copy() if state["order"] is not None else {}
    
    if not order_state:
        logger.info("order trống -> không thể thay đổi sản phẩm")
        return Command(
            update=build_update(
                content="Không có thông tin đơn của khách, lấy các đơn của khách",
                tool_call_id=tool_call_id
            )
        )
        
    if not state["seen_products"]:
        logger.info("seen_products rỗng")
        return Command(
            update=build_update(
                content=(
                    "Khách chưa xem sản phẩm nào nên không thể lấy "
                    "thông tin sản phẩm từ seen_products, gọi tool "
                    "get_products_tool để tìm sản phẩm theo yêu cầu "
                    "của khách"
                ),
                tool_call_id=tool_call_id
            )
        )
        
    if not order_id:
        logger.info("Không thể xác định được order_id mà khách muốn")
        return Command(
            update=build_update(
                content="Không xác định đơn hàng khách muốn cập nhật, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
    
    if not item_id:
        logger.info("Không thể xác định được item_id mà khách muốn")
        return Command(
            update=build_update(
                content="Không xác định được sản phẩm khách muốn cập nhật, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
        
    if not new_product_des_id:
        logger.info("Không thể xác định được new_product_des_id mà khách muốn")
        return Command(
            update=build_update(
                content="Không xác định được sản phẩm mới mà khách muốn thay thế sản phẩm cũ, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
        
    if not old_product_des_id:
        logger.info("Không thể xác định được old_product_des_id mà khách muốn")
        return Command(
            update=build_update(
                content="Không xác định được sản phẩm cũ mà khách muốn thay thế bởi sản phẩm mới, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
        
    if not new_quantity:
        logger.info("Không thể xác định được new_quantity mà khách muốn")
        return Command(
            update=build_update(
                content="Không xác định được số lượng sản phẩm mới mà khách muốn thay thế sản phẩm cũ, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
    
    if old_quantity is None:
        logger.info("Không thể xác định được old_quantity mà khách muốn")
        return Command(
            update=build_update(
                content="Không xác định được số lượng sản phẩm cũ mà bị thay thế bởi sản phẩm mới, nói khách miêu tả rõ hơn",
                tool_call_id=tool_call_id
            )
        )
    
    try:
        logger.info(
            "Xác định được các thông tin "
            f"order_id: {order_id} | "
            f"item_id: {item_id} | "
            f"new_product_des_id: {new_product_des_id} | "
            f"new_quantity: {new_quantity} | "
            f"old_product_des_id: {old_product_des_id} | "
            f"old_quantity: {old_quantity}"
        )
        
        # Trường hợp thay thế hoàn toàn sản phẩm cũ bằng sản phẩm mới
        if old_quantity == 0:
            logger.info("Trường hợp thay thế hoàn toàn sản phẩm cũ bằng sản phẩm mới")
            
            response = order_repo.update_order_item(
                item_id=item_id,
                update_payload={
                    "product_des_id": new_product_des_id,
                    "quantity": new_quantity,
                    "price": state["seen_products"][new_product_des_id]["price"]
                }
            )
            
            if not response:
                logger.error("Lỗi ở cấp DB -> Không thể thay đổi sản phẩm")
                return Command(
                    update=build_update(
                        content="Lỗi trong quá trình thay đổi sản phẩm, xin lỗi khách",
                        tool_call_id=tool_call_id
                    )
                )
        else:
            logger.info("Trường hợp thay thế 1 phần sản phẩm cũ bằng sản phẩm mới")
            # Trường hợp thay thế 1 phần sản phẩm cũ bằng sản phẩm mới
            # Cập nhật sản phẩm cũ
            old_item = order_repo.update_order_item(
                item_id=item_id,
                update_payload={"quantity": old_quantity}
            )
            
            # Thêm sản phẩm mới
            new_item = order_repo.create_order_item(
                item_to_insert={
                    "order_id": order_id, 
                    "product_des_id": new_product_des_id,
                    "quantity": new_quantity,
                    "price": state["seen_products"][new_product_des_id]["price"]
                }
            )
            
            if not old_item or not new_item:
                logger.error("Lỗi ở cấp DB -> Không thể thay đổi sản phẩm")
                return Command(
                    update=build_update(
                        content="Lỗi trong quá trình thay đổi sản phẩm, xin lỗi khách",
                        tool_call_id=tool_call_id
                    )
                )
        
        logger.info("Thay đổi sản phẩm thành công")
        order = order_repo.get_order_details(order_id=order_id)
        order_detail = _return_order_details(
            order_id=order,
            raw_order_detail=order
        )
        order_state[order_id] = _update_order_state(order=order)

        return Command(
            update=build_update(
                content=(
                    "Thay thế phẩm thành công, đây là đơn hàng của khách sau khi cập nhật:\n"
                    f"{order_detail}\n"
                    "Không được tóm gọn, phải liệt kê chi tiết, đầy đủ, không bịa đặt."
                ),
                tool_call_id=tool_call_id,
                order=order_state
            )
        )
        
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise

@tool
def get_customer_orders_tool(
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Dùng công cụ này khi khách hàng muốn chỉnh sửa đơn hàng nhưng không cung cấp ID cụ thể, hoặc khi cần kiểm tra lịch sử đơn hàng của khách.

    Chức năng: Lấy danh sách các đơn hàng gần đây của khách hàng mà có thể chỉnh sửa được.
    """
    logger.info("get_customer_orders_tool được gọi")
    customer_id = state.get("customer_id")
    order_state = state["order"].copy() if state["order"] is not None else {}

    if not customer_id:
        logger.info("Không tìm thấy customer_id trong state")
        return Command(update=build_update(
            content="Lỗi không thấy customer_id, xin lỗi khách và hứa sẽ khắc phục sớm nhất có thể",
            tool_call_id=tool_call_id
        ))

    logger.info(f"Tìm thấy customer_id: {customer_id}")
    try:
        all_editablt_orders = order_repo.get_all_editable_orders(
            customer_id=customer_id
        )

        if not all_editablt_orders:
            logger.info(f"Không tìm thấy đơn hàng nào cho customer_id: {customer_id}")
            return Command(
                update=build_update(
                    content="Thông báo khách chưa đặt đơn hàng nào",
                    tool_call_id=tool_call_id
                )
            )

        logger.info(f"Tìm thấy {len(all_editablt_orders)} đơn hàng cho customer_id: {customer_id}")

        order_detail = _return_all_editable_orders(
            customer_id=customer_id,
            list_raw_order_detail=all_editablt_orders
        )
        
        for order in all_editablt_orders:
            order_state[order["order_id"]] = _update_order_state(order=order)
        
        return Command(
            update=build_update(
                content=(
                    "Đây là đơn hàng mà khách có thể chỉnh sửa:\n"
                    f"{order_detail}\n\n"
                    "Bạn phải in ra dưới dạng rút gọn các đơn để khách xác định được "
                    "đơn khách muốn chỉnh sửa"
                ),
                tool_call_id=tool_call_id,
                order=order_state
            )
        )

    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise