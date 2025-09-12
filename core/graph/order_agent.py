from langgraph.types import Command
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from core.tools import order_toolbox
from core.graph.state import AgentState
from database.connection import specialist_llm

from log.logger_config import setup_logging

logger = setup_logging(__name__)


class OrderAgent:
    def __init__(self):
        with open("core/prompts/order_agent_prompt.md", "r", encoding="utf-8") as f:
            system_prompt = f.read()
            
        context = """
        Các thông tin bạn nhận được:
        - Tên của khách hàng customer_name: {name}
        - SĐT của khách phone_number: {phone_number}
        - Địa chỉ của khách: {address}
        - Các sản phẩm khách đã xem seen_products: {seen_products}
        - Giỏ hàng của khách: {cart}
        """
            
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt + context),
            MessagesPlaceholder(variable_name="messages")
        ])
        
        self.agent = create_react_agent(
            model=specialist_llm,
            tools=order_toolbox,
            prompt=self.prompt,
            state_schema=AgentState
        )
    
    def order_agent_node(self, state: AgentState) -> Command:
        """
        Xử lý các yêu cầu liên quan đến đơn hàng (lên đơn, cập nhật, hủy, ...) bằng `order_toolbox`.

        Args:
            state (AgentState): Trạng thái hội thoại hiện tại.

        Returns:
            Command: Lệnh cập nhật `messages`, các trường trạng thái (`order`, `cart`, ... nếu có) và kết thúc luồng.
        """
        try:
            result = self.agent.invoke(state)
            content = result["messages"][-1].content
            
            update = {
                "messages": [AIMessage(content=content, name="order_agent")],
                "next": "__end__"
            }
            
            for key in ([
                "customer_id", "name", "phone_number", "order",
                "address", "seen_products", "cart", "grand_total"
            ]):
                if result.get(key, None) is not None:
                    update[key] = result[key]
            
            return Command(
                update=update,
                goto="__end__"
            )
            
        except Exception as e:
            logger.error(f"Lỗi: {e}")
            raise