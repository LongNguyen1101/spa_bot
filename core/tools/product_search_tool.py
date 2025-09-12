import json
from pydantic import BaseModel, Field
from typing import Annotated, Optional, List

from langgraph.types import Command
from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool, InjectedToolCallId

from repository.sync_repo import ProductRepo
from core.utils.function import build_update
from core.graph.state import AgentState, SeenProducts
from database.connection import supabase_client, embeddings_model

from log.logger_config import setup_logging

logger = setup_logging(__name__)

product_repo = ProductRepo(supabase_client=supabase_client)

class ProductIdentifier(BaseModel):
    sku: Optional[str] = Field(description="Mã SKU của sản phẩm, ví dụ: 'TP-L530E'.")
    product_name: Optional[str] = Field(description="Tên đầy đủ hoặc một phần của sản phẩm, ví dụ: 'Bóng đèn thông minh'.")

def _update_seen_products(
    seen_products: dict, 
    products: List[dict]
) -> dict:
    """
    Cập nhật `seen_products` trong state bằng kết quả sản phẩm trả về.

    Args:
        seen_products (dict): Bộ nhớ sản phẩm đã xem hiện có.
        products (List[dict]): Danh sách sản phẩm từ SQL/RAG.

    Returns:
        dict: Tập `seen_products` sau khi được cập nhật/ghi đè theo `product_des_id`.
    """
    for prod in products:
        product_des_id = prod.get("product_des_id")
        
        seen_products[product_des_id] = SeenProducts(
            product_des_id=product_des_id,
            product_name=prod.get("product_name"),
            product_id=prod.get("product_id"),
            sku=prod.get("sku"),
            variance_des=prod.get("variance_des"),
            brief_des=prod.get("brief_des"),
            price=prod.get("price"),
            inventory=prod.get("inventory")
        )
    return seen_products

@tool
def get_products_tool(
    keyword: Annotated[str, "Từ khóa tìm kiếm sản phẩm mà nguời dùng cung cấp"],
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Công cụ này ưu tiên tìm kiếm chính xác bằng SQL nếu người dùng cung cấp SKU hoặc tên sản phẩm. 
    Nếu không, nó sẽ sử dụng tìm kiếm ngữ nghĩa (RAG) để xử lý các câu hỏi chung chung về sản phẩm.

    Chức năng: Tìm kiếm thông tin sản phẩm. 

    Tham số: 
        - keywords (str): chỉ chứa phần từ khoá cốt lõi là tên hoặc mô tả chính xác của sản phẩm mà người dùng quan tâm.
        - Ví dụ:
            - "đèn led bản rẻ nhất"  → chỉ lấy "đèn led"
            - "bút thử điện mắc nhất"  → chỉ lấy "bút thử điện"
            - "camera an ninh"  → giữ nguyên "camera an ninh"
    """
    logger.info(f"get_products_tool được gọi với keywords: {keyword}")
    # --- SQL First Approach ---
    try:
        db_result = product_repo.get_product_by_keyword(
            keyword=keyword
        )
     
        # logger.info(f"Dữ liệu SQL trả về: {db_result}")

        if db_result:
            logger.info("Có dữ liệu trả về từ SQL")
            
            updated_seen_products = _update_seen_products(
                seen_products=state["seen_products"] if state["seen_products"] is not None else {},
                products=db_result
            )
            
            formatted_response = (
                "Đây là các sản phẩm tìm thấy dựa trên yêu cầu của khách:\n"
                f"{db_result}\n"
                "Tóm gọn lại thông tin sản phẩm một cách ngắn gọn và dễ hiểu "
                "nhưng khách vẫn nắm được các ý chính\n"
            )
            
            if state["phone_number"]:
                formatted_response += "Khách đã có số điện thoại, hỏi khách có muốn mua sản phẩm không"
            else:
                formatted_response += "Khách chưa có số điện thoại, xin số điện thoại của khách"
            
            logger.info("Trả về kết quả từ SQL")
            return Command(
                update=build_update(
                    content=formatted_response,
                    tool_call_id=tool_call_id,
                    seen_products=updated_seen_products
                )
            )
            
        logger.info("Không có kết quả từ SQL, chuyển sang tìm kiếm RAG")
        
        query_embedding = embeddings_model.embed_query(state["user_input"])
        
        rag_results = product_repo.get_product_by_embedding(
            query_embedding=query_embedding,
            match_count=5
        )
        
        # logger.info(f"Kết quả RAG: {rag_results}")
        
        if not rag_results:
            logger.info("Không có kết quả từ RAG")
            return Command(update=build_update(
                content="Xin lỗi, tôi không tìm thấy thông tin nào liên quan đến câu hỏi của bạn.",
                tool_call_id=tool_call_id
            ))

        logger.info("Có kết quả trả về từ RAG")
        products = [json.loads(item.get("content")) for item in rag_results if item.get("content")]
        
        if not products:
            logger.info("Không thể parse sản phẩm từ kết quả RAG")
            return Command(update=build_update(
                content="Xin lỗi, tôi không thể xác định được sản phẩm từ kết quả tìm kiếm.",
                tool_call_id=tool_call_id
            ))

        
        updated_seen_products = _update_seen_products(
            seen_products=state["seen_products"] if state["seen_products"] is not None else {}, 
            products=products
        )
        formatted_response = (
            "Đây là các sản phẩm được trả về dựa trên yêu cầu của khách:\n\n"
            f"{products}\n"
            "Tóm gọn lại thông tin sản phẩm một cách ngắn gọn và dễ hiểu."
        )
        
        logger.info("Trả về kết quả từ RAG")
        return Command(
            update=build_update(
                content=formatted_response,
                tool_call_id=tool_call_id,
                seen_products=updated_seen_products
            )
        )

    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise


@tool
def get_qna_tool(
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    """
    Sử dụng công cụ này cho các câu hỏi về hướng dẫn sử dụng, khắc phục sự cố, cài đặt thiết bị, hoặc các vấn đề kỹ thuật khác. 
    Công cụ sẽ tìm kiếm trong cơ sở dữ liệu Hỏi & Đáp (Q&A) để cung cấp câu trả lời và hướng dẫn chi tiết.

    Chức năng: Trả lời các câu hỏi liên quan đến kỹ thuật.
    """
    query = state["user_input"]
    logger.info(f"get_qna_tool được gọi với query: {query}")
    all_documents = []
    
    # --- 1. Retrieve documents from qna table ---
    try:
        query_embedding = embeddings_model.embed_query(query)
        
        response = product_repo.get_qna_by_embedding(
            query_embedding=query_embedding,
            match_count=3
        )

        if not response:
            logger.error("Lỗi khi gọi RPC match_qna")
            return Command(
                update=build_update(
                    content="Xin lỗi khách vì đã xảy ra lỗi khi tìm kiếm thông tin hướng dẫn.",
                    tool_call_id=tool_call_id
                )
            ) 
              
        for item in response:
            all_documents.append(item.get("content", ""))
        
        logger.info(f"Tìm thấy {len(all_documents)} tài liệu Q&A")
        return Command(
            update=build_update(
                content=f"Đây là các thông tin tìm thấy liên quan đến câu hỏi của khách:({all_documents})",
                tool_call_id=tool_call_id
            )
        )
             
    except Exception as e:
        logger.error(f"Lỗi: {e}")
        raise
