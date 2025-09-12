# from langgraph.pregel import RetryPolicy
import os
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from core.graph.state import AgentState
from core.graph.supervisor import Supervisor
from core.graph.order_agent import OrderAgent
from core.graph.product_agent import ProductAgent
from core.graph.modify_order_agent import ModifyOrderAgent
from state_management.state_cleanup_manager import StateCleanupManager

load_dotenv()

CLEANUP_INTERVAL_MINUTES = os.getenv("CLEANUP_INTERVAL_MINUTES")
STATE_TTL_MINUTES = os.getenv("STATE_TTL_MINUTES")

# retry_policy = RetryPolicy(
#     max_attempts=2,
#     backoff_factor=1,
#     retry_on=(Exception,)
# )

def create_main_graph() -> StateGraph:
    # Khởi tạo các agent
    product_agent = ProductAgent()
    order_agent = OrderAgent()
    modify_order_agent = ModifyOrderAgent()
    supervisor_chain = Supervisor()

    # Xây dựng graph
    workflow = StateGraph(AgentState)
    workflow.add_node(
        "supervisor", 
        supervisor_chain.supervisor_node,
        # retry=retry_policy
    )
    workflow.add_node(
        "product_agent", 
        product_agent.product_agent_node,
        # retry=retry_policy
    )
    workflow.add_node(
        "order_agent", 
        order_agent.order_agent_node,
        # retry=retry_policy
    )
    workflow.add_node(
        "modify_order_agent", 
        modify_order_agent.modify_order_agent_node,
        # retry=retry_policy
    )

    workflow.set_entry_point("supervisor")
    
    workflow.add_edge("supervisor", "product_agent")
    workflow.add_edge("supervisor", "order_agent")
    workflow.add_edge("supervisor", "modify_order_agent")
    
    workflow.add_edge("product_agent", END)
    workflow.add_edge("order_agent", END)
    workflow.add_edge("modify_order_agent", END)
    
    memory = MemorySaver()
    graph = workflow.compile(checkpointer=memory)
    
    # Khởi tạo cleanup manager
    cleanup_manager = StateCleanupManager(
        graph=graph,
        cleanup_interval_minutes=CLEANUP_INTERVAL_MINUTES, # Chạy cleanup mỗi 30 phút
        state_ttl_minutes=STATE_TTL_MINUTES # State sống 2 tiếng
    )
    
    graph.cleanup_manager = cleanup_manager

    return graph